"""The signed-in user's own profile: details, photo and password."""

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

# A 1x1 PNG, enough to exercise the data-URI validation.
TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def test_me_returns_the_stored_profile(client, owner):
    response = await client.get("/api/auth/me", headers=owner)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "owner"
    assert body["role"] == "OWNER"
    assert "avatar_url" in body


async def test_me_requires_authentication(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_owner_can_edit_their_details(client, owner):
    response = await client.put(
        "/api/auth/me",
        json={"full_name": "Dulan Ranaweera", "email": "owner@supersale.lk", "phone": "+94771234567"},
        headers=owner,
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Dulan Ranaweera"
    assert response.json()["email"] == "owner@supersale.lk"

    # The change is persisted, not just echoed back.
    again = await client.get("/api/auth/me", headers=owner)
    assert again.json()["phone"] == "+94771234567"


async def test_profile_edit_does_not_require_a_new_login(client, owner):
    """The token still carries the old name, so /me must read the database."""
    await client.put("/api/auth/me", json={"full_name": "Renamed Owner"}, headers=owner)
    assert (await client.get("/api/auth/me", headers=owner)).json()["full_name"] == "Renamed Owner"


async def test_a_cashier_can_edit_their_own_profile(client, cashier):
    response = await client.put("/api/auth/me", json={"full_name": "Front Desk"}, headers=cashier)
    assert response.status_code == 200
    assert response.json()["full_name"] == "Front Desk"


async def test_role_and_username_cannot_be_changed_through_the_profile(client, cashier):
    await client.put(
        "/api/auth/me",
        json={"full_name": "Sneaky", "role": "OWNER", "username": "owner"},
        headers=cashier,
    )
    body = (await client.get("/api/auth/me", headers=cashier)).json()
    assert body["role"] == "CASHIER"
    assert body["username"] == "cashier"


async def test_photo_round_trips_and_can_be_removed(client, owner):
    saved = await client.put("/api/auth/me", json={"avatar_url": TINY_PNG}, headers=owner)
    assert saved.status_code == 200
    assert saved.json()["avatar_url"] == TINY_PNG

    cleared = await client.put("/api/auth/me", json={"avatar_url": None}, headers=owner)
    assert cleared.json()["avatar_url"] is None


async def test_photo_must_be_an_inline_image(client, owner):
    for bad in ("https://example.com/photo.png", "data:text/html;base64,PHNjcmlwdD4=", "not a url"):
        response = await client.put("/api/auth/me", json={"avatar_url": bad}, headers=owner)
        assert response.status_code == 422, bad
        assert "PNG, JPEG or WebP" in response.json()["detail"]


async def test_oversized_photo_is_rejected(client, owner):
    huge = "data:image/png;base64," + ("A" * 400_001)
    assert (await client.put("/api/auth/me", json={"avatar_url": huge}, headers=owner)).status_code == 422


async def test_invalid_profile_values_are_rejected(client, owner):
    assert (await client.put("/api/auth/me", json={"full_name": ""}, headers=owner)).status_code == 422
    assert (await client.put("/api/auth/me", json={"email": "no-at-sign"}, headers=owner)).status_code == 422
    assert (await client.put("/api/auth/me", json={}, headers=owner)).status_code == 400


async def test_password_change_requires_the_current_password(client, cashier):
    wrong = await client.post(
        "/api/auth/me/password",
        json={"current_password": "not-it", "new_password": "a-better-secret"},
        headers=cashier,
    )
    assert wrong.status_code == 400
    assert "not correct" in wrong.json()["detail"]


async def test_password_change_rejects_a_short_or_unchanged_password(client, cashier):
    short = await client.post(
        "/api/auth/me/password",
        json={"current_password": "cashier123", "new_password": "short"},
        headers=cashier,
    )
    assert short.status_code == 422

    same = await client.post(
        "/api/auth/me/password",
        json={"current_password": "cashier123", "new_password": "cashier123"},
        headers=cashier,
    )
    assert same.status_code == 400
    assert "different" in same.json()["detail"]


async def test_password_change_takes_effect_on_the_next_login(client, cashier):
    changed = await client.post(
        "/api/auth/me/password",
        json={"current_password": "cashier123", "new_password": "fresh-password-9"},
        headers=cashier,
    )
    assert changed.status_code == 200

    assert (
        await client.post("/api/auth/login", json={"username": "cashier", "password": "cashier123"})
    ).status_code == 401
    assert (
        await client.post("/api/auth/login", json={"username": "cashier", "password": "fresh-password-9"})
    ).status_code == 200

    # Restore it so the shared session fixtures keep working.
    token = (
        await client.post("/api/auth/login", json={"username": "cashier", "password": "fresh-password-9"})
    ).json()["access_token"]
    await client.post(
        "/api/auth/me/password",
        json={"current_password": "fresh-password-9", "new_password": "cashier123"},
        headers={"Authorization": f"Bearer {token}"},
    )
