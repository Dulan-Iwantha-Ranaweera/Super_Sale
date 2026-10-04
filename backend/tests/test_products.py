"""Catalogue CRUD, validation bounds, role gating and guarded stock movement."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_requires_authentication(client):
    assert (await client.get("/api/products")).status_code == 401


async def test_create_returns_derived_financials(client, owner, product_payload):
    response = await client.post("/api/products", json=product_payload(), headers=owner)
    assert response.status_code == 201

    body = response.json()
    assert body["effective_selling_price"] == 13.50
    assert body["unit_profit"] == 3.50
    assert body["margin_percent"] == 25.93
    assert body["stock_total"] == 150
    assert body["status"] == "IN_STOCK"
    # The id must be a plain string, never a serialised ObjectId object.
    assert isinstance(body["id"], str)


async def test_barcode_must_be_unique(client, owner, make_product, product_payload):
    await make_product()
    duplicate = await client.post(
        "/api/products", json=product_payload(name="Another product"), headers=owner
    )
    assert duplicate.status_code == 409
    assert "already belongs" in duplicate.json()["detail"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("discount_percentage", 150),
        ("discount_percentage", -1),
        ("buying_price", -5),
        ("stock_shelf", -1),
        ("reorder_threshold", -1),
        ("barcode", "has spaces"),
        ("name", ""),
    ],
)
async def test_rejects_out_of_bounds_input(client, owner, product_payload, field, value):
    response = await client.post("/api/products", json=product_payload(**{field: value}), headers=owner)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


async def test_cashier_cannot_write_to_the_catalogue(client, cashier, product_payload, make_product):
    created = await make_product()

    assert (await client.post("/api/products", json=product_payload(barcode="X"), headers=cashier)).status_code == 403
    assert (
        await client.put(f"/api/products/{created['id']}", json={"selling_price": 1}, headers=cashier)
    ).status_code == 403
    assert (await client.delete(f"/api/products/{created['id']}", headers=cashier)).status_code == 403
    # Reading stays available to cashiers: the POS needs it.
    assert (await client.get("/api/products", headers=cashier)).status_code == 200


async def test_status_reflects_the_reorder_threshold(client, owner, make_product):
    low = await make_product(barcode="LOW-1", stock_shelf=5, stock_warehouse=5, reorder_threshold=20)
    assert low["status"] == "LOW_STOCK"

    out = await make_product(barcode="OUT-1", stock_shelf=0, stock_warehouse=0)
    assert out["status"] == "OUT_OF_STOCK"

    response = await client.get("/api/products?stock_status=LOW_STOCK", headers=owner)
    names = [item["barcode"] for item in response.json()["items"]]
    assert "LOW-1" in names and "OUT-1" not in names

    response = await client.get("/api/products?stock_status=OUT_OF_STOCK", headers=owner)
    assert [item["barcode"] for item in response.json()["items"]] == ["OUT-1"]


async def test_search_matches_name_or_barcode(client, owner, make_product):
    await make_product(barcode="AAA-111", name="Jasmine Rice 5kg")
    await make_product(barcode="BBB-222", name="Laundry Powder")

    by_name = await client.get("/api/products?search=jasmine", headers=owner)
    assert [item["barcode"] for item in by_name.json()["items"]] == ["AAA-111"]

    by_barcode = await client.get("/api/products?search=BBB", headers=owner)
    assert [item["name"] for item in by_barcode.json()["items"]] == ["Laundry Powder"]


async def test_update_recalculates_profit(client, owner, make_product):
    created = await make_product()
    response = await client.put(
        f"/api/products/{created['id']}",
        json={"selling_price": 20.00, "discount_percentage": 0.0},
        headers=owner,
    )
    assert response.status_code == 200
    assert response.json()["unit_profit"] == 10.00
    assert response.json()["effective_selling_price"] == 20.00


async def test_stock_adjust_cannot_go_negative(client, owner, make_product):
    created = await make_product(stock_shelf=5)

    ok = await client.patch(
        f"/api/products/{created['id']}/stock-adjust", json={"delta_shelf": -5}, headers=owner
    )
    assert ok.status_code == 200 and ok.json()["stock_shelf"] == 0

    rejected = await client.patch(
        f"/api/products/{created['id']}/stock-adjust", json={"delta_shelf": -1}, headers=owner
    )
    assert rejected.status_code == 409
    assert "below zero" in rejected.json()["detail"]


async def test_stock_adjust_writes_an_audit_entry(client, owner, make_product, database):
    created = await make_product()
    await client.patch(
        f"/api/products/{created['id']}/stock-adjust",
        json={"delta_warehouse": 25, "reason": "Supplier delivery"},
        headers=owner,
    )
    audit = await database.stock_audits.find_one({"reason": "Supplier delivery"})
    assert audit is not None
    assert audit["user"] == "owner"
    assert audit["warehouse_after"] == audit["warehouse_before"] + 25


async def test_transfer_moves_stock_and_respects_availability(client, owner, make_product):
    created = await make_product(stock_shelf=10, stock_warehouse=30)

    moved = await client.post(f"/api/products/{created['id']}/transfer", json={"quantity": 25}, headers=owner)
    assert moved.status_code == 200
    assert moved.json()["stock_shelf"] == 35
    assert moved.json()["stock_warehouse"] == 5
    # Total stock is conserved by the move.
    assert moved.json()["stock_total"] == created["stock_total"]

    too_many = await client.post(f"/api/products/{created['id']}/transfer", json={"quantity": 6}, headers=owner)
    assert too_many.status_code == 409
    assert "available in the warehouse" in too_many.json()["detail"]


async def test_lookup_by_barcode_for_the_scanner(client, cashier, make_product):
    created = await make_product(barcode="SCAN-9999")
    found = await client.get("/api/products/barcode/SCAN-9999", headers=cashier)
    assert found.status_code == 200 and found.json()["id"] == created["id"]
    assert (await client.get("/api/products/barcode/NOPE", headers=cashier)).status_code == 404


async def test_delete_is_a_soft_delete(client, owner, make_product):
    created = await make_product()
    assert (await client.delete(f"/api/products/{created['id']}", headers=owner)).status_code == 204

    listed = await client.get("/api/products", headers=owner)
    assert created["id"] not in [item["id"] for item in listed.json()["items"]]

    # Still retrievable by id, so historical sales keep resolving.
    assert (await client.get(f"/api/products/{created['id']}", headers=owner)).status_code == 200


async def test_invalid_object_id_is_a_clean_422(client, owner):
    response = await client.get("/api/products/not-an-object-id", headers=owner)
    assert response.status_code == 422
    assert "not a valid identifier" in response.json()["detail"]
