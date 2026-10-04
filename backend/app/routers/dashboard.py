"""Dashboard aggregates: capacity gauges, today's KPIs and demand forecasting."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..config import get_settings
from ..database import get_db
from ..models import (
    CapacityGauge,
    CapacityOut,
    DashboardMetrics,
    ForecastRow,
    ProfitPoint,
)
from ..money import percent_of, q2
from ..security import current_user
from ..timeutils import local_day_start, local_tz_offset

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

VELOCITY_WINDOW_DAYS = 14


async def _sales_totals(start: datetime, end: datetime) -> dict[str, float]:
    db = get_db()
    # Refunds are negative documents in the same ledger, so sales and refunds
    # are separated with $cond instead of querying the collection twice.
    is_return = {"$eq": [{"$ifNull": ["$type", "SALE"]}, "RETURN"]}
    pipeline = [
        {"$match": {"timestamp": {"$gte": start, "$lt": end}}},
        {
            "$group": {
                "_id": None,
                "revenue": {"$sum": {"$cond": [is_return, 0, "$grand_total"]}},
                "refunds": {"$sum": {"$cond": [is_return, "$grand_total", 0]}},
                "profit": {"$sum": "$net_profit"},
                "transactions": {"$sum": {"$cond": [is_return, 0, 1]}},
                "returns": {"$sum": {"$cond": [is_return, 1, 0]}},
            }
        },
    ]
    result = await db.sales.aggregate(pipeline).to_list(length=1)
    if not result:
        return {"revenue": 0.0, "refunds": 0.0, "profit": 0.0, "transactions": 0, "returns": 0}
    row = result[0]
    return {
        "revenue": q2(row.get("revenue", 0.0)),
        "refunds": abs(q2(row.get("refunds", 0.0))),
        "profit": q2(row.get("profit", 0.0)),
        "transactions": int(row.get("transactions", 0)),
        "returns": int(row.get("returns", 0)),
    }


@router.get("/capacity", response_model=CapacityOut)
async def capacity(_: dict[str, Any] = Depends(current_user)) -> CapacityOut:
    db = get_db()
    settings = get_settings()
    store = await db.stores.find_one({"_id": settings.store_id}) or {}

    pipeline = [
        {"$match": {"is_active": True}},
        {
            "$group": {
                "_id": None,
                "shelf": {"$sum": "$stock_shelf"},
                "warehouse": {"$sum": "$stock_warehouse"},
            }
        },
    ]
    result = await db.products.aggregate(pipeline).to_list(length=1)
    used_shelf = int(result[0]["shelf"]) if result else 0
    used_warehouse = int(result[0]["warehouse"]) if result else 0

    shelf_max = int(store.get("shelf_capacity_max", 0)) or 1
    warehouse_max = int(store.get("warehouse_capacity_max", 0)) or 1

    return CapacityOut(
        shelf=CapacityGauge(
            used=used_shelf,
            maximum=shelf_max,
            percent=min(100.0, percent_of(used_shelf, shelf_max)),
        ),
        warehouse=CapacityGauge(
            used=used_warehouse,
            maximum=warehouse_max,
            percent=min(100.0, percent_of(used_warehouse, warehouse_max)),
        ),
    )


@router.get("/metrics", response_model=DashboardMetrics)
async def metrics(_: dict[str, Any] = Depends(current_user)) -> DashboardMetrics:
    db = get_db()

    inventory_pipeline = [
        {"$match": {"is_active": True}},
        {
            "$addFields": {
                "stock_total": {"$add": ["$stock_shelf", "$stock_warehouse"]},
                "effective_price": {
                    "$multiply": [
                        "$selling_price",
                        {"$subtract": [1, {"$divide": ["$discount_percentage", 100]}]},
                    ]
                },
            }
        },
        {
            "$group": {
                "_id": None,
                "cost_value": {"$sum": {"$multiply": ["$buying_price", "$stock_total"]}},
                "retail_value": {"$sum": {"$multiply": ["$effective_price", "$stock_total"]}},
                "low_stock": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gt": ["$stock_total", 0]},
                                    {"$lte": ["$stock_total", "$reorder_threshold"]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "out_of_stock": {"$sum": {"$cond": [{"$lte": ["$stock_total", 0]}, 1, 0]}},
            }
        },
    ]
    inventory = await db.products.aggregate(inventory_pipeline).to_list(length=1)
    inventory_row = inventory[0] if inventory else {}

    today_start = local_day_start()
    tomorrow_start = today_start + timedelta(days=1)
    yesterday_start = local_day_start(1)

    today = await _sales_totals(today_start, tomorrow_start)
    yesterday = await _sales_totals(yesterday_start, today_start)

    revenue_today = today["revenue"]
    refunds_today = today["refunds"]
    net_revenue_today = q2(revenue_today - refunds_today)
    profit_today = today["profit"]
    cogs_today = q2(net_revenue_today - profit_today)

    return DashboardMetrics(
        inventory_value_cost=q2(inventory_row.get("cost_value", 0.0)),
        inventory_value_retail=q2(inventory_row.get("retail_value", 0.0)),
        gross_revenue_today=revenue_today,
        refunds_today=refunds_today,
        net_revenue_today=net_revenue_today,
        cogs_today=cogs_today,
        net_profit_today=profit_today,
        profit_margin_today=percent_of(profit_today, net_revenue_today),
        profit_change_percent=percent_of(profit_today - yesterday["profit"], abs(yesterday["profit"]))
        if yesterday["profit"]
        else 0.0,
        transactions_today=int(today["transactions"]),
        returns_today=int(today["returns"]),
        low_stock_count=int(inventory_row.get("low_stock", 0)),
        out_of_stock_count=int(inventory_row.get("out_of_stock", 0)),
    )


@router.get("/forecast", response_model=list[ForecastRow])
async def forecast(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=100),
    _: dict[str, Any] = Depends(current_user),
) -> list[ForecastRow]:
    """Next-duration demand from 14-day sales velocity.

    projected = velocity * days + safety stock - current total stock
    """
    db = get_db()
    window_start = local_day_start(VELOCITY_WINDOW_DAYS)

    velocity_pipeline = [
        {"$match": {"timestamp": {"$gte": window_start}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.product_id", "units": {"$sum": "$items.quantity"}}},
    ]
    sold = {
        str(row["_id"]): int(row["units"])
        async for row in db.sales.aggregate(velocity_pipeline)
    }

    rows: list[ForecastRow] = []
    async for product in db.products.find({"is_active": True}):
        product_id = str(product["_id"])
        units_sold = sold.get(product_id, 0)
        daily_velocity = q2(units_sold / VELOCITY_WINDOW_DAYS)
        current_stock = int(product.get("stock_shelf", 0)) + int(product.get("stock_warehouse", 0))
        safety_stock = int(product.get("reorder_threshold", 0))

        projected = max(0.0, q2(daily_velocity * days + safety_stock - current_stock))
        recommended = max(0, math.ceil(projected))
        if recommended <= 0:
            continue

        days_of_cover = q2(current_stock / daily_velocity) if daily_velocity > 0 else None
        rows.append(
            ForecastRow(
                product_id=product_id,
                name=product.get("name", ""),
                category=product.get("category", ""),
                image_url=product.get("image_url"),
                current_stock=current_stock,
                daily_velocity=daily_velocity,
                projected_demand=projected,
                recommended_order=recommended,
                days_of_cover=days_of_cover,
            )
        )

    rows.sort(key=lambda row: (-row.recommended_order, row.name))
    return rows[:limit]


@router.get("/profit-series", response_model=list[ProfitPoint])
async def profit_series(
    days: int = Query(7, ge=1, le=90),
    _: dict[str, Any] = Depends(current_user),
) -> list[ProfitPoint]:
    db = get_db()
    start = local_day_start(days - 1)

    pipeline = [
        {"$match": {"timestamp": {"$gte": start}}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$timestamp",
                        "timezone": local_tz_offset(),
                    }
                },
                "revenue": {"$sum": "$grand_total"},
                "profit": {"$sum": "$net_profit"},
            }
        },
    ]
    buckets = {
        row["_id"]: row
        async for row in db.sales.aggregate(pipeline)
    }

    points: list[ProfitPoint] = []
    for offset in range(days - 1, -1, -1):
        # `local_day_start` returns local midnight expressed in UTC, so the key
        # has to be formatted back in local time to line up with the buckets,
        # which MongoDB grouped using the same local offset.
        day = local_day_start(offset).astimezone()
        key = day.strftime("%Y-%m-%d")
        bucket = buckets.get(key, {})
        points.append(
            ProfitPoint(
                label=day.strftime("%a"),
                date=key,
                revenue=q2(bucket.get("revenue", 0.0)),
                profit=q2(bucket.get("profit", 0.0)),
            )
        )
    return points
