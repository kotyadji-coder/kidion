"""
tests/test_curriculum_new.py
TDD tests for: DB seed data, subject enrollment, stars, progression, skip test.
All tests should FAIL before implementation (Red phase).
"""
import os
import sqlite3

import pytest
import pytest_asyncio

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db_path():
    return os.environ.get("DATABASE_PATH", "./kidion.db")


def direct_db():
    """Return a direct sqlite3 connection to the test DB."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def enrolled_child(auth_client: AsyncClient) -> dict:
    """Create a child and enroll in math grade 1."""
    # Create child
    child_resp = await auth_client.post("/api/children", json={
        "name": "Тестик",
        "gender": "boy",
        "birth_date": "2018-01-01",
        "grade": 1,
        "universe": "Космос",
        "pin_code":"5739"
    })
    assert child_resp.status_code == 201, f"Child creation failed: {child_resp.text}"
    child_id = child_resp.json()["id"]

    # Enroll in math
    enroll_resp = await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )
    assert enroll_resp.status_code == 200, f"Enrollment failed: {enroll_resp.text}"
    return {"child_id": child_id, "client": auth_client}


@pytest_asyncio.fixture
async def child_with_crystals(auth_client: AsyncClient) -> dict:
    """Parent with 200 crystals + a child enrolled in math."""
    # Add crystals directly
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    me_resp = await auth_client.get("/auth/me")
    user_id = me_resp.json()["id"]
    conn.execute("UPDATE users SET crystals = 200 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Create child
    child_resp = await auth_client.post("/api/children", json={
        "name": "Звёздочка",
        "gender": "girl",
        "birth_date": "2018-05-15",
        "grade": 1,
        "universe": "Феи",
        "pin_code":"5947"
    })
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    # Enroll
    await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )
    return {"child_id": child_id, "user_id": user_id}


# ---------------------------------------------------------------------------
# Seed data tests
# ---------------------------------------------------------------------------

def test_seed_math_grade1_creates_12_topics(client):
    """After DB init, curriculum_topics should have 12 rows for math grade 1."""
    conn = direct_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM curriculum_topics WHERE subject='math' AND grade=1"
    ).fetchone()[0]
    conn.close()
    assert count == 12, f"Expected 12 topics, got {count}"


def test_seed_math_grade1_creates_60_lessons(client):
    """After DB init, curriculum_lessons should have 60 rows for math grade 1."""
    conn = direct_db()
    count = conn.execute(
        """SELECT COUNT(*) FROM curriculum_lessons cl
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE ct.subject = 'math' AND ct.grade = 1"""
    ).fetchone()[0]
    conn.close()
    assert count == 60, f"Expected 60 lessons, got {count}"


def test_seed_idempotent(client):
    """Running seed twice should not create duplicate rows."""
    from db import get_connection
    db_path = get_db_path()
    conn = get_connection(db_path)
    from db import _init_schema
    _init_schema(conn)  # run again
    count = conn.execute(
        "SELECT COUNT(*) FROM curriculum_topics WHERE subject='math' AND grade=1"
    ).fetchone()[0]
    assert count == 12


# ---------------------------------------------------------------------------
# Enrollment tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enroll_subject_creates_60_progress_rows(auth_client: AsyncClient):
    """POST /api/children/{id}/enroll-subject creates 60 child_lesson_progress rows."""
    child_resp = await auth_client.post("/api/children", json={
        "name": "Прогресс",
        "gender": "boy",
        "birth_date": "2019-01-01",
        "grade": 1,
        "universe": "Марс",
        "pin_code":"6381"
    })
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["total_lessons"] == 60

    conn = direct_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id = ?",
        (child_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 60


@pytest.mark.asyncio
async def test_enroll_subject_first_lesson_available(auth_client: AsyncClient):
    """After enrollment, exactly 1 lesson should be 'available' (lesson 1 of topic 1)."""
    child_resp = await auth_client.post("/api/children", json={
        "name": "Первый",
        "gender": "boy",
        "birth_date": "2019-01-01",
        "grade": 1,
        "universe": "Солнце",
        "pin_code":"7429"
    })
    child_id = child_resp.json()["id"]

    await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )

    conn = direct_db()
    available_count = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()[0]
    locked_count = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=? AND status='locked'",
        (child_id,)
    ).fetchone()[0]
    conn.close()

    assert available_count == 1, f"Expected 1 available, got {available_count}"
    assert locked_count == 59, f"Expected 59 locked, got {locked_count}"


@pytest.mark.asyncio
async def test_enroll_subject_idempotent(auth_client: AsyncClient):
    """Enrolling twice should return 200 and not duplicate rows."""
    child_resp = await auth_client.post("/api/children", json={
        "name": "Дважды",
        "gender": "girl",
        "birth_date": "2019-01-01",
        "grade": 1,
        "universe": "Луна",
        "pin_code":"3849"
    })
    child_id = child_resp.json()["id"]

    await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )
    resp2 = await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "math", "grade": 1}
    )
    assert resp2.status_code == 200

    conn = direct_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=?",
        (child_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 60  # No duplicates


@pytest.mark.asyncio
async def test_enroll_subject_no_curriculum_returns_400(auth_client: AsyncClient):
    """Enrolling in a subject with no seed data returns 400."""
    child_resp = await auth_client.post("/api/children", json={
        "name": "Нет данных",
        "gender": "boy",
        "birth_date": "2019-01-01",
        "grade": 3,
        "universe": "Роботы",
        "pin_code":"4917"
    })
    child_id = child_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/children/{child_id}/enroll-subject",
        json={"subject": "world", "grade": 1}  # No seed data
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Stars tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stars_awarded_on_lesson_result(enrolled_child: dict):
    """Submitting lesson result awards stars equal to correct_answers."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    # Get first available progress row and its lesson
    conn = direct_db()
    progress = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()
    assert progress is not None, "No available progress row found"

    # Manually create a lesson linked to this progress row
    lesson_id_row = conn.execute(
        """INSERT INTO lessons (child_id, mode, topic_id, topic_title, subject, status, sequence_number)
           VALUES (?, 'curriculum', '1', 'Test Topic', 'math', 'ready', 1)""",
        (child_id,)
    ).lastrowid
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id_row, progress["id"])
    )
    conn.commit()
    conn.close()

    # Submit result
    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_row}/result",
        json={"correct_answers": 5, "total_answers": 5}
    )
    assert resp.status_code == 200, f"Result submit failed: {resp.text}"

    # Check stars in DB
    conn = direct_db()
    stars = conn.execute(
        "SELECT stars FROM children WHERE id=?", (child_id,)
    ).fetchone()[0]
    conn.close()
    assert stars == 5, f"Expected 5 stars, got {stars}"


