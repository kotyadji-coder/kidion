"""
Tests for generation endpoints.

Covers:
  POST /api/generate
  GET  /api/poll/{gen_id}
"""

import sqlite3

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, email: str, password: str) -> None:
    await client.post("/auth/register", json={"email": email, "password": password})
    await client.post("/auth/login", json={"email": email, "password": password})


async def _set_crystals(temp_db_path: str, email: str, amount: int) -> None:
    con = sqlite3.connect(temp_db_path)
    con.execute(
        "UPDATE users SET crystals = ? WHERE email = ?",
        (amount, email),
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# POST /api/generate — auth guard
# ---------------------------------------------------------------------------

async def test_generate_returns_401_when_not_authenticated(client: AsyncClient):
    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/generate — insufficient crystals
# ---------------------------------------------------------------------------

async def test_generate_returns_402_when_crystals_below_10(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "poor@example.com", "password99")
    await _set_crystals(temp_db_path, "poor@example.com", 5)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    assert resp.status_code == 402
    assert resp.json()["error"] == "insufficient_crystals"


async def test_generate_returns_402_when_crystals_zero(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "broke@example.com", "password99")
    await _set_crystals(temp_db_path, "broke@example.com", 0)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Что такое гравитация?"},
    )
    assert resp.status_code == 402
    assert resp.json()["error"] == "insufficient_crystals"


# ---------------------------------------------------------------------------
# POST /api/generate — happy path
# ---------------------------------------------------------------------------

async def test_generate_returns_gen_id_when_enough_crystals(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "gen_id" in data
    assert isinstance(data["gen_id"], int)


async def test_generate_tale_type_accepted(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Откуда берётся дождь?"},
    )
    assert resp.status_code == 200


async def test_generate_lesson_type_accepted(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    resp = await client.post(
        "/api/generate",
        json={"type": "lesson", "question": "Что такое дроби?"},
    )
    assert resp.status_code == 200


async def test_generate_creates_pending_record_in_db(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    gen_id = resp.json()["gen_id"]

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT status FROM generations WHERE id = ?", (gen_id,)
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "pending"


async def test_generate_does_not_deduct_crystals_on_creation(
    client: AsyncClient, temp_db_path: str
):
    """Crystals are only deducted when callback reports 'done', not on generation start."""
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )

    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 50


async def test_generate_exactly_10_crystals_passes_balance_check(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "exact@example.com", "password99")
    await _set_crystals(temp_db_path, "exact@example.com", 20)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Как работает радуга?"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/poll/{gen_id} — auth guard
# ---------------------------------------------------------------------------

async def test_poll_returns_401_when_not_authenticated(client: AsyncClient):
    resp = await client.get("/api/poll/1")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/poll/{gen_id} — happy path
# ---------------------------------------------------------------------------

async def test_poll_returns_pending_status_for_new_generation(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    await _set_crystals(temp_db_path, "rich@example.com", 50)

    gen_resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    gen_id = gen_resp.json()["gen_id"]

    poll_resp = await client.get(f"/api/poll/{gen_id}")
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert data["status"] == "pending"
    assert data["result_url"] is None
    assert "crystals" in data


async def test_poll_returns_404_for_nonexistent_gen_id(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client, "rich@example.com", "password99")
    resp = await client.get("/api/poll/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/poll/{gen_id} — ownership check
# ---------------------------------------------------------------------------

async def test_poll_returns_403_for_another_users_generation(
    client: AsyncClient, temp_db_path: str
):
    # First user creates a generation
    await _register_and_login(client, "owner@example.com", "password99")
    await _set_crystals(temp_db_path, "owner@example.com", 50)
    gen_resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    gen_id = gen_resp.json()["gen_id"]

    # Second user logs in and tries to poll the first user's generation
    await client.post("/auth/logout")
    await _register_and_login(client, "intruder@example.com", "password99")

    poll_resp = await client.get(f"/api/poll/{gen_id}")
    assert poll_resp.status_code == 403
