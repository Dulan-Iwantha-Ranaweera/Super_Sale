"""Returns and refunds.

A refund is written as a **negative document in the same `sales` ledger**
rather than into a separate collection. That one decision keeps every existing
aggregation honest for free: revenue, profit, category mix and even the 14-day
sales velocity behind the demand forecast all net refunds out automatically,
instead of each report having to remember to subtract a second source.

As with checkout, there are no multi-document transactions available, so the
over-return guard is a single conditional update on the original sale and any
later failure is compensated.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import get_settings
from ..database import get_db, next_sequence, utcnow
from ..models import (
    LedgerType,
    ReturnableLine,
    ReturnableSale,
    ReturnRequest,
    SaleOut,
    to_object_id,
)
from ..money import effective_price, q2
from ..security import current_user
from ..serializers import sale_out

router = APIRouter(prefix="/api/sales", tags=["returns"])


def _effective_unit(item: dict[str, Any]) -> float:
    return effective_price(
        q2(item.get("unit_selling_price", 0.0)),
        q2(item.get("discount_percentage", 0.0)),
    )


def _implied_tax_rate(sale: dict[str, Any]) -> Decimal:
    """Recover the tax rate the original sale was charged at.

    The store's rate may have changed since. A refund must hand back exactly
    what was taken, so the rate comes from the sale, not from current settings.
    """
    taxable = Decimal(str(q2(sale.get("subtotal", 0.0)))) - Decimal(str(q2(sale.get("discount_total", 0.0))))
    if taxable <= 0:
        return Decimal("0")
    return Decimal(str(q2(sale.get("tax_amount", 0.0)))) / taxable * Decimal("100")


async def _load_sale(sale_id: str) -> dict[str, Any]:
    db = get_db()
    sale = await db.sales.find_one({"_id": to_object_id(sale_id, "sale_id")})
    if not sale:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")
    if sale.get("type") == LedgerType.RETURN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That receipt is itself a refund, so it cannot be returned",
        )
    return sale


@router.get("/{sale_id}/returnable", response_model=ReturnableSale)
async def returnable_lines(sale_id: str, _: dict[str, Any] = Depends(current_user)) -> ReturnableSale:
    """What is still returnable on a sale, after any earlier partial refunds."""
    sale = await _load_sale(sale_id)
    already = sale.get("returned") or {}

    lines: list[ReturnableLine] = []
    for item in sale.get("items", []):
        product_id = str(item["product_id"])
        sold = int(item.get("quantity", 0))
        returned = int(already.get(product_id, 0))
        lines.append(
            ReturnableLine(
                product_id=product_id,
                barcode=item.get("barcode", ""),
                name=item.get("name", ""),
                quantity_sold=sold,
                quantity_returned=returned,
                quantity_remaining=max(0, sold - returned),
                unit_selling_price=q2(item.get("unit_selling_price", 0.0)),
                discount_percentage=q2(item.get("discount_percentage", 0.0)),
                refund_per_unit=_effective_unit(item),
            )
        )

    return ReturnableSale(
        sale_id=str(sale["_id"]),
        receipt_number=sale.get("receipt_number", ""),
        timestamp=sale["timestamp"],
        customer_name=sale.get("customer_name"),
        grand_total=q2(sale.get("grand_total", 0.0)),
        lines=lines,
        fully_returned=all(line.quantity_remaining == 0 for line in lines),
    )


@router.post("/{sale_id}/return", response_model=SaleOut, status_code=status.HTTP_201_CREATED)
async def create_return(
    sale_id: str,
    payload: ReturnRequest,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    """Refund part or all of a sale.

    Cashiers can issue refunds too: returns happen at the counter. Every one
    is recorded against the cashier who took it, with a reason, so the owner
    can review them in the sales history.
    """
    db = get_db()
    sale = await _load_sale(sale_id)
    sale_items = {str(item["product_id"]): item for item in sale.get("items", [])}

    # Merge repeated product ids in one request.
    requested: dict[str, int] = {}
    for item in payload.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    unknown = [pid for pid in requested if pid not in sale_items]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Those items were not on this sale, so they cannot be refunded against it",
        )

    already = sale.get("returned") or {}
    for product_id, quantity in requested.items():
        sold = int(sale_items[product_id].get("quantity", 0))
        remaining = sold - int(already.get(product_id, 0))
        if quantity > remaining:
            name = sale_items[product_id].get("name", "that item")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Only {remaining} unit(s) of {name} can still be returned on this receipt",
            )

    # Claim the quantities atomically. The $expr guard re-checks every line
    # inside the write itself, so a concurrent refund cannot push it over.
    guard = [
        {
            "$lte": [
                {"$add": [{"$ifNull": ["$returned." + product_id, 0]}, quantity]},
                int(sale_items[product_id].get("quantity", 0)),
            ]
        }
        for product_id, quantity in requested.items()
    ]
    claim = await db.sales.update_one(
        {"_id": sale["_id"], "$expr": {"$and": guard}},
        {"$inc": {"returned." + product_id: quantity for product_id, quantity in requested.items()}},
    )
    if claim.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Those units have already been refunded on another return",
        )

    restocked: list[tuple[Any, int]] = []
    try:
        tax_rate = _implied_tax_rate(sale)
        lines: list[dict[str, Any]] = []
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        profit_reversed = Decimal("0")

        for product_id, quantity in requested.items():
            item = sale_items[product_id]
            selling = q2(item.get("unit_selling_price", 0.0))
            buying = q2(item.get("unit_buying_price", 0.0))
            discount = q2(item.get("discount_percentage", 0.0))
            effective = effective_price(selling, discount)

            gross_line = Decimal(str(selling)) * quantity
            line_total = Decimal(str(effective)) * quantity
            line_profit = (Decimal(str(effective)) - Decimal(str(buying))) * quantity

            subtotal += gross_line
            discount_total += gross_line - line_total
            profit_reversed += line_profit

            # Negative quantities and amounts keep the ledger purely additive.
            lines.append(
                {
                    "product_id": item["product_id"],
                    "barcode": item.get("barcode", ""),
                    "name": item.get("name", ""),
                    "quantity": -quantity,
                    "unit_buying_price": buying,
                    "unit_selling_price": selling,
                    "discount_percentage": discount,
                    "line_total": q2(-line_total),
                    "line_profit": q2(-line_profit),
                }
            )

            if payload.restock:
                await db.products.update_one(
                    {"_id": item["product_id"]},
                    {"$inc": {"stock_shelf": quantity}, "$set": {"updated_at": utcnow()}},
                )
                restocked.append((item["product_id"], quantity))

        taxable = subtotal - discount_total
        tax_amount = taxable * tax_rate / Decimal("100")
        refund_total = q2(taxable + tax_amount)

        now = utcnow()
        sequence = await next_sequence(db, f"return:{now.year}")

        loyalty_reversed = 0
        if sale.get("customer_id"):
            store = await db.stores.find_one({"_id": get_settings().store_id}) or {}
            spend_per_point = float(store.get("loyalty_spend_per_point", 10.0)) or 10.0
            loyalty_reversed = int(Decimal(str(refund_total)) // Decimal(str(spend_per_point)))

        return_document = {
            "receipt_number": f"RET-{now.year}-{sequence:05d}",
            "type": LedgerType.RETURN.value,
            "original_sale_id": sale["_id"],
            "original_receipt_number": sale.get("receipt_number"),
            "cashier_id": user["username"],
            "customer_id": sale.get("customer_id"),
            "customer_name": sale.get("customer_name"),
            "items": lines,
            "subtotal": q2(-subtotal),
            "discount_total": q2(-discount_total),
            "tax_amount": q2(-tax_amount),
            "grand_total": q2(-refund_total),
            "net_profit": q2(-profit_reversed),
            "payment_method": payload.refund_method.value,
            "payment_breakdown": None,
            "amount_tendered": None,
            "change_due": None,
            "loyalty_points_earned": -loyalty_reversed,
            "reason": payload.reason,
            "restocked": payload.restock,
            "timestamp": now,
        }
        insert_result = await db.sales.insert_one(return_document)
    except Exception:
        # Hand back the claimed quantities and any stock already put away.
        await db.sales.update_one(
            {"_id": sale["_id"]},
            {"$inc": {"returned." + pid: -qty for pid, qty in requested.items()}},
        )
        for product_id, quantity in restocked:
            await db.products.update_one({"_id": product_id}, {"$inc": {"stock_shelf": -quantity}})
        raise

    if sale.get("customer_id"):
        # Clamped at zero: a refund must never drive a customer negative.
        try:
            await db.customers.update_one(
                {"_id": sale["customer_id"]},
                [
                    {
                        "$set": {
                            "total_spend": {
                                "$max": [0, {"$add": ["$total_spend", return_document["grand_total"]]}]
                            },
                            "loyalty_points": {
                                "$max": [
                                    0,
                                    {"$add": [{"$ifNull": ["$loyalty_points", 0]}, -loyalty_reversed]},
                                ]
                            },
                        }
                    }
                ],
            )
        except Exception:  # pragma: no cover - defensive
            pass

    stored = await db.sales.find_one({"_id": insert_result.inserted_id})
    return sale_out(stored or {})


@router.get("/{sale_id}/returns", response_model=list[SaleOut])
async def returns_for_sale(sale_id: str, _: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    db = get_db()
    object_id = to_object_id(sale_id, "sale_id")
    return [
        sale_out(document)
        async for document in db.sales.find({"original_sale_id": object_id}).sort("timestamp", -1)
    ]
