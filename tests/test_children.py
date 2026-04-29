"""
tests/test_children.py — TDD tests for Children CRUD API and Kid PIN Auth.

All tests are expected to FAIL until the implementation is complete.

Covers:
  DB CRUD unit tests (create_child, get_children_by_parent, get_child_by_id,
                       update_child, delete_child, count_children_by_parent,
                       get_streak_by_child)
  POST   /api/children
  GET    /api/children
  GET    /api/children/{child_id}
  PUT    /api/children/{child_id}
  DELETE /api/children/{child_id}
  POST   /api/kid/auth
  get_current_child helper (auth.py)
"""

import os
import sqlite3

import pytest
import pytest_asyncio
from httpx import AsyncClient

# These imports will succeed (they already exist)
from auth import (
    hash_password,
    verify_password,
    create_child_session_token,
    decode_child_session_token,
    get_current_child,
)
from db import (
    get_connection,
    create_child,
    get_children_by_parent,
    get_child_by_id,
    update_child,
    delete_child,
    count_children_by_parent,
    get_streak_by_child,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHILD_PAYLOAD = {
    "name": "Тестик",
    "gender": "boy",
    "birth_date": "2018-05-10",
    "grade": 2,
    "universe": "Майнкрафт",
    "pin_code": "1234",
}


def _make_conn(db_path: str) -> sqlite3.Connection:
    """Open a fresh connection to the temp DB (schema already initialised by app)."""
    return get_connection(db_path)


# ---------------------------------------------------------------------------
# Fixture: registered_child  (depends on auth_client / registered_user)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def registered_child(auth_client: AsyncClient, registered_user: dict) -> dict:
    """Create one child for registered_user via the API. Returns child dict."""
    resp = await auth_client.post("/api/children", json=CHILD_PAYLOAD)
    assert resp.status_code == 201, f"Child creation failed: {resp.text}"
    return resp.json()


# ===========================================================================
# SECTION 1 — DB CRUD unit tests
# ===========================================================================


async def test_create_child_persists_to_db(temp_db_path: str, registered_user: dict, auth_client: AsyncClient):
    """create_child() inserts a row and returns it without pin_hash."""
    conn = _make_conn(temp_db_path)
    pin_hash = hash_password("1234")
    # We need a real parent_id — fetch it via /auth/me
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]

    child = create_child(
        conn,
        parent_id=parent_id,
        name="Петя",
        gender="boy",
        birth_date="2017-06-01",
        grade=3,
        universe="Лего",
        pin_hash=pin_hash,
    )

    assert child["id"] is not None
    assert child["name"] == "Петя"
    assert child["parent_id"] == parent_id
    assert child["difficulty_level"] == 2
    assert "pin_hash" not in child


async def test_create_child_creates_streak_row(temp_db_path: str, auth_client: AsyncClient):
    """create_child() must also insert a streak row for the new child."""
    conn = _make_conn(temp_db_path)
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]
    pin_hash = hash_password("5678")

    child = create_child(conn, parent_id=parent_id, name="Аня", gender="girl",
                         birth_date="2019-01-20", grade=1, universe="Frozen",
                         pin_hash=pin_hash)

    streak = get_streak_by_child(conn, child["id"])
    assert streak is not None
    assert streak["child_id"] == child["id"]
    assert streak["current_streak"] == 0
    assert streak["longest_streak"] == 0


async def test_count_children_by_parent(temp_db_path: str, auth_client: AsyncClient):
    """count_children_by_parent returns 0 before any children, 1 after one created."""
    conn = _make_conn(temp_db_path)
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]

    assert count_children_by_parent(conn, parent_id) == 0

    create_child(conn, parent_id=parent_id, name="Рома", gender="boy",
                 birth_date="2016-03-15", grade=4, universe="Minecraft",
                 pin_hash=hash_password("0000"))

    assert count_children_by_parent(conn, parent_id) == 1


async def test_update_child_partial_fields_db(temp_db_path: str, auth_client: AsyncClient):
    """update_child() changes only the supplied fields."""
    conn = _make_conn(temp_db_path)
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]

    child = create_child(conn, parent_id=parent_id, name="Оля", gender="girl",
                         birth_date="2020-07-07", grade=1, universe="МиМиМишки",
                         pin_hash=hash_password("1111"))

    updated = update_child(conn, child["id"], name="Оленька", grade=2)

    assert updated["name"] == "Оленька"
    assert updated["grade"] == 2
    assert updated["gender"] == "girl"  # unchanged
    assert "pin_hash" not in updated


