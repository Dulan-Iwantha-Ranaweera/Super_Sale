"""Items Prices in Future (IPF) — owner-only price forecasting.

Every route here is gated on `require_owner`: pricing intent, margins and the
loss-risk list are commercially sensitive and must not be visible from the till.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..ml import dataset, model as ml_model
from ..ml.pricing import recommend
from ..models import IpfForecast, IpfModelStatus, IpfRow
from ..money import q2
from ..security import require_owner

router = APIRouter(prefix="/api/ipf", tags=["ipf"])

# How much history to pull for training. More is better; the loader is cheap.
TRAINING_WINDOW_DAYS = 400


async def _load_frames(db, days: int):
    products = await dataset.load_products(db)
    series, day_keys = await dataset.load_daily_units(db, days)
    return products, series, day_keys


@router.get("/model", response_model=IpfModelStatus)
async def model_status(_: dict[str, Any] = Depends(require_owner)) -> IpfModelStatus:
    loaded = ml_model.load_model()
    if not loaded:
        return IpfModelStatus(trained=False)
    _, _, metadata = loaded
    return IpfModelStatus(trained=True, **metadata)


@router.post("/train", response_model=IpfModelStatus)
async def train(_: dict[str, Any] = Depends(require_owner)) -> IpfModelStatus:
    """Retrain on the full sales history and report how it scored."""
    db = get_db()
    products, series, day_keys = await _load_frames(db, TRAINING_WINDOW_DAYS)

    if len(day_keys) < dataset.MIN_HISTORY_DAYS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"At least {dataset.MIN_HISTORY_DAYS} days of sales are needed to train. "
                "Keep trading and try again."
            ),
        )

    features, targets, baselines, anchors, categories = dataset.build_training_frame(
        products, series, day_keys
    )

    try:
        # scikit-learn is CPU-bound and synchronous: keep it off the event loop.
        estimator, metadata = await run_in_threadpool(
            ml_model.train_model, features, targets, baselines, anchors, categories
        )
    except ml_model.NotEnoughData as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await run_in_threadpool(ml_model.save_model, estimator, metadata)
    return IpfModelStatus(trained=True, **metadata.to_dict())


@router.get("/forecast", response_model=IpfForecast)
async def forecast(
    limit: int = Query(10, ge=1, le=50),
    _: dict[str, Any] = Depends(require_owner),
) -> IpfForecast:
    """Products that could carry a higher price, and those heading for a loss."""
    loaded = ml_model.load_model()
    if not loaded:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The forecasting model has not been trained yet. Train it to see predictions.",
        )
    estimator, categories, metadata = loaded

    db = get_db()
    products, series, day_keys = await _load_frames(db, TRAINING_WINDOW_DAYS)
    features, rows = dataset.build_prediction_frame(products, series, day_keys, categories)

    if not rows:
        return IpfForecast(
            horizon_days=metadata.get("horizon_days", dataset.HORIZON_DAYS),
            generated_rows=0,
            opportunities=[],
            risks=[],
            steady=0,
            projected_upside=0.0,
            projected_exposure=0.0,
            model=IpfModelStatus(trained=True, **metadata),
        )

    expected = ml_model.expected_feature_count(categories)
    if features.shape[1] != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The catalogue has changed since the model was trained "
                "(a new category was added). Retrain to refresh the predictions."
            ),
        )

    predictions = await run_in_threadpool(ml_model.predict, estimator, features)
    beats_baseline = bool(metadata.get("beats_baseline", False))

    scored = [
        recommend(row, float(prediction), beats_baseline)
        for row, prediction in zip(rows, predictions)
    ]

    opportunities = sorted(
        (item for item in scored if item["recommendation"] == "PRICE_UP"),
        key=lambda item: -item["projected_profit_impact"],
    )
    risks = sorted(
        (item for item in scored if item["recommendation"] == "LOSS_RISK"),
        key=lambda item: (item["unit_profit"], -item["days_of_cover"]),
    )
    steady = sum(1 for item in scored if item["recommendation"] == "HOLD")

    return IpfForecast(
        horizon_days=metadata.get("horizon_days", dataset.HORIZON_DAYS),
        generated_rows=len(scored),
        opportunities=[IpfRow(**item) for item in opportunities[:limit]],
        risks=[IpfRow(**item) for item in risks[:limit]],
        steady=steady,
        projected_upside=q2(sum(item["projected_profit_impact"] for item in opportunities)),
        projected_exposure=q2(
            sum(
                item["unit_profit"] * item["predicted_units"]
                for item in risks
                if item["unit_profit"] < 0
            )
        ),
        model=IpfModelStatus(trained=True, **metadata),
    )
