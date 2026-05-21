"""
Tests for Этап 3: Kid Interface

Covers:
- GET /api/kid/me
- GET /api/kid/lessons
- GET /api/kid/lessons/{id}
- GET /kid (redirect logic)
- GET /kid/login
- GET /kid/home
- GET /kid/lesson/{id}
- GET /kid/result/{id}
- POST /api/kid/logout
"""

import os
import sqlite3
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def parent_client(client: AsyncClient) -> AsyncClient:
    """Authenticated parent client with a registered+logged-in user."""
    resp = await client.post("/auth/register", json={"email": "parent@example.com", "password": "password123"})
    assert resp.status_code == 200
    resp = await client.post("/auth/login", json={"email": "parent@example.com", "password": "password123"})
    assert resp.status_code == 200
    return client


@pytest_asyncio.fixture
async def child_profile(parent_client: AsyncClient) -> dict:
    """Create a child profile for the parent."""
    resp = await parent_client.post("/api/children", json={
        "name": "Маша",
        "gender": "girl",
        "birth_date": "2017-06-15",
        "grade": 1,
        "universe": "Холодное сердце",
        "pin_code": "5739",
    })
    assert resp.status_code == 201
    data = resp.json()
    data["_pin"] = "5739"
    return data


@pytest_asyncio.fixture
async def kid_client(parent_client: AsyncClient, child_profile: dict) -> AsyncClient:
    """A client authenticated as the child (has kid_session_child cookie)."""
    # Mark child as onboarded so /kid/home doesn't redirect to /kid/onboarding
    from db import update_child_character_name
    from main import get_db_connection
    conn = get_db_connection()
    update_child_character_name(conn, child_profile["id"], "Искатель")

    # Auth child via parent session (no PIN needed)
    resp = await parent_client.post("/api/kid/auth", json={
        "child_id": child_profile["id"],
    })
    assert resp.status_code == 200
    yield parent_client


@pytest_asyncio.fixture
async def lesson_with_result(parent_client: AsyncClient, child_profile: dict) -> dict:
    """Create a lesson and submit a result for it. Returns lesson data with stars."""
    with patch("services.generation.generate_lesson_content"):
        resp = await parent_client.post("/api/lessons/generate", json={
            "child_id": child_profile["id"],
            "topic": "Буквы А и Б",
            "subject": "русский",
        })
    assert resp.status_code == 200
    lesson_id = resp.json()["lesson_id"]

    # Submit result as parent
    resp = await parent_client.post(f"/api/lessons/{lesson_id}/result", json={
        "correct_answers": 4,
        "total_answers": 5,
    })
    assert resp.status_code == 200

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT * FROM lesson_results WHERE lesson_id = ?", (lesson_id,))
    row = cursor.fetchone()
    conn.close()

    return {"id": lesson_id, "stars": resp.json()["stars"], "result_row": row}


@pytest_asyncio.fixture
async def pending_lesson(parent_client: AsyncClient, child_profile: dict) -> dict:
    """Create a pending lesson (no result submitted)."""
    with patch("services.generation.generate_lesson_content"):
        resp = await parent_client.post("/api/lessons/generate", json={
            "child_id": child_profile["id"],
            "topic": "Числа до 10",
            "subject": "математика",
        })
    assert resp.status_code == 200
    return {"id": resp.json()["lesson_id"]}


# ---------------------------------------------------------------------------
# GET /api/kid/me
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_me_success(kid_client: AsyncClient, child_profile: dict):
    """Child can get their own profile."""
    resp = await kid_client.get("/api/kid/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == child_profile["id"]
    assert data["name"] == "Маша"
    assert data["grade"] == 1
    assert data["universe"] == "Холодное сердце"
    assert "difficulty_level" in data
    assert "current_streak" in data
    assert "longest_streak" in data


@pytest.mark.asyncio
async def test_kid_me_no_auth(client: AsyncClient):
    """Unauthenticated request returns 401."""
    resp = await client.get("/api/kid/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# GET /api/kid/lessons
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_lessons_empty(kid_client: AsyncClient):
    """Returns empty lists when no lessons exist."""
    resp = await kid_client.get("/api/kid/lessons")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] is None
    assert data["history"] == []


@pytest.mark.asyncio
async def test_kid_lessons_with_pending(kid_client: AsyncClient, pending_lesson: dict):
    """Returns pending lesson as current."""
    resp = await kid_client.get("/api/kid/lessons")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] is not None
    assert data["current"]["id"] == pending_lesson["id"]
    assert data["current"]["stars"] is None
    assert data["history"] == []


@pytest.mark.asyncio
async def test_kid_lessons_with_history(kid_client: AsyncClient, lesson_with_result: dict):
    """Completed lessons show in history with stars."""
    resp = await kid_client.get("/api/kid/lessons")
    assert resp.status_code == 200
    data = resp.json()
    # Lesson with result moves to history
    assert len(data["history"]) == 1
    assert data["history"][0]["id"] == lesson_with_result["id"]
    assert data["history"][0]["stars"] == lesson_with_result["stars"]


@pytest.mark.asyncio
async def test_kid_lessons_no_auth(client: AsyncClient):
    """Unauthenticated request returns 401."""
    resp = await client.get("/api/kid/lessons")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


