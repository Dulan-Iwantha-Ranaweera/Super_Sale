"""POS checkout: totals, payment rules, stock atomicity and compensating rollback."""

import asyncio

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _set_tax_rate(client, owner, rate):
    response = await client.put("/api/store", json={"tax_rate": rate}, headers=owner)
    assert response.status_code == 200


async def test_checkout_totals_discount_and_tax(client, owner, cashier, make_product):
    product = await make_product()  # sells 15.00 at 10% off, costs 10.00
    await _set_tax_rate(client, owner, 5.0)

    response = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 4}], "payment_method": "CASH", "amount_tendered": 100},
        headers=cashier,
    )
    assert response.status_code == 201, response.text

    sale = response.json()
    assert sale["subtotal"] == 60.00  # 4 x 15.00 before discount
    assert sale["discount_total"] == 6.00  # 10% of 60.00
    assert sale["tax_amount"] == 2.70  # 5% of 54.00
    assert sale["grand_total"] == 56.70
    assert sale["net_profit"] == 14.00  # 4 x (13.50 - 10.00)
    assert sale["change_due"] == 43.30
    assert sale["receipt_number"].startswith("REC-")
    assert sale["cashier_id"] == "cashier"


async def test_checkout_decrements_shelf_stock_only(client, cashier, owner, make_product):
    product = await make_product(stock_shelf=50, stock_warehouse=100)
    await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 4}]},
        headers=cashier,
    )
    after = (await client.get(f"/api/products/{product['id']}", headers=owner)).json()
    assert after["stock_shelf"] == 46
    assert after["stock_warehouse"] == 100


async def test_repeated_scans_of_one_product_merge_into_a_single_line(client, cashier, make_product):
    product = await make_product()
    response = await client.post(
        "/api/sales/checkout",
        json={
            "items": [
                {"product_id": product["id"], "quantity": 1},
                {"product_id": product["id"], "quantity": 2},
            ]
        },
        headers=cashier,
    )
    sale = response.json()
    assert len(sale["items"]) == 1
    assert sale["items"][0]["quantity"] == 3


async def test_line_discount_overrides_the_product_discount(client, cashier, owner, make_product):
    product = await make_product()  # product discount is 10%
    await _set_tax_rate(client, owner, 0.0)

    response = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 1, "discount_percentage": 50}]},
        headers=cashier,
    )
    sale = response.json()
    assert sale["items"][0]["discount_percentage"] == 50.0
    assert sale["grand_total"] == 7.50
    assert sale["net_profit"] == -2.50  # selling below cost is allowed, and recorded honestly


async def test_prices_come_from_the_database_not_the_client(client, cashier, make_product):
    """A tampered client price must be ignored: the server re-reads the catalogue."""
    product = await make_product()
    response = await client.post(
        "/api/sales/checkout",
        json={
            "items": [{"product_id": product["id"], "quantity": 1, "unit_selling_price": 0.01}],
            "payment_method": "CASH",
        },
        headers=cashier,
    )
    assert response.status_code == 201
    assert response.json()["items"][0]["unit_selling_price"] == 15.00


async def test_insufficient_stock_returns_409_and_changes_nothing(client, cashier, owner, make_product):
    product = await make_product(stock_shelf=3)
    response = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 99}]},
        headers=cashier,
    )
    assert response.status_code == 409
    assert "Insufficient stock" in response.json()["detail"]

    after = (await client.get(f"/api/products/{product['id']}", headers=owner)).json()
    assert after["stock_shelf"] == 3


async def test_partial_failure_rolls_the_earlier_lines_back(client, cashier, owner, make_product):
    """The core compensating-rollback guarantee: no stock lost to a failed sale."""
    plenty = await make_product(barcode="ROLL-1", stock_shelf=50)
    scarce = await make_product(barcode="ROLL-2", stock_shelf=2)

    response = await client.post(
        "/api/sales/checkout",
        json={
            "items": [
                {"product_id": plenty["id"], "quantity": 5},
                {"product_id": scarce["id"], "quantity": 50},
            ]
        },
        headers=cashier,
    )
    assert response.status_code == 409

    first = (await client.get(f"/api/products/{plenty['id']}", headers=owner)).json()
    second = (await client.get(f"/api/products/{scarce['id']}", headers=owner)).json()
    assert first["stock_shelf"] == 50, "the successful line was not rolled back"
    assert second["stock_shelf"] == 2


