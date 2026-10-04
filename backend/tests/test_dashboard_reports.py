"""Dashboard aggregates, forecasting, reports, CRM and sales history."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _sell(client, cashier, product_id, quantity=1):
    response = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product_id, "quantity": quantity}]},
        headers=cashier,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------- dashboard
async def test_capacity_is_the_sum_of_stock_over_the_configured_maximum(client, owner, make_product):
    await client.put(
        "/api/store",
        json={"shelf_capacity_max": 1000, "warehouse_capacity_max": 2000},
        headers=owner,
    )
    await make_product(barcode="CAP-1", stock_shelf=200, stock_warehouse=400)
    await make_product(barcode="CAP-2", stock_shelf=300, stock_warehouse=600)

    capacity = (await client.get("/api/dashboard/capacity", headers=owner)).json()
    assert capacity["shelf"] == {"used": 500, "maximum": 1000, "percent": 50.0}
    assert capacity["warehouse"] == {"used": 1000, "maximum": 2000, "percent": 50.0}


async def test_capacity_percent_is_capped_at_100(client, owner, make_product):
    await client.put("/api/store", json={"shelf_capacity_max": 10, "warehouse_capacity_max": 10}, headers=owner)
    await make_product(stock_shelf=500, stock_warehouse=500)

    capacity = (await client.get("/api/dashboard/capacity", headers=owner)).json()
    assert capacity["shelf"]["percent"] == 100.0


async def test_metrics_report_inventory_value_and_todays_trade(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product(stock_shelf=10, stock_warehouse=10)  # cost 10.00, effective 13.50

    before = (await client.get("/api/dashboard/metrics", headers=owner)).json()
    assert before["inventory_value_cost"] == 200.00  # 20 units at cost
    assert before["inventory_value_retail"] == 270.00  # 20 units at the discounted price

    await _sell(client, cashier, product["id"], quantity=2)

    after = (await client.get("/api/dashboard/metrics", headers=owner)).json()
    assert after["gross_revenue_today"] == 27.00
    assert after["net_profit_today"] == 7.00
    assert after["cogs_today"] == 20.00
    assert after["transactions_today"] == 1
    assert after["profit_margin_today"] == 25.93


async def test_metrics_count_low_and_out_of_stock_separately(client, owner, make_product):
    await make_product(barcode="M-LOW", stock_shelf=2, stock_warehouse=0, reorder_threshold=10)
    await make_product(barcode="M-OUT", stock_shelf=0, stock_warehouse=0)
    await make_product(barcode="M-OK", stock_shelf=500, stock_warehouse=0, reorder_threshold=10)

    metrics = (await client.get("/api/dashboard/metrics", headers=owner)).json()
    assert metrics["low_stock_count"] == 1
    assert metrics["out_of_stock_count"] == 1


async def test_metrics_on_an_empty_database_are_zero_not_an_error(client, owner):
    metrics = (await client.get("/api/dashboard/metrics", headers=owner)).json()
    assert metrics["gross_revenue_today"] == 0.0
    assert metrics["profit_margin_today"] == 0.0
    assert metrics["inventory_value_cost"] == 0.0


# --------------------------------------------------------------------- forecast
async def test_forecast_recommends_an_order_from_sales_velocity(client, owner, cashier, make_product):
    # 14 units sold today -> velocity 1.0/day over the 14-day window.
    product = await make_product(stock_shelf=20, stock_warehouse=0, reorder_threshold=10)
    await _sell(client, cashier, product["id"], quantity=14)

    forecast = (await client.get("/api/dashboard/forecast?days=7", headers=owner)).json()
    row = next(item for item in forecast if item["product_id"] == product["id"])

    assert row["daily_velocity"] == 1.0
    assert row["current_stock"] == 6  # 20 - 14
    # velocity(1.0) * 7 days + safety(10) - stock(6) = 11
    assert row["recommended_order"] == 11
    assert row["days_of_cover"] == 6.0


async def test_forecast_omits_products_that_have_enough_cover(client, owner, make_product):
    await make_product(barcode="PLENTY", stock_shelf=5000, reorder_threshold=10)
    forecast = (await client.get("/api/dashboard/forecast?days=7", headers=owner)).json()
    assert all(row["name"] != "Test Milk 1L" for row in forecast)


async def test_forecast_never_returns_a_negative_recommendation(client, owner, make_product):
    await make_product(stock_shelf=1, stock_warehouse=0, reorder_threshold=0)
    forecast = (await client.get("/api/dashboard/forecast?days=7", headers=owner)).json()
    assert all(row["recommended_order"] >= 0 and row["projected_demand"] >= 0 for row in forecast)


async def test_profit_series_returns_one_point_per_day(client, owner, cashier, make_product):
    product = await make_product()
    await _sell(client, cashier, product["id"])

    series = (await client.get("/api/dashboard/profit-series?days=7", headers=owner)).json()
    assert len(series) == 7
    assert series[-1]["profit"] > 0  # today carries the sale
    assert all(point["revenue"] == 0 for point in series[:-1])


# ---------------------------------------------------------------------- reports
async def test_reports_summary_derives_cogs_and_margin(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product()
    await _sell(client, cashier, product["id"], quantity=10)  # 135.00 revenue, 35.00 profit

    summary = (await client.get("/api/reports/summary?days=30", headers=owner)).json()
    assert summary["net_revenue"] == 135.00
    assert summary["net_profit"] == 35.00
    assert summary["cost_of_goods"] == 100.00
    assert summary["profit_margin"] == 25.93
    assert summary["transactions"] == 1
    assert summary["items_sold"] == 10


async def test_reports_are_owner_only(client, cashier):
    for path in ("/api/reports/summary", "/api/reports/monthly", "/api/reports/by-category", "/api/reports/top-products"):
        assert (await client.get(path, headers=cashier)).status_code == 403


async def test_monthly_returns_twelve_buckets(client, owner):
    monthly = (await client.get("/api/reports/monthly", headers=owner)).json()
    assert len(monthly) == 12
    assert [row["month"] for row in monthly][:3] == ["Jan", "Feb", "Mar"]


async def test_by_category_groups_through_the_product_lookup(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    dairy = await make_product(barcode="CAT-1", category="Dairy")
    rice = await make_product(barcode="CAT-2", category="Rice", buying_price=5.0, selling_price=10.0, discount_percentage=0.0)

    await _sell(client, cashier, dairy["id"], quantity=2)
    await _sell(client, cashier, rice["id"], quantity=3)

    rows = {row["category"]: row for row in (await client.get("/api/reports/by-category?days=30", headers=owner)).json()}
    assert rows["Dairy"]["revenue"] == 27.00
    assert rows["Rice"]["revenue"] == 30.00
    assert rows["Rice"]["profit"] == 15.00
    assert rows["Rice"]["units"] == 3


async def test_report_date_range_validation(client, owner):
    bad_format = await client.get("/api/reports/summary?start=01-01-2026&end=2026-02-01", headers=owner)
    assert bad_format.status_code == 400

    inverted = await client.get("/api/reports/summary?start=2026-03-01&end=2026-01-01", headers=owner)
    assert inverted.status_code == 400


# ----------------------------------------------------------------- sales history
async def test_sales_history_filters_by_payment_method_and_search(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product(stock_shelf=50)

    cash_sale = (
        await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "CASH"},
            headers=cashier,
        )
    ).json()
    await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "CARD"},
        headers=cashier,
    )

    all_sales = (await client.get("/api/sales", headers=cashier)).json()
    assert all_sales["total"] == 2

    cash_only = (await client.get("/api/sales?payment_method=CASH", headers=cashier)).json()
    assert cash_only["total"] == 1
    assert cash_only["items"][0]["payment_method"] == "CASH"

    by_receipt = (await client.get(f"/api/sales?search={cash_sale['receipt_number']}", headers=cashier)).json()
    assert by_receipt["total"] == 1

    by_item = (await client.get("/api/sales?search=Test Milk", headers=cashier)).json()
    assert by_item["total"] == 2


async def test_sales_stats_match_the_filtered_set(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product(stock_shelf=50)
    await _sell(client, cashier, product["id"], quantity=2)  # 27.00
    await _sell(client, cashier, product["id"], quantity=4)  # 54.00

    stats = (await client.get("/api/sales/stats?days=30", headers=cashier)).json()
    assert stats["transactions"] == 2
    assert stats["revenue"] == 81.00
    assert stats["profit"] == 21.00
    assert stats["items_sold"] == 6
    assert stats["average_basket"] == 40.50


async def test_sales_stats_are_zero_when_nothing_matches(client, cashier):
    stats = (await client.get("/api/sales/stats?days=1", headers=cashier)).json()
    assert stats == {
        "revenue": 0.0,
        "refunds": 0.0,
        "net_revenue": 0.0,
        "profit": 0.0,
        "transactions": 0,
        "returns": 0,
        "items_sold": 0,
        "average_basket": 0.0,
    }


async def test_receipt_lookup_by_number(client, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"])

    found = await client.get(f"/api/sales/receipt/{sale['receipt_number']}", headers=cashier)
    assert found.status_code == 200
    assert found.json()["id"] == sale["id"]

    assert (await client.get("/api/sales/receipt/REC-1900-00001", headers=cashier)).status_code == 404


async def test_sale_line_keeps_the_price_it_was_sold_at(client, owner, cashier, make_product):
    """Repricing a product must not rewrite historical profit."""
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=1)

    await client.put(f"/api/products/{product['id']}", json={"selling_price": 99.00}, headers=owner)

    stored = (await client.get(f"/api/sales/{sale['id']}", headers=cashier)).json()
    assert stored["items"][0]["unit_selling_price"] == 15.00
    assert stored["net_profit"] == sale["net_profit"]


# -------------------------------------------------------------------------- CRM
async def test_customer_phone_is_unique(client, owner):
    payload = {"name": "First Person", "phone": "+9477000111"}
    assert (await client.post("/api/customers", json=payload, headers=owner)).status_code == 201
    duplicate = await client.post("/api/customers", json={**payload, "name": "Second"}, headers=owner)
    assert duplicate.status_code == 409


async def test_customer_segments_filter_the_list(client, owner, database):
    created = (
        await client.post("/api/customers", json={"name": "Big Spender", "phone": "+9477000222"}, headers=owner)
    ).json()
    await client.post("/api/customers", json={"name": "Rare Visitor", "phone": "+9477000333"}, headers=owner)
    await database.customers.update_one(
        {"phone": "+9477000222"},
        {"$set": {"total_spend": 500.0, "total_visits": 20, "loyalty_points": 150}},
    )

    high = (await client.get("/api/customers?segment=HIGH_SPENDING", headers=owner)).json()
    assert [item["id"] for item in high["items"]] == [created["id"]]

    frequent = (await client.get("/api/customers?segment=FREQUENT_VISITORS", headers=owner)).json()
    assert frequent["total"] == 1

    unknown = await client.get("/api/customers?segment=NOPE", headers=owner)
    assert unknown.status_code == 400


async def test_cashier_can_create_but_not_edit_customers(client, cashier, owner):
    created = (
        await client.post("/api/customers", json={"name": "Walk In", "phone": "+9477000444"}, headers=cashier)
    ).json()
    assert (
        await client.put(f"/api/customers/{created['id']}", json={"name": "Edited"}, headers=cashier)
    ).status_code == 403
    assert (
        await client.put(f"/api/customers/{created['id']}", json={"name": "Edited"}, headers=owner)
    ).status_code == 200


# ----------------------------------------------------------------------- store
async def test_store_settings_round_trip(client, owner, cashier):
    updated = await client.put(
        "/api/store",
        json={"name": "Super Sale", "currency": "LKR", "tax_rate": 8.5},
        headers=owner,
    )
    assert updated.status_code == 200
    assert updated.json()["currency"] == "LKR"
    assert updated.json()["tax_rate"] == 8.5

    assert (await client.put("/api/store", json={"tax_rate": 150}, headers=owner)).status_code == 422
    assert (await client.put("/api/store", json={"tax_rate": 5}, headers=cashier)).status_code == 403
    # Cashiers still read settings: the POS needs the currency and tax rate.
    assert (await client.get("/api/store", headers=cashier)).status_code == 200


async def test_health_needs_no_authentication(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_bad_credentials_are_rejected(client):
    assert (
        await client.post("/api/auth/login", json={"username": "owner", "password": "wrong"})
    ).status_code == 401
    assert (
        await client.post("/api/auth/login", json={"username": "ghost", "password": "whatever"})
    ).status_code == 401


async def test_a_tampered_token_is_rejected(client):
    response = await client.get("/api/products", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
