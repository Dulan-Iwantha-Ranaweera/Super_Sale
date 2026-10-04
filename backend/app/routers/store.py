"""Store profile and system preferences backing the Settings screen."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import get_settings
from ..database import ensure_store, get_db, utcnow
from ..models import StoreOut, StoreUpdate
from ..security import current_user, require_owner
from ..serializers import store_out

router = APIRouter(prefix="/api/store", tags=["store"])


@router.get("", response_model=StoreOut)
async def read_store(_: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db = get_db()
    document = await ensure_store(db)
    return store_out(document)


@router.put("", response_model=StoreOut)
async def update_store(
    payload: StoreUpdate,
    _: dict[str, Any] = Depends(require_owner),
) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settings supplied to update",
        )
    updates["updated_at"] = utcnow()
    await db.stores.update_one({"_id": settings.store_id}, {"$set": updates}, upsert=True)
    document = await db.stores.find_one({"_id": settings.store_id})
    return store_out(document or {})
