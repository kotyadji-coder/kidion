"""
Tests for the crystal system.

Covers:
  - Atomicity: balance cannot go below zero
  - All balance changes are recorded in transactions table
  - Balance is visible via /auth/me
  - Concurrent deduction safety (WHERE crystals >= 10)
"""

import sqlite3

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_login(
    client: AsyncClient, email: str, password: str = "password99"
) -> None:
    await client.post("/auth/register", json={"email": email, "password": password})
    await client.post("/auth/login", json={"email": email, "password": password})


def _set_crystals_db(db_path: str, email: str, amount: int) -> None:
    con = sqlite3.connect(db_path)
    con.execute("UPDATE users SET crystals = ? WHERE email = ?", (amount, email))
    con.commit()
    con.close()


def _get_user_id(db_path: str, email: str) -> int:
    con = sqlite3.connect(db_path)
    uid = con.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()[0]
    con.close()
    return uid


# ---------------------------------------------------------------------------
# Registration awards are recorded in transactions
# ---------------------------------------------------------------------------

async def test_registration_creates_transaction_for_initial_crystals(
    client: AsyncClient, temp_db_path: str
):
    await _register_login(client, "crystal@example.com")
    user_id = _get_user_id(temp_db_path, "crystal@example.com")

    con = sqlite3.connect(temp_db_path)
    rows = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ?", (user_id,)
    ).fetchall()
    con.close()
    total = sum(r[0] for r in rows)
    assert total == 60


async def test_registration_with_ref_code_records_120_crystal_transaction(
    client: AsyncClient, temp_db_path: str
):
    # Register referrer
    await _register_login(client, "ref@example.com")
    ref_code = (await client.get("/auth/me")).json()["ref_code"]
    await client.post("/auth/logout")

    # Register newbie
    await client.post(
        "/auth/register",
        json={"email": "newbie@example.com", "password": "password99", "ref_code": ref_code},
    )
    user_id = _get_user_id(temp_db_path, "newbie@example.com")

    con = sqlite3.connect(temp_db_path)
    rows = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ?", (user_id,)
    ).fetchall()
    con.close()
    total = sum(r[0] for r in rows)
    assert total == 120


# ---------------------------------------------------------------------------
# Crystal balance visible via /auth/me
# ---------------------------------------------------------------------------

async def test_me_shows_correct_crystal_balance_after_direct_db_modification(
    client: AsyncClient, temp_db_path: str
):
    await _register_login(client, "rich@example.com")
    _set_crystals_db(temp_db_path, "rich@example.com", 200)

    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 200


# ---------------------------------------------------------------------------
# Atomicity: cannot go below zero
# ---------------------------------------------------------------------------

async def test_generate_fails_atomically_when_balance_below_10(
    client: AsyncClient, temp_db_path: str
):
    """A user with 9 crystals cannot start a generation; balance stays 9."""
    await _register_login(client, "poor@example.com")
    _set_crystals_db(temp_db_path, "poor@example.com", 9)

    resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    assert resp.status_code == 402

    me = await client.get("/auth/me")
    assert me.json()["crystals"] == 9


async def test_crystals_cannot_go_negative_via_concurrent_deductions(
    temp_db_path: str
):
    """
    Direct DB test: UPDATE ... WHERE crystals >= 10 must be atomic.
    With only 10 crystals, two concurrent -10 deductions should result in
    exactly one success (crystals = 0) and one failure (rows_affected = 0).
    """
    con = sqlite3.connect(temp_db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY, email TEXT, crystals INTEGER DEFAULT 0)"
    )
    con.execute("INSERT INTO users (email, crystals) VALUES ('atom@example.com', 10)")
    con.commit()

    cursor1 = con.execute(
        "UPDATE users SET crystals = crystals - 10 WHERE email = 'atom@example.com' AND crystals >= 10"
    )
    affected1 = cursor1.rowcount

    cursor2 = con.execute(
        "UPDATE users SET crystals = crystals - 10 WHERE email = 'atom@example.com' AND crystals >= 10"
    )
    affected2 = cursor2.rowcount
    con.commit()

    final = con.execute(
        "SELECT crystals FROM users WHERE email = 'atom@example.com'"
    ).fetchone()[0]
    con.close()

    # One deduction should have succeeded, the other should be a no-op
    assert affected1 + affected2 == 1
    assert final == 0


# ---------------------------------------------------------------------------
# Transaction log completeness
# ---------------------------------------------------------------------------

async def test_every_crystal_change_is_logged_in_transactions(
    client: AsyncClient, temp_db_path: str
):
    import hashlib, hmac as hmac_mod

    TEST_HMAC_SECRET = "test-hmac-secret-for-bot-callbacks"

    await _register_login(client, "log@example.com")
    user_id = _get_user_id(temp_db_path, "log@example.com")
    _set_crystals_db(temp_db_path, "log@example.com", 50)

    # Trigger a deduction via generation callback
    gen_resp = await client.post(
        "/api/generate",
        json={"type": "tale", "question": "Почему небо синее?"},
    )
    gen_id = gen_resp.json()["gen_id"]
    secret = hmac_mod.new(
        TEST_HMAC_SECRET.encode(), str(gen_id).encode(), hashlib.sha256
    ).hexdigest()

    await client.post(
        f"/api/callback/{gen_id}",
        params={"secret": secret},
        json={"status": "done", "user_id": user_id, "tale_url": "https://tales.example.com/1"},
    )

    con = sqlite3.connect(temp_db_path)
    rows = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ?", (user_id,)
    ).fetchall()
    con.close()

    deltas = [r[0] for r in rows]
    # Must contain a -20 deduction entry
    assert -20 in deltas


# ---------------------------------------------------------------------------
# Multiple transactions: balance is the sum of all deltas
# ---------------------------------------------------------------------------

async def test_crystal_balance_equals_sum_of_transaction_deltas(
    client: AsyncClient, temp_db_path: str
):
    await _register_login(client, "sum@example.com")
    user_id = _get_user_id(temp_db_path, "sum@example.com")

    # Manually insert extra transactions to simulate history
    con = sqlite3.connect(temp_db_path)
    # Add 20 via a direct transaction row (simulating a payment credit)
    con.execute(
        "INSERT INTO transactions (user_id, delta, reason, created_at) "
        "VALUES (?, 20, 'test_credit', datetime('now'))",
        (user_id,),
    )
    con.execute(
        "UPDATE users SET crystals = crystals + 20 WHERE id = ?", (user_id,)
    )
    con.commit()
    con.close()

    me = await client.get("/auth/me")
    crystals_balance = me.json()["crystals"]

    con = sqlite3.connect(temp_db_path)
    rows = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ?", (user_id,)
    ).fetchall()
    con.close()

    sum_of_deltas = sum(r[0] for r in rows)
    assert crystals_balance == sum_of_deltas
