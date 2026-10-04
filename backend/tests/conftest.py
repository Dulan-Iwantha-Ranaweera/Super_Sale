"""Shared pytest fixtures.

The suite talks to a real MongoDB, but to a dedicated `supersale_test`
database that is wiped between tests — the atomicity and concurrency
guarantees cannot be proven against a mock.
"""

from __future__ import annotations

import os

# Must be set before `app.config` is imported, so the settings cache picks them
# up. Environment variables take precedence over backend/.env.
import tempfile

os.environ["DB_NAME"] = "supersale_test"
os.environ["JWT_SECRET"] = "test-secret-not-for-production"
# Trained models go to a scratch directory, so a test run can never overwrite
# the model the running store is using.
os.environ["IPF_MODEL_DIR"] = os.path.join(tempfile.gettempdir(), "supersale_test_models")

import pytest  # noqa: E402
from bson import ObjectId  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import close_mongo_connection, connect_to_mongo  # noqa: E402
from app.main import app  # noqa: E402

WIPED_COLLECTIONS = ("products", "sales", "customers", "counters", "stock_audits")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database():
    settings = get_settings()
    # Hard guard: never let the suite point at a real database.
    assert settings.db_name.endswith("_test"), f"refusing to run against {settings.db_name!r}"
    db = await connect_to_mongo()
    yield db
    await db.client.drop_database(settings.db_name)
    await close_mongo_connection()


@pytest_asyncio.fixture(loop_scope="session")
async def clean_db(database):
    for name in WIPED_COLLECTIONS:
        await database[name].delete_many({})
    await database.stores.update_one(
        {"_id": get_settings().store_id},
        {"$set": {"tax_rate": 0.0, "loyalty_spend_per_point": 10.0, "currency": "LKR"}},
    )
    return database


@pytest_asyncio.fixture(loop_scope="session")
async def client(clean_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client


async def _token(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture(loop_scope="session")
async def owner(client):
    """Request headers for the seeded owner account."""
    token = await _token(client, "owner", "owner123")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="session")
async def cashier(client):
    token = await _token(client, "cashier", "cashier123")
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
def product_payload():
    """A product whose numbers make the expected maths easy to read."""

    def build(**overrides):
        payload = {
            "barcode": "TEST-0001",
            "name": "Test Milk 1L",
            "category": "Dairy",
            "buying_price": 10.00,
            "market_price": 20.00,
            "selling_price": 15.00,
            "discount_percentage": 10.0,
            "stock_shelf": 50,
            "stock_warehouse": 100,
            "reorder_threshold": 20,
        }
        payload.update(overrides)
        return payload

    return build


@pytest_asyncio.fixture(loop_scope="session")
async def make_product(client, owner, product_payload):
    """Create a product through the API and return the response body."""

    async def create(**overrides):
        response = await client.post("/api/products", json=product_payload(**overrides), headers=owner)
        assert response.status_code == 201, response.text
        return response.json()

    return create


@pytest.fixture
def clean_model_dir():
    """Start each model-lifecycle test with no trained artifact on disk."""
    from app.ml import model as ml_model

    directory = ml_model.model_dir()
    assert "test" in directory.lower(), f"refusing to wipe {directory!r}"
    os.makedirs(directory, exist_ok=True)
    for name in os.listdir(directory):
        os.remove(os.path.join(directory, name))
    yield directory


@pytest_asyncio.fixture(loop_scope="session")
async def sales_history(client, owner, clean_db, make_product):
    """Insert a synthetic trading history long enough to train on.

    Written straight to the collection rather than through checkout: the model
    needs several months of days, and a few thousand real checkouts would make
    the suite crawl. The shape is what matters — per-product demand that varies
    day to day and drifts over time, which is the signal the model learns.
    """
    import random
    from datetime import timedelta

    from app.database import utcnow

    rng = random.Random(20261002)
    days = 140

    products = []
    for index in range(6):
        products.append(
            await make_product(
                barcode=f"HIST-{index}",
                name=f"History Product {index}",
                category="Dairy" if index % 2 else "Snacks",
                buying_price=50.0 + index * 10,
                market_price=120.0 + index * 10,
                selling_price=100.0 + index * 10,
                discount_percentage=0.0,
                stock_shelf=500,
                stock_warehouse=500,
                reorder_threshold=20,
            )
        )

    now = utcnow()
    documents = []
    sequence = 0
    for day_offset in range(days, 0, -1):
        when = now - timedelta(days=day_offset, hours=rng.randint(0, 10))
        for index, product in enumerate(products):
            # A rising line, a falling line, and steady ones in between.
            drift = 1.0 + (index - 2) * 0.004 * (days - day_offset)
            rate = max(0.2, (1.5 + index * 0.4) * max(0.2, drift))
            quantity = max(0, int(rng.gauss(rate, 1.0)))
            if quantity == 0:
                continue
            sequence += 1
            selling = product["selling_price"]
            buying = product["buying_price"]
            documents.append(
                {
                    "receipt_number": f"HIST-{sequence:06d}",
                    "type": "SALE",
                    "returned": {},
                    "cashier_id": "cashier",
                    "customer_id": None,
                    "customer_name": None,
                    "items": [
                        {
                            "product_id": ObjectId(product["id"]),
                            "barcode": product["barcode"],
                            "name": product["name"],
                            "quantity": quantity,
                            "unit_buying_price": buying,
                            "unit_selling_price": selling,
                            "discount_percentage": 0.0,
                            "line_total": round(selling * quantity, 2),
                            "line_profit": round((selling - buying) * quantity, 2),
                        }
                    ],
                    "subtotal": round(selling * quantity, 2),
                    "discount_total": 0.0,
                    "tax_amount": 0.0,
                    "grand_total": round(selling * quantity, 2),
                    "net_profit": round((selling - buying) * quantity, 2),
                    "payment_method": "CASH",
                    "payment_breakdown": None,
                    "amount_tendered": None,
                    "change_due": None,
                    "loyalty_points_earned": 0,
                    "timestamp": when,
                }
            )

    await clean_db.sales.insert_many(documents)
    return products


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: tests that exercise concurrency")