async def test_update_child_ignores_difficulty_level_db(temp_db_path: str, auth_client: AsyncClient):
    """update_child() silently ignores difficulty_level in kwargs."""
    conn = _make_conn(temp_db_path)
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]

    child = create_child(conn, parent_id=parent_id, name="Вася", gender="boy",
                         birth_date="2015-12-31", grade=5, universe="Звёздные войны",
                         pin_hash=hash_password("2222"))

    updated = update_child(conn, child["id"], difficulty_level=3, name="Василий")

    assert updated["difficulty_level"] == 2  # must still be default
    assert updated["name"] == "Василий"


async def test_delete_child_cascades_streak(temp_db_path: str, auth_client: AsyncClient):
    """Deleting a child removes its streak row via CASCADE."""
    conn = _make_conn(temp_db_path)
    me = await auth_client.get("/auth/me")
    parent_id = me.json()["id"]

    child = create_child(conn, parent_id=parent_id, name="Стас", gender="boy",
                         birth_date="2014-11-11", grade=6, universe="Трансформеры",
                         pin_hash=hash_password("3333"))
    child_id = child["id"]

    # Streak row exists before deletion
    assert get_streak_by_child(conn, child_id) is not None

    result = delete_child(conn, child_id)
    assert result is True

    # Streak must be gone after cascade delete
    assert get_streak_by_child(conn, child_id) is None


# ===========================================================================
# SECTION 2 — POST /api/children
# ===========================================================================