async def test_no_sale_document_is_written_when_checkout_fails(client, cashier, make_product, database):
    product = await make_product(stock_shelf=1)
    before = await database.sales.count_documents({})
    await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 99}]},
        headers=cashier,
    )
    assert await database.sales.count_documents({}) == before


@pytest.mark.slow
async def test_concurrent_checkouts_never_oversell(client, cashier, owner, make_product):
    """20 cashiers race for 10 units: exactly 10 win, stock lands on zero."""
    product = await make_product(stock_shelf=10, stock_warehouse=0)

    async def buy():
        response = await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 1}]},
            headers=cashier,
        )
        return response.status_code

    results = await asyncio.gather(*(buy() for _ in range(20)))

    assert results.count(201) == 10
    assert results.count(409) == 10
    after = (await client.get(f"/api/products/{product['id']}", headers=owner)).json()
    assert after["stock_shelf"] == 0


@pytest.mark.slow
async def test_concurrent_receipt_numbers_are_unique(client, cashier, make_product):
    product = await make_product(stock_shelf=15)

    async def buy():
        response = await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 1}]},
            headers=cashier,
        )
        return response.json().get("receipt_number")

    numbers = [number for number in await asyncio.gather(*(buy() for _ in range(15))) if number]
    assert len(numbers) == 15
    assert len(set(numbers)) == 15, "the atomic counter produced a duplicate receipt number"


async def test_split_payment_must_match_the_total(client, cashier, owner, make_product):
    product = await make_product()
    await _set_tax_rate(client, owner, 0.0)

    wrong = await client.post(
        "/api/sales/checkout",
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "SPLIT",
            "payment_breakdown": {"cash": 1.00, "card": 1.00},
        },
        headers=cashier,
    )
    assert wrong.status_code == 400
    assert "does not match" in wrong.json()["detail"]

    missing = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 1}], "payment_method": "SPLIT"},
        headers=cashier,
    )
    assert missing.status_code == 400

    correct = await client.post(
        "/api/sales/checkout",
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "SPLIT",
            "payment_breakdown": {"cash": 10.00, "card": 3.50},
        },
        headers=cashier,
    )
    assert correct.status_code == 201
    assert correct.json()["payment_breakdown"] == {"cash": 10.00, "card": 3.50}


async def test_cash_tendered_below_the_total_is_rejected(client, cashier, owner, make_product):
    product = await make_product()
    await _set_tax_rate(client, owner, 0.0)
    response = await client.post(
        "/api/sales/checkout",
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "CASH",
            "amount_tendered": 1.00,
        },
        headers=cashier,
    )
    assert response.status_code == 400
    assert "less than the total" in response.json()["detail"]


async def test_customer_visit_spend_and_loyalty_accrue(client, cashier, owner, make_product):
    product = await make_product()
    await _set_tax_rate(client, owner, 0.0)
    customer = (
        await client.post("/api/customers", json={"name": "Loyal Shopper", "phone": "+9400011122"}, headers=owner)
    ).json()

    sale = (
        await client.post(
            "/api/sales/checkout",
            json={
                "items": [{"product_id": product["id"], "quantity": 4}],  # 4 x 13.50 = 54.00
                "customer_id": customer["id"],
                "payment_method": "CARD",
            },
            headers=cashier,
        )
    ).json()

    assert sale["grand_total"] == 54.00
    assert sale["loyalty_points_earned"] == 5  # one point per 10.00 spent
    assert sale["customer_name"] == "Loyal Shopper"

    after = (await client.get(f"/api/customers/{customer['id']}", headers=owner)).json()
    assert after["total_visits"] == 1
    assert after["total_spend"] == 54.00
    assert after["loyalty_points"] == 5
    assert after["last_visit"] is not None


async def test_checkout_rejects_an_unknown_customer(client, cashier, make_product):
    product = await make_product()
    response = await client.post(
        "/api/sales/checkout",
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "customer_id": "0123456789abcdef01234567",
        },
        headers=cashier,
    )
    assert response.status_code == 404


async def test_checkout_rejects_an_empty_or_invalid_cart(client, cashier, make_product):
    product = await make_product()
    assert (await client.post("/api/sales/checkout", json={"items": []}, headers=cashier)).status_code == 422
    assert (
        await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 0}]},
            headers=cashier,
        )
    ).status_code == 422


async def test_a_deactivated_product_cannot_be_sold(client, owner, cashier, make_product):
    product = await make_product()
    await client.delete(f"/api/products/{product['id']}", headers=owner)
    response = await client.post(
        "/api/sales/checkout",
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
        headers=cashier,
    )
    assert response.status_code == 404
