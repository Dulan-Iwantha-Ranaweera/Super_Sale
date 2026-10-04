"""Reports & analytics: period summaries, monthly series and category breakdown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..database import get_db
from ..models import CategorySlice, MonthlyPoint, ReportSummary
from ..money import percent_of, q2
from ..security import require_owner
from ..timeutils import local_day_start, local_tz_offset, month_bounds

router = APIRouter(prefix="/api/reports", tags=["reports"])

MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _resolve_range(start: str | None, end: str | None, days: int) -> tuple[datetime, datetime]:
    """Explicit YYYY-MM-DD range when given, otherwise a trailing window."""
    if start or end:
        try:
            start_dt = (
                datetime.fromisoformat(start).astimezone().astimezone(timezone.utc)
                if start
                else local_day_start(days - 1)
            )
            end_dt = (
                (datetime.fromisoformat(end).astimezone() + timedelta(days=1)).astimezone(timezone.utc)
                if end
                else local_day_start(-1)
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
        return start_dt, end_dt
    return local_day_start(days - 1), local_day_start(-1)


@router.get("/summary", response_model=ReportSummary)
async def summary(
    start: str | None = None,
    end: str | None = None,
    days: int = Query(30, ge=1, le=730),
    _: dict[str, Any] = Depends(require_owner),
) -> ReportSummary:
    db = get_db()
    start_dt, end_dt = _resolve_range(start, end, days)

    is_return = {"$eq": [{"$ifNull": ["$type", "SALE"]}, "RETURN"]}
    pipeline = [
        {"$match": {"timestamp": {"$gte": start_dt, "$lt": end_dt}}},
        {
            "$group": {
                "_id": None,
                "gross_revenue": {"$sum": {"$cond": [is_return, 0, "$grand_total"]}},
                "refunds": {"$sum": {"$cond": [is_return, "$grand_total", 0]}},
                "net_profit": {"$sum": "$net_profit"},
                "transactions": {"$sum": {"$cond": [is_return, 0, 1]}},
                "returns": {"$sum": {"$cond": [is_return, 1, 0]}},
                "items_sold": {"$sum": {"$sum": "$items.quantity"}},
            }
        },
    ]
    result = await db.sales.aggregate(pipeline).to_list(length=1)
    if not result:
        return ReportSummary(
            gross_revenue=0.0,
            refunds=0.0,
            net_revenue=0.0,
            cost_of_goods=0.0,
            net_profit=0.0,
            profit_margin=0.0,
            transactions=0,
            returns=0,
            items_sold=0,
        )

    row = result[0]
    gross_revenue = q2(row.get("gross_revenue", 0.0))
    refunds = abs(q2(row.get("refunds", 0.0)))
    net_revenue = q2(gross_revenue - refunds)
    profit = q2(row.get("net_profit", 0.0))
    return ReportSummary(
        gross_revenue=gross_revenue,
        refunds=refunds,
        net_revenue=net_revenue,
        cost_of_goods=q2(net_revenue - profit),
        net_profit=profit,
        profit_margin=percent_of(profit, net_revenue),
        transactions=int(row.get("transactions", 0)),
        returns=int(row.get("returns", 0)),
        items_sold=int(row.get("items_sold", 0)),
    )


@router.get("/monthly", response_model=list[MonthlyPoint])
async def monthly(
    year: int = Query(default=0, ge=0, le=9999),
    _: dict[str, Any] = Depends(require_owner),
) -> list[MonthlyPoint]:
    db = get_db()
    target_year = year or datetime.now().astimezone().year
    start_dt, end_dt = month_bounds(target_year)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_dt, "$lt": end_dt}}},
        {
            "$group": {
                "_id": {"$month": {"date": "$timestamp", "timezone": local_tz_offset()}},
                "revenue": {"$sum": "$grand_total"},
                "profit": {"$sum": "$net_profit"},
            }
        },
    ]
    buckets = {int(row["_id"]): row async for row in db.sales.aggregate(pipeline)}

    return [
        MonthlyPoint(
            month=MONTH_LABELS[index],
            revenue=q2(buckets.get(index + 1, {}).get("revenue", 0.0)),
            profit=q2(buckets.get(index + 1, {}).get("profit", 0.0)),
        )
        for index in range(12)
    ]


@router.get("/by-category", response_model=list[CategorySlice])
async def by_category(
    start: str | None = None,
    end: str | None = None,
    days: int = Query(30, ge=1, le=730),
    _: dict[str, Any] = Depends(require_owner),
) -> list[CategorySlice]:
    """Revenue and profit per category.

    The sale line stores a product reference, so the category is looked up with
    a `$lookup` rather than denormalised onto every sale item.
    """
    db = get_db()
    start_dt, end_dt = _resolve_range(start, end, days)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_dt, "$lt": end_dt}}},
        {"$unwind": "$items"},
        {
            "$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product",
            }
        },
        {
            "$addFields": {
                "category": {
                    "$ifNull": [{"$arrayElemAt": ["$product.category", 0]}, "Uncategorised"]
                }
            }
        },
        {
            "$group": {
                "_id": "$category",
                "revenue": {"$sum": "$items.line_total"},
                "profit": {"$sum": "$items.line_profit"},
                "units": {"$sum": "$items.quantity"},
            }
        },
        {"$sort": {"revenue": -1}},
    ]

    return [
        CategorySlice(
            category=row["_id"],
            revenue=q2(row.get("revenue", 0.0)),
            profit=q2(row.get("profit", 0.0)),
            units=int(row.get("units", 0)),
        )
        async for row in db.sales.aggregate(pipeline)
    ]


@router.get("/top-products", response_model=list[dict])
async def top_products(
    days: int = Query(30, ge=1, le=730),
    limit: int = Query(10, ge=1, le=50),
    _: dict[str, Any] = Depends(require_owner),
) -> list[dict]:
    db = get_db()
    start_dt = local_day_start(days - 1)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_dt}}},
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.name",
                "units": {"$sum": "$items.quantity"},
                "revenue": {"$sum": "$items.line_total"},
                "profit": {"$sum": "$items.line_profit"},
            }
        },
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    return [
        {
            "name": row["_id"],
            "units": int(row.get("units", 0)),
            "revenue": q2(row.get("revenue", 0.0)),
            "profit": q2(row.get("profit", 0.0)),
        }
        async for row in db.sales.aggregate(pipeline)
    ]
