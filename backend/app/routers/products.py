"""Product catalog: owner input, inventory listing, and audited stock movement."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from ..database import get_db, utcnow
from ..models import (
    ProductCreate,
    ProductOut,
    ProductPage,
    ProductUpdate,
    StockAdjustRequest,
    StockStatus,
    StockTransferRequest,
    to_object_id,
)
from ..money import q2
from ..security import current_user, require_owner
from ..serializers import product_out

router = APIRouter(prefix="/api/products", tags=["products"])

SORTABLE_FIELDS = {
    "name": "name",
    "brand": "brand",
    "barcode": "barcode",
    "category": "category",
    "buying_price": "buying_price",
    "selling_price": "selling_price",
    "market_price": "market_price",
    "discount_percentage": "discount_percentage",
    "stock_shelf": "stock_shelf",
    "stock_warehouse": "stock_warehouse",
    "updated_at": "updated_at",
}

_MONEY_FIELDS = ("buying_price", "market_price", "selling_price", "discount_percentage")


def _status_filter(stock_status: StockStatus) -> dict[str, Any]:
    total = {"$add": ["$stock_shelf", "$stock_warehouse"]}
    if stock_status is StockStatus.OUT_OF_STOCK:
        return {"$expr": {"$lte": [total, 0]}}
    if stock_status is StockStatus.LOW_STOCK:
        return {"$expr": {"$and": [{"$gt": [total, 0]}, {"$lte": [total, "$reorder_threshold"]}]}}
    if stock_status is StockStatus.IN_STOCK:
        return {"$expr": {"$gt": [total, "$reorder_threshold"]}}
    return {}


async def _audit(product_id: Any, user: dict[str, Any], before: dict[str, Any], after: dict[str, Any], reason: str) -> None:
    db = get_db()
    await db.stock_audits.insert_one(
        {
            "product_id": product_id,
            "user": user["username"],
            "reason": reason,
            "shelf_before": before.get("stock_shelf", 0),
            "warehouse_before": before.get("stock_warehouse", 0),
            "shelf_after": after.get("stock_shelf", 0),
            "warehouse_after": after.get("stock_warehouse", 0),
            "timestamp": utcnow(),
        }
    )


@router.get("", response_model=ProductPage)
async def list_products(
    search: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    stock_status: StockStatus = StockStatus.ALL,
    include_inactive: bool = False,
    sort_by: str = "name",
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    _: dict[str, Any] = Depends(current_user),
) -> ProductPage:
    db = get_db()
    query: dict[str, Any] = {}
    if not include_inactive:
        query["is_active"] = True
    if category and category.upper() != "ALL":
        query["category"] = category
    if brand and brand.upper() != "ALL":
        query["brand"] = brand
    if search:
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"name": {"$regex": pattern, "$options": "i"}},
            {"brand": {"$regex": pattern, "$options": "i"}},
            {"barcode": {"$regex": pattern, "$options": "i"}},
        ]
    query.update(_status_filter(stock_status))

    sort_field = SORTABLE_FIELDS.get(sort_by, "name")
    direction = 1 if sort_dir == "asc" else -1

    total = await db.products.count_documents(query)
    cursor = (
        db.products.find(query)
        .sort(sort_field, direction)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [product_out(doc) async for doc in cursor]
    return ProductPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/categories", response_model=list[str])
async def list_categories(_: dict[str, Any] = Depends(current_user)) -> list[str]:
    db = get_db()
    categories = await db.products.distinct("category", {"is_active": True})
    return sorted(category for category in categories if category)


@router.get("/brands", response_model=list[str])
async def list_brands(_: dict[str, Any] = Depends(current_user)) -> list[str]:
    db = get_db()
    brands = await db.products.distinct("brand", {"is_active": True})
    return sorted(brand for brand in brands if brand)


@router.get("/barcode/{barcode}", response_model=ProductOut)
async def get_by_barcode(barcode: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.products.find_one({"barcode": barcode.strip(), "is_active": True})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active product found for barcode {barcode}",
        )
    return product_out(document)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.products.find_one({"_id": to_object_id(product_id, "product_id")})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product_out(document)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    db = get_db()
    document = payload.model_dump()
    for field in _MONEY_FIELDS:
        document[field] = q2(document[field])
    document["created_at"] = utcnow()
    document["updated_at"] = utcnow()
    try:
        result = await db.products.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Barcode {payload.barcode} already belongs to another product",
        ) from exc

    created = await db.products.find_one({"_id": result.inserted_id})
    await _audit(result.inserted_id, user, {}, created or {}, "Product created")
    return product_out(created or {})


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    user: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    db = get_db()
    object_id = to_object_id(product_id, "product_id")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields supplied to update",
        )
    for field in _MONEY_FIELDS:
        if field in updates and updates[field] is not None:
            updates[field] = q2(updates[field])

    before = await db.products.find_one({"_id": object_id})
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    updates["updated_at"] = utcnow()
    try:
        await db.products.update_one({"_id": object_id}, {"$set": updates})
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Barcode already belongs to another product",
        ) from exc

    after = await db.products.find_one({"_id": object_id})
    if {"stock_shelf", "stock_warehouse"} & updates.keys():
        await _audit(object_id, user, before, after or {}, "Stock set via product edit")
    return product_out(after or {})


@router.patch("/{product_id}/stock-adjust", response_model=ProductOut)
async def adjust_stock(
    product_id: str,
    payload: StockAdjustRequest,
    user: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    """Relative stock change, applied atomically and never allowed below zero."""
    db = get_db()
    object_id = to_object_id(product_id, "product_id")
    if payload.delta_shelf == 0 and payload.delta_warehouse == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide a non-zero shelf or warehouse adjustment",
        )

    before = await db.products.find_one({"_id": object_id})
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Guard the decrements inside the filter so a concurrent sale cannot push
    # either bucket negative between the read above and this write.
    guard: dict[str, Any] = {"_id": object_id}
    if payload.delta_shelf < 0:
        guard["stock_shelf"] = {"$gte": abs(payload.delta_shelf)}
    if payload.delta_warehouse < 0:
        guard["stock_warehouse"] = {"$gte": abs(payload.delta_warehouse)}

    result = await db.products.update_one(
        guard,
        {
            "$inc": {"stock_shelf": payload.delta_shelf, "stock_warehouse": payload.delta_warehouse},
            "$set": {"updated_at": utcnow()},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Adjustment rejected: it would drive stock below zero",
        )

    after = await db.products.find_one({"_id": object_id})
    await _audit(object_id, user, before, after or {}, payload.reason)
    return product_out(after or {})


@router.post("/{product_id}/transfer", response_model=ProductOut)
async def transfer_to_shelf(
    product_id: str,
    payload: StockTransferRequest,
    user: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    """Move units from the warehouse onto the shelf in one atomic write."""
    db = get_db()
    object_id = to_object_id(product_id, "product_id")
    before = await db.products.find_one({"_id": object_id})
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.products.update_one(
        {"_id": object_id, "stock_warehouse": {"$gte": payload.quantity}},
        {
            "$inc": {"stock_warehouse": -payload.quantity, "stock_shelf": payload.quantity},
            "$set": {"updated_at": utcnow()},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only {before.get('stock_warehouse', 0)} units available in the warehouse",
        )

    after = await db.products.find_one({"_id": object_id})
    await _audit(object_id, user, before, after or {}, payload.reason)
    return product_out(after or {})


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def deactivate_product(product_id: str, user: dict[str, Any] = Depends(require_owner)) -> Response:
    """Soft delete: sale history keeps referencing the product document."""
    db = get_db()
    object_id = to_object_id(product_id, "product_id")
    result = await db.products.update_one(
        {"_id": object_id}, {"$set": {"is_active": False, "updated_at": utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
