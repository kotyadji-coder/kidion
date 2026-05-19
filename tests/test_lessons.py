"""
TDD Tests for Lessons Generation Feature (Этап 2)

These tests MUST FAIL initially (Red phase) because:
1. services/ module doesn't exist yet
2. DB functions (create_lesson, update_lesson_content, etc.) don't exist
3. API endpoints (/api/lessons/generate, /poll, /result) don't exist

Test coverage:
- POST /api/lessons/generate: auth, authorization, crystals, generation launch
- GET /api/lessons/{lesson_id}/poll: auth, authorization, status polling
- POST /api/lessons/{lesson_id}/result: auth, stars, streaks, difficulty
- Business logic: crystals deduction, streak updates, difficulty adjustments
"""

import os
import sqlite3
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from main import app


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def child_data(auth_client: AsyncClient) -> dict:
    """Create a child profile for the authenticated user."""
    payload = {
        "name": "Vasya",
        "birth_date": "2015-03-15",
        "gender": "boy",
        "grade": 3,
        "universe": "Minecraft",
        "pin_code": "5739",
    }
    resp = await auth_client.post("/api/children", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    data["_pin"] = "5739"  # preserve raw PIN for tests
    return data


@pytest_asyncio.fixture
async def second_user_client() -> AsyncClient:
    """A completely separate HTTP client with its own user (no shared state with auth_client)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        # Register and login as a separate user on this client only
        payload = {"email": "second@example.com", "password": "password456"}
        resp = await ac.post("/auth/register", json=payload)
        assert resp.status_code == 200
        yield ac


@pytest_asyncio.fixture
async def second_user_child(second_user_client: AsyncClient) -> dict:
    """Create a child for the second user (for authorization tests)."""
    payload = {
        "name": "Petya",
        "birth_date": "2016-05-20",
        "gender": "boy",
        "grade": 2,
        "universe": "Harry Potter",
        "pin_code": "5947",
    }
    resp = await second_user_client.post("/api/children", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    data["_pin"] = "5947"
    return data


# ---------------------------------------------------------------------------
# POST /api/lessons/generate Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_lesson_success(auth_client: AsyncClient, child_data: dict):
    """Test successful lesson generation."""
    with patch("services.generation.generate_lesson_content") as mock_gen:
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Таблица умножения на 7",
                "subject": "математика",
            }
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "lesson_id" in data
    assert isinstance(data["lesson_id"], int)

    # Verify generation was launched
    mock_gen.assert_called_once()


@pytest.mark.asyncio
async def test_generate_lesson_deducts_crystals(auth_client: AsyncClient, child_data: dict):
    """Test that lesson generation deducts 10 crystals immediately."""
    # Get initial crystals
    resp = await auth_client.get("/auth/me")
    initial_crystals = resp.json()["crystals"]

    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Фотосинтез",
            }
        )

    assert resp.status_code == 200

    # Check crystals after generation
    resp = await auth_client.get("/auth/me")
    final_crystals = resp.json()["crystals"]
    assert final_crystals == initial_crystals - 20


@pytest.mark.asyncio
async def test_generate_lesson_insufficient_crystals(auth_client: AsyncClient, child_data: dict):
    """Test generation fails when user has < 20 crystals."""
    # Drain crystals
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET crystals = 5 WHERE email = 'user@example.com'")
    conn.commit()
    conn.close()

    resp = await auth_client.post(
        "/api/lessons/generate",
        json={
            "child_id": child_data["id"],
            "topic": "Деление столбиком",
        }
    )

    assert resp.status_code == 402
    data = resp.json()
    assert data["error"] == "insufficient_crystals"


@pytest.mark.asyncio
async def test_generate_lesson_unauthorized(client: AsyncClient):
    """Test generation requires authentication."""
    resp = await client.post(
        "/api/lessons/generate",
        json={
            "child_id": 1,
            "topic": "Test topic",
        }
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_generate_lesson_child_not_found(auth_client: AsyncClient):
    """Test generation fails for non-existent child."""
    resp = await auth_client.post(
        "/api/lessons/generate",
        json={
            "child_id": 99999,
            "topic": "Test topic",
        }
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


@pytest.mark.asyncio
async def test_generate_lesson_forbidden_other_users_child(
    auth_client: AsyncClient, second_user_client: AsyncClient, second_user_child: dict
):
    """Test user cannot generate lessons for another user's child."""
    resp = await auth_client.post(
        "/api/lessons/generate",
        json={
            "child_id": second_user_child["id"],
            "topic": "Test topic",
        }
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


@pytest.mark.asyncio
async def test_generate_lesson_empty_topic(auth_client: AsyncClient, child_data: dict):
    """Test validation fails for empty topic."""
    resp = await auth_client.post(
        "/api/lessons/generate",
        json={
            "child_id": child_data["id"],
            "topic": "   ",
        }
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_lesson_default_subject(auth_client: AsyncClient, child_data: dict):
    """Test subject defaults to 'general' when not provided."""
    with patch("services.generation.generate_lesson_content") as mock_gen:
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Динозавры",
            }
        )

    assert resp.status_code == 200

    # Check the DB to verify subject was set to "general"
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT subject FROM lessons WHERE id = ?",
        (resp.json()["lesson_id"],)
    )
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "general"


