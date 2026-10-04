"""Motor (async MongoDB) setup, index creation and startup bootstrapping."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument

from .config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def connect_to_mongo() -> AsyncIOMotorDatabase:
    global _client, _db
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongo_uri, uuidRepresentation="standard", tz_aware=True)
    _db = _client[settings.db_name]
    # Fail fast and loudly if MongoDB is unreachable, rather than on the first query.
    await _client.admin.command("ping")
    await ensure_indexes(_db)
    await ensure_store(_db)
    await ensure_default_users(_db)
    return _db


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:  # pragma: no cover - guarded by the lifespan handler
        raise RuntimeError("Database is not initialised. Did the app lifespan run?")
    return _db


async def _drop_stale_text_index(collection, keep: str) -> None:
    """MongoDB allows one text index per collection.

    When the indexed fields change the create fails with IndexOptionsConflict,
    so the superseded index is dropped first. Named rather than blanket-dropped
    so an unrelated index is never removed.
    """
    try:
        existing = await collection.index_information()
    except Exception:  # pragma: no cover - collection may not exist yet
        return
    for name, spec in existing.items():
        if name == keep:
            continue
        if any(field == "_fts" for field, _ in spec.get("key", [])):
            await collection.drop_index(name)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await _drop_stale_text_index(db.products, "text_name_brand_barcode")
    await db.products.create_indexes(
        [
            IndexModel([("barcode", ASCENDING)], unique=True, name="uniq_barcode"),
            IndexModel([("category", ASCENDING)], name="idx_category"),
            IndexModel([("brand", ASCENDING)], name="idx_brand"),
            IndexModel([("is_active", ASCENDING)], name="idx_is_active"),
            IndexModel(
                [("name", "text"), ("brand", "text"), ("barcode", "text")],
                name="text_name_brand_barcode",
            ),
        ]
    )
    await db.sales.create_indexes(
        [
            IndexModel([("receipt_number", ASCENDING)], unique=True, name="uniq_receipt"),
            IndexModel([("timestamp", DESCENDING)], name="idx_timestamp"),
            IndexModel([("customer_id", ASCENDING)], name="idx_customer"),
            IndexModel([("items.product_id", ASCENDING)], name="idx_items_product"),
            IndexModel([("type", ASCENDING), ("timestamp", DESCENDING)], name="idx_type_timestamp"),
            IndexModel([("original_sale_id", ASCENDING)], name="idx_original_sale"),
        ]
    )
    await db.customers.create_indexes(
        [
            IndexModel([("phone", ASCENDING)], unique=True, name="uniq_phone"),
            IndexModel([("total_spend", DESCENDING)], name="idx_total_spend"),
            IndexModel([("name", "text")], name="text_customer_name"),
        ]
    )
    await db.users.create_indexes(
        [IndexModel([("username", ASCENDING)], unique=True, name="uniq_username")]
    )
    await db.stock_audits.create_indexes(
        [
            IndexModel([("product_id", ASCENDING)], name="idx_audit_product"),
            IndexModel([("timestamp", DESCENDING)], name="idx_audit_timestamp"),
        ]
    )


async def ensure_store(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Create the single store document on first boot; return it either way."""
    settings = get_settings()
    existing = await db.stores.find_one({"_id": settings.store_id})
    if existing:
        return existing
    document = {
        "_id": settings.store_id,
        "name": "Super Sale",
        "address": "",
        "tax_id": "",
        "currency": "LKR",
        # Sri Lankan VAT.
        "tax_rate": 18.0,
        "default_discount": 0.0,
        "shelf_capacity_max": 5000,
        "warehouse_capacity_max": 20000,
        "loyalty_spend_per_point": 100.0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    await db.stores.insert_one(document)
    return document


async def ensure_default_users(db: AsyncIOMotorDatabase) -> None:
    """Seed one owner and one cashier so a fresh database is immediately usable."""
    from .security import hash_password  # imported here to avoid a circular import

    defaults = [
        {"username": "owner", "password": "owner123", "full_name": "Store Owner", "role": "OWNER"},
        {"username": "cashier", "password": "cashier123", "full_name": "Front Cashier", "role": "CASHIER"},
    ]
    for item in defaults:
        await db.users.update_one(
            {"username": item["username"]},
            {
                "$setOnInsert": {
                    "username": item["username"],
                    "full_name": item["full_name"],
                    "role": item["role"],
                    "password_hash": hash_password(item["password"]),
                    "email": None,
                    "phone": None,
                    "avatar_url": None,
                    "is_active": True,
                    "created_at": utcnow(),
                }
            },
            upsert=True,
        )


async def next_sequence(db: AsyncIOMotorDatabase, key: str) -> int:
    """Atomic counter used for receipt numbers, so concurrent sales never collide."""
    document = await db.counters.find_one_and_update(
        {"_id": key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(document["value"])
