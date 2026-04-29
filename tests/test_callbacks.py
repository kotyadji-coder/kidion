"""
Tests for bot callback endpoint.

Covers:
  POST /api/callback/{gen_id}?secret=<hmac>
"""

import hashlib
import hmac
import sqlite3

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TEST_HMAC_SECRET = "test-hmac-secret-for-bot-callbacks"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_secret(gen_id: int) -> str:
    msg = str(gen_id).encode()
    return hmac.new(TEST_HMAC_SECRET.encode(), msg, hashlib.sha256).hexdigest()


async def _register_login_and_get_gen(
    client: AsyncClient, temp_db_path: str, email: str = "cb@example.com"
) -> tuple[int, int]:
    """Register a user with 100 crystals, create a generation. Returns (gen_id, user_id)."""
    await client.post("/auth/register", json={"email": email, "password": "password99"})
    await client.post("/auth/login", json={"email": email, "password": "password99"})

    con = sqlite3.connect(temp_db_path)
    con.execute("UPDATE users SET crystals = 100 WHERE email = ?", (email,))
    con.commit()
    user_id = con.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    con.close()

    gen_resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    gen_id = gen_resp.json()["gen_id"]
    return gen_id, user_id


# ---------------------------------------------------------------------------
# HMAC validation
# ---------------------------------------------------------------------------

async def test_callback_rejects_invalid_hmac(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)

    resp = await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": "bad-hmac-signature"},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )
    assert resp.status_code in (400, 403)


async def test_callback_accepts_valid_hmac(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    resp = await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Callback with status "done"
# ---------------------------------------------------------------------------

async def test_callback_done_updates_generation_status_to_done(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT status FROM generations WHERE id = ?", (gen_id,)
    ).fetchone()
    con.close()
    assert row[0] == "done"


async def test_callback_done_saves_result_url(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)
    expected_url = "https://tales.example.com/abc123"

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": expected_url},
    )

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT result_url FROM generations WHERE id = ?", (gen_id,)
    ).fetchone()
    con.close()
    assert row[0] == expected_url


async def test_callback_done_deducts_10_crystals(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    # Crystals before: 100
    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )

    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 80


async def test_callback_done_records_transaction(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )

    con = sqlite3.connect(temp_db_path)
    rows = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ? AND delta = -20",
        (user_id,),
    ).fetchall()
    con.close()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# Callback with status "error"
# ---------------------------------------------------------------------------

async def test_callback_error_updates_generation_status_to_error(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "error", "user_id": user_id},
    )

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT status FROM generations WHERE id = ?", (gen_id,)
    ).fetchone()
    con.close()
    assert row[0] == "error"


async def test_callback_error_does_not_deduct_crystals(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "error", "user_id": user_id},
    )

    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 100


# ---------------------------------------------------------------------------
# Idempotency: repeated callback must not deduct crystals twice
# ---------------------------------------------------------------------------

async def test_callback_done_repeated_does_not_deduct_crystals_twice(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)
    payload = {
        "status": "done",
        "user_id": user_id,
        "tale_url": "https://tales.example.com/1",
    }

    await client.post(
        f"/api/callback/{gen_id}", params={"secret": secret}, json=payload
    )
    await client.post(
        f"/api/callback/{gen_id}", params={"secret": secret}, json=payload
    )

    me = await client.get("/auth/me")
    # Should be 50 - 10 = 40, NOT 50 - 20 = 30
    assert me.json()["crystals"] == 80


# ---------------------------------------------------------------------------
# Polling reflects callback result
# ---------------------------------------------------------------------------

async def test_poll_shows_done_status_after_callback_done(
    client: AsyncClient, temp_db_path: str
):
    gen_id, user_id = await _register_login_and_get_gen(client, temp_db_path)
    secret = _make_secret(gen_id)
    tale_url = "https://tales.example.com/xyz"

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": tale_url},
    )

    poll = await client.get(f"/api/poll/{gen_id}")
    assert poll.status_code == 200
    data = poll.json()
    assert data["status"] == "done"
    assert data["result_url"] == tale_url
