"""CRM: registered shoppers, their spend, visits and loyalty balance."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from ..database import get_db, utcnow
from ..models import (
    CustomerCreate,
    CustomerOut,
    CustomerPage,
    CustomerUpdate,
    to_object_id,
)
from ..money import q2
from ..security import current_user, require_owner
from ..serializers import customer_out

router = APIRouter(prefix="/api/customers", tags=["customers"])

SORTABLE_FIELDS = {
    "name": "name",
    "phone": "phone",
    "total_visits": "total_visits",
    "total_spend": "total_spend",
    "loyalty_points": "loyalty_points",
    "credit_due": "credit_due",
    "last_visit": "last_visit",
}

# Segments backing the CRM dropdown.
SEGMENT_FILTERS: dict[str, dict[str, Any]] = {
    "ALL": {},
    "HIGH_SPENDING": {"total_spend": {"$gte": 100}},
    "FREQUENT_VISITORS": {"total_visits": {"$gte": 10}},
    "LOYALTY_REWARDS": {"loyalty_points": {"$gte": 100}},
    "CREDIT_DUE": {"credit_due": {"$gt": 0}},
}


@router.get("", response_model=CustomerPage)
async def list_customers(
    search: str | None = None,
    segment: str = "ALL",
    sort_by: str = "total_spend",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    _: dict[str, Any] = Depends(current_user),
) -> CustomerPage:
    db = get_db()
    segment_key = segment.upper()
    if segment_key not in SEGMENT_FILTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown segment {segment}. Expected one of {', '.join(SEGMENT_FILTERS)}",
        )

    query: dict[str, Any] = dict(SEGMENT_FILTERS[segment_key])
    if search:
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"name": {"$regex": pattern, "$options": "i"}},
            {"phone": {"$regex": pattern, "$options": "i"}},
        ]

    sort_field = SORTABLE_FIELDS.get(sort_by, "total_spend")
    direction = 1 if sort_dir == "asc" else -1

    total = await db.customers.count_documents(query)
    cursor = (
        db.customers.find(query)
        .sort(sort_field, direction)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [customer_out(doc) async for doc in cursor]
    return CustomerPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/lookup", response_model=CustomerOut)
async def lookup_by_phone(phone: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.customers.find_one({"phone": phone.strip()})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No customer with that number")
    return customer_out(document)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(customer_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await db.customers.find_one({"_id": to_object_id(customer_id, "customer_id")})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer_out(document)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    db = get_db()
    document = payload.model_dump()
    document["credit_due"] = q2(document["credit_due"])
    document.update(
        {
            "total_visits": 0,
            "total_spend": 0.0,
            "loyalty_points": 0,
            "last_visit": None,
            "created_at": utcnow(),
        }
    )
    try:
        result = await db.customers.insert_one(document)
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A customer with phone {payload.phone} already exists",
        ) from exc
    created = await db.customers.find_one({"_id": result.inserted_id})
    return customer_out(created or {})


@router.put("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    _: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    db = get_db()
    object_id = to_object_id(customer_id, "customer_id")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields supplied to update")
    if "credit_due" in updates and updates["credit_due"] is not None:
        updates["credit_due"] = q2(updates["credit_due"])

    try:
        result = await db.customers.update_one({"_id": object_id}, {"$set": updates})
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That phone number belongs to another customer",
        ) from exc
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    document = await db.customers.find_one({"_id": object_id})
    return customer_out(document or {})