# ---------------------------------------------------------------------------
# GET /api/lessons/{lesson_id}/poll Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_lesson_pending(auth_client: AsyncClient, child_data: dict):
    """Test polling a lesson that is still generating."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Круговорот воды",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Poll immediately (should be pending)
    resp = await auth_client.get(f"/api/lessons/{lesson_id}/poll")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["content_url"] is None
    assert data["print_url"] is None


@pytest.mark.asyncio
async def test_poll_lesson_done(auth_client: AsyncClient, child_data: dict):
    """Test polling a completed lesson."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Планеты солнечной системы",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Manually mark lesson as done with content URLs
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE lessons SET status = 'done', content_url = ?, print_url = ? WHERE id = ?",
        ("http://testserver/content/abc123.html", "http://testserver/content/abc123_print.html", lesson_id)
    )
    conn.commit()
    conn.close()

    # Poll
    resp = await auth_client.get(f"/api/lessons/{lesson_id}/poll")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["content_url"] == "http://testserver/content/abc123.html"
    assert data["print_url"] == "http://testserver/content/abc123_print.html"


@pytest.mark.asyncio
async def test_poll_lesson_error(auth_client: AsyncClient, child_data: dict):
    """Test polling a lesson that failed generation."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Test topic",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Mark as error
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE lessons SET status = 'error' WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()

    resp = await auth_client.get(f"/api/lessons/{lesson_id}/poll")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_poll_lesson_unauthorized(client: AsyncClient):
    """Test polling requires authentication."""
    resp = await client.get("/api/lessons/1/poll")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_poll_lesson_not_found(auth_client: AsyncClient):
    """Test polling non-existent lesson."""
    resp = await auth_client.get("/api/lessons/99999/poll")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


@pytest.mark.asyncio
async def test_poll_lesson_forbidden_other_users_child(
    auth_client: AsyncClient, second_user_client: AsyncClient, second_user_child: dict
):
    """Test user cannot poll lessons for another user's child."""
    # Create lesson as second user
    with patch("services.generation.generate_lesson_content"):
        resp = await second_user_client.post(
            "/api/lessons/generate",
            json={
                "child_id": second_user_child["id"],
                "topic": "Test topic",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Try to poll as first user
    resp = await auth_client.get(f"/api/lessons/{lesson_id}/poll")
    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


# ---------------------------------------------------------------------------
# POST /api/lessons/{lesson_id}/result Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_result_success_by_parent(auth_client: AsyncClient, child_data: dict):
    """Test parent can submit lesson result."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Test topic",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Submit result
    resp = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={
            "correct_answers": 4,
            "total_answers": 5,
        }
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["stars"] == 2  # 4 correct = 2 stars
    assert "difficulty_level" in data
    assert "current_streak" in data


@pytest.mark.asyncio
async def test_submit_result_stars_calculation(auth_client: AsyncClient, child_data: dict):
    """Test stars calculation: 5=3★, 3-4=2★, 0-2=1★"""
    # Give extra crystals for 6 generations (need 120, have 60)
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET crystals = crystals + 100 WHERE email = 'user@example.com'")
    conn.commit()
    conn.close()

    test_cases = [
        (5, 3),  # Perfect score
        (4, 2),
        (3, 2),
        (2, 1),
        (1, 1),
        (0, 1),
    ]

    for correct, expected_stars in test_cases:
        with patch("services.generation.generate_lesson_content"):
            resp = await auth_client.post(
                "/api/lessons/generate",
                json={
                    "child_id": child_data["id"],
                    "topic": f"Topic {correct}",
                }
            )

        assert resp.status_code == 200, f"Generate failed for {correct}: {resp.json()}"
        lesson_id = resp.json()["lesson_id"]

        resp = await auth_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": correct}
        )

        assert resp.status_code == 200
        assert resp.json()["stars"] == expected_stars, f"Failed for {correct} correct answers"


@pytest.mark.asyncio
async def test_submit_result_streak_first_lesson(auth_client: AsyncClient, child_data: dict):
    """Test streak is set to 1 on first lesson."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "First lesson",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 3}
    )

    assert resp.status_code == 200
    assert resp.json()["current_streak"] == 1


@pytest.mark.asyncio
async def test_submit_result_streak_consecutive_days(auth_client: AsyncClient, child_data: dict):
    """Test streak increments on consecutive days."""
    # First lesson today
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Lesson 1",
            }
        )

    lesson_id_1 = resp.json()["lesson_id"]

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_1}/result",
        json={"correct_answers": 3}
    )
    assert resp.json()["current_streak"] == 1

    # Second lesson yesterday (simulate)
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE streaks SET last_activity_date = ? WHERE child_id = ?",
        (yesterday, child_data["id"])
    )
    conn.commit()
    conn.close()

    # Create another lesson and submit
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Lesson 2",
            }
        )

    lesson_id_2 = resp.json()["lesson_id"]

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_2}/result",
        json={"correct_answers": 4}
    )

    assert resp.status_code == 200
    assert resp.json()["current_streak"] == 2


