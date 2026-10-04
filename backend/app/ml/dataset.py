"""Feature engineering for the IPF (Items Prices in Future) model.

What this model actually learns
-------------------------------
The sales ledger records one selling price per product for its whole history —
the shop has never run a price experiment — so there is **no price-elasticity
signal in the data**. A model claiming to predict future market prices from it
would be inventing numbers.

What the data does contain is real, varying daily demand per product. So the
model is trained to forecast **demand over the next 14 days**, and the pricing
recommendation in `pricing.py` combines that forecast with figures the store
already knows: the margin, and the gap between our shelf price and the
competitor reference price (`market_price`). That is a defensible chain of
reasoning end to end, and every step of it is visible to the owner.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..timeutils import local_day_start, local_tz_offset

LOOKBACK_DAYS = 28
HORIZON_DAYS = 14
# Enough days to cut at least a couple of distinct training windows.
MIN_HISTORY_DAYS = LOOKBACK_DAYS + HORIZON_DAYS + 14

NUMERIC_FEATURES = [
    "velocity_7",
    "velocity_14",
    "velocity_28",
    "velocity_trend",
    "velocity_ratio",
    "active_day_share_14",
    "peak_units_14",
    "units_std_14",
    "units_total_28",
    "selling_price",
    "buying_price",
    "market_price",
    "discount_percentage",
    "margin_percent",
    "price_vs_market",
    "stock_total",
    "days_of_cover",
    "anchor_weekday",
]


async def load_daily_units(
    db: AsyncIOMotorDatabase, days: int
) -> tuple[dict[str, np.ndarray], list[str]]:
    """Net units sold per product per local day, as dense arrays.

    Refund lines carry negative quantities, so summing gives net demand — a
    basket that came back was not real demand and should not inflate a forecast.
    """
    start = local_day_start(days - 1)
    timezone = local_tz_offset()

    pipeline = [
        {"$match": {"timestamp": {"$gte": start}}},
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": {
                    "product": "$items.product_id",
                    "day": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp",
                            "timezone": timezone,
                        }
                    },
                },
                "units": {"$sum": "$items.quantity"},
            }
        },
    ]

    day_keys = [
        local_day_start(days - 1 - offset).astimezone().strftime("%Y-%m-%d")
        for offset in range(days)
    ]
    index_of_day = {key: index for index, key in enumerate(day_keys)}

    series: dict[str, np.ndarray] = {}
    async for row in db.sales.aggregate(pipeline):
        product_id = str(row["_id"]["product"])
        day_index = index_of_day.get(row["_id"]["day"])
        if day_index is None:
            continue
        if product_id not in series:
            series[product_id] = np.zeros(days, dtype=float)
        # Net demand cannot be negative on a day where returns outweigh sales.
        series[product_id][day_index] += float(row["units"])

    for units in series.values():
        np.clip(units, 0, None, out=units)

    return series, day_keys


async def load_products(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    return [product async for product in db.products.find({"is_active": True})]


def _static_features(product: dict[str, Any]) -> dict[str, float]:
    selling = float(product.get("selling_price", 0.0))
    buying = float(product.get("buying_price", 0.0))
    market = float(product.get("market_price", 0.0))
    discount = float(product.get("discount_percentage", 0.0))
    effective = round(selling * (1 - discount / 100), 2)
    margin = ((effective - buying) / effective * 100) if effective > 0 else 0.0
    stock_total = float(product.get("stock_shelf", 0)) + float(product.get("stock_warehouse", 0))

    return {
        "selling_price": selling,
        "buying_price": buying,
        "market_price": market,
        "discount_percentage": discount,
        "margin_percent": margin,
        # Below 1.0 means we sit under the competitor reference price.
        "price_vs_market": (effective / market) if market > 0 else 1.0,
        "stock_total": stock_total,
    }


def _window_features(units: np.ndarray, anchor: int) -> dict[str, float]:
    last_7 = units[anchor - 7 : anchor]
    last_14 = units[anchor - 14 : anchor]
    last_28 = units[anchor - LOOKBACK_DAYS : anchor]

    velocity_7 = float(last_7.mean())
    velocity_14 = float(last_14.mean())

    return {
        "velocity_7": velocity_7,
        "velocity_14": velocity_14,
        "velocity_28": float(last_28.mean()),
        "velocity_trend": velocity_7 - velocity_14,
        # Guarded ratio: a product that sold nothing must not divide by zero.
        "velocity_ratio": velocity_7 / (velocity_14 + 0.1),
        "active_day_share_14": float((last_14 > 0).mean()),
        "peak_units_14": float(last_14.max()),
        "units_std_14": float(last_14.std()),
        "units_total_28": float(last_28.sum()),
    }


def category_vocabulary(products: list[dict[str, Any]]) -> list[str]:
    return sorted({str(product.get("category", "")) for product in products})


def _one_hot(category: str, vocabulary: list[str]) -> list[float]:
    return [1.0 if category == name else 0.0 for name in vocabulary]


def feature_names(vocabulary: list[str]) -> list[str]:
    return NUMERIC_FEATURES + [f"category={name}" for name in vocabulary]


def _row(
    product: dict[str, Any],
    units: np.ndarray,
    anchor: int,
    anchor_weekday: int,
    vocabulary: list[str],
) -> list[float]:
    static = _static_features(product)
    window = _window_features(units, anchor)
    days_of_cover = static["stock_total"] / (window["velocity_14"] + 0.1)

    values = {**static, **window, "days_of_cover": days_of_cover, "anchor_weekday": float(anchor_weekday)}
    return [values[name] for name in NUMERIC_FEATURES] + _one_hot(
        str(product.get("category", "")), vocabulary
    )


def build_training_frame(
    products: list[dict[str, Any]],
    series: dict[str, np.ndarray],
    day_keys: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Cut every (product, anchor day) window into one training example.

    Returns features, target (units over the next horizon), the naive baseline
    for each row, and the anchor index so the split can be made in time order
    rather than at random — a random split would let the model peek at the
    future of a product it also trained on.
    """
    vocabulary = category_vocabulary(products)
    total_days = len(day_keys)

    features: list[list[float]] = []
    targets: list[float] = []
    baselines: list[float] = []
    anchors: list[int] = []

    first_anchor = LOOKBACK_DAYS
    last_anchor = total_days - HORIZON_DAYS

    for product in products:
        product_id = str(product["_id"])
        units = series.get(product_id)
        if units is None:
            continue
        for anchor in range(first_anchor, last_anchor):
            window = units[anchor - LOOKBACK_DAYS : anchor]
            # Skip products with no trading history in the window: there is
            # nothing to learn from an all-zero row.
            if window.sum() <= 0:
                continue
            weekday = datetime.strptime(day_keys[anchor], "%Y-%m-%d").weekday()
            features.append(_row(product, units, anchor, weekday, vocabulary))
            targets.append(float(units[anchor : anchor + HORIZON_DAYS].sum()))
            baselines.append(float(units[anchor - 14 : anchor].mean() * HORIZON_DAYS))
            anchors.append(anchor)

    if not features:
        return (
            np.empty((0, len(feature_names(vocabulary)))),
            np.empty(0),
            np.empty(0),
            np.empty(0),
            vocabulary,
        )

    return (
        np.asarray(features, dtype=float),
        np.asarray(targets, dtype=float),
        np.asarray(baselines, dtype=float),
        np.asarray(anchors, dtype=int),
        vocabulary,
    )


def build_prediction_frame(
    products: list[dict[str, Any]],
    series: dict[str, np.ndarray],
    day_keys: list[str],
    vocabulary: list[str],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Features for "right now" — the anchor is the end of the history."""
    anchor = len(day_keys)
    weekday = datetime.now().astimezone().weekday()

    features: list[list[float]] = []
    rows: list[dict[str, Any]] = []

    for product in products:
        product_id = str(product["_id"])
        units = series.get(product_id)
        if units is None:
            units = np.zeros(len(day_keys), dtype=float)
        if len(units) < LOOKBACK_DAYS:
            continue

        window = _window_features(units, anchor)
        static = _static_features(product)
        features.append(_row(product, units, anchor, weekday, vocabulary))
        rows.append(
            {
                "product": product,
                "recent_velocity": window["velocity_14"],
                "velocity_7": window["velocity_7"],
                "baseline_units": window["velocity_14"] * HORIZON_DAYS,
                "days_of_cover": static["stock_total"] / (window["velocity_14"] + 0.1),
                **static,
            }
        )

    if not features:
        return np.empty((0, len(feature_names(vocabulary)))), []
    return np.asarray(features, dtype=float), rows
