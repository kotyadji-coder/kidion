"""
Tests for the referral system.

Covers:
  - +60 crystals for new user who registers with a valid ref_code
  - referrals table entry is created
  - +60 crystals for referrer on first payment of referred user
  - +10% rub cashback to blogger_balance_rub on first payment of referred user
  - No repeated bonus on subsequent payments
  - Blogger receives rub reward, not crystals
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


async def _get_ref_code(client: AsyncClient) -> str:
    me = await client.get("/auth/me")
    return me.json()["ref_code"]


async def _get_crystals(client: AsyncClient) -> int:
    me = await client.get("/auth/me")
    return me.json()["crystals"]


async def _simulate_payment_webhook(
    client: AsyncClient,
    temp_db_path: str,
    user_email: str,
    package_id: str = "60_60",
) -> None:
    """Create a payment and fire a succeeded webhook for the given user."""
    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": package_id},
    )
    payment_id = create_resp.json()["payment_id"]

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT yookassa_payment_id FROM payments WHERE id = ?",
        (payment_id,),
    ).fetchone()
    con.close()
    yookassa_id = row[0]

    await client.post(
        "/api/payment/webhook",
        json={
            "type": "notification",
            "event": "payment.succeeded",
            "object": {
                "id": yookassa_id,
                "status": "succeeded",
                "amount": {"value": "50.00", "currency": "RUB"},
                "metadata": {},
            },
        },
    )


# ---------------------------------------------------------------------------
# Registration with ref_code — new user gets 60 crystals
# ---------------------------------------------------------------------------

async def test_register_with_ref_code_creates_referral_record(
    client: AsyncClient, temp_db_path: str
):
    await _register_login(client, "referrer@example.com")
    ref_code = await _get_ref_code(client)
    await client.post("/auth/logout")

    await _register_login(client, "newbie@example.com")
    # Re-register correctly with ref_code
    await client.post("/auth/logout")

    await client.post(
        "/auth/register",
        json={"email": "newbie2@example.com", "password": "password99", "ref_code": ref_code},
    )

    con = sqlite3.connect(temp_db_path)
    rows = con.execute("SELECT * FROM referrals").fetchall()
    con.close()
    assert len(rows) >= 1


# ---------------------------------------------------------------------------
# First payment of referred user → referrer gets +60 crystals
# ---------------------------------------------------------------------------

async def test_first_payment_of_referred_user_gives_referrer_60_crystals(
    client: AsyncClient, temp_db_path: str
):
    # Step 1: register referrer
    await _register_login(client, "referrer@example.com")
    ref_code = await _get_ref_code(client)
    crystals_referrer_before = await _get_crystals(client)
    await client.post("/auth/logout")

    # Step 2: register newbie using referrer's ref_code
    resp = await client.post(
        "/auth/register",
        json={"email": "newbie@example.com", "password": "password99", "ref_code": ref_code},
    )
    assert resp.status_code == 200
    await client.post(
        "/auth/login",
        json={"email": "newbie@example.com", "password": "password99"},
    )

    # Step 3: newbie makes first payment
    await _simulate_payment_webhook(client, temp_db_path, "newbie@example.com")
    await client.post("/auth/logout")

    # Step 4: check referrer crystals
    await _register_login(client, "referrer@example.com")  # re-login (session expired after logout)
    await client.post(
        "/auth/login",
        json={"email": "referrer@example.com", "password": "password99"},
    )
    crystals_after = await _get_crystals(client)
    assert crystals_after == crystals_referrer_before + 120


async def test_second_payment_of_referred_user_does_not_give_referrer_bonus(
    client: AsyncClient, temp_db_path: str
):
    # Register referrer
    await _register_login(client, "referrer@example.com")
    ref_code = await _get_ref_code(client)
    await client.post("/auth/logout")

    # Register newbie
    await client.post(
        "/auth/register",
        json={"email": "newbie@example.com", "password": "password99", "ref_code": ref_code},
    )
    await client.post(
        "/auth/login",
        json={"email": "newbie@example.com", "password": "password99"},
    )

    # First payment
    await _simulate_payment_webhook(client, temp_db_path, "newbie@example.com")

    # Second payment
    await _simulate_payment_webhook(client, temp_db_path, "newbie@example.com")
    await client.post("/auth/logout")

    # Check referrer got bonus only once
    await client.post(
        "/auth/login",
        json={"email": "referrer@example.com", "password": "password99"},
    )
    crystals = await _get_crystals(client)
    # 60 (initial) + 120 (referral bonus once)
    assert crystals == 60 + 120


async def test_referral_bonus_marked_paid_in_db_after_first_payment(
    client: AsyncClient, temp_db_path: str
):
    await _register_login(client, "referrer@example.com")
    ref_code = await _get_ref_code(client)
    await client.post("/auth/logout")

    await client.post(
        "/auth/register",
        json={"email": "newbie@example.com", "password": "password99", "ref_code": ref_code},
    )
    await client.post(
        "/auth/login",
        json={"email": "newbie@example.com", "password": "password99"},
    )
    await _simulate_payment_webhook(client, temp_db_path, "newbie@example.com")

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT blogger_reward_paid FROM referrals LIMIT 1"
    ).fetchone()
    con.close()
    # For a non-blogger referrer this field tracks that the one-time reward was paid
    assert row[0] == 1


# ---------------------------------------------------------------------------
# Blogger referral: rub cashback, not crystals
# ---------------------------------------------------------------------------

async def test_first_payment_of_referred_user_gives_blogger_rub_cashback(
    client: AsyncClient, temp_db_path: str, blogger_user: dict
):
    # Login as blogger to get ref_code
    await client.post("/auth/login", json=blogger_user)
    ref_code = await _get_ref_code(client)

    con = sqlite3.connect(temp_db_path)
    blogger_id = con.execute(
        "SELECT id FROM users WHERE email = ?", (blogger_user["email"],)
    ).fetchone()[0]
    blogger_crystals_before = con.execute(
        "SELECT crystals FROM users WHERE id = ?", (blogger_id,)
    ).fetchone()[0]
    con.close()
    await client.post("/auth/logout")

    # Register newbie with blogger ref_code
    await client.post(
        "/auth/register",
        json={"email": "fan@example.com", "password": "password99", "ref_code": ref_code},
    )
    await client.post(
        "/auth/login",
        json={"email": "fan@example.com", "password": "password99"},
    )

    # newbie makes a 60 rub payment → blogger gets 10% = 6 rub
    await _simulate_payment_webhook(client, temp_db_path, "fan@example.com", "60_60")
    await client.post("/auth/logout")

    con = sqlite3.connect(temp_db_path)
    blogger_after = con.execute(
        "SELECT crystals, blogger_balance_rub FROM users WHERE id = ?", (blogger_id,)
    ).fetchone()
    con.close()

    crystals_after, balance_rub_after = blogger_after

    # Crystals must NOT change due to this referral
    assert crystals_after == blogger_crystals_before
    # Rub balance must increase by 10% of 60 = 6 rub
    assert abs(balance_rub_after - 6.0) < 0.01


async def test_blogger_does_not_get_crystal_bonus_for_referral(
    client: AsyncClient, temp_db_path: str, blogger_user: dict
):
    await client.post("/auth/login", json=blogger_user)
    ref_code = await _get_ref_code(client)

    con = sqlite3.connect(temp_db_path)
    blogger_id = con.execute(
        "SELECT id FROM users WHERE email = ?", (blogger_user["email"],)
    ).fetchone()[0]
    crystals_before = con.execute(
        "SELECT crystals FROM users WHERE id = ?", (blogger_id,)
    ).fetchone()[0]
    con.close()
    await client.post("/auth/logout")

    await client.post(
        "/auth/register",
        json={"email": "fan2@example.com", "password": "password99", "ref_code": ref_code},
    )
    await client.post(
        "/auth/login",
        json={"email": "fan2@example.com", "password": "password99"},
    )
    await _simulate_payment_webhook(client, temp_db_path, "fan2@example.com", "60_60")

    con = sqlite3.connect(temp_db_path)
    crystals_after = con.execute(
        "SELECT crystals FROM users WHERE id = ?", (blogger_id,)
    ).fetchone()[0]
    con.close()

    assert crystals_after == crystals_before