@pytest.mark.asyncio
async def test_submit_result_streak_breaks(auth_client: AsyncClient, child_data: dict):
    """Test streak resets to 1 if gap > 1 day."""
    # First lesson
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Lesson 1",
            }
        )

    lesson_id_1 = resp.json()["lesson_id"]
    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_1}/result",
        json={"correct_answers": 3}
    )
    assert resp.json()["current_streak"] == 1

    # Simulate last activity 3 days ago
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE streaks SET last_activity_date = ?, current_streak = 5 WHERE child_id = ?",
        (three_days_ago, child_data["id"])
    )
    conn.commit()
    conn.close()

    # New lesson today
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Lesson 2",
            }
        )

    lesson_id_2 = resp.json()["lesson_id"]
    resp = await auth_client.post(
        f"/api/lessons/{lesson_id_2}/result",
        json={"correct_answers": 4}
    )

    assert resp.status_code == 200
    assert resp.json()["current_streak"] == 1


@pytest.mark.asyncio
async def test_submit_result_difficulty_increase(auth_client: AsyncClient, child_data: dict):
    """Test difficulty increases after 2 consecutive perfect scores."""
    # Child starts at difficulty level 2 (default)
    # Submit 2 lessons with 5/5 correct

    for i in range(2):
        with patch("services.generation.generate_lesson_content"):
            resp = await auth_client.post(
                "/api/lessons/generate",
                json={
                    "child_id": child_data["id"],
                    "topic": f"Perfect lesson {i+1}",
                }
            )

        lesson_id = resp.json()["lesson_id"]
        resp = await auth_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": 5}
        )

        assert resp.status_code == 200

    # After 2nd perfect score, difficulty should increase to 3
    assert resp.json()["difficulty_level"] == 3


@pytest.mark.asyncio
async def test_submit_result_difficulty_decrease(auth_client: AsyncClient, child_data: dict):
    """Test difficulty decreases after 2 consecutive low scores (≤2)."""
    # Submit 2 lessons with ≤2 correct

    for i in range(2):
        with patch("services.generation.generate_lesson_content"):
            resp = await auth_client.post(
                "/api/lessons/generate",
                json={
                    "child_id": child_data["id"],
                    "topic": f"Hard lesson {i+1}",
                }
            )

        lesson_id = resp.json()["lesson_id"]
        resp = await auth_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": 2}
        )

        assert resp.status_code == 200

    # After 2nd low score, difficulty should decrease to 1
    assert resp.json()["difficulty_level"] == 1