@pytest.mark.asyncio
async def test_stars_zero_if_zero_correct(enrolled_child: dict):
    """Submitting 0 correct answers awards 0 stars."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    conn = direct_db()
    progress = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()

    lesson_id_row = conn.execute(
        """INSERT INTO lessons (child_id, mode, topic_id, topic_title, subject, status, sequence_number)
           VALUES (?, 'curriculum', '1', 'Test Topic', 'math', 'ready', 1)""",
        (child_id,)
    ).lastrowid
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id_row, progress["id"])
    )
    conn.commit()
    conn.close()

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_row}/result",
        json={"correct_answers": 0, "total_answers": 5}
    )
    assert resp.status_code == 200

    conn = direct_db()
    stars = conn.execute(
        "SELECT stars FROM children WHERE id=?", (child_id,)
    ).fetchone()[0]
    conn.close()
    assert stars == 0


@pytest.mark.asyncio
async def test_child_stars_accumulate(enrolled_child: dict):
    """Stars accumulate across multiple lessons."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    # Give child some initial stars directly
    conn = direct_db()
    conn.execute("UPDATE children SET stars=3 WHERE id=?", (child_id,))
    conn.commit()
    conn.close()

    # Complete a lesson with 4 correct
    conn = direct_db()
    progress = conn.execute(
        "SELECT * FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()
    lesson_id_row = conn.execute(
        """INSERT INTO lessons (child_id, mode, topic_id, topic_title, subject, status, sequence_number)
           VALUES (?, 'curriculum', '1', 'Test', 'math', 'ready', 1)""",
        (child_id,)
    ).lastrowid
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id_row, progress["id"])
    )
    conn.commit()
    conn.close()

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_row}/result",
        json={"correct_answers": 4, "total_answers": 5}
    )
    assert resp.status_code == 200

    conn = direct_db()
    stars = conn.execute(
        "SELECT stars FROM children WHERE id=?", (child_id,)
    ).fetchone()[0]
    conn.close()
    assert stars == 7  # 3 initial + 4 new


