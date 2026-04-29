"""
Tests for payment endpoints.

Covers:
  POST /api/payment/create
  POST /api/payment/webhook
  GET  /api/payment/status/{payment_id}
"""

import sqlite3
import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# Known packages from spec
PACKAGES = {
    "60_60": {"rub": 60, "crystals": 60},
    "360_320": {"rub": 320, "crystals": 360},
    "600_490": {"rub": 490, "crystals": 600},
    "1000_800": {"rub": 800, "crystals": 1000},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(
    client: AsyncClient, email: str = "payer@example.com", password: str = "password99"
) -> None:
    await client.post("/auth/register", json={"email": email, "password": password})
    await client.post("/auth/login", json={"email": email, "password": password})


def _build_yookassa_webhook(
    yookassa_payment_id: str,
    status: str = "succeeded",
    amount_value: str = "50.00",
    metadata: dict | None = None,
) -> dict:
    """Construct a minimal YooKassa webhook payload."""
    return {
        "type": "notification",
        "event": f"payment.{status}",
        "object": {
            "id": yookassa_payment_id,
            "status": status,
            "amount": {"value": amount_value, "currency": "RUB"},
            "metadata": metadata or {},
        },
    }


# ---------------------------------------------------------------------------
# POST /api/payment/create — auth guard
# ---------------------------------------------------------------------------

async def test_create_payment_returns_401_when_not_authenticated(client: AsyncClient):
    resp = await client.post(
        "/api/payment/create",
        json={"package_id": "60_60"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/payment/create — unknown package
# ---------------------------------------------------------------------------

async def test_create_payment_returns_400_for_unknown_package(client: AsyncClient):
    await _register_and_login(client)
    resp = await client.post(
        "/api/payment/create",
        json={"package_id": "999_999"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/payment/create — happy path for each package
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("package_id", list(PACKAGES.keys()))
async def test_create_payment_returns_payment_id_and_confirmation_url(
    client: AsyncClient, package_id: str
):
    await _register_and_login(client)
    resp = await client.post(
        "/api/payment/create",
        json={"package_id": package_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "payment_id" in data
    assert "confirmation_url" in data
    assert isinstance(data["confirmation_url"], str)
    assert data["confirmation_url"].startswith("http")


# ---------------------------------------------------------------------------
# POST /api/payment/webhook — credits crystals on "payment.succeeded"
# ---------------------------------------------------------------------------

async def test_webhook_credits_crystals_on_payment_succeeded(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client)

    # Simulate payment creation to get a yookassa_payment_id in DB
    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": "60_60"},
    )
    internal_payment_id = create_resp.json()["payment_id"]

    # Read yookassa_payment_id from DB
    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT yookassa_payment_id FROM payments WHERE id = ?",
        (internal_payment_id,),
    ).fetchone()
    con.close()
    yookassa_id = row[0]

    crystals_before = (await client.get("/auth/me")).json()["crystals"]

    webhook_payload = _build_yookassa_webhook(yookassa_id, "succeeded", "50.00")
    resp = await client.post("/api/payment/webhook", json=webhook_payload)
    assert resp.status_code == 200

    crystals_after = (await client.get("/auth/me")).json()["crystals"]
    assert crystals_after == crystals_before + PACKAGES["60_60"]["crystals"]


async def test_webhook_always_returns_200(client: AsyncClient):
    """YooKassa expects HTTP 200 even for unrecognised events."""
    resp = await client.post(
        "/api/payment/webhook",
        json={"type": "notification", "event": "payment.canceled", "object": {"id": "unknown"}},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/payment/webhook — idempotency
# ---------------------------------------------------------------------------

async def test_webhook_idempotent_does_not_credit_twice(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client)

    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": "60_60"},
    )
    internal_payment_id = create_resp.json()["payment_id"]

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT yookassa_payment_id FROM payments WHERE id = ?",
        (internal_payment_id,),
    ).fetchone()
    con.close()
    yookassa_id = row[0]

    webhook_payload = _build_yookassa_webhook(yookassa_id, "succeeded", "50.00")

    await client.post("/api/payment/webhook", json=webhook_payload)
    await client.post("/api/payment/webhook", json=webhook_payload)

    crystals = (await client.get("/auth/me")).json()["crystals"]
    # 60 initial + 60 from package, no double-credit
    assert crystals == 60 + PACKAGES["60_60"]["crystals"]


# ---------------------------------------------------------------------------
# POST /api/payment/webhook — records transaction
# ---------------------------------------------------------------------------

async def test_webhook_records_transaction_in_db(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client)

    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": "360_320"},
    )
    internal_payment_id = create_resp.json()["payment_id"]

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT yookassa_payment_id, user_id FROM payments WHERE id = ?",
        (internal_payment_id,),
    ).fetchone()
    con.close()
    yookassa_id, user_id = row

    webhook_payload = _build_yookassa_webhook(yookassa_id, "succeeded", "300.00")
    await client.post("/api/payment/webhook", json=webhook_payload)

    con = sqlite3.connect(temp_db_path)
    txn = con.execute(
        "SELECT delta FROM transactions WHERE user_id = ? AND delta = ?",
        (user_id, PACKAGES["360_320"]["crystals"]),
    ).fetchone()
    con.close()
    assert txn is not None


# ---------------------------------------------------------------------------
# GET /api/payment/status/{payment_id}
# ---------------------------------------------------------------------------

async def test_payment_status_returns_pending_before_webhook(
    client: AsyncClient
):
    await _register_and_login(client)
    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": "60_60"},
    )
    payment_id = create_resp.json()["payment_id"]

    status_resp = await client.get(f"/api/payment/status/{payment_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "status" in data
    assert "crystals" in data


async def test_payment_status_returns_succeeded_after_webhook(
    client: AsyncClient, temp_db_path: str
):
    await _register_and_login(client)
    create_resp = await client.post(
        "/api/payment/create",
        json={"package_id": "60_60"},
    )
    payment_id = create_resp.json()["payment_id"]

    con = sqlite3.connect(temp_db_path)
    row = con.execute(
        "SELECT yookassa_payment_id FROM payments WHERE id = ?", (payment_id,)
    ).fetchone()
    con.close()
    yookassa_id = row[0]

    await client.post(
        "/api/payment/webhook",
        json=_build_yookassa_webhook(yookassa_id, "succeeded", "50.00"),
    )

    status_resp = await client.get(f"/api/payment/status/{payment_id}")
    assert status_resp.json()["status"] == "succeeded"
