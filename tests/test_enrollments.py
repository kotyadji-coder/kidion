"""
tests/test_enrollments.py — TDD tests for Stage 5: Curriculum Enrollment
TL;DR: Tests for POST/GET/DELETE /api/enrollments, advance logic,
and auto-advance in lesson result. ~50 tests covering all paths.
"""
import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, email="parent@enroll.com", password="password123"):
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return client


async def _create_child(client: AsyncClient, grade=1, name="Тест") -> dict:
    resp = await client.post("/api/children", json={
        "name": name,
        "gender": "boy",
        "birth_date": "2017-05-10",
        "grade": grade,
        "universe": "Фиксики",
        "pin_code": "5739",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_enrollment(client: AsyncClient, child_id: int, subject="math", start_index=0) -> dict:
    resp = await client.post("/api/enrollments", json={
        "child_id": child_id,
        "subject": subject,
        "start_topic_index": start_index,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# DB Layer Tests
# ---------------------------------------------------------------------------

class TestEnrollmentDB:
    def test_create_enrollment_returns_id(self, temp_db_path):
        """create_enrollment returns a positive integer id."""
        from db import get_connection, init_db, create_enrollment
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        # Get a real curriculum id
        row = conn.execute("SELECT id FROM curriculum_templates WHERE subject='math' AND grade=1").fetchone()
        curriculum_id = row[0]
        # Need a child; create parent user first
        from db import create_user
        user_id = create_user(conn, "u@test.com", "hash", 30, "UCODE1", None)
        from db import create_child
        child = create_child(conn, user_id, "Вася", "boy", "2017-01-01", 1, "Фиксики", "hashpin")
        eid = create_enrollment(conn, child["id"], curriculum_id)
        assert isinstance(eid, int)
        assert eid > 0

    def test_get_enrollment_by_id(self, temp_db_path):
        """get_enrollment_by_id returns dict with expected fields."""
        from db import get_connection, init_db, create_enrollment, get_enrollment_by_id
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT id FROM curriculum_templates WHERE subject='math' AND grade=1").fetchone()
        curriculum_id = row[0]
        from db import create_user, create_child
        user_id = create_user(conn, "u2@test.com", "hash", 30, "UCODE2", None)
        child = create_child(conn, user_id, "Петя", "boy", "2017-01-01", 1, "Фиксики", "hashpin")
        eid = create_enrollment(conn, child["id"], curriculum_id)
        enrollment = get_enrollment_by_id(conn, eid)
        assert enrollment is not None
        assert enrollment["id"] == eid
        assert enrollment["child_id"] == child["id"]
        assert enrollment["curriculum_id"] == curriculum_id
        assert enrollment["current_topic_index"] == 0
        assert enrollment["retry_count"] == 0
        assert enrollment["status"] == "active"

    def test_get_enrollment_by_id_not_found(self, temp_db_path):
        """get_enrollment_by_id returns None for unknown id."""
        from db import get_connection, init_db, get_enrollment_by_id
        init_db(temp_db_path)
        conn = get_connection(temp_db_path)
        assert get_enrollment_by_id(conn, 9999) is None

    def test_get_active_enrollments(self, temp_db_path):
        """get_active_enrollments returns list of active enrollments."""
        from db import get_connection, init_db, create_enrollment, get_active_enrollments
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        rows = conn.execute("SELECT id FROM curriculum_templates LIMIT 2").fetchall()
        from db import create_user, create_child
        user_id = create_user(conn, "u3@test.com", "hash", 30, "UCODE3", None)
        child = create_child(conn, user_id, "Маша", "girl", "2017-01-01", 1, "Пони", "hashpin")
        create_enrollment(conn, child["id"], rows[0][0])
        create_enrollment(conn, child["id"], rows[1][0])
        result = get_active_enrollments(conn, child["id"])
        assert len(result) == 2

    def test_get_enrollment_by_subject(self, temp_db_path):
        """get_enrollment_by_subject finds active enrollment by subject."""
        from db import get_connection, init_db, create_enrollment, get_enrollment_by_subject
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT id FROM curriculum_templates WHERE subject='math' AND grade=1").fetchone()
        from db import create_user, create_child
        user_id = create_user(conn, "u4@test.com", "hash", 30, "UCODE4", None)
        child = create_child(conn, user_id, "Ваня", "boy", "2017-01-01", 1, "Фиксики", "hashpin")
        create_enrollment(conn, child["id"], row[0])
        found = get_enrollment_by_subject(conn, child["id"], "math")
        assert found is not None
        assert found["curriculum_id"] == row[0]

    def test_get_enrollment_by_subject_no_match(self, temp_db_path):
        """get_enrollment_by_subject returns None when no match."""
        from db import get_connection, init_db, get_enrollment_by_subject
        init_db(temp_db_path)
        conn = get_connection(temp_db_path)
        assert get_enrollment_by_subject(conn, 1, "math") is None

    def test_update_enrollment_progress(self, temp_db_path):
        """update_enrollment_progress updates all fields correctly."""
        from db import get_connection, init_db, create_enrollment, get_enrollment_by_id, update_enrollment_progress
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT id FROM curriculum_templates WHERE subject='math' AND grade=1").fetchone()
        from db import create_user, create_child
        user_id = create_user(conn, "u5@test.com", "hash", 30, "UCODE5", None)
        child = create_child(conn, user_id, "Саша", "boy", "2017-01-01", 1, "Фиксики", "hashpin")
        eid = create_enrollment(conn, child["id"], row[0])
        update_enrollment_progress(conn, eid, 5, 1, "completed")
        updated = get_enrollment_by_id(conn, eid)
        assert updated["current_topic_index"] == 5
        assert updated["retry_count"] == 1
        assert updated["status"] == "completed"

    def test_create_enrollment_with_start_index(self, temp_db_path):
        """create_enrollment respects start_topic_index."""
        from db import get_connection, init_db, create_enrollment, get_enrollment_by_id
        from services.curricula import load_curricula
        init_db(temp_db_path)
        load_curricula(temp_db_path)
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT id FROM curriculum_templates WHERE subject='math' AND grade=1").fetchone()
        from db import create_user, create_child
        user_id = create_user(conn, "u6@test.com", "hash", 30, "UCODE6", None)
        child = create_child(conn, user_id, "Коля", "boy", "2017-01-01", 1, "Фиксики", "hashpin")
        eid = create_enrollment(conn, child["id"], row[0], start_topic_index=5)
        enrollment = get_enrollment_by_id(conn, eid)
        assert enrollment["current_topic_index"] == 5


# ---------------------------------------------------------------------------
# POST /api/enrollments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreateEnrollment:
    async def test_create_enrollment_success(self, client: AsyncClient):
        """POST /api/enrollments creates enrollment and returns expected fields."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)

        resp = await client.post("/api/enrollments", json={
            "child_id": child["id"],
            "subject": "math",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "enrollment_id" in data
        assert "curriculum_title" in data
        assert "total_topics" in data
        assert data["total_topics"] > 0
        assert "current_topic_index" in data
        assert data["current_topic_index"] == 0

    async def test_create_enrollment_with_start_index(self, client: AsyncClient):
        """start_topic_index is respected."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)

        resp = await client.post("/api/enrollments", json={
            "child_id": child["id"],
            "subject": "math",
            "start_topic_index": 3,
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["current_topic_index"] == 3

    async def test_create_enrollment_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.post("/api/enrollments", json={"child_id": 1, "subject": "math"})
        assert resp.status_code == 401

    async def test_create_enrollment_child_not_found(self, client: AsyncClient):
        """Returns 404 when child doesn't exist."""
        await _register_and_login(client)
        resp = await client.post("/api/enrollments", json={"child_id": 9999, "subject": "math"})
        assert resp.status_code == 404

    async def test_create_enrollment_forbidden(self, client: AsyncClient):
        """Returns 403 when child belongs to another parent."""
        await _register_and_login(client, "en1@test.com", "password123")
        child = await _create_child(client)
        child_id = child["id"]

        await _register_and_login(client, "en2@test.com", "password456")
        resp = await client.post("/api/enrollments", json={"child_id": child_id, "subject": "math"})
        assert resp.status_code == 403

    async def test_create_enrollment_invalid_subject(self, client: AsyncClient):
        """Returns 422 for invalid subject."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        resp = await client.post("/api/enrollments", json={"child_id": child["id"], "subject": "science"})
        assert resp.status_code == 422

    async def test_create_enrollment_duplicate_active(self, client: AsyncClient):
        """Returns 409 when active enrollment for subject already exists."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        await _create_enrollment(client, child["id"], "math")
        # Second attempt
        resp = await client.post("/api/enrollments", json={"child_id": child["id"], "subject": "math"})
        assert resp.status_code == 409
        assert resp.json()["error"] == "enrollment_already_active"

    async def test_create_enrollment_different_subjects_allowed(self, client: AsyncClient):
        """Can have math and russian enrollments simultaneously."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        await _create_enrollment(client, child["id"], "math")
        resp = await client.post("/api/enrollments", json={"child_id": child["id"], "subject": "russian"})
        assert resp.status_code == 201

    async def test_create_enrollment_russian(self, client: AsyncClient):
        """Russian subject works correctly."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        resp = await client.post("/api/enrollments", json={"child_id": child["id"], "subject": "russian"})
        assert resp.status_code == 201
        data = resp.json()
        assert "Русский" in data["curriculum_title"] or data["total_topics"] > 0

    async def test_create_enrollment_grade2(self, client: AsyncClient):
        """Grade 2 child gets grade 2 curriculum."""
        await _register_and_login(client)
        child = await _create_child(client, grade=2)
        resp = await client.post("/api/enrollments", json={"child_id": child["id"], "subject": "math"})
        assert resp.status_code == 201
        data = resp.json()
        assert "2" in data["curriculum_title"]


# ---------------------------------------------------------------------------
# GET /api/enrollments/{enrollment_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetEnrollment:
    async def test_get_enrollment_success(self, client: AsyncClient):
        """GET /api/enrollments/{id} returns full details."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        resp = await client.get(f"/api/enrollments/{eid}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == eid
        assert "curriculum_title" in data
        assert "subject" in data
        assert "grade" in data
        assert data["grade"] == 1
        assert "total_topics" in data
        assert data["total_topics"] > 0
        assert "current_topic_index" in data
        assert data["current_topic_index"] == 0
        assert "status" in data
        assert data["status"] == "active"
        assert "current_topic" in data
        assert data["current_topic"] is not None
        assert "id" in data["current_topic"]
        assert "title" in data["current_topic"]
        assert "completed_topics" in data
        assert data["completed_topics"] == []

    async def test_get_enrollment_not_found(self, client: AsyncClient):
        """Returns 404 for unknown enrollment."""
        await _register_and_login(client)
        resp = await client.get("/api/enrollments/9999")
        assert resp.status_code == 404

    async def test_get_enrollment_forbidden(self, client: AsyncClient):
        """Returns 403 for another parent's enrollment."""
        await _register_and_login(client, "eg1@test.com", "password123")
        child = await _create_child(client)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        await _register_and_login(client, "eg2@test.com", "password456")
        resp = await client.get(f"/api/enrollments/{eid}")
        assert resp.status_code == 403

    async def test_get_enrollment_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.get("/api/enrollments/1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/enrollments/active/{child_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetActiveEnrollments:
    async def test_active_enrollments_list(self, client: AsyncClient):
        """Returns list of active enrollments."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        await _create_enrollment(client, child["id"], "math")
        await _create_enrollment(client, child["id"], "russian")

        resp = await client.get(f"/api/enrollments/active/{child['id']}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "enrollment_id" in item
            assert "subject" in item
            assert "curriculum_title" in item
            assert "total_topics" in item
            assert "current_topic_index" in item
            assert "status" in item

    async def test_active_enrollments_empty(self, client: AsyncClient):
        """Returns empty list when no active enrollments."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)

        resp = await client.get(f"/api/enrollments/active/{child['id']}")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_active_enrollments_child_not_found(self, client: AsyncClient):
        """Returns 404 when child doesn't exist."""
        await _register_and_login(client)
        resp = await client.get("/api/enrollments/active/9999")
        assert resp.status_code == 404

    async def test_active_enrollments_forbidden(self, client: AsyncClient):
        """Returns 403 for another parent's child."""
        await _register_and_login(client, "ea1@test.com", "password123")
        child = await _create_child(client)
        child_id = child["id"]

        await _register_and_login(client, "ea2@test.com", "password456")
        resp = await client.get(f"/api/enrollments/active/{child_id}")
        assert resp.status_code == 403

    async def test_active_enrollments_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.get("/api/enrollments/active/1")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/enrollments/{enrollment_id}/next
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEnrollmentNext:
    async def test_next_creates_lesson(self, client: AsyncClient):
        """POST /next creates lesson and returns lesson_id + topic_title."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "lesson_id" in data
        assert data["lesson_id"] > 0
        assert "topic_title" in data
        assert len(data["topic_title"]) > 0

    async def test_next_lesson_mode_is_curriculum(self, client: AsyncClient, temp_db_path):
        """Lesson created via /next has mode='curriculum'."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")

        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["mode"] == "curriculum"

    async def test_next_lesson_has_enrollment_id(self, client: AsyncClient, temp_db_path):
        """Lesson created via /next has enrollment_id set."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")

        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["enrollment_id"] == eid

    async def test_next_lesson_has_sequence_number(self, client: AsyncClient, temp_db_path):
        """Lesson sequence_number equals current_topic_index at time of creation."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"], start_index=0)
        eid = created["enrollment_id"]

        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")

        lesson_id = resp.json()["lesson_id"]
        from db import get_connection, get_lesson_by_id
        conn = get_connection(temp_db_path)
        lesson = get_lesson_by_id(conn, lesson_id)
        assert lesson["sequence_number"] == 0

    async def test_next_enrollment_completed(self, client: AsyncClient, temp_db_path):
        """Returns enrollment_completed when all topics done."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]
        total = created["total_topics"]

        # Jump to end via DB
        from db import get_connection, update_enrollment_progress
        conn = get_connection(temp_db_path)
        update_enrollment_progress(conn, eid, total, 0, "active")

        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")

        assert resp.status_code == 200
        assert resp.json().get("error") == "enrollment_completed"

    async def test_next_not_found(self, client: AsyncClient):
        """Returns 404 for unknown enrollment."""
        await _register_and_login(client)
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post("/api/enrollments/9999/next")
        assert resp.status_code == 404

    async def test_next_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.post("/api/enrollments/1/next")
        assert resp.status_code == 401

    async def test_next_forbidden(self, client: AsyncClient):
        """Returns 403 for another parent's enrollment."""
        await _register_and_login(client, "en1@test.com", "password123")
        child = await _create_child(client)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        await _register_and_login(client, "en2@test.com", "password456")
        with patch("services.generation.generate_lesson_content"):
            resp = await client.post(f"/api/enrollments/{eid}/next")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/enrollments/{enrollment_id}/advance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEnrollmentAdvance:
    async def _setup_enrollment_with_lesson_result(self, client, temp_db_path, correct_answers):
        """Helper: create enrollment, lesson, result. Returns (eid, enrollment_id)."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        # Create lesson directly in DB
        from db import get_connection, create_curriculum_lesson, create_lesson_result
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT curriculum_id FROM curriculum_enrollments WHERE id=?", (eid,)).fetchone()
        row2 = conn.execute("SELECT subject FROM curriculum_templates WHERE id=?", (row[0],)).fetchone()
        lesson_id = create_curriculum_lesson(
            conn, child["id"], "m1-01", "Счёт", row2["subject"], eid, 0
        )
        stars = 3 if correct_answers == 5 else (2 if correct_answers >= 3 else 1)
        create_lesson_result(conn, lesson_id, child["id"], correct_answers, 5, stars)
        return eid, child["id"]

    async def test_advance_next_topic_on_good_result(self, client: AsyncClient, temp_db_path):
        """≥3/5 correct → next_action='next_topic', index increments."""
        eid, _ = await self._setup_enrollment_with_lesson_result(client, temp_db_path, 4)

        resp = await client.post(f"/api/enrollments/{eid}/advance")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["next_action"] == "next_topic"
        assert data["current_topic_index"] == 1
        assert data["retry_count"] == 0

    async def test_advance_retry_on_bad_result_first_time(self, client: AsyncClient, temp_db_path):
        """<3/5 correct, retry_count=0 → next_action='retry', index stays."""
        eid, _ = await self._setup_enrollment_with_lesson_result(client, temp_db_path, 2)

        resp = await client.post(f"/api/enrollments/{eid}/advance")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["next_action"] == "retry"
        assert data["current_topic_index"] == 0
        assert data["retry_count"] == 1

    async def test_advance_retry_on_bad_result_second_time(self, client: AsyncClient, temp_db_path):
        """<3/5 correct, retry_count=1 → next_action='retry', retry_count=2."""
        eid, _ = await self._setup_enrollment_with_lesson_result(client, temp_db_path, 1)
        # Pre-set retry_count=1
        from db import get_connection, update_enrollment_progress
        conn = get_connection(temp_db_path)
        update_enrollment_progress(conn, eid, 0, 1, "active")

        resp = await client.post(f"/api/enrollments/{eid}/advance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_action"] == "retry"
        assert data["retry_count"] == 2

    async def test_advance_force_next_after_two_retries(self, client: AsyncClient, temp_db_path):
        """<3/5 correct, retry_count=2 → advance anyway, next_action='next_topic'."""
        eid, _ = await self._setup_enrollment_with_lesson_result(client, temp_db_path, 1)
        from db import get_connection, update_enrollment_progress
        conn = get_connection(temp_db_path)
        update_enrollment_progress(conn, eid, 0, 2, "active")

        resp = await client.post(f"/api/enrollments/{eid}/advance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_action"] == "next_topic"
        assert data["current_topic_index"] == 1
        assert data["retry_count"] == 0

    async def test_advance_completed_on_last_topic(self, client: AsyncClient, temp_db_path):
        """Advancing past last topic → next_action='completed', status='completed'."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]
        total = created["total_topics"]

        # Set to second-to-last topic
        from db import get_connection, update_enrollment_progress, create_curriculum_lesson, create_lesson_result
        conn = get_connection(temp_db_path)
        update_enrollment_progress(conn, eid, total - 1, 0, "active")
        row = conn.execute("SELECT curriculum_id FROM curriculum_enrollments WHERE id=?", (eid,)).fetchone()
        row2 = conn.execute("SELECT subject FROM curriculum_templates WHERE id=?", (row[0],)).fetchone()
        lesson_id = create_curriculum_lesson(conn, child["id"], "m1-last", "Последняя", row2["subject"], eid, total - 1)
        create_lesson_result(conn, lesson_id, child["id"], 5, 5, 3)

        resp = await client.post(f"/api/enrollments/{eid}/advance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_action"] == "completed"

        # Verify DB status
        from db import get_enrollment_by_id
        enrollment = get_enrollment_by_id(conn, eid)
        assert enrollment["status"] == "completed"

    async def test_advance_not_found(self, client: AsyncClient):
        """Returns 404 for unknown enrollment."""
        await _register_and_login(client)
        resp = await client.post("/api/enrollments/9999/advance")
        assert resp.status_code == 404

    async def test_advance_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.post("/api/enrollments/1/advance")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/enrollments/{enrollment_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDeleteEnrollment:
    async def test_delete_enrollment_pauses(self, client: AsyncClient, temp_db_path):
        """DELETE sets status to 'paused'."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        resp = await client.delete(f"/api/enrollments/{eid}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["ok"] is True

        # Verify DB
        from db import get_connection, get_enrollment_by_id
        conn = get_connection(temp_db_path)
        enrollment = get_enrollment_by_id(conn, eid)
        assert enrollment["status"] == "paused"

    async def test_delete_enrollment_not_found(self, client: AsyncClient):
        """Returns 404 for unknown enrollment."""
        await _register_and_login(client)
        resp = await client.delete("/api/enrollments/9999")
        assert resp.status_code == 404

    async def test_delete_enrollment_forbidden(self, client: AsyncClient):
        """Returns 403 for another parent's enrollment."""
        await _register_and_login(client, "del1@test.com", "password123")
        child = await _create_child(client)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        await _register_and_login(client, "del2@test.com", "password456")
        resp = await client.delete(f"/api/enrollments/{eid}")
        assert resp.status_code == 403

    async def test_delete_enrollment_unauthorized(self, client: AsyncClient):
        """Requires auth."""
        resp = await client.delete("/api/enrollments/1")
        assert resp.status_code == 401

    async def test_delete_removes_from_active(self, client: AsyncClient):
        """After delete, enrollment no longer appears in active list."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        await client.delete(f"/api/enrollments/{eid}")

        resp = await client.get(f"/api/enrollments/active/{child['id']}")
        assert resp.status_code == 200
        active = resp.json()
        assert not any(e["enrollment_id"] == eid for e in active)


# ---------------------------------------------------------------------------
# POST /api/lessons/{lesson_id}/result — auto-advance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLessonResultAutoAdvance:
    async def _setup(self, client, temp_db_path):
        """Setup: parent, child, enrollment, curriculum lesson."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)
        created = await _create_enrollment(client, child["id"])
        eid = created["enrollment_id"]

        # Create a curriculum lesson directly in DB
        from db import get_connection, create_curriculum_lesson, update_lesson_content
        conn = get_connection(temp_db_path)
        row = conn.execute("SELECT curriculum_id FROM curriculum_enrollments WHERE id=?", (eid,)).fetchone()
        row2 = conn.execute("SELECT subject FROM curriculum_templates WHERE id=?", (row[0],)).fetchone()
        lesson_id = create_curriculum_lesson(
            conn, child["id"], "m1-01", "Счёт предметов", row2["subject"], eid, 0
        )
        update_lesson_content(conn, lesson_id, "/content/test.json", None, "ready")
        return eid, lesson_id, child["id"]

    async def test_result_includes_next_action(self, client: AsyncClient, temp_db_path):
        """Lesson result for curriculum lesson includes next_action field."""
        eid, lesson_id, child_id = await self._setup(client, temp_db_path)

        resp = await client.post(f"/api/lessons/{lesson_id}/result", json={
            "correct_answers": 4,
            "total_answers": 5,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "next_action" in data
        assert data["next_action"] in ("next_topic", "retry", "completed")

    async def test_result_next_topic_on_good_score(self, client: AsyncClient, temp_db_path):
        """4/5 correct → next_action='next_topic'."""
        eid, lesson_id, _ = await self._setup(client, temp_db_path)

        resp = await client.post(f"/api/lessons/{lesson_id}/result", json={"correct_answers": 4})
        assert resp.json()["next_action"] == "next_topic"

    async def test_result_retry_on_bad_score(self, client: AsyncClient, temp_db_path):
        """2/5 correct → next_action='retry'."""
        eid, lesson_id, _ = await self._setup(client, temp_db_path)

        resp = await client.post(f"/api/lessons/{lesson_id}/result", json={"correct_answers": 2})
        assert resp.json()["next_action"] == "retry"

    async def test_result_no_next_action_for_on_demand(self, client: AsyncClient, temp_db_path):
        """Lesson result for on_demand lesson has no next_action."""
        await _register_and_login(client)
        child = await _create_child(client, grade=1)

        # Create an on_demand lesson directly
        from db import get_connection, create_lesson, update_lesson_content
        conn = get_connection(temp_db_path)
        lesson_id = create_lesson(conn, child["id"], "on_demand", "Тест", "math")
        update_lesson_content(conn, lesson_id, "/content/test.json", None, "ready")

        resp = await client.post(f"/api/lessons/{lesson_id}/result", json={"correct_answers": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert "next_action" not in data

    async def test_result_advances_enrollment_index(self, client: AsyncClient, temp_db_path):
        """After 5/5 correct, enrollment current_topic_index increments."""
        eid, lesson_id, _ = await self._setup(client, temp_db_path)

        await client.post(f"/api/lessons/{lesson_id}/result", json={"correct_answers": 5})

        from db import get_connection, get_enrollment_by_id
        conn = get_connection(temp_db_path)
        enrollment = get_enrollment_by_id(conn, eid)
        assert enrollment["current_topic_index"] == 1
        assert enrollment["retry_count"] == 0

    async def test_result_completed_returns_existing_fields(self, client: AsyncClient, temp_db_path):
        """Response still includes stars, difficulty_level, current_streak."""
        eid, lesson_id, _ = await self._setup(client, temp_db_path)

        resp = await client.post(f"/api/lessons/{lesson_id}/result", json={"correct_answers": 3})
        data = resp.json()
        assert "stars" in data
        assert "difficulty_level" in data
        assert "current_streak" in data
        assert data["ok"] is True
