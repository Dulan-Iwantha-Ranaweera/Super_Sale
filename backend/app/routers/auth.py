"""Authentication and the signed-in user's own profile."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_db, utcnow
from ..models import LoginRequest, PasswordChange, ProfileUpdate, TokenOut, UserOut
from ..security import create_access_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _profile(document: dict[str, Any]) -> UserOut:
    return UserOut(
        username=document["username"],
        full_name=document.get("full_name", document["username"]),
        role=document.get("role", "CASHIER"),
        email=document.get("email"),
        phone=document.get("phone"),
        avatar_url=document.get("avatar_url"),
    )


async def _load_user(username: str) -> dict[str, Any]:
    db = get_db()
    document = await db.users.find_one({"username": username})
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found")
    return document


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginRequest) -> TokenOut:
    db = get_db()
    user = await db.users.find_one({"username": payload.username.lower().strip()})
    if not user or not user.get("is_active", True) or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(user["username"], user["role"], user.get("full_name", user["username"]))
    return TokenOut(access_token=token, user=_profile(user))


@router.get("/me", response_model=UserOut)
async def me(user: dict[str, Any] = Depends(current_user)) -> UserOut:
    """Read the profile from the database, not the token.

    The token carries the name it was issued with, so after a profile edit only
    a database read reflects the change without forcing a re-login.
    """
    return _profile(await _load_user(user["username"]))


@router.put("/me", response_model=UserOut)
async def update_profile(
    payload: ProfileUpdate,
    user: dict[str, Any] = Depends(current_user),
) -> UserOut:
    """Edit your own profile. Role and username are deliberately not editable."""
    db = get_db()
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile fields supplied to update",
        )
    updates["updated_at"] = utcnow()
    await db.users.update_one({"username": user["username"]}, {"$set": updates})
    return _profile(await _load_user(user["username"]))


@router.post("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: PasswordChange,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, str]:
    db = get_db()
    document = await _load_user(user["username"])
    if not verify_password(payload.current_password, document["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current password is not correct",
        )
    if verify_password(payload.new_password, document["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current one",
        )
    await db.users.update_one(
        {"username": user["username"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": utcnow()}},
    )
    return {"detail": "Password updated"}
