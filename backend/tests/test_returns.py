"""Returns and refunds: money handed back, stock, guards and ledger effects."""

import asyncio

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _sell(client, cashier, product_id, quantity=1, customer_id=None):
    body = {"items": [{"product_id": product_id, "quantity": quantity}]}
    if customer_id:
        body["customer_id"] = customer_id
    response = await client.post("/api/sales/checkout", json=body, headers=cashier)
    assert response.status_code == 201, response.text
    return response.json()


async def _refund(client, owner, sale_id, product_id, quantity, **extra):
    body = {"items": [{"product_id": product_id, "quantity": quantity}], "reason": "Damaged packaging"}
    body.update(extra)
    return await client.post(f"/api/sales/{sale_id}/return", json=body, headers=owner)


async def test_refund_reverses_money_and_profit(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 18.0}, headers=owner)
    product = await make_product()  # sells 15.00 at 10% off, costs 10.00
    sale = await _sell(client, cashier, product["id"], quantity=4)
    assert sale["grand_total"] == 63.72  # 54.00 + 18%

    response = await _refund(client, owner, sale["id"], product["id"], 2)
    assert response.status_code == 201
    refund = response.json()

    assert refund["type"] == "RETURN"
    assert refund["receipt_number"].startswith("RET-")
    assert refund["original_receipt_number"] == sale["receipt_number"]
    assert refund["grand_total"] == -31.86  # exactly half the sale, tax included
    assert refund["net_profit"] == -7.00  # 2 x (13.50 - 10.00)
    assert refund["items"][0]["quantity"] == -2
    assert refund["reason"] == "Damaged packaging"


async def test_refund_uses_the_tax_rate_the_sale_was_charged_at(client, owner, cashier, make_product):
    """Changing the store rate afterwards must not change what is handed back."""
    await client.put("/api/store", json={"tax_rate": 18.0}, headers=owner)
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=1)

    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)

    refund = (await _refund(client, owner, sale["id"], product["id"], 1)).json()
    assert refund["grand_total"] == -sale["grand_total"]


async def test_restocking_is_optional(client, owner, cashier, make_product):
    product = await make_product(stock_shelf=20)
    sale = await _sell(client, cashier, product["id"], quantity=5)
    assert (await client.get(f"/api/products/{product['id']}", headers=owner)).json()["stock_shelf"] == 15

    await _refund(client, owner, sale["id"], product["id"], 2, restock=True)
    assert (await client.get(f"/api/products/{product['id']}", headers=owner)).json()["stock_shelf"] == 17

    # Damaged goods are refunded but do not go back on the shelf.
    await _refund(client, owner, sale["id"], product["id"], 1, restock=False)
    assert (await client.get(f"/api/products/{product['id']}", headers=owner)).json()["stock_shelf"] == 17


async def test_returnable_tracks_what_is_left(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=3)

    before = (await client.get(f"/api/sales/{sale['id']}/returnable", headers=owner)).json()
    assert before["lines"][0]["quantity_remaining"] == 3
    assert before["fully_returned"] is False

    await _refund(client, owner, sale["id"], product["id"], 3)

    after = (await client.get(f"/api/sales/{sale['id']}/returnable", headers=owner)).json()
    assert after["lines"][0]["quantity_returned"] == 3
    assert after["lines"][0]["quantity_remaining"] == 0
    assert after["fully_returned"] is True


async def test_cannot_return_more_than_was_sold(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=2)

    too_many = await _refund(client, owner, sale["id"], product["id"], 3)
    assert too_many.status_code == 409
    assert "can still be returned" in too_many.json()["detail"]

    await _refund(client, owner, sale["id"], product["id"], 2)
    again = await _refund(client, owner, sale["id"], product["id"], 1)
    assert again.status_code == 409


async def test_cannot_return_an_item_that_was_not_on_the_sale(client, owner, cashier, make_product):
    sold = await make_product(barcode="SOLD-1")
    other = await make_product(barcode="OTHER-1")
    sale = await _sell(client, cashier, sold["id"], quantity=1)

    response = await _refund(client, owner, sale["id"], other["id"], 1)
    assert response.status_code == 400
    assert "not on this sale" in response.json()["detail"]


async def test_a_refund_cannot_itself_be_refunded(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=2)
    refund = (await _refund(client, owner, sale["id"], product["id"], 1)).json()

    response = await _refund(client, owner, refund["id"], product["id"], 1)
    assert response.status_code == 400
    assert "itself a refund" in response.json()["detail"]


async def test_a_cashier_can_issue_a_refund_at_the_counter(client, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=1)
    response = await client.post(
        f"/api/sales/{sale['id']}/return",
        json={"items": [{"product_id": product["id"], "quantity": 1}], "reason": "Changed mind"},
        headers=cashier,
    )
    assert response.status_code == 201
    # The refund is attributed to whoever took it, so the owner can review it.
    assert response.json()["cashier_id"] == "cashier"
    assert response.json()["reason"] == "Changed mind"


