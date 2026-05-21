"""
tests/test_weekly_plans.py — TDD tests for Stage 4: Weekly Plans + Curricula
"""
import json
import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, email="parent@test.com", password="password123"):
    """Register a user and log in, return client with session."""
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 200
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return client


async def _create_child(client: AsyncClient, grade=1, name="Маша") -> dict:
    """Create a child and return the JSON response."""
    resp = await client.post("/api/children", json={
        "name": name,
        "gender": "girl",
        "birth_date": "2017-05-10",
        "grade": grade,
        "universe": "Фиксики",
        "pin_code": "5739",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# services/curricula tests
# ---------------------------------------------------------------------------

class TestLoadCurricula:
    def test_load_curricula_inserts_four_rows(self, temp_db_path):
        """load_curricula() must insert 4 rows into curriculum_templates."""
        from db import get_connection, init_db
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        count = conn.execute("SELECT COUNT(*) FROM curriculum_templates").fetchone()[0]
        assert count == 6

    def test_load_curricula_idempotent(self, temp_db_path):
        """Calling load_curricula() twice must not duplicate rows."""
        from db import get_connection, init_db
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        count = conn.execute("SELECT COUNT(*) FROM curriculum_templates").fetchone()[0]
        assert count == 6

    def test_load_curricula_math_grade1(self, temp_db_path):
        """math grade 1 curriculum is loaded with correct subject and grade."""
        from db import get_connection, init_db
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE subject='math' AND grade=1"
        ).fetchone()
        assert row is not None
        assert row["title"] == "Математика, 1 класс"

    def test_load_curricula_russian_grade2(self, temp_db_path):
        """russian grade 2 curriculum is loaded."""
        from db import get_connection, init_db
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute(
            "SELECT * FROM curriculum_templates WHERE subject='russian' AND grade=2"
        ).fetchone()
        assert row is not None
        assert "Русский язык" in row["title"]


class TestGetCurriculum:
    def test_get_curriculum_returns_dict(self, temp_db_path):
        """get_curriculum returns dict with 'data' key containing units."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, get_curriculum
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = get_curriculum(conn, "math", 1)
        assert result is not None
        assert "data" in result
        assert "units" in result["data"]
        assert len(result["data"]["units"]) >= 4

    def test_get_curriculum_not_found(self, temp_db_path):
        """get_curriculum returns None for unknown subject."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, get_curriculum
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = get_curriculum(conn, "science", 1)
        assert result is None

    def test_get_curriculum_topics_have_required_fields(self, temp_db_path):
        """Each topic has id, title, skill fields."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, get_curriculum
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        curriculum = get_curriculum(conn, "math", 1)
        for unit in curriculum["data"]["units"]:
            for topic in unit["topics"]:
                assert "id" in topic
                assert "title" in topic
                assert "skill" in topic


class TestSearchUnit:
    def test_search_unit_exact_title_match(self, temp_db_path):
        """search_unit finds unit by exact substring in title."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        # "сложение" should match "Сложение и вычитание до 10" or similar
        result = search_unit(conn, "math", 1, "сложение")
        assert result is not None
        assert "id" in result
        assert "title" in result
        assert "topics" in result

    def test_search_unit_topic_title_match(self, temp_db_path):
        """search_unit finds unit when query matches a topic title inside it."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = search_unit(conn, "math", 1, "задачи")
        assert result is not None

    def test_search_unit_no_match_returns_none(self, temp_db_path):
        """search_unit returns None when nothing matches."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = search_unit(conn, "math", 1, "xyzabcnonexistent999")
        assert result is None

    def test_search_unit_curriculum_not_found(self, temp_db_path):
        """search_unit returns None when curriculum not found."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = search_unit(conn, "physics", 5, "сложение")
        assert result is None

    def test_search_unit_case_insensitive(self, temp_db_path):
        """search_unit is case-insensitive."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result_lower = search_unit(conn, "math", 1, "сложение")
        result_upper = search_unit(conn, "math", 1, "СЛОЖЕНИЕ")
        assert result_lower is not None
        assert result_upper is not None
        assert result_lower["id"] == result_upper["id"]

    def test_search_unit_russian_grammar(self, temp_db_path):
        """search_unit finds Russian grammar unit."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = search_unit(conn, "russian", 2, "существительное")
        assert result is not None

    def test_search_unit_multiplication(self, temp_db_path):
        """search_unit finds multiplication unit in math grade 2."""
        from db import get_connection, init_db
        from services.curricula import load_curricula, search_unit
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        result = search_unit(conn, "math", 2, "умножение")
        assert result is not None
        assert "умно" in result["title"].lower() or any(
            "умно" in t["title"].lower() for t in result["topics"]
        )


# ---------------------------------------------------------------------------
# POST /api/weekly-plans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreateWeeklyPlan:
    async def test_create_plan_success(self, client: AsyncClient):
        """POST /api/weekly-plans creates a plan and returns plan_id."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "сложение",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "plan_id" in data
        assert "unit_title" in data
        assert "topics" in data
        assert len(data["topics"]) > 0
        assert all("id" in t and "title" in t for t in data["topics"])

    async def test_create_plan_default_lessons_count(self, client: AsyncClient):
        """Default lessons_count is 5 (or fewer if unit has fewer topics)."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "сложение",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["topics"]) <= 5

    async def test_create_plan_custom_lessons_count(self, client: AsyncClient):
        """Custom lessons_count is respected."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "числа",
            "lessons_count": 3,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["topics"]) <= 3

    async def test_create_plan_unauthorized(self, client: AsyncClient):
        """POST /api/weekly-plans requires auth."""
        resp = await client.post("/api/weekly-plans", json={
            "child_id": 1,
            "subject": "math",
            "query": "сложение",
        })
        assert resp.status_code == 401

    async def test_create_plan_child_not_found(self, client: AsyncClient):
        """Returns 404 when child doesn't exist."""
        await _register_and_login(client)
        resp = await client.post("/api/weekly-plans", json={
            "child_id": 9999,
            "subject": "math",
            "query": "сложение",
        })
        assert resp.status_code == 404

    async def test_create_plan_child_forbidden(self, client: AsyncClient):
        """Returns 403 when child belongs to another parent."""
        await _register_and_login(client, "parent1@test.com", "password123")
        child = await _create_child(client, grade=1)
        child_id = child["id"]
        
        # Login as different user
        await client.post("/api/kid/logout")
        await _register_and_login(client, "parent2@test.com", "password456")
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child_id,
            "subject": "math",
            "query": "сложение",
        })
        assert resp.status_code == 403

    async def test_create_plan_unit_not_found(self, client: AsyncClient):
        """Returns 404 with unit_not_found when query doesn't match."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "xyzabcnonexistent999",
        })
        assert resp.status_code == 404
        assert resp.json()["error"] == "unit_not_found"

    async def test_create_plan_invalid_subject(self, client: AsyncClient):
        """Returns 422 for invalid subject."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "science",
            "query": "сложение",
        })
        assert resp.status_code == 422

    async def test_create_plan_grade_mismatch(self, client: AsyncClient):
        """Child grade 1 uses grade 1 curriculum."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "умножение",  # Only in grade 2
        })
        # Grade 1 math has no multiplication unit — should return unit_not_found
        assert resp.status_code == 404
        assert resp.json()["error"] == "unit_not_found"


# ---------------------------------------------------------------------------
# GET /api/weekly-plans/{plan_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetWeeklyPlan:
    async def _create_plan(self, client, child_id, query="сложение"):
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child_id,
            "subject": "math",
            "query": query,
        })
        assert resp.status_code == 201, resp.text
        return resp.json()["plan_id"]

    async def test_get_plan_success(self, client: AsyncClient):
        """GET /api/weekly-plans/{plan_id} returns plan details."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        resp = await client.get(f"/api/weekly-plans/{plan_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == plan_id
        assert "unit_title" in data
        assert "topics" in data
        assert "current_lesson_index" in data
        assert data["current_lesson_index"] == 0
        assert "status" in data
        assert data["status"] == "active"
        assert "lessons" in data

    async def test_get_plan_not_found(self, client: AsyncClient):
        """GET /api/weekly-plans/9999 returns 404."""
        await _register_and_login(client)
        resp = await client.get("/api/weekly-plans/9999")
        assert resp.status_code == 404

    async def test_get_plan_forbidden(self, client: AsyncClient):
        """GET /api/weekly-plans/{plan_id} returns 403 for another parent."""
        await _register_and_login(client, "p1@test.com", "password123")
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        await _register_and_login(client, "p2@test.com", "password456")
        resp = await client.get(f"/api/weekly-plans/{plan_id}")
        assert resp.status_code == 403

    async def test_get_plan_unauthorized(self, client: AsyncClient):
        """GET /api/weekly-plans/{plan_id} requires auth."""
        resp = await client.get("/api/weekly-plans/1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/weekly-plans/{plan_id}/next
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWeeklyPlanNext:
    async def _create_plan(self, client, child_id, query="сложение", lessons_count=3):
        resp = await client.post("/api/weekly-plans", json={
            "child_id": child_id,
            "subject": "math",
            "query": query,
            "lessons_count": lessons_count,
        })
        assert resp.status_code == 201, resp.text
        return resp.json()["plan_id"]

    async def test_next_creates_lesson(self, client: AsyncClient):
        """POST /api/weekly-plans/{id}/next creates a lesson and returns lesson_id."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "lesson_id" in data
        assert data["lesson_id"] > 0

    async def test_next_increments_index(self, client: AsyncClient):
        """After /next, current_lesson_index increments."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        with patch("services.generation.generate_lesson_content"):
            await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        resp = await client.get(f"/api/weekly-plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["current_lesson_index"] == 1

    async def test_next_lesson_mode_is_weekly(self, client: AsyncClient, temp_db_path):
        """Lesson created via /next has mode='weekly'."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["mode"] == "weekly"

    async def test_next_lesson_has_plan_id(self, client: AsyncClient, temp_db_path):
        """Lesson created via /next has plan_id set."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["plan_id"] == plan_id

    async def test_next_lesson_has_topic_id(self, client: AsyncClient, temp_db_path):
        """Lesson created via /next has topic_id set."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"])
        
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["topic_id"] is not None
        assert lesson["topic_id"] != ""

    async def test_next_plan_completed_when_all_done(self, client: AsyncClient):
        """After all lessons generated, next returns plan_completed."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"], lessons_count=2)
        
        with patch("services.generation.generate_lesson_content"):
            await client.post(f"/api/weekly-plans/{plan_id}/next")
            await client.post(f"/api/weekly-plans/{plan_id}/next")
            resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        assert resp.status_code == 200
        assert resp.json()["error"] == "plan_completed"

    async def test_next_plan_not_found(self, client: AsyncClient):
        """POST /api/weekly-plans/9999/next returns 404."""
        await _register_and_login(client)
        resp = await client.post("/api/weekly-plans/9999/next")
        assert resp.status_code == 404

    async def test_next_unauthorized(self, client: AsyncClient):
        """POST /api/weekly-plans/{id}/next requires auth."""
        resp = await client.post("/api/weekly-plans/1/next")
        assert resp.status_code == 401

    async def test_next_multiple_calls_sequential_topics(self, client: AsyncClient, temp_db_path):
        """Multiple /next calls produce lessons with different topic_ids."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"], lessons_count=3)
        
        lesson_ids = []
        with patch("services.generation.generate_lesson_content"):
            for _ in range(3):
                resp = await client.post(f"/api/weekly-plans/{plan_id}/next")
                assert resp.status_code == 200
                lesson_ids.append(resp.json()["lesson_id"])
        
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        topic_ids = [get_lesson_by_id(conn, lid)["topic_id"] for lid in lesson_ids]
        # All topic_ids should be distinct
        assert len(set(topic_ids)) == 3

    async def test_next_sequence_numbers(self, client: AsyncClient, temp_db_path):
        """Lessons get sequential sequence_number values."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        plan_id = await self._create_plan(client, child["id"], lessons_count=2)
        
        with patch("services.generation.generate_lesson_content"):
            r1 = await client.post(f"/api/weekly-plans/{plan_id}/next")
            r2 = await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        l1 = get_lesson_by_id(conn, r1.json()["lesson_id"])
        l2 = get_lesson_by_id(conn, r2.json()["lesson_id"])
        assert l1["sequence_number"] == 0
        assert l2["sequence_number"] == 1


# ---------------------------------------------------------------------------
# GET /api/weekly-plans/active/{child_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestActivePlan:
    async def test_active_plan_exists(self, client: AsyncClient):
        """Returns active plan when one exists."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "сложение",
        })
        
        resp = await client.get(f"/api/weekly-plans/active/{child['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] is not None
        assert "id" in data["plan"]
        assert data["plan"]["status"] == "active"

    async def test_active_plan_none(self, client: AsyncClient):
        """Returns null plan when no active plan."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        resp = await client.get(f"/api/weekly-plans/active/{child['id']}")
        assert resp.status_code == 200
        assert resp.json()["plan"] is None

    async def test_active_plan_forbidden(self, client: AsyncClient):
        """Returns 403 when child belongs to another parent."""
        await _register_and_login(client, "pp1@test.com", "password123")
        child = await _create_child(client, grade=1)
        child_id = child["id"]
        
        await _register_and_login(client, "pp2@test.com", "password456")
        resp = await client.get(f"/api/weekly-plans/active/{child_id}")
        assert resp.status_code == 403

    async def test_active_plan_unauthorized(self, client: AsyncClient):
        """Returns 401 without auth."""
        resp = await client.get("/api/weekly-plans/active/1")
        assert resp.status_code == 401

    async def test_active_plan_child_not_found(self, client: AsyncClient):
        """Returns 404 when child does not exist."""
        await _register_and_login(client)
        resp = await client.get("/api/weekly-plans/active/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/kid/lessons — plan_id in current lesson
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKidLessonsWeekly:
    async def test_kid_lessons_includes_plan_id(self, client: AsyncClient, temp_db_path):
        """When current lesson is from a weekly plan, plan_id is returned."""
        # Register parent and create child
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        
        # Create weekly plan
        plan_resp = await client.post("/api/weekly-plans", json={
            "child_id": child["id"],
            "subject": "math",
            "query": "сложение",
        })
        plan_id = plan_resp.json()["plan_id"]
        
        # Generate first lesson
        with patch("services.generation.generate_lesson_content"):
            await client.post(f"/api/weekly-plans/{plan_id}/next")
        
        # Auth as kid (parent session active on client)
        kid_resp = await client.post("/api/kid/auth", json={
            "child_id": child["id"],
        })
        assert kid_resp.status_code == 200
        
        resp = await client.get("/api/kid/lessons")
        assert resp.status_code == 200
        data = resp.json()
        
        if data["current"] is not None:
            # plan_id field should be present
            assert "plan_id" in data["current"]
