import pytest
from httpx import AsyncClient

import services.generation as generation
from db import create_lesson, get_connection, insert_transaction, update_crystals
from main import _parent_gate_challenges

pytestmark = pytest.mark.asyncio


async def _create_child_and_login_as_kid(client: AsyncClient) -> dict:
    await client.post(
        "/auth/register",
        json={"email": "gate-parent@example.com", "password": "password123", "consent": True},
    )
    await client.post(
        "/auth/login",
        json={"email": "gate-parent@example.com", "password": "password123"},
    )
    child_resp = await client.post(
        "/api/children",
        json={
            "name": "Миша",
            "gender": "boy",
            "birth_date": "2017-01-01",
            "grade": 3,
            "universe": "Лего",
            "pin_code": "5739",
        },
    )
    assert child_resp.status_code == 201
    child = child_resp.json()
    kid_resp = await client.post("/api/kid/auth", json={"child_id": child["id"]})
    assert kid_resp.status_code == 200
    return child


async def test_parent_gate_challenge_requires_child_session(client: AsyncClient):
    resp = await client.post("/api/kid/parent-gate/challenge")
    assert resp.status_code == 401


async def test_parent_gate_verifies_answer_and_allows_dashboard(client: AsyncClient):
    await _create_child_and_login_as_kid(client)

    challenge = await client.post("/api/kid/parent-gate/challenge")
    assert challenge.status_code == 200
    assert "question" in challenge.json()

    token = client.cookies.get("kid_parent_gate")
    answer = _parent_gate_challenges[token]["answer"]

    wrong = await client.post(
        "/api/kid/parent-gate/verify",
        json={"answer": answer + 1, "target": "/dashboard"},
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "wrong_answer"

    ok = await client.post(
        "/api/kid/parent-gate/verify",
        json={"answer": answer, "target": "/dashboard"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True, "redirect": "/dashboard"}


async def test_parent_gate_rejects_unlisted_targets(client: AsyncClient):
    await _create_child_and_login_as_kid(client)
    challenge = await client.post("/api/kid/parent-gate/challenge")
    assert challenge.status_code == 200
    token = client.cookies.get("kid_parent_gate")
    answer = _parent_gate_challenges[token]["answer"]

    resp = await client.post(
        "/api/kid/parent-gate/verify",
        json={"answer": answer, "target": "https://example.com"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_target"


async def test_evals_run_requires_admin_user(auth_client: AsyncClient):
    resp = await auth_client.post("/evals/run", json={"mode": "quick"})
    assert resp.status_code == 403
    assert resp.json()["error"] == "admin required"


async def test_generate_lesson_rejects_planned_subject(auth_client: AsyncClient):
    child_resp = await auth_client.post(
        "/api/children",
        json={
            "name": "Оля",
            "gender": "girl",
            "birth_date": "2018-01-01",
            "grade": 2,
            "universe": "Космос",
            "pin_code": "5739",
        },
    )
    assert child_resp.status_code == 201

    resp = await auth_client.post(
        "/api/lessons/generate",
        json={
            "child_id": child_resp.json()["id"],
            "topic": "Планеты",
            "subject": "world",
        },
    )
    assert resp.status_code == 422


async def test_failed_paid_lesson_generation_refunds_once(
    auth_client: AsyncClient,
    temp_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
):
    me = (await auth_client.get("/auth/me")).json()
    child_resp = await auth_client.post(
        "/api/children",
        json={
            "name": "Ира",
            "gender": "girl",
            "birth_date": "2018-01-01",
            "grade": 2,
            "universe": "Космос",
            "pin_code": "5739",
        },
    )
    assert child_resp.status_code == 201
    child = child_resp.json()

    conn = get_connection(temp_db_path)
    lesson_id = create_lesson(conn, child["id"], "on_demand", "Сложение", "math")
    assert update_crystals(conn, me["id"], -20)
    insert_transaction(conn, me["id"], -20, f"lesson_generation:lesson_{lesson_id}")

    def fail_generation(*args, **kwargs):
        raise RuntimeError("offline test failure")

    monkeypatch.setattr(generation, "generate_explanation", fail_generation)

    generation.generate_lesson_content(
        lesson_id,
        child,
        "Сложение",
        "math",
        temp_db_path,
        "http://testserver",
        refund_user_id=me["id"],
        refund_amount=20,
        refund_reason=f"lesson_generation:lesson_{lesson_id}",
    )

    row = conn.execute("SELECT status FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    balance = conn.execute("SELECT crystals FROM users WHERE id=?", (me["id"],)).fetchone()[0]
    refund_count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND reason=?",
        (me["id"], f"refund:lesson_generation:lesson_{lesson_id}"),
    ).fetchone()[0]

    assert row["status"] == "error"
    assert balance == me["crystals"]
    assert refund_count == 1

    generation.generate_lesson_content(
        lesson_id,
        child,
        "Сложение",
        "math",
        temp_db_path,
        "http://testserver",
        refund_user_id=me["id"],
        refund_amount=20,
        refund_reason=f"lesson_generation:lesson_{lesson_id}",
    )

    balance_again = conn.execute("SELECT crystals FROM users WHERE id=?", (me["id"],)).fetchone()[0]
    refund_count_again = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND reason=?",
        (me["id"], f"refund:lesson_generation:lesson_{lesson_id}"),
    ).fetchone()[0]
    assert balance_again == me["crystals"]
    assert refund_count_again == 1
