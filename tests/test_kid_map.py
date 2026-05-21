"""
tests/test_kid_map.py
TDD tests for: kid subjects endpoint, kid lesson map, kid lesson start.
All tests should FAIL before implementation (Red phase).
"""
import os
import sqlite3

import pytest
import pytest_asyncio
from httpx import AsyncClient


def get_db_path():
    return os.environ.get("DATABASE_PATH", "./kidion.db")


def direct_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Fixtures: kid session
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def kid_session(auth_client: AsyncClient):
    """
    Create a child enrolled in math, add crystals to parent, log in as kid.
    Returns: {"child_id": int, "kid_client": AsyncClient}
    """
    # Add crystals
    me_resp = await auth_client.get("/auth/me")
    user_id = me_resp.json()["id"]
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET crystals=200 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    # Create child
    child_resp = await auth_client.post("/api/children", json={
        "name": "Карта",
        "gender": "girl",
        "birth_date": "2018-09-01",
        "grade": 1,
        "universe": "Принцессы",
        "pin_code": "7493"
    })
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    # Enroll
    await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )

    # Login as kid
    login_resp = await auth_client.post("/api/kid/auth", json={
        "child_id": child_id,
    })
    assert login_resp.status_code == 200, f"Kid login failed: {login_resp.text}"

    return {"child_id": child_id, "kid_client": auth_client}


# ---------------------------------------------------------------------------
# GET /api/kid/me — stars field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_me_includes_stars(kid_session: dict):
    """GET /api/kid/me should include stars field."""
    client = kid_session["kid_client"]
    resp = await client.get("/api/kid/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "stars" in data, f"stars field missing in response: {data}"
    assert isinstance(data["stars"], int)


# ---------------------------------------------------------------------------
# GET /api/kid/subjects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_subjects_returns_enrolled_subjects(kid_session: dict):
    """GET /api/kid/subjects returns list with math enrolled."""
    client = kid_session["kid_client"]
    resp = await client.get("/api/kid/subjects")
    assert resp.status_code == 200, f"Failed: {resp.text}"
    data = resp.json()
    assert "subjects" in data
    assert len(data["subjects"]) >= 1

    math_subj = next((s for s in data["subjects"] if s["subject"] == "math"), None)
    assert math_subj is not None, "math not in subjects list"
    assert math_subj["total_lessons"] == 60
    assert math_subj["completed_lessons"] == 0


@pytest.mark.asyncio
async def test_kid_subjects_requires_auth(client: AsyncClient):
    """GET /api/kid/subjects without session returns 401."""
    resp = await client.get("/api/kid/subjects")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/kid/subject/{subject}/map
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_map_returns_correct_structure(kid_session: dict):
    """GET /api/kid/subject/math/map returns topic/lesson structure."""
    client = kid_session["kid_client"]
    resp = await client.get("/api/kid/subject/math/map")
    assert resp.status_code == 200, f"Map failed: {resp.text}"
    data = resp.json()

    assert data["subject"] == "math"
    assert data["total_lessons"] == 60
    assert "topics" in data
    assert len(data["topics"]) == 12

    first_topic = data["topics"][0]
    assert len(first_topic["lessons"]) == 5
    assert first_topic["lessons"][0]["status"] == "available"
    for lesson in first_topic["lessons"][1:]:
        assert lesson["status"] == "locked"


@pytest.mark.asyncio
async def test_kid_map_requires_auth(client: AsyncClient):
    """GET /api/kid/subject/math/map without session returns 401."""
    resp = await client.get("/api/kid/subject/math/map")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_kid_map_no_enrollment_returns_404(auth_client: AsyncClient):
    """GET /api/kid/subject/math/map for child not enrolled returns 404."""
    # Create a child but DON'T enroll
    child_resp = await auth_client.post("/api/children", json={
        "name": "Неактивный",
        "gender": "boy",
        "birth_date": "2019-01-01",
        "grade": 1,
        "universe": "Марс",
        "pin_code": "8274"
    })
    child_id = child_resp.json()["id"]

    # Login as kid
    login_resp = await auth_client.post("/api/kid/auth", json={
        "child_id": child_id,
    })
    assert login_resp.status_code == 200

    resp = await auth_client.get("/api/kid/subject/math/map")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/kid/lessons/{curriculum_lesson_id}/start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kid_start_available_lesson(kid_session: dict):
    """POST /api/kid/lessons/{id}/start for an available lesson returns ok."""
    client = kid_session["kid_client"]
    child_id = kid_session["child_id"]

    # Get curriculum_lesson_id for lesson 1 of topic 1
    conn = direct_db()
    cl = conn.execute(
        """SELECT cl.id FROM curriculum_lessons cl
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE ct.subject='math' AND ct.grade=1 AND ct.theme_order=1
           AND cl.lesson_order=1"""
    ).fetchone()
    conn.close()
    cl_id = cl["id"]

    resp = await client.post(f"/api/kid/lessons/{cl_id}/start")
    assert resp.status_code == 200, f"Start lesson failed: {resp.text}"
    data = resp.json()
    assert data["ok"] is True
    assert "lesson_id" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_kid_start_locked_lesson_returns_400(kid_session: dict):
    """POST /api/kid/lessons/{id}/start for a locked lesson returns 400."""
    client = kid_session["kid_client"]

    # Get curriculum_lesson_id for lesson 2 of topic 1 (should be locked)
    conn = direct_db()
    cl = conn.execute(
        """SELECT cl.id FROM curriculum_lessons cl
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE ct.subject='math' AND ct.grade=1 AND ct.theme_order=1
           AND cl.lesson_order=2"""
    ).fetchone()
    conn.close()
    cl_id = cl["id"]

    resp = await client.post(f"/api/kid/lessons/{cl_id}/start")
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_kid_start_lesson_deducts_parent_crystals(kid_session: dict):
    """Starting a lesson deducts 10 crystals from parent."""
    client = kid_session["kid_client"]
    child_id = kid_session["child_id"]

    # Find parent's user_id via DB
    conn = direct_db()
    child = conn.execute("SELECT parent_id FROM children WHERE id=?", (child_id,)).fetchone()
    parent_id = child["parent_id"]
    crystals_before = conn.execute(
        "SELECT crystals FROM users WHERE id=?", (parent_id,)
    ).fetchone()[0]

    cl = conn.execute(
        """SELECT cl.id FROM curriculum_lessons cl
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE ct.subject='math' AND ct.grade=1 AND ct.theme_order=1
           AND cl.lesson_order=1"""
    ).fetchone()
    conn.close()

    await client.post(f"/api/kid/lessons/{cl['id']}/start")

    conn = direct_db()
    crystals_after = conn.execute(
        "SELECT crystals FROM users WHERE id=?", (parent_id,)
    ).fetchone()[0]
    conn.close()

    assert crystals_after == crystals_before - 20
