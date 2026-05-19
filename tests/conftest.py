import hashlib
import hmac
import os
import sqlite3
import tempfile
import uuid
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# main.py does not exist yet — this import will fail during Red phase (expected)
from main import app, get_db_connection

# ---------------------------------------------------------------------------
# Environment setup for tests
# ---------------------------------------------------------------------------

TEST_SECRET_KEY = "test-secret-key-for-kidion-sessions-32chars"
TEST_HMAC_SECRET = "test-hmac-secret-for-bot-callbacks"


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("CALLBACK_HMAC_SECRET", TEST_HMAC_SECRET)
    monkeypatch.setenv("YOOKASSA_SHOP_ID", "test-shop-id")
    monkeypatch.setenv("YOOKASSA_SECRET_KEY", "test-yookassa-key")
    monkeypatch.setenv("APP_BASE_URL", "http://testserver")
    monkeypatch.setenv("TESTING", "1")


@pytest.fixture(autouse=True)
def mock_yookassa_payment(monkeypatch):
    """Mock yookassa.Payment.create to avoid real HTTP calls during tests."""
    def _fake_create(payload, idempotency_key=None):
        fake_id = str(uuid.uuid4())
        mock_payment = MagicMock()
        mock_payment.id = fake_id
        mock_payment.confirmation.confirmation_url = (
            f"https://yookassa.ru/checkout/payments/{fake_id}"
        )
        return mock_payment

    monkeypatch.setattr("payments.Payment.create", _fake_create)


# ---------------------------------------------------------------------------
# In-memory / temp-file SQLite database fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db_path(tmp_path):
    return str(tmp_path / "test_kidion.db")


@pytest.fixture(autouse=True)
def override_db(temp_db_path, monkeypatch):
    """Override DATABASE_PATH so every test uses its own fresh SQLite file."""
    monkeypatch.setenv("DATABASE_PATH", temp_db_path)
    from db import init_db
    init_db(temp_db_path)


# ---------------------------------------------------------------------------
# Async HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Registered & logged-in user helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a user and return {"email", "password"}."""
    payload = {"email": "user@example.com", "password": "password123", "consent": True}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 200, f"Registration failed: {resp.text}"
    return payload


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, registered_user: dict) -> AsyncClient:
    """AsyncClient with a valid session cookie after login."""
    resp = await client.post("/auth/login", json=registered_user)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client


@pytest_asyncio.fixture
async def second_user(client: AsyncClient) -> dict:
    """A second registered user for isolation tests."""
    payload = {"email": "other@example.com", "password": "password456", "consent": True}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 200, f"Second user registration failed: {resp.text}"
    return payload


# ---------------------------------------------------------------------------
# Helper: compute a valid HMAC secret for callback tests
# ---------------------------------------------------------------------------

def make_callback_secret(gen_id: int) -> str:
    """Return a valid HMAC-SHA256 hex digest for the given gen_id."""
    msg = str(gen_id).encode()
    return hmac.new(TEST_HMAC_SECRET.encode(), msg, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Helper: give a user extra crystals directly in DB (bypasses app logic)
# ---------------------------------------------------------------------------

def add_crystals_direct(db_path: str, user_id: int, amount: int) -> None:
    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE users SET crystals = crystals + ? WHERE id = ?",
        (amount, user_id),
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Blogger user fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def blogger_user(client: AsyncClient) -> dict:
    """A user marked as blogger (is_blogger=1) in the DB."""
    payload = {"email": "blogger@example.com", "password": "blogpass1", "consent": True}
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 200

    # Directly flip is_blogger flag — production code may expose an admin
    # endpoint later; for now we touch the DB directly.
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE users SET is_blogger = 1 WHERE email = ?",
        (payload["email"],),
    )
    con.commit()
    con.close()
    return payload