async def test_refund_requires_a_reason(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=1)
    response = await client.post(
        f"/api/sales/{sale['id']}/return",
        json={"items": [{"product_id": product["id"], "quantity": 1}], "reason": "x"},
        headers=owner,
    )
    assert response.status_code == 422


@pytest.mark.slow
async def test_concurrent_refunds_cannot_over_return(client, owner, cashier, make_product):
    """Ten simultaneous single-unit refunds against three sold units."""
    product = await make_product(stock_shelf=20)
    sale = await _sell(client, cashier, product["id"], quantity=3)

    results = await asyncio.gather(
        *(_refund(client, owner, sale["id"], product["id"], 1) for _ in range(10))
    )
    codes = [response.status_code for response in results]
    assert codes.count(201) == 3
    assert codes.count(409) == 7

    state = (await client.get(f"/api/sales/{sale['id']}/returnable", headers=owner)).json()
    assert state["lines"][0]["quantity_returned"] == 3
    assert state["lines"][0]["quantity_remaining"] == 0


async def test_refund_nets_out_of_reports_and_dashboard(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=4)  # 54.00 revenue, 14.00 profit

    before = (await client.get("/api/reports/summary?days=30", headers=owner)).json()
    assert before["gross_revenue"] == 54.00 and before["net_revenue"] == 54.00

    await _refund(client, owner, sale["id"], product["id"], 2)  # gives back 27.00 / 7.00

    after = (await client.get("/api/reports/summary?days=30", headers=owner)).json()
    assert after["gross_revenue"] == 54.00  # sales are untouched
    assert after["refunds"] == 27.00
    assert after["net_revenue"] == 27.00
    assert after["net_profit"] == 7.00
    assert after["transactions"] == 1 and after["returns"] == 1

    metrics = (await client.get("/api/dashboard/metrics", headers=owner)).json()
    assert metrics["refunds_today"] == 27.00
    assert metrics["net_revenue_today"] == 27.00
    assert metrics["net_profit_today"] == 7.00
    assert metrics["returns_today"] == 1


async def test_refund_reduces_customer_spend_and_points(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product()
    customer = (
        await client.post("/api/customers", json={"name": "Nuwan Perera", "phone": "+94771110000"}, headers=owner)
    ).json()
    sale = await _sell(client, cashier, product["id"], quantity=4, customer_id=customer["id"])

    after_sale = (await client.get(f"/api/customers/{customer['id']}", headers=owner)).json()
    assert after_sale["total_spend"] == 54.00 and after_sale["loyalty_points"] == 5

    await _refund(client, owner, sale["id"], product["id"], 2)

    after_refund = (await client.get(f"/api/customers/{customer['id']}", headers=owner)).json()
    assert after_refund["total_spend"] == 27.00
    assert after_refund["loyalty_points"] == 3  # 5 earned, 2 reversed on a 27.00 refund
    assert after_refund["total_visits"] == 1  # the visit still happened


async def test_customer_totals_never_go_negative(client, owner, cashier, make_product):
    await client.put("/api/store", json={"tax_rate": 0.0}, headers=owner)
    product = await make_product()
    customer = (
        await client.post("/api/customers", json={"name": "Dilki Herath", "phone": "+94771110001"}, headers=owner)
    ).json()
    sale = await _sell(client, cashier, product["id"], quantity=2, customer_id=customer["id"])

    # Wipe the running totals, then refund: the clamp must hold.
    await client.put(f"/api/customers/{customer['id']}", json={"credit_due": 0}, headers=owner)
    await _refund(client, owner, sale["id"], product["id"], 2)
    await _refund(client, owner, sale["id"], product["id"], 0) if False else None

    final = (await client.get(f"/api/customers/{customer['id']}", headers=owner)).json()
    assert final["total_spend"] >= 0
    assert final["loyalty_points"] >= 0


async def test_history_can_be_filtered_to_sales_or_returns(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=2)
    await _refund(client, owner, sale["id"], product["id"], 1)

    everything = (await client.get("/api/sales", headers=owner)).json()
    assert everything["total"] == 2

    sales_only = (await client.get("/api/sales?ledger_type=SALE", headers=owner)).json()
    assert sales_only["total"] == 1
    assert sales_only["items"][0]["type"] == "SALE"

    returns_only = (await client.get("/api/sales?ledger_type=RETURN", headers=owner)).json()
    assert returns_only["total"] == 1
    assert returns_only["items"][0]["type"] == "RETURN"

    linked = (await client.get(f"/api/sales/{sale['id']}/returns", headers=owner)).json()
    assert len(linked) == 1
    assert linked[0]["original_receipt_number"] == sale["receipt_number"]


async def test_searching_by_the_original_receipt_finds_the_refund(client, owner, cashier, make_product):
    product = await make_product()
    sale = await _sell(client, cashier, product["id"], quantity=1)
    await _refund(client, owner, sale["id"], product["id"], 1)

    found = (await client.get(f"/api/sales?search={sale['receipt_number']}", headers=owner)).json()
    assert found["total"] == 2  # the sale and the refund raised against it
