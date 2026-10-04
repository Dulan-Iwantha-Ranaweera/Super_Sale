"""Pure unit tests for the currency layer — no database involved."""

import pytest

from app.money import effective_price, margin_percent, percent_of, q2, unit_profit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.1 + 0.2, 0.30),  # the classic float-drift case
        (1.005, 1.01),  # half-up, not banker's rounding
        (2.675, 2.68),
        (10, 10.00),
        (-1.005, -1.01),
        ("3.14159", 3.14),
    ],
)
def test_q2_rounds_half_up(value, expected):
    assert q2(value) == expected


def test_q2_keeps_long_sums_exact():
    total = 0.0
    for _ in range(10):
        total = q2(total + 0.1)
    assert total == 1.00


@pytest.mark.parametrize(
    ("selling", "discount", "expected"),
    [
        (15.00, 0.0, 15.00),
        (15.00, 10.0, 13.50),
        (15.00, 100.0, 0.00),
        (2.00, 33.0, 1.34),
        (0.00, 50.0, 0.00),
    ],
)
def test_effective_price(selling, discount, expected):
    assert effective_price(selling, discount) == expected


def test_unit_profit_matches_the_spec_formula():
    # effective 13.50, cost 10.00 -> profit 3.50, margin 25.93%
    assert unit_profit(15.00, 10.00, 10.0) == 3.50
    assert margin_percent(15.00, 10.00, 10.0) == 25.93


def test_unit_profit_can_be_negative():
    assert unit_profit(5.00, 20.00, 0.0) == -15.00
    assert margin_percent(5.00, 20.00, 0.0) == -300.00


def test_margin_is_zero_when_the_effective_price_is_zero():
    """A 100% discount must not raise ZeroDivisionError."""
    assert margin_percent(15.00, 10.00, 100.0) == 0.0
    assert margin_percent(0.0, 0.0, 0.0) == 0.0


def test_percent_of_guards_division_by_zero():
    assert percent_of(5, 0) == 0.0
    assert percent_of(25, 200) == 12.50
