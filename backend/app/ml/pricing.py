"""Turn a demand forecast into a pricing recommendation.

The model forecasts demand; it does not forecast prices, because the sales
history contains no price variation to learn elasticity from. This module makes
the remaining step explicit and auditable: a product is a candidate for a
**higher** price when demand is rising *and* we are still priced under the
competitor reference, and a **loss risk** when it is already below cost, or
slow-moving and overstocked so that clearing it will need a discount.

Every row carries the numbers behind its verdict, so the owner can disagree.
"""

from __future__ import annotations

from typing import Any

from ..money import q2

# A product must be moving at all before any pricing advice is worth giving.
MIN_PREDICTED_UNITS = 1.0

RISING_DEMAND = 1.08
FALLING_DEMAND = 0.85

MIN_HEADROOM_PERCENT = 2.0
MAX_UPLIFT_PERCENT = 10.0
MAX_MARKDOWN_PERCENT = 15.0

THIN_MARGIN_PERCENT = 6.0


def _confidence(row: dict[str, Any], model_beats_baseline: bool) -> str:
    """How much the figures deserve to be trusted for this product."""
    units = row["recent_velocity"] * 14
    if units >= 20 and model_beats_baseline:
        return "HIGH"
    if units >= 6:
        return "MEDIUM"
    return "LOW"


def recommend(row: dict[str, Any], predicted_units: float, model_beats_baseline: bool) -> dict[str, Any]:
    product = row["product"]
    selling = q2(row["selling_price"])
    buying = q2(row["buying_price"])
    market = q2(row["market_price"])
    discount = q2(row["discount_percentage"])
    effective = q2(selling * (1 - discount / 100))

    unit_profit = q2(effective - buying)
    margin = q2(unit_profit / effective * 100) if effective > 0 else 0.0

    baseline_units = max(row["baseline_units"], 0.0)
    predicted = max(0.0, float(predicted_units))
    demand_ratio = predicted / baseline_units if baseline_units > 0.5 else (1.0 if predicted <= 0.5 else 2.0)
    demand_change = q2((demand_ratio - 1) * 100)

    headroom_percent = q2((market - effective) / effective * 100) if effective > 0 else 0.0
    days_of_cover = q2(row["days_of_cover"])

    recommendation = "HOLD"
    suggested = effective
    reason = "Demand and pricing both look steady — leave the price alone."

    if unit_profit <= 0:
        recommendation = "LOSS_RISK"
        # Lift at least to cost plus a thin margin, but never past the market.
        target = max(buying * 1.08, effective)
        suggested = q2(min(target, market) if market > 0 else target)
        reason = (
            f"Already sells at a loss of {abs(unit_profit):.2f} per unit after its "
            f"{discount:.0f}% discount. Raise the price or drop the discount."
        )
    elif demand_ratio <= FALLING_DEMAND and days_of_cover > 2 * 14 and predicted >= MIN_PREDICTED_UNITS:
        recommendation = "LOSS_RISK"
        # Mark down enough to move it, but never below cost.
        markdown = min(MAX_MARKDOWN_PERCENT, max(5.0, (1 - demand_ratio) * 40))
        floor = q2(buying * 1.02)
        suggested = q2(max(floor, effective * (1 - markdown / 100)))
        reason = (
            f"Demand is falling {abs(demand_change):.0f}% and there is "
            f"{days_of_cover:.0f} days of stock on hand. Clearing it will need a markdown, "
            "which eats the margin."
        )
    elif margin < THIN_MARGIN_PERCENT and demand_ratio < 1.0:
        recommendation = "LOSS_RISK"
        suggested = q2(min(market, effective * 1.04) if market > effective else effective)
        reason = (
            f"Margin is only {margin:.1f}% and demand is softening — one supplier "
            "increase turns this line into a loss."
        )
    elif (
        demand_ratio >= RISING_DEMAND
        and headroom_percent >= MIN_HEADROOM_PERCENT
        and predicted >= MIN_PREDICTED_UNITS
    ):
        recommendation = "PRICE_UP"
        # Take a share of the gap to the market price, in proportion to how
        # strongly demand is rising, and never price above the market.
        strength = min(1.0, (demand_ratio - 1) / 0.4)
        uplift = min(headroom_percent, MAX_UPLIFT_PERCENT) * strength
        suggested = q2(min(market, effective * (1 + uplift / 100)))
        reason = (
            f"Demand is up {demand_change:.0f}% on the last fortnight and we are still "
            f"{headroom_percent:.0f}% under the market price of {market:.2f}."
        )

    price_change_percent = q2((suggested - effective) / effective * 100) if effective > 0 else 0.0
    extra_per_unit = q2(suggested - effective)
    projected_impact = q2(extra_per_unit * predicted)

    return {
        "product_id": str(product["_id"]),
        "name": product.get("name", ""),
        "brand": product.get("brand"),
        "category": product.get("category", ""),
        "image_url": product.get("image_url"),
        "current_price": effective,
        "list_price": selling,
        "buying_price": buying,
        "market_price": market,
        "discount_percentage": discount,
        "unit_profit": unit_profit,
        "margin_percent": margin,
        "recent_units": q2(baseline_units),
        "predicted_units": q2(predicted),
        "demand_change_percent": demand_change,
        "days_of_cover": days_of_cover,
        "headroom_percent": headroom_percent,
        "recommendation": recommendation,
        "suggested_price": suggested,
        "price_change_percent": price_change_percent,
        "extra_profit_per_unit": extra_per_unit,
        "projected_profit_impact": projected_impact,
        "confidence": _confidence(row, model_beats_baseline),
        "reason": reason,
    }
