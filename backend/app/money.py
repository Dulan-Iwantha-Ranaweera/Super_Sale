"""Currency helpers.

Every monetary value crossing the API or hitting the database goes through
`q2`, which rounds with Decimal (ROUND_HALF_UP) instead of relying on IEEE-754
binary floats. This keeps 0.1 + 0.2 style drift out of persisted totals.
"""

from decimal import Decimal, ROUND_HALF_UP


def q2(value: float | int | Decimal | str) -> float:
    """Round to exactly 2 decimal places using half-up rounding."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def effective_price(selling_price: float, discount_percentage: float) -> float:
    """Selling price after the product/line discount is applied."""
    return q2(Decimal(str(selling_price)) * (Decimal("1") - Decimal(str(discount_percentage)) / Decimal("100")))


def unit_profit(selling_price: float, buying_price: float, discount_percentage: float) -> float:
    return q2(Decimal(str(effective_price(selling_price, discount_percentage))) - Decimal(str(buying_price)))


def margin_percent(selling_price: float, buying_price: float, discount_percentage: float) -> float:
    effective = effective_price(selling_price, discount_percentage)
    if effective <= 0:
        return 0.0
    profit = unit_profit(selling_price, buying_price, discount_percentage)
    return q2(Decimal(str(profit)) / Decimal(str(effective)) * Decimal("100"))


def percent_of(part: float, whole: float) -> float:
    """Safe percentage helper: returns 0.0 instead of dividing by zero."""
    if not whole:
        return 0.0
    return q2(Decimal(str(part)) / Decimal(str(whole)) * Decimal("100"))
