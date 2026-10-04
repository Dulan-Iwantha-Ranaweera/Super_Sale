"""Brands: the same item stocked under several names."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_brand_round_trips_and_is_optional(client, owner, make_product):
    branded = await make_product(barcode="BR-1", name="Fresh Milk 1L", brand="Ambewela")
    assert branded["brand"] == "Ambewela"

    loose = await make_product(barcode="BR-2", name="Tomato 1kg", brand=None)
    assert loose["brand"] is None


async def test_the_same_item_can_be_stocked_under_several_brands(client, owner, make_product):
    for index, brand in enumerate(("Anchor", "Highland", "Ratthi")):
        await make_product(
            barcode=f"MILK-{index}",
            name="Full Cream Milk Powder 400g",
            brand=brand,
        )

    listed = (await client.get("/api/products?search=Milk Powder", headers=owner)).json()
    assert listed["total"] == 3
    assert {item["brand"] for item in listed["items"]} == {"Anchor", "Highland", "Ratthi"}
    # Same product name, three separate SKUs with their own stock and pricing.
    assert len({item["id"] for item in listed["items"]}) == 3


async def test_products_can_be_filtered_by_brand(client, owner, make_product):
    await make_product(barcode="F-1", name="Cream Cracker 190g", brand="Maliban")
    await make_product(barcode="F-2", name="Marie Biscuit 400g", brand="Munchee")
    await make_product(barcode="F-3", name="Cream Cracker 190g", brand="Munchee")

    munchee = (await client.get("/api/products?brand=Munchee", headers=owner)).json()
    assert munchee["total"] == 2
    assert all(item["brand"] == "Munchee" for item in munchee["items"])

    assert (await client.get("/api/products?brand=ALL", headers=owner)).json()["total"] == 3


async def test_search_matches_the_brand(client, owner, make_product):
    await make_product(barcode="S-1", name="Ceylon Black Tea 400g", brand="Dilmah")
    await make_product(barcode="S-2", name="Ceylon Black Tea 400g", brand="Zesta")

    found = (await client.get("/api/products?search=dilmah", headers=owner)).json()
    assert found["total"] == 1
    assert found["items"][0]["brand"] == "Dilmah"


async def test_brands_endpoint_lists_distinct_brands(client, owner, make_product):
    await make_product(barcode="B-1", brand="Anchor")
    await make_product(barcode="B-2", brand="Highland")
    await make_product(barcode="B-3", brand="Anchor")
    await make_product(barcode="B-4", brand=None)

    brands = (await client.get("/api/products/brands", headers=owner)).json()
    assert brands == ["Anchor", "Highland"]


async def test_products_can_be_sorted_by_brand(client, owner, make_product):
    await make_product(barcode="O-1", brand="Zesta")
    await make_product(barcode="O-2", brand="Anchor")

    ascending = (await client.get("/api/products?sort_by=brand&sort_dir=asc", headers=owner)).json()
    assert [item["brand"] for item in ascending["items"]] == ["Anchor", "Zesta"]


async def test_receipts_record_the_brand_with_the_item_name(client, owner, cashier, make_product):
    """A receipt line must say which brand was sold, and keep saying it."""
    product = await make_product(name="Fresh Milk 1L", brand="Ambewela")
    sale = (
        await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 1}]},
            headers=cashier,
        )
    ).json()
    assert sale["items"][0]["name"] == "Ambewela Fresh Milk 1L"

    # Rebranding the product later must not rewrite the historical receipt.
    await client.put(f"/api/products/{product['id']}", json={"brand": "Highland"}, headers=owner)
    stored = (await client.get(f"/api/sales/{sale['id']}", headers=cashier)).json()
    assert stored["items"][0]["name"] == "Ambewela Fresh Milk 1L"


async def test_an_unbranded_item_has_no_leading_space_on_the_receipt(client, cashier, make_product):
    product = await make_product(name="Tomato 1kg", brand=None)
    sale = (
        await client.post(
            "/api/sales/checkout",
            json={"items": [{"product_id": product["id"], "quantity": 1}]},
            headers=cashier,
        )
    ).json()
    assert sale["items"][0]["name"] == "Tomato 1kg"


async def test_brand_can_be_cleared(client, owner, make_product):
    product = await make_product(brand="Anchor")
    updated = await client.put(f"/api/products/{product['id']}", json={"brand": None}, headers=owner)
    assert updated.status_code == 200
    assert updated.json()["brand"] is None