@pytest.mark.asyncio
async def test_submit_result_difficulty_stays_at_boundaries(auth_client: AsyncClient, child_data: dict):
    """Test difficulty stays at 1 (min) and 3 (max)."""
    # Give extra crystals for 4 generations
    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET crystals = crystals + 100 WHERE email = 'user@example.com'")
    conn.execute(
        "UPDATE children SET difficulty_level = 1 WHERE id = ?",
        (child_data["id"],)
    )
    conn.commit()
    conn.close()

    # Submit 2 low scores - should stay at 1
    for i in range(2):
        with patch("services.generation.generate_lesson_content"):
            resp = await auth_client.post(
                "/api/lessons/generate",
                json={
                    "child_id": child_data["id"],
                    "topic": f"Low {i}",
                }
            )

        assert resp.status_code == 200, f"Generate failed: {resp.json()}"
        lesson_id = resp.json()["lesson_id"]
        resp = await auth_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": 1}
        )

    assert resp.json()["difficulty_level"] == 1  # Should not go below 1

    # Set difficulty to 3 and clear old results
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE children SET difficulty_level = 3 WHERE id = ?",
        (child_data["id"],)
    )
    conn.execute("DELETE FROM lesson_results WHERE child_id = ?", (child_data["id"],))
    conn.commit()
    conn.close()

    # Submit 2 perfect scores - should stay at 3
    for i in range(2):
        with patch("services.generation.generate_lesson_content"):
            resp = await auth_client.post(
                "/api/lessons/generate",
                json={
                    "child_id": child_data["id"],
                    "topic": f"Perfect {i}",
                }
            )

        assert resp.status_code == 200, f"Generate failed: {resp.json()}"
        lesson_id = resp.json()["lesson_id"]
        resp = await auth_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": 5}
        )

    assert resp.json()["difficulty_level"] == 3  # Should not go above 3


