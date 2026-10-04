"""Document -> response shaping, including every derived financial field.

Derived values (effective price, unit profit, margin, stock status) are computed
here rather than stored, so a price or discount edit can never leave a stale
profit figure behind in the database.
"""

from __future__ import annotations

from typing import Any

from .models import StockStatus, serialize_doc
from .money import effective_price, margin_percent, q2, unit_profit


def stock_status(stock_total: int, reorder_threshold: int) -> StockStatus:
    if stock_total <= 0:
        return StockStatus.OUT_OF_STOCK
    if stock_total <= reorder_threshold:
        return StockStatus.LOW_STOCK
    return StockStatus.IN_STOCK


def product_out(document: dict[str, Any]) -> dict[str, Any]:
    data = serialize_doc(document) or {}
    selling = float(data.get("selling_price", 0.0))
    buying = float(data.get("buying_price", 0.0))
    discount = float(data.get("discount_percentage", 0.0))
    shelf = int(data.get("stock_shelf", 0))
    warehouse = int(data.get("stock_warehouse", 0))
    threshold = int(data.get("reorder_threshold", 0))
    total = shelf + warehouse

    data.update(
        {
            "buying_price": q2(buying),
            "market_price": q2(data.get("market_price", 0.0)),
            "selling_price": q2(selling),
            "discount_percentage": q2(discount),
            "stock_total": total,
            "effective_selling_price": effective_price(selling, discount),
            "unit_profit": unit_profit(selling, buying, discount),
            "margin_percent": margin_percent(selling, buying, discount),
            "status": stock_status(total, threshold),
        }
    )
    return data


def customer_out(document: dict[str, Any]) -> dict[str, Any]:
    data = serialize_doc(document) or {}
    data["total_spend"] = q2(data.get("total_spend", 0.0))
    data["credit_due"] = q2(data.get("credit_due", 0.0))
    data["total_visits"] = int(data.get("total_visits", 0))
    data["loyalty_points"] = int(data.get("loyalty_points", 0))
    return data


def sale_out(document: dict[str, Any]) -> dict[str, Any]:
    data = serialize_doc(document) or {}
    data["items"] = [
        {
            **item,
            "line_total": q2(item.get("line_total", 0.0)),
            "line_profit": q2(item.get("line_profit", 0.0)),
        }
        for item in data.get("items", [])
    ]
    for field in ("subtotal", "discount_total", "tax_amount", "grand_total", "net_profit"):
        data[field] = q2(data.get(field, 0.0))
    return data


def store_out(document: dict[str, Any]) -> dict[str, Any]:
    data = serialize_doc(document) or {}
    data["tax_rate"] = q2(data.get("tax_rate", 0.0))
    data["default_discount"] = q2(data.get("default_discount", 0.0))
    return data