# ---------------------------------------------------------------------------
# Progression tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lesson_complete_unlocks_next_in_topic(enrolled_child: dict):
    """Completing lesson 1 of topic 1 should make lesson 2 of topic 1 available."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    conn = direct_db()
    # Get the available progress row (should be topic1, lesson1)
    progress = conn.execute(
        """SELECT clp.*, cl.lesson_order, ct.theme_order
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND clp.status='available'""",
        (child_id,)
    ).fetchone()
    assert progress is not None
    assert dict(progress)["lesson_order"] == 1
    assert dict(progress)["theme_order"] == 1

    # Link a lesson
    lesson_id_row = conn.execute(
        """INSERT INTO lessons (child_id, mode, topic_id, topic_title, subject, status, sequence_number)
           VALUES (?, 'curriculum', '1', 'L1T1', 'math', 'ready', 1)""",
        (child_id,)
    ).lastrowid
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id_row, progress["id"])
    )
    conn.commit()
    conn.close()

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_row}/result",
        json={"correct_answers": 5, "total_answers": 5}
    )
    assert resp.status_code == 200

    conn = direct_db()
    available_rows = conn.execute(
        """SELECT clp.*, cl.lesson_order, ct.theme_order
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND clp.status='available'""",
        (child_id,)
    ).fetchall()
    conn.close()

    assert len(available_rows) == 1
    row = dict(available_rows[0])
    assert row["lesson_order"] == 2
    assert row["theme_order"] == 1


@pytest.mark.asyncio
async def test_lesson_complete_unlocks_next_topic(enrolled_child: dict):
    """Completing lesson 5 of topic 1 should make lesson 1 of topic 2 available."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    conn = direct_db()
    # Find topic 1, lesson 5
    topic1_lesson5 = conn.execute(
        """SELECT clp.id as progress_id, cl.id as cl_id
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND ct.theme_order=1 AND cl.lesson_order=5""",
        (child_id,)
    ).fetchone()
    assert topic1_lesson5 is not None

    # Force status to 'available' for that row
    conn.execute(
        "UPDATE child_lesson_progress SET status='available' WHERE id=?",
        (topic1_lesson5["progress_id"],)
    )
    # Mark lessons 1-4 of topic1 as completed
    conn.execute(
        """UPDATE child_lesson_progress SET status='completed'
           WHERE child_id=?
           AND curriculum_lesson_id IN (
               SELECT cl.id FROM curriculum_lessons cl
               JOIN curriculum_topics ct ON ct.id = cl.topic_id
               WHERE ct.theme_order=1 AND cl.lesson_order < 5
           )""",
        (child_id,)
    )

    lesson_id_row = conn.execute(
        """INSERT INTO lessons (child_id, mode, topic_id, topic_title, subject, status, sequence_number)
           VALUES (?, 'curriculum', '1', 'L5T1', 'math', 'ready', 5)""",
        (child_id,)
    ).lastrowid
    conn.execute(
        "UPDATE child_lesson_progress SET lesson_id=? WHERE id=?",
        (lesson_id_row, topic1_lesson5["progress_id"])
    )
    conn.commit()
    conn.close()

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_row}/result",
        json={"correct_answers": 5, "total_answers": 5}
    )
    assert resp.status_code == 200

    conn = direct_db()
    available_rows = conn.execute(
        """SELECT clp.*, cl.lesson_order, ct.theme_order
           FROM child_lesson_progress clp
           JOIN curriculum_lessons cl ON cl.id = clp.curriculum_lesson_id
           JOIN curriculum_topics ct ON ct.id = cl.topic_id
           WHERE clp.child_id=? AND clp.status='available'""",
        (child_id,)
    ).fetchall()
    conn.close()

    assert len(available_rows) == 1
    row = dict(available_rows[0])
    assert row["lesson_order"] == 1
    assert row["theme_order"] == 2


# ---------------------------------------------------------------------------
# Subject progress API tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subject_progress_returns_correct_structure(enrolled_child: dict):
    """GET /api/children/{id}/subject-progress/math returns correct data structure."""
    auth_client = enrolled_child["client"]
    child_id = enrolled_child["child_id"]

    resp = await auth_client.get(
        f"/api/children/{child_id}/subject-progress/math"
    )
    assert resp.status_code == 200, f"Failed: {resp.text}"
    data = resp.json()

    assert data["subject"] == "math"
    assert data["total_lessons"] == 60
    assert data["completed_lessons"] == 0
    assert "topics" in data
    assert len(data["topics"]) == 12

    first_topic = data["topics"][0]
    assert "id" in first_topic
    assert "title_ru" in first_topic
    assert "lessons" in first_topic
    assert len(first_topic["lessons"]) == 5

    first_lesson = first_topic["lessons"][0]
    assert first_lesson["status"] == "available"
    assert first_lesson["lesson_order"] == 1