@pytest.mark.asyncio
async def test_submit_result_by_child_session(client: AsyncClient, child_data: dict):
    """Test child can submit result with kid_session_child cookie."""
    # First, create a lesson (as parent)
    resp = await client.post("/auth/login", json={"email": "user@example.com", "password": "password123"})
    assert resp.status_code == 200

    with patch("services.generation.generate_lesson_content"):
        resp = await client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Child's lesson",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Logout parent
    await client.post("/auth/logout")

    # Login as child with PIN
    resp = await client.post(
        "/api/kid/auth",
        json={
            "child_id": child_data["id"],
            "pin": child_data["_pin"],
        }
    )
    assert resp.status_code == 200

    # Submit result as child
    resp = await client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 3}
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_submit_result_unauthorized(client: AsyncClient):
    """Test result submission requires authentication."""
    resp = await client.post(
        "/api/lessons/1/result",
        json={"correct_answers": 3}
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_submit_result_not_found(auth_client: AsyncClient):
    """Test submitting result for non-existent lesson."""
    resp = await auth_client.post(
        "/api/lessons/99999/result",
        json={"correct_answers": 3}
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


@pytest.mark.asyncio
async def test_submit_result_forbidden_parent(
    auth_client: AsyncClient, second_user_client: AsyncClient, second_user_child: dict
):
    """Test parent cannot submit result for another user's child."""
    # Create lesson as second user
    with patch("services.generation.generate_lesson_content"):
        resp = await second_user_client.post(
            "/api/lessons/generate",
            json={
                "child_id": second_user_child["id"],
                "topic": "Test",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Try to submit as first user
    resp = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 3}
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "forbidden"


@pytest.mark.asyncio
async def test_submit_result_forbidden_wrong_child_session(
    auth_client: AsyncClient, child_data: dict
):
    """Test child cannot submit result for another child's lesson."""
    # Create second child for same parent
    resp = await auth_client.post(
        "/api/children",
        json={
            "name": "Masha",
            "birth_date": "2017-08-10",
            "gender": "girl",
            "grade": 1,
            "universe": "Disney",
            "pin_code": "9427",
        }
    )
    child2 = resp.json()

    # Create lesson for first child
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Test",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    # Use a separate client to login as second child
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as kid_client:
        resp = await kid_client.post(
            "/api/kid/auth",
            json={
                "child_id": child2["id"],
                "pin": "9427",
            }
        )
        assert resp.status_code == 200

        # Try to submit result for first child's lesson
        resp = await kid_client.post(
            f"/api/lessons/{lesson_id}/result",
            json={"correct_answers": 3}
        )

        assert resp.status_code == 403
        assert resp.json()["error"] == "forbidden"


@pytest.mark.asyncio
async def test_submit_result_validation_correct_answers_out_of_range(
    auth_client: AsyncClient, child_data: dict
):
    """Test validation fails for correct_answers > 5."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Test",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": 6}
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_result_validation_negative_correct_answers(
    auth_client: AsyncClient, child_data: dict
):
    """Test validation fails for negative correct_answers."""
    with patch("services.generation.generate_lesson_content"):
        resp = await auth_client.post(
            "/api/lessons/generate",
            json={
                "child_id": child_data["id"],
                "topic": "Test",
            }
        )

    lesson_id = resp.json()["lesson_id"]

    resp = await auth_client.post(
        f"/api/lessons/{lesson_id}/result",
        json={"correct_answers": -1}
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DB Functions Tests (will fail until db.py is updated)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_db_create_lesson(auth_client: AsyncClient, child_data: dict):
    """Test create_lesson DB function."""
    from db import get_connection, create_lesson

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    lesson_id = create_lesson(
        conn,
        child_id=child_data["id"],
        mode="on_demand",
        topic_title="Test Topic",
        subject="math"
    )

    assert isinstance(lesson_id, int)
    assert lesson_id > 0

    # Verify in DB
    cursor = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
    row = cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_db_get_lesson_by_id(auth_client: AsyncClient, child_data: dict):
    """Test get_lesson_by_id DB function."""
    from db import get_connection, create_lesson, get_lesson_by_id

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    lesson_id = create_lesson(conn, child_data["id"], "on_demand", "Topic", "science")

    lesson = get_lesson_by_id(conn, lesson_id)
    assert lesson is not None
    assert lesson["id"] == lesson_id
    assert lesson["child_id"] == child_data["id"]
    assert lesson["status"] == "pending"


@pytest.mark.asyncio
async def test_db_update_lesson_content(auth_client: AsyncClient, child_data: dict):
    """Test update_lesson_content DB function."""
    from db import get_connection, create_lesson, update_lesson_content, get_lesson_by_id

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    lesson_id = create_lesson(conn, child_data["id"], "on_demand", "Topic", "math")

    update_lesson_content(
        conn,
        lesson_id,
        content_url="http://test.com/lesson.html",
        print_url="http://test.com/lesson_print.html",
        status="done"
    )

    lesson = get_lesson_by_id(conn, lesson_id)
    assert lesson["status"] == "done"
    assert lesson["content_url"] == "http://test.com/lesson.html"
    assert lesson["print_url"] == "http://test.com/lesson_print.html"


@pytest.mark.asyncio
async def test_db_get_recent_lesson_titles(auth_client: AsyncClient, child_data: dict):
    """Test get_recent_lesson_titles DB function."""
    from db import get_connection, create_lesson, get_recent_lesson_titles

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    # Create multiple lessons
    create_lesson(conn, child_data["id"], "on_demand", "Topic 1", "math")
    create_lesson(conn, child_data["id"], "on_demand", "Topic 2", "science")
    create_lesson(conn, child_data["id"], "on_demand", "Topic 3", "history")

    titles = get_recent_lesson_titles(conn, child_data["id"], limit=2)
    assert len(titles) == 2
    assert "Topic 3" in titles  # Most recent
    assert "Topic 2" in titles


@pytest.mark.asyncio
async def test_db_create_lesson_result(auth_client: AsyncClient, child_data: dict):
    """Test create_lesson_result DB function."""
    from db import get_connection, create_lesson, create_lesson_result

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    lesson_id = create_lesson(conn, child_data["id"], "on_demand", "Topic", "math")

    result_id = create_lesson_result(
        conn,
        lesson_id=lesson_id,
        child_id=child_data["id"],
        correct_answers=4,
        total_answers=5,
        stars=2
    )

    assert isinstance(result_id, int)
    assert result_id > 0


@pytest.mark.asyncio
async def test_db_update_streak(auth_client: AsyncClient, child_data: dict):
    """Test update_streak DB function."""
    from db import get_connection, update_streak

    db_path = os.environ.get("DATABASE_PATH", "./kidion.db")
    conn = get_connection(db_path)

    today = date.today().isoformat()

    streak = update_streak(conn, child_data["id"], today)
    assert streak["current_streak"] == 1
    assert streak["last_activity_date"] == today

    # Same day - no change
    streak2 = update_streak(conn, child_data["id"], today)
    assert streak2["current_streak"] == 1