async def test_create_child_success(auth_client: AsyncClient):
    """POST /api/children returns 201 with child dict, no pin_hash."""
    resp = await auth_client.post("/api/children", json=CHILD_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == CHILD_PAYLOAD["name"]
    assert body["gender"] == CHILD_PAYLOAD["gender"]
    assert body["difficulty_level"] == 2
    assert "pin_hash" not in body


async def test_create_child_max_3_returns_400(auth_client: AsyncClient):
    """Creating a 4th child returns 400 max_children_reached."""
    for i in range(3):
        payload = {**CHILD_PAYLOAD, "name": f"Ребёнок {i}"}
        resp = await auth_client.post("/api/children", json=payload)
        assert resp.status_code == 201

    resp = await auth_client.post("/api/children", json={**CHILD_PAYLOAD, "name": "Лишний"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "max_children_reached"


async def test_create_child_invalid_gender_returns_422(auth_client: AsyncClient):
    """Invalid gender value triggers 422."""
    payload = {**CHILD_PAYLOAD, "gender": "unknown"}
    resp = await auth_client.post("/api/children", json=payload)
    assert resp.status_code == 422


async def test_create_child_invalid_grade_returns_422(auth_client: AsyncClient):
    """Grade outside 1–11 triggers 422."""
    payload = {**CHILD_PAYLOAD, "grade": 12}
    resp = await auth_client.post("/api/children", json=payload)
    assert resp.status_code == 422


async def test_create_child_invalid_pin_returns_422(auth_client: AsyncClient):
    """PIN that is not 4-6 digits triggers 422."""
    payload = {**CHILD_PAYLOAD, "pin_code": "abc"}
    resp = await auth_client.post("/api/children", json=payload)
    assert resp.status_code == 422


async def test_create_child_unauthenticated_returns_401(client: AsyncClient):
    """Unauthenticated request returns 401."""
    resp = await client.post("/api/children", json=CHILD_PAYLOAD)
    assert resp.status_code == 401


# ===========================================================================
# SECTION 3 — GET /api/children
# ===========================================================================


async def test_get_children_returns_only_own(auth_client: AsyncClient, registered_child: dict):
    """GET /api/children returns only children belonging to authenticated user."""
    resp = await auth_client.get("/api/children")
    assert resp.status_code == 200
    children = resp.json()
    assert isinstance(children, list)
    assert len(children) == 1
    assert children[0]["id"] == registered_child["id"]


async def test_get_children_empty_list(auth_client: AsyncClient):
    """GET /api/children returns empty list when parent has no children."""
    resp = await auth_client.get("/api/children")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_children_unauthenticated_returns_401(client: AsyncClient):
    """Unauthenticated GET /api/children returns 401."""
    resp = await client.get("/api/children")
    assert resp.status_code == 401


# ===========================================================================
# SECTION 4 — GET /api/children/{child_id}
# ===========================================================================


async def test_get_child_by_id_success(auth_client: AsyncClient, registered_child: dict):
    """GET /api/children/{id} returns child fields."""
    child_id = registered_child["id"]
    resp = await auth_client.get(f"/api/children/{child_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == child_id
    assert body["name"] == registered_child["name"]


async def test_get_child_by_id_includes_streak(auth_client: AsyncClient, registered_child: dict):
    """GET /api/children/{id} response includes streak fields."""
    child_id = registered_child["id"]
    resp = await auth_client.get(f"/api/children/{child_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "current_streak" in body
    assert "longest_streak" in body
    assert "last_activity_date" in body


async def test_get_child_by_id_no_pin_hash_in_response(auth_client: AsyncClient, registered_child: dict):
    """GET /api/children/{id} must never expose pin_hash."""
    child_id = registered_child["id"]
    resp = await auth_client.get(f"/api/children/{child_id}")
    assert resp.status_code == 200
    assert "pin_hash" not in resp.json()


async def test_get_child_by_id_wrong_parent_returns_403(
    auth_client: AsyncClient, registered_child: dict, client: AsyncClient
):
    """A different logged-in user gets 403 for another user's child."""
    # Register and log in as second user
    await client.post("/auth/register", json={"email": "other2@example.com", "password": "pass4567"})
    await client.post("/auth/login", json={"email": "other2@example.com", "password": "pass4567"})

    child_id = registered_child["id"]
    resp = await client.get(f"/api/children/{child_id}")
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


async def test_get_child_by_id_not_found_returns_404(auth_client: AsyncClient):
    """Non-existent child_id returns 404."""
    resp = await auth_client.get("/api/children/99999")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


# ===========================================================================
# SECTION 5 — PUT /api/children/{child_id}
# ===========================================================================


async def test_update_child_partial_fields(auth_client: AsyncClient, registered_child: dict):
    """PUT /api/children/{id} with partial fields updates only those fields."""
    child_id = registered_child["id"]
    resp = await auth_client.put(f"/api/children/{child_id}", json={"name": "Новое Имя"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Новое Имя"
    assert body["gender"] == registered_child["gender"]  # unchanged


async def test_update_child_pin(auth_client: AsyncClient, registered_child: dict):
    """PUT /api/children/{id} with pin_code changes the PIN."""
    child_id = registered_child["id"]
    resp = await auth_client.put(f"/api/children/{child_id}", json={"pin_code": "9999"})
    assert resp.status_code == 200
    # After updating PIN, kid/auth with new PIN must succeed
    auth_resp = await auth_client.post("/api/kid/auth", json={"child_id": child_id, "pin": "9999"})
    assert auth_resp.status_code == 200


async def test_update_child_ignores_difficulty_level(auth_client: AsyncClient, registered_child: dict):
    """PUT /api/children/{id} silently ignores difficulty_level in body."""
    child_id = registered_child["id"]
    resp = await auth_client.put(f"/api/children/{child_id}", json={"difficulty_level": 3})
    assert resp.status_code == 200
    assert resp.json()["difficulty_level"] == 2  # unchanged


async def test_update_child_ignores_parent_id(auth_client: AsyncClient, registered_child: dict):
    """PUT /api/children/{id} silently ignores parent_id in body."""
    child_id = registered_child["id"]
    original_parent_id = registered_child["parent_id"]
    resp = await auth_client.put(f"/api/children/{child_id}", json={"parent_id": 9999})
    assert resp.status_code == 200
    assert resp.json()["parent_id"] == original_parent_id


async def test_update_child_wrong_parent_returns_403(
    auth_client: AsyncClient, registered_child: dict, client: AsyncClient
):
    """Different user cannot update another user's child."""
    await client.post("/auth/register", json={"email": "other3@example.com", "password": "pass8901"})
    await client.post("/auth/login", json={"email": "other3@example.com", "password": "pass8901"})

    child_id = registered_child["id"]
    resp = await client.put(f"/api/children/{child_id}", json={"name": "Взломщик"})
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


# ===========================================================================
# SECTION 6 — DELETE /api/children/{child_id}
# ===========================================================================


async def test_delete_child_success(auth_client: AsyncClient, registered_child: dict):
    """DELETE /api/children/{id} returns 200 ok:true."""
    child_id = registered_child["id"]
    resp = await auth_client.delete(f"/api/children/{child_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Child should no longer appear in list
    list_resp = await auth_client.get("/api/children")
    assert list_resp.json() == []


async def test_delete_child_cascades_related_data(
    temp_db_path: str, auth_client: AsyncClient, registered_child: dict
):
    """Deleting a child removes its streaks row via cascade (DB-level check)."""
    conn = _make_conn(temp_db_path)
    child_id = registered_child["id"]

    # Streak must exist before deletion
    streak_before = conn.execute(
        "SELECT id FROM streaks WHERE child_id = ?", (child_id,)
    ).fetchone()
    assert streak_before is not None, "Streak row missing before delete"

    resp = await auth_client.delete(f"/api/children/{child_id}")
    assert resp.status_code == 200

    # Streak must be gone after delete (cascade)
    streak_after = conn.execute(
        "SELECT id FROM streaks WHERE child_id = ?", (child_id,)
    ).fetchone()
    assert streak_after is None, "Streak row should have been cascade-deleted"


async def test_delete_child_wrong_parent_returns_403(
    auth_client: AsyncClient, registered_child: dict, client: AsyncClient
):
    """Different user cannot delete another user's child."""
    await client.post("/auth/register", json={"email": "other4@example.com", "password": "pass2345"})
    await client.post("/auth/login", json={"email": "other4@example.com", "password": "pass2345"})

    child_id = registered_child["id"]
    resp = await client.delete(f"/api/children/{child_id}")
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


# ===========================================================================
# SECTION 7 — POST /api/kid/auth
# ===========================================================================


async def test_kid_auth_correct_pin(auth_client: AsyncClient, registered_child: dict):
    """POST /api/kid/auth with correct PIN returns 200 and ok:true."""
    resp = await auth_client.post(
        "/api/kid/auth",
        json={"child_id": registered_child["id"], "pin": "1234"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True


async def test_kid_auth_wrong_pin_returns_401(auth_client: AsyncClient, registered_child: dict):
    """POST /api/kid/auth with wrong PIN returns 401 invalid_credentials."""
    resp = await auth_client.post(
        "/api/kid/auth",
        json={"child_id": registered_child["id"], "pin": "0000"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


async def test_kid_auth_unknown_child_returns_401(client: AsyncClient):
    """POST /api/kid/auth with non-existent child_id returns 401 (no info leakage)."""
    resp = await client.post(
        "/api/kid/auth",
        json={"child_id": 99999, "pin": "1234"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


async def test_kid_auth_sets_cookie(auth_client: AsyncClient, registered_child: dict):
    """POST /api/kid/auth sets kid_session_child cookie on success."""
    resp = await auth_client.post(
        "/api/kid/auth",
        json={"child_id": registered_child["id"], "pin": "1234"},
    )
    assert resp.status_code == 200
    assert "kid_session_child" in resp.cookies


async def test_kid_auth_response_has_name(auth_client: AsyncClient, registered_child: dict):
    """POST /api/kid/auth response includes child_id and name."""
    resp = await auth_client.post(
        "/api/kid/auth",
        json={"child_id": registered_child["id"], "pin": "1234"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["child_id"] == registered_child["id"]
    assert body["name"] == registered_child["name"]


# ===========================================================================
# SECTION 8 — get_current_child helper
# ===========================================================================


async def test_get_current_child_valid_cookie(temp_db_path: str, auth_client: AsyncClient, registered_child: dict):
    """get_current_child returns child dict when cookie is valid."""
    from unittest.mock import MagicMock

    child_id = registered_child["id"]
    token = create_child_session_token(child_id)
    conn = _make_conn(temp_db_path)

    request = MagicMock()
    request.cookies = {"kid_session_child": token}

    child = get_current_child(request, conn)
    assert child is not None
    assert child["id"] == child_id


async def test_get_current_child_no_cookie_returns_none(temp_db_path: str):
    """get_current_child returns None when no cookie present."""
    from unittest.mock import MagicMock

    conn = _make_conn(temp_db_path)
    request = MagicMock()
    request.cookies = {}

    child = get_current_child(request, conn)
    assert child is None


async def test_get_current_child_no_pin_hash_in_result(
    temp_db_path: str, auth_client: AsyncClient, registered_child: dict
):
    """get_current_child strips pin_hash from the returned dict."""
    from unittest.mock import MagicMock

    child_id = registered_child["id"]
    token = create_child_session_token(child_id)
    conn = _make_conn(temp_db_path)

    request = MagicMock()
    request.cookies = {"kid_session_child": token}

    child = get_current_child(request, conn)
    assert child is not None
    assert "pin_hash" not in child