# ---------------------------------------------------------------------------
# Skip test tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_test_assign_is_free(child_with_crystals: dict, auth_client: AsyncClient):
    """POST /api/children/{id}/skip-test is free — no crystal deduction."""
    child_id = child_with_crystals["child_id"]
    user_id = child_with_crystals["user_id"]

    # Get a locked topic (theme 2+)
    conn = direct_db()
    topic = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=3"
    ).fetchone()
    conn.close()
    topic_id = topic["id"]

    resp = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic_id}
    )
    assert resp.status_code == 200, f"Skip test failed: {resp.text}"

    conn = direct_db()
    crystals = conn.execute(
        "SELECT crystals FROM users WHERE id=?", (user_id,)
    ).fetchone()[0]
    conn.close()
    assert crystals == 200, f"Expected 200 crystals (free), got {crystals}"


@pytest.mark.asyncio
async def test_skip_test_assign_creates_lesson(child_with_crystals: dict, auth_client: AsyncClient):
    """POST skip-test creates a lesson row with mode='skip_test'."""
    child_id = child_with_crystals["child_id"]

    conn = direct_db()
    topic = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=4"
    ).fetchone()
    topic_id = topic["id"]
    conn.close()

    resp = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic_id}
    )
    assert resp.status_code == 200
    lesson_id = resp.json()["lesson_id"]

    conn = direct_db()
    lesson = conn.execute(
        "SELECT * FROM lessons WHERE id=?", (lesson_id,)
    ).fetchone()
    conn.close()

    assert lesson is not None
    assert lesson["mode"] == "skip_test"
    assert lesson["child_id"] == child_id


@pytest.mark.asyncio
async def test_skip_test_only_one_at_a_time(child_with_crystals: dict, auth_client: AsyncClient):
    """Cannot assign a second skip test while one is active."""
    child_id = child_with_crystals["child_id"]

    conn = direct_db()
    topic2 = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=2"
    ).fetchone()
    topic5 = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=5"
    ).fetchone()
    conn.close()

    resp1 = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic2["id"]}
    )
    assert resp1.status_code == 200

    resp2 = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic5["id"]}
    )
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"


@pytest.mark.asyncio
async def test_skip_test_fail_no_unlock(child_with_crystals: dict, auth_client: AsyncClient):
    """Skip test with < 4 correct should not unlock lessons beyond current position."""
    child_id = child_with_crystals["child_id"]

    conn = direct_db()
    topic = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=3"
    ).fetchone()
    topic_id = topic["id"]
    conn.close()

    # Assign skip test
    resp = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic_id}
    )
    assert resp.status_code == 200
    lesson_id = resp.json()["lesson_id"]

    # Submit failing result
    resp2 = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 2, "total_answers": 5}
    )
    assert resp2.status_code == 200

    # Should still have only 1 available (first lesson of topic 1)
    conn = direct_db()
    available = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()[0]
    conn.close()
    assert available == 1


@pytest.mark.asyncio
async def test_skip_test_pass_bulk_unlock(child_with_crystals: dict, auth_client: AsyncClient):
    """Skip test with 4+ correct should mark all lessons in tested topic (and prior) as completed."""
    child_id = child_with_crystals["child_id"]

    conn = direct_db()
    topic = conn.execute(
        "SELECT id FROM curriculum_topics WHERE subject='math' AND grade=1 AND theme_order=2"
    ).fetchone()
    topic_id = topic["id"]
    conn.close()

    resp = await auth_client.post(
        f"/api/children/{child_id}/skip-test",
        json={"topic_id": topic_id}
    )
    assert resp.status_code == 200
    lesson_id = resp.json()["lesson_id"]

    # Submit passing result
    resp2 = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 4, "total_answers": 5}
    )
    assert resp2.status_code == 200

    # All 10 lessons in topics 1+2 should be completed (or more accurately, >= 10 completed)
    conn = direct_db()
    completed = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=? AND status='completed'",
        (child_id,)
    ).fetchone()[0]
    available = conn.execute(
        "SELECT COUNT(*) FROM child_lesson_progress WHERE child_id=? AND status='available'",
        (child_id,)
    ).fetchone()[0]
    conn.close()
    assert completed >= 10, f"Expected >= 10 completed, got {completed}"
    assert available >= 1, f"Expected >= 1 available after unlock, got {available}"