# ---------------------------------------------------------------------------
# GET /api/kid/lessons/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_lesson_detail_success(kid_client: AsyncClient, pending_lesson: dict):
    """Child can get their lesson details."""
    resp = await kid_client.get(f"/api/kid/lessons/{pending_lesson['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pending_lesson["id"]
    assert "topic_title" in data
    assert "subject" in data
    assert "status" in data
    assert "content_url" in data
    assert "print_url" in data


@pytest.mark.asyncio
async def test_kid_lesson_detail_no_auth(client: AsyncClient, pending_lesson: dict):
    """Unauthenticated request returns 401."""
    resp = await client.get(f"/api/kid/lessons/{pending_lesson['id']}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_kid_lesson_detail_wrong_child(child_profile: dict, pending_lesson: dict):
    """Child cannot access another child's lesson."""
    # Create a second parent + child, auth as that child
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as parent2:
        await parent2.post("/auth/register", json={"email": "parent2@example.com", "password": "pass12345"})
        await parent2.post("/auth/login", json={"email": "parent2@example.com", "password": "pass12345"})
        resp = await parent2.post("/api/children", json={
            "name": "Ваня",
            "gender": "boy",
            "birth_date": "2016-01-01",
            "grade": 2,
            "universe": "Лего",
        })
        assert resp.status_code == 201
        child2_id = resp.json()["id"]
        resp = await parent2.post("/api/kid/auth", json={"child_id": child2_id})
        assert resp.status_code == 200
        resp = await parent2.get(f"/api/kid/lessons/{pending_lesson['id']}")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_kid_lesson_detail_not_found(kid_client: AsyncClient):
    """Returns 404 for non-existent lesson."""
    resp = await kid_client.get("/api/kid/lessons/99999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /kid (redirect logic)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_root_no_auth_redirects_to_login(client: AsyncClient):
    """Without cookie, /kid redirects to /kid/login."""
    resp = await client.get("/kid", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_kid_root_with_auth_redirects_to_home(kid_client: AsyncClient):
    """With valid kid cookie, /kid redirects to /kid/home."""
    resp = await kid_client.get("/kid", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/home" in resp.headers["location"]


# ---------------------------------------------------------------------------
# GET /kid/login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_login_page_renders(client: AsyncClient):
    """Login page renders successfully without child_id."""
    resp = await client.get("/kid/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_kid_login_page_with_child_id(client: AsyncClient, child_profile: dict):
    """Login page renders with child name when child_id is provided."""
    resp = await client.get(f"/kid/login?child_id={child_profile['id']}")
    assert resp.status_code == 200
    assert "Маша" in resp.text


@pytest.mark.asyncio
async def test_kid_login_page_unknown_child_id(client: AsyncClient):
    """Login page renders generically for unknown child_id."""
    resp = await client.get("/kid/login?child_id=99999")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /kid/home
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_home_no_auth_redirects(client: AsyncClient):
    """Without cookie, /kid/home redirects to login."""
    resp = await client.get("/kid/home", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_kid_home_renders(kid_client: AsyncClient):
    """With valid kid cookie, /kid/home renders."""
    resp = await kid_client.get("/kid/home")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Маша" in resp.text


# ---------------------------------------------------------------------------
# GET /kid/lesson/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_lesson_page_no_auth_redirects(client: AsyncClient, pending_lesson: dict):
    """Without cookie, /kid/lesson/{id} redirects to login."""
    resp = await client.get(f"/kid/lesson/{pending_lesson['id']}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_kid_lesson_page_renders(kid_client: AsyncClient, pending_lesson: dict):
    """With valid kid cookie and correct lesson, page renders."""
    resp = await kid_client.get(f"/kid/lesson/{pending_lesson['id']}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_kid_lesson_page_wrong_child_redirects(kid_client: AsyncClient):
    """Kid accessing another child's lesson page gets redirected to home."""
    # Create a lesson for a different child
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as other_parent:
        await other_parent.post("/auth/register", json={"email": "other3@example.com", "password": "pass12345"})
        await other_parent.post("/auth/login", json={"email": "other3@example.com", "password": "pass12345"})
        resp = await other_parent.post("/api/children", json={
            "name": "Стёпа",
            "gender": "boy",
            "birth_date": "2015-07-01",
            "grade": 3,
            "universe": "Человек-паук",
            "pin_code": "8274",
        })
        other_child_id = resp.json()["id"]
        with patch("services.generation.generate_lesson_content"):
            resp = await other_parent.post("/api/lessons/generate", json={
                "child_id": other_child_id,
                "topic": "Дроби",
            })
        other_lesson_id = resp.json()["lesson_id"]

    resp = await kid_client.get(f"/kid/lesson/{other_lesson_id}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/home" in resp.headers["location"]


# ---------------------------------------------------------------------------
# GET /kid/result/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_result_page_no_auth_redirects(client: AsyncClient, lesson_with_result: dict):
    """Without cookie, /kid/result/{id} redirects to login."""
    resp = await client.get(f"/kid/result/{lesson_with_result['id']}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/kid/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_kid_result_page_renders(kid_client: AsyncClient, lesson_with_result: dict):
    """With valid kid cookie and result, page renders."""
    resp = await kid_client.get(f"/kid/result/{lesson_with_result['id']}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_kid_result_page_no_result_still_renders(kid_client: AsyncClient, pending_lesson: dict):
    """Result page for lesson without result still renders (shows 0 stars or empty state)."""
    resp = await kid_client.get(f"/kid/result/{pending_lesson['id']}")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/kid/logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_logout(kid_client: AsyncClient):
    """Logout clears kid_session_child cookie."""
    resp = await kid_client.post("/api/kid/logout")
    assert resp.status_code == 200
    # After logout, /api/kid/me should return 401
    resp = await kid_client.get("/api/kid/me")
    assert resp.status_code == 401
