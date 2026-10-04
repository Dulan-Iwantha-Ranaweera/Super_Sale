"""POS checkout.

MongoDB here runs as a standalone node, so multi-document transactions are not
available. Instead every stock decrement is an individually atomic guarded
`$inc`, and anything that fails part-way through is compensated by incrementing
the already-decremented lines back. The sale document is only written once all
stock has been secured, so the database is never left with stock removed for a
sale that does not exist.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import get_settings
from ..database import get_db, next_sequence, utcnow
from ..models import (
    CheckoutRequest,
    LedgerType,
    PaymentMethod,
    ReturnableLine,
    ReturnableSale,
    ReturnRequest,
    SaleOut,
    SalePage,
    SalesStats,
    to_object_id,
)
from ..money import effective_price, q2
from ..security import current_user
from ..serializers import sale_out

router = APIRouter(prefix="/api/sales", tags=["sales"])


class _StockShortfall(Exception):
    def __init__(self, name: str, available: int, requested: int) -> None:
        self.name = name
        self.available = available
        self.requested = requested
        super().__init__(name)


def _history_filter(
    days: int,
    search: str | None,
    payment_method: PaymentMethod | None,
    cashier_id: str | None,
    customer_id: str | None,
    start: str | None,
    end: str | None,
    ledger_type: LedgerType | None = None,
) -> dict[str, Any]:
    """Shared query for the sales history list and its totals."""
    if start or end:
        try:
            start_dt = (
                datetime.fromisoformat(start).astimezone().astimezone(timezone.utc)
                if start
                else datetime.now(timezone.utc) - timedelta(days=days)
            )
            end_dt = (
                (datetime.fromisoformat(end).astimezone() + timedelta(days=1)).astimezone(timezone.utc)
                if end
                else datetime.now(timezone.utc) + timedelta(days=1)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dates must be in YYYY-MM-DD format",
            ) from exc
        if end_dt <= start_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The end date must fall after the start date",
            )
        timestamp_filter = {"$gte": start_dt, "$lt": end_dt}
    else:
        timestamp_filter = {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}

    query: dict[str, Any] = {"timestamp": timestamp_filter}
    if ledger_type is LedgerType.SALE:
        # Documents written before returns existed carry no `type` field.
        query["type"] = {"$ne": LedgerType.RETURN.value}
    elif ledger_type is LedgerType.RETURN:
        query["type"] = LedgerType.RETURN.value
    if payment_method:
        query["payment_method"] = payment_method.value
    if cashier_id:
        query["cashier_id"] = cashier_id
    if customer_id:
        query["customer_id"] = to_object_id(customer_id, "customer_id")
    if search:
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"receipt_number": {"$regex": pattern, "$options": "i"}},
            # Searching a receipt number should also surface refunds raised
            # against it, not just the sale itself.
            {"original_receipt_number": {"$regex": pattern, "$options": "i"}},
            {"customer_name": {"$regex": pattern, "$options": "i"}},
            {"items.name": {"$regex": pattern, "$options": "i"}},
        ]
    return query


async def _rollback(applied: list[tuple[ObjectId, int]]) -> None:
    """Return stock that was taken before a later line failed."""
    db = get_db()
    for object_id, quantity in applied:
        await db.products.update_one({"_id": object_id}, {"$inc": {"stock_shelf": quantity}})


@router.post("/checkout", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
async def checkout(payload: CheckoutRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()

    # Collapse repeated scans of the same product into a single line.
    merged: dict[str, dict[str, Any]] = {}
    for item in payload.items:
        key = item.product_id
        if key in merged:
            merged[key]["quantity"] += item.quantity
            if item.discount_percentage is not None:
                merged[key]["discount_percentage"] = item.discount_percentage
        else:
            merged[key] = {
                "quantity": item.quantity,
                "discount_percentage": item.discount_percentage,
            }

    object_ids = [to_object_id(pid, "product_id") for pid in merged]
    catalog = {
        str(doc["_id"]): doc
        async for doc in db.products.find({"_id": {"$in": object_ids}, "is_active": True})
    }
    missing = [pid for pid in merged if pid not in catalog]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{len(missing)} item(s) in the cart are no longer available",
        )

    customer: dict[str, Any] | None = None
    if payload.customer_id:
        customer = await db.customers.find_one({"_id": to_object_id(payload.customer_id, "customer_id")})
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    store = await db.stores.find_one({"_id": settings.store_id}) or {}
    tax_rate = float(store.get("tax_rate", 0.0))
    spend_per_point = float(store.get("loyalty_spend_per_point", 10.0)) or 10.0

    applied: list[tuple[ObjectId, int]] = []
    try:
        lines: list[dict[str, Any]] = []
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        net_profit = Decimal("0")

        for product_id, request in merged.items():
            product = catalog[product_id]
            quantity = int(request["quantity"])
            object_id = product["_id"]

            # Atomic, guarded decrement: the $gte filter is what makes two
            # concurrent cashiers safe. A miss means someone else got there first.
            result = await db.products.update_one(
                {"_id": object_id, "is_active": True, "stock_shelf": {"$gte": quantity}},
                {"$inc": {"stock_shelf": -quantity}, "$set": {"updated_at": utcnow()}},
            )
            if result.modified_count == 0:
                current = await db.products.find_one({"_id": object_id}, {"stock_shelf": 1})
                raise _StockShortfall(
                    product.get("name", "Unknown product"),
                    int((current or {}).get("stock_shelf", 0)),
                    quantity,
                )
            applied.append((object_id, quantity))

            discount = request["discount_percentage"]
            if discount is None:
                discount = float(product.get("discount_percentage", 0.0))
            discount = q2(discount)

            selling = q2(product.get("selling_price", 0.0))
            buying = q2(product.get("buying_price", 0.0))
            effective = effective_price(selling, discount)

            gross_line = Decimal(str(selling)) * quantity
            line_total = Decimal(str(effective)) * quantity
            line_profit = (Decimal(str(effective)) - Decimal(str(buying))) * quantity

            subtotal += gross_line
            discount_total += gross_line - line_total
            net_profit += line_profit

            lines.append(
                {
                    "product_id": object_id,
                    "barcode": product.get("barcode", ""),
                    # Snapshot the display name, brand included, so a receipt
                    # still reads correctly if the product is renamed later.
                    "name": " ".join(
                        part for part in (product.get("brand"), product.get("name", "")) if part
                    ),
                    "quantity": quantity,
                    "unit_buying_price": buying,
                    "unit_selling_price": selling,
                    "discount_percentage": discount,
                    "line_total": q2(line_total),
                    "line_profit": q2(line_profit),
                }
            )

        taxable = subtotal - discount_total
        tax_amount = taxable * Decimal(str(tax_rate)) / Decimal("100")
        grand_total = q2(taxable + tax_amount)

        _validate_payment(payload, grand_total)

        change_due = None
        if payload.payment_method is PaymentMethod.CASH and payload.amount_tendered is not None:
            change_due = q2(Decimal(str(payload.amount_tendered)) - Decimal(str(grand_total)))

        loyalty_points = int(Decimal(str(grand_total)) // Decimal(str(spend_per_point))) if customer else 0

        now = utcnow()
        sequence = await next_sequence(db, f"receipt:{now.year}")
        sale_document = {
            "receipt_number": f"REC-{now.year}-{sequence:05d}",
            "cashier_id": user["username"],
            "customer_id": customer["_id"] if customer else None,
            "customer_name": customer.get("name") if customer else None,
            "items": lines,
            "subtotal": q2(subtotal),
            "discount_total": q2(discount_total),
            "tax_amount": q2(tax_amount),
            "grand_total": grand_total,
            "net_profit": q2(net_profit),
            "payment_method": payload.payment_method.value,
            "payment_breakdown": payload.payment_breakdown.model_dump() if payload.payment_breakdown else None,
            "amount_tendered": q2(payload.amount_tendered) if payload.amount_tendered is not None else None,
            "change_due": change_due,
            "loyalty_points_earned": loyalty_points,
            "timestamp": now,
            "type": LedgerType.SALE.value,
            "returned": {},
        }
        insert_result = await db.sales.insert_one(sale_document)
    except _StockShortfall as exc:
        await _rollback(applied)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Insufficient stock for {exc.name}: {exc.available} on shelf, {exc.requested} requested",
        ) from exc
    except Exception:
        await _rollback(applied)
        raise

    if customer:
        # Non-critical: a failure here must not void a completed, paid sale.
        try:
            await db.customers.update_one(
                {"_id": customer["_id"]},
                {
                    "$inc": {
                        "total_visits": 1,
                        "total_spend": sale_document["grand_total"],
                        "loyalty_points": loyalty_points,
                    },
                    "$set": {"last_visit": sale_document["timestamp"]},
                },
            )
        except Exception:  # pragma: no cover - defensive
            pass

    stored = await db.sales.find_one({"_id": insert_result.inserted_id})
    return sale_out(stored or {})


def _validate_payment(payload: CheckoutRequest, grand_total: float) -> None:
    if payload.payment_method is PaymentMethod.SPLIT:
        if not payload.payment_breakdown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A split payment needs a cash and card breakdown",
            )
        paid = q2(Decimal(str(payload.payment_breakdown.cash)) + Decimal(str(payload.payment_breakdown.card)))
        if abs(paid - grand_total) > 0.009:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Split payment of {paid:.2f} does not match the total of {grand_total:.2f}",
            )
    elif payload.payment_method is PaymentMethod.CASH and payload.amount_tendered is not None:
        if payload.amount_tendered + 0.009 < grand_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cash tendered {payload.amount_tendered:.2f} is less than the total {grand_total:.2f}",
            )


@router.get("", response_model=SalePage)
async def list_sales(
    days: int = Query(30, ge=1, le=365),
    search: str | None = None,
    payment_method: PaymentMethod | None = None,
    cashier_id: str | None = None,
    customer_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ledger_type: LedgerType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict[str, Any] = Depends(current_user),
) -> SalePage:
    db = get_db()
    query = _history_filter(days, search, payment_method, cashier_id, customer_id, start, end, ledger_type)

    total = await db.sales.count_documents(query)
    cursor = (
        db.sales.find(query)
        .sort("timestamp", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [sale_out(doc) async for doc in cursor]
    return SalePage(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=SalesStats)
async def sales_stats(
    days: int = Query(30, ge=1, le=365),
    search: str | None = None,
    payment_method: PaymentMethod | None = None,
    cashier_id: str | None = None,
    customer_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    ledger_type: LedgerType | None = None,
    _: dict[str, Any] = Depends(current_user),
) -> SalesStats:
    """Totals for whatever the history filters currently select."""
    db = get_db()
    query = _history_filter(days, search, payment_method, cashier_id, customer_id, start, end, ledger_type)

    # Returns are negative documents in the same ledger, so sales and refunds
    # are split with $cond rather than by querying twice.
    is_return = {"$eq": [{"$ifNull": ["$type", "SALE"]}, "RETURN"]}
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": None,
                "revenue": {"$sum": {"$cond": [is_return, 0, "$grand_total"]}},
                "refunds": {"$sum": {"$cond": [is_return, "$grand_total", 0]}},
                "profit": {"$sum": "$net_profit"},
                "transactions": {"$sum": {"$cond": [is_return, 0, 1]}},
                "returns": {"$sum": {"$cond": [is_return, 1, 0]}},
                "items_sold": {"$sum": {"$sum": "$items.quantity"}},
            }
        },
    ]
    result = await db.sales.aggregate(pipeline).to_list(length=1)
    if not result:
        return SalesStats(
            revenue=0.0,
            refunds=0.0,
            net_revenue=0.0,
            profit=0.0,
            transactions=0,
            returns=0,
            items_sold=0,
            average_basket=0.0,
        )

    row = result[0]
    transactions = int(row.get("transactions", 0))
    revenue = q2(row.get("revenue", 0.0))
    refunds = abs(q2(row.get("refunds", 0.0)))
    return SalesStats(
        revenue=revenue,
        refunds=refunds,
        net_revenue=q2(revenue - refunds),
        profit=q2(row.get("profit", 0.0)),
        transactions=transactions,
        returns=int(row.get("returns", 0)),
        items_sold=int(row.get("items_sold", 0)),
        average_basket=q2(revenue / transactions) if transactions else 0.0,
    )


@router.get("/receipt/{receipt_number}", response_model=SaleOut)
async def get_by_receipt(receipt_number: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.sales.find_one({"receipt_number": receipt_number.strip().upper()})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sale found with receipt number {receipt_number}",
        )
    return sale_out(document)


@router.get("/{sale_id}", response_model=SaleOut)
async def get_sale(sale_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.sales.find_one({"_id": to_object_id(sale_id, "sale_id")})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    return sale_out(document)
