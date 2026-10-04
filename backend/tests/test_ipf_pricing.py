"""Pricing logic behind the IPF screen — pure functions, no database."""

from __future__ import annotations

from app.ml.pricing import recommend


def _row(**overrides):
    base = {
        "product": {"_id": "p1", "name": "Fresh Milk 1L", "brand": "Ambewela", "category": "Dairy"},
        "selling_price": 100.0,
        "buying_price": 70.0,
        "market_price": 120.0,
        "discount_percentage": 0.0,
        "stock_total": 100.0,
        "recent_velocity": 2.0,
        "velocity_7": 2.0,
        "baseline_units": 28.0,
        "days_of_cover": 50.0,
    }
    base.update(overrides)
    return base


def test_rising_demand_under_the_market_is_a_price_up():
    result = recommend(_row(), predicted_units=42.0, model_beats_baseline=True)  # +50% demand
    assert result["recommendation"] == "PRICE_UP"
    assert result["suggested_price"] > result["current_price"]
    assert result["suggested_price"] <= result["market_price"]
    assert result["projected_profit_impact"] > 0


def test_a_product_already_below_cost_is_a_loss_risk():
    result = recommend(
        _row(selling_price=100.0, buying_price=120.0), predicted_units=30.0, model_beats_baseline=True
    )
    assert result["recommendation"] == "LOSS_RISK"
    assert result["unit_profit"] < 0
    assert "loss" in result["reason"].lower()
    # The fix is to lift the price, but never above the market reference.
    assert result["suggested_price"] >= result["current_price"]
    assert result["suggested_price"] <= result["market_price"]


def test_slow_moving_overstock_is_a_loss_risk_with_a_markdown():
    result = recommend(
        _row(days_of_cover=120.0), predicted_units=14.0, model_beats_baseline=True
    )  # demand halves
    assert result["recommendation"] == "LOSS_RISK"
    assert result["suggested_price"] < result["current_price"]
    # A markdown must never go below what the stock cost.
    assert result["suggested_price"] >= result["buying_price"]


def test_a_thin_margin_with_softening_demand_is_flagged():
    result = recommend(
        _row(buying_price=97.0, market_price=105.0, days_of_cover=10.0),
        predicted_units=26.0,
        model_beats_baseline=True,
    )
    assert result["recommendation"] == "LOSS_RISK"
    assert "margin" in result["reason"].lower()


def test_steady_demand_is_left_alone():
    result = recommend(_row(), predicted_units=28.0, model_beats_baseline=True)
    assert result["recommendation"] == "HOLD"
    assert result["suggested_price"] == result["current_price"]
    assert result["extra_profit_per_unit"] == 0


def test_rising_demand_without_headroom_is_not_a_price_up():
    """Already at the market price: demand alone is not a reason to go above it."""
    result = recommend(_row(market_price=100.0), predicted_units=42.0, model_beats_baseline=True)
    assert result["recommendation"] == "HOLD"


def test_discount_is_taken_off_before_any_judgement():
    result = recommend(
        _row(selling_price=100.0, discount_percentage=40.0, buying_price=70.0),
        predicted_units=28.0,
        model_beats_baseline=True,
    )
    # 100 less 40% is 60, which is under the 70 cost: a loss, not a healthy line.
    assert result["current_price"] == 60.0
    assert result["unit_profit"] == -10.0
    assert result["recommendation"] == "LOSS_RISK"


def test_confidence_falls_when_there_is_little_recent_trade():
    busy = recommend(_row(recent_velocity=3.0), predicted_units=60.0, model_beats_baseline=True)
    quiet = recommend(_row(recent_velocity=0.1, baseline_units=1.4), predicted_units=3.0, model_beats_baseline=True)
    assert busy["confidence"] == "HIGH"
    assert quiet["confidence"] == "LOW"


def test_confidence_is_capped_when_the_model_loses_to_the_baseline():
    result = recommend(_row(recent_velocity=3.0), predicted_units=60.0, model_beats_baseline=False)
    assert result["confidence"] != "HIGH"
