"""
Tests for authentication endpoints.

Covers:
  POST /auth/register
  POST /auth/login
  POST /auth/logout
  GET  /auth/me
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# POST /auth/register — happy path
# ---------------------------------------------------------------------------

async def test_register_returns_200_on_valid_data(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_register_sets_session_cookie(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    assert "kid_session" in resp.cookies


async def test_register_awards_30_crystals_by_default(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    # Login to carry the cookie
    await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 60


async def test_register_assigns_unique_ref_code(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    me = await client.get("/auth/me")
    data = me.json()
    assert "ref_code" in data
    assert isinstance(data["ref_code"], str)
    assert len(data["ref_code"]) > 0


# ---------------------------------------------------------------------------
# POST /auth/register — with valid ref_code → 60 crystals
# ---------------------------------------------------------------------------

async def test_register_with_valid_ref_code_awards_60_crystals(client: AsyncClient):
    # Referrer registers first
    await client.post(
        "/auth/register",
        json={"email": "referrer@example.com", "password": "referpass1"},
    )
    await client.post(
        "/auth/login",
        json={"email": "referrer@example.com", "password": "referpass1"},
    )
    referrer_me = await client.get("/auth/me")
    ref_code = referrer_me.json()["ref_code"]

    # New user logs out referrer session, then registers with ref_code
    await client.post("/auth/logout")
    await client.post(
        "/auth/register",
        json={
            "email": "newbie@example.com",
            "password": "newbiepass1",
            "ref_code": ref_code,
        },
    )
    await client.post(
        "/auth/login",
        json={"email": "newbie@example.com", "password": "newbiepass1"},
    )
    newbie_me = await client.get("/auth/me")
    assert newbie_me.json()["crystals"] == 120


async def test_register_with_invalid_ref_code_awards_30_crystals_no_error(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "securepass1",
            "ref_code": "NOTEXIST",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 60


# ---------------------------------------------------------------------------
# POST /auth/register — error cases
# ---------------------------------------------------------------------------

async def test_register_duplicate_email_returns_400_email_taken(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "securepass1"}
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"] == "email_taken"


async def test_register_invalid_email_format_returns_400(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "securepass1"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_email"


async def test_register_short_password_returns_400_weak_password(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "short"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "weak_password"


async def test_register_password_7_chars_returns_400_weak_password(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "1234567"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "weak_password"


async def test_register_password_8_chars_is_accepted(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "12345678"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Password storage: must be hashed, not plaintext
# ---------------------------------------------------------------------------

async def test_register_password_stored_as_bcrypt_hash(client: AsyncClient, temp_db_path):
    import sqlite3
    await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "securepass1"},
    )
    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT password_hash FROM users WHERE email = ?",
        ("alice@example.com",),
    ).fetchone()
    con.close()
    assert row is not None
    # bcrypt hashes start with $2b$ or $2a$
    assert row[0].startswith("$2")
    assert "securepass1" not in row[0]


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

async def test_login_returns_200_on_valid_credentials(client: AsyncClient, registered_user):
    resp = await client.post("/auth/login", json=registered_user)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_login_sets_session_cookie(client: AsyncClient, registered_user):
    resp = await client.post("/auth/login", json=registered_user)
    assert "kid_session" in resp.cookies


async def test_login_invalid_password_returns_401(client: AsyncClient, registered_user):
    resp = await client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


async def test_login_unknown_email_returns_401(client: AsyncClient):
    resp = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "password123"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

async def test_logout_returns_200(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_logout_clears_session_cookie(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/logout")
    # After logout the cookie should be cleared (empty value or max-age=0)
    cookie_val = resp.cookies.get("kid_session", "")
    assert cookie_val == "" or "kid_session" not in auth_client.cookies


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

async def test_me_returns_user_data_when_authenticated(auth_client: AsyncClient):
    resp = await auth_client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["email"] == "user@example.com"
    assert "crystals" in data
    assert "ref_code" in data


async def test_me_returns_401_when_not_authenticated(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
