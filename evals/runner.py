"""
runner.py — Main eval runner. Orchestrates dataset → generation → validation → scoring → storage.
"""

import json
import logging
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from evals.dataset import LESSON_TEST_CASES, CHAT_TEST_CASES
from evals.validators import run_all_validators, deterministic_score
from evals.llm_judge import judge_lesson, judge_chat_response, generate_recommendations

logger = logging.getLogger("kidion.evals")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DB = os.path.join(_BASE_DIR, "evals_data.db")


def _get_git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_BASE_DIR, text=True
        ).strip()
    except Exception:
        return "unknown"


def _get_eval_db() -> sqlite3.Connection:
    """Get or create the eval database."""
    conn = sqlite3.connect(_EVAL_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            git_hash TEXT,
            version TEXT,
            lesson_count INTEGER DEFAULT 0,
            chat_count INTEGER DEFAULT 0,
            avg_deterministic REAL,
            avg_llm_score REAL,
            recommendations_json TEXT,
            status TEXT DEFAULT 'running'
        );

        CREATE TABLE IF NOT EXISTS eval_lesson_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES eval_runs(id),
            test_case_id TEXT NOT NULL,
            subject TEXT,
            grade INTEGER,
            topic TEXT,
            universe TEXT,
            lesson_json TEXT,
            methodologist_output TEXT,
            deterministic_json TEXT,
            deterministic_score REAL,
            llm_scores_json TEXT,
            llm_avg_score REAL,
            generation_time_ms INTEGER,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS eval_chat_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES eval_runs(id),
            test_case_id TEXT NOT NULL,
            character_key TEXT,
            user_message TEXT,
            bot_response TEXT,
            llm_scores_json TEXT,
            llm_avg_score REAL,
            generation_time_ms INTEGER,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_elr_run ON eval_lesson_results(run_id);
        CREATE INDEX IF NOT EXISTS idx_ecr_run ON eval_chat_results(run_id);
    """)
    conn.commit()
    return conn


def _generate_lesson(test_case: dict) -> tuple[str, dict, int]:
    """Generate a lesson for a test case. Returns (methodologist_output, lesson_dict, time_ms)."""
    from services.generation import build_question
    from services.gemini_client import generate_explanation

    child = {
        "name": "Тест",
        "gender": test_case["gender"],
        "grade": test_case["grade"],
        "universe": test_case["universe"],
        "difficulty_level": test_case["difficulty_level"],
        "universe_description": "",
        "interests": test_case.get("interests", []),
    }

    question = build_question(child, test_case["topic"], test_case["subject"], [])
    start = time.time()
    methodologist, lesson = generate_explanation(question)
    elapsed_ms = int((time.time() - start) * 1000)
    return methodologist, lesson, elapsed_ms


def _generate_chat(test_case: dict) -> tuple[str, int]:
    """Generate a chat response. Returns (response, time_ms)."""
    from services.kid_chat import generate_chat_response

    start = time.time()
    response = generate_chat_response(
        messages=test_case["messages"],
        child_name=test_case.get("child_name", ""),
        character_key=test_case["character"],
    )
    elapsed_ms = int((time.time() - start) * 1000)
    return response, elapsed_ms


def run_eval(
    lesson_cases: list[dict] | None = None,
    chat_cases: list[dict] | None = None,
    version: str = "",
) -> int:
    """Run a full eval. Returns run_id."""
    if lesson_cases is None:
        lesson_cases = LESSON_TEST_CASES
    if chat_cases is None:
        chat_cases = CHAT_TEST_CASES

    db = _get_eval_db()
    now = datetime.now(timezone.utc).isoformat()
    git_hash = _get_git_hash()

    db.execute(
        "INSERT INTO eval_runs (started_at, git_hash, version, status) VALUES (?, ?, ?, 'running')",
        (now, git_hash, version or git_hash),
    )
    db.commit()
    run_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  Eval Run #{run_id} | {git_hash} | {now[:19]}")
    print(f"  Lessons: {len(lesson_cases)} | Chats: {len(chat_cases)}")
    print(f"{'='*60}\n")

    # ── Lesson evals ──
    lesson_results_for_recs = []
    lesson_det_scores = []
    lesson_llm_scores = []

    for i, tc in enumerate(lesson_cases):
        print(f"  [{i+1}/{len(lesson_cases)}] Lesson: {tc['id']} ...", end=" ", flush=True)
        try:
            methodologist, lesson, time_ms = _generate_lesson(tc)

            # Level 1: deterministic
            det_results = run_all_validators(lesson, tc)
            det_score = deterministic_score(det_results)
            lesson_det_scores.append(det_score)

            # Level 2: LLM judge
            llm_scores = judge_lesson(lesson, tc)
            llm_avg = None
            if llm_scores:
                numeric = [v for k, v in llm_scores.items()
                           if isinstance(v, (int, float)) and k not in ("strengths", "weaknesses", "suggestion")]
                llm_avg = sum(numeric) / len(numeric) if numeric else None
                if llm_avg:
                    lesson_llm_scores.append(llm_avg)

            db.execute(
                """INSERT INTO eval_lesson_results
                   (run_id, test_case_id, subject, grade, topic, universe,
                    lesson_json, methodologist_output,
                    deterministic_json, deterministic_score,
                    llm_scores_json, llm_avg_score, generation_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, tc["id"], tc["subject"], tc["grade"], tc["topic"], tc["universe"],
                 json.dumps(lesson, ensure_ascii=False),
                 methodologist,
                 json.dumps(det_results, ensure_ascii=False),
                 det_score,
                 json.dumps(llm_scores, ensure_ascii=False) if llm_scores else None,
                 llm_avg,
                 time_ms),
            )

            lesson_results_for_recs.append({
                "test_case_id": tc["id"],
                "deterministic": det_results,
                "llm_scores": llm_scores,
            })

            status = f"det={det_score:.0%}"
            if llm_avg:
                status += f" llm={llm_avg:.1f}/5"
            status += f" ({time_ms}ms)"
            print(f"OK — {status}")

        except Exception as e:
            logger.error("Eval error for %s: %s", tc["id"], e)
            db.execute(
                """INSERT INTO eval_lesson_results
                   (run_id, test_case_id, subject, grade, topic, universe, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, tc["id"], tc["subject"], tc["grade"], tc["topic"],
                 tc["universe"], str(e)),
            )
            print(f"ERROR: {e}")

        db.commit()

    # ── Chat evals ──
    chat_results_for_recs = []
    chat_llm_scores = []

    for i, tc in enumerate(chat_cases):
        print(f"  [{i+1}/{len(chat_cases)}] Chat: {tc['id']} ...", end=" ", flush=True)
        try:
            response, time_ms = _generate_chat(tc)

            # Level 2: LLM judge
            llm_scores = judge_chat_response(response, tc)
            llm_avg = None
            if llm_scores:
                numeric = [v for k, v in llm_scores.items()
                           if isinstance(v, (int, float)) and k not in ("comment",)]
                llm_avg = sum(numeric) / len(numeric) if numeric else None
                if llm_avg:
                    chat_llm_scores.append(llm_avg)

            db.execute(
                """INSERT INTO eval_chat_results
                   (run_id, test_case_id, character_key, user_message, bot_response,
                    llm_scores_json, llm_avg_score, generation_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, tc["id"], tc["character"],
                 tc["messages"][-1]["content"], response,
                 json.dumps(llm_scores, ensure_ascii=False) if llm_scores else None,
                 llm_avg, time_ms),
            )

            chat_results_for_recs.append({
                "test_case_id": tc["id"],
                "llm_scores": llm_scores,
            })

            status = ""
            if llm_avg:
                status = f"llm={llm_avg:.1f}/5"
            status += f" ({time_ms}ms)"
            print(f"OK — {status}")

        except Exception as e:
            logger.error("Chat eval error for %s: %s", tc["id"], e)
            db.execute(
                """INSERT INTO eval_chat_results
                   (run_id, test_case_id, character_key, user_message, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (run_id, tc["id"], tc["character"],
                 tc["messages"][-1]["content"], str(e)),
            )
            print(f"ERROR: {e}")

        db.commit()

    # ── Recommendations ──
    print("\n  Generating recommendations...", end=" ", flush=True)
    recommendations = generate_recommendations(lesson_results_for_recs, chat_results_for_recs)
    print(f"OK ({len(recommendations)} recommendations)")

    # ── Finalize run ──
    finished = datetime.now(timezone.utc).isoformat()
    avg_det = sum(lesson_det_scores) / len(lesson_det_scores) if lesson_det_scores else None
    all_llm = lesson_llm_scores + chat_llm_scores
    avg_llm = sum(all_llm) / len(all_llm) if all_llm else None

    db.execute(
        """UPDATE eval_runs SET
           finished_at=?, lesson_count=?, chat_count=?,
           avg_deterministic=?, avg_llm_score=?,
           recommendations_json=?, status='completed'
           WHERE id=?""",
        (finished, len(lesson_cases), len(chat_cases),
         avg_det, avg_llm,
         json.dumps(recommendations, ensure_ascii=False),
         run_id),
    )
    db.commit()
    db.close()

    print(f"\n{'='*60}")
    print(f"  Run #{run_id} complete!")
    if avg_det is not None:
        print(f"  Deterministic avg: {avg_det:.0%}")
    if avg_llm is not None:
        print(f"  LLM judge avg: {avg_llm:.1f}/5")
    print(f"  Dashboard: /evals/dashboard")
    print(f"{'='*60}\n")

    return run_id


def compare_runs(run_id_a: int | None = None, run_id_b: int | None = None) -> dict:
    """Compare two runs. If not specified, compares last two runs."""
    db = _get_eval_db()

    if run_id_a is None or run_id_b is None:
        runs = db.execute(
            "SELECT id FROM eval_runs WHERE status='completed' ORDER BY id DESC LIMIT 2"
        ).fetchall()
        if len(runs) < 2:
            db.close()
            return {"error": "Need at least 2 completed runs to compare"}
        run_id_b = runs[0]["id"]  # newer
        run_id_a = runs[1]["id"]  # older (baseline)

    def _run_stats(run_id):
        run = db.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            return None
        lessons = db.execute(
            "SELECT * FROM eval_lesson_results WHERE run_id=?", (run_id,)
        ).fetchall()
        chats = db.execute(
            "SELECT * FROM eval_chat_results WHERE run_id=?", (run_id,)
        ).fetchall()

        # Per-metric averages for lessons
        lesson_metrics = {}
        for r in lessons:
            if r["llm_scores_json"]:
                scores = json.loads(r["llm_scores_json"])
                for key in ["curriculum_match", "correctness", "universe_integration",
                            "child_friendliness", "engagement"]:
                    if isinstance(scores.get(key), (int, float)):
                        lesson_metrics.setdefault(key, []).append(scores[key])

        chat_metrics = {}
        for r in chats:
            if r["llm_scores_json"]:
                scores = json.loads(r["llm_scores_json"])
                for key in ["safety", "character_consistency", "helpfulness",
                            "age_appropriateness", "engagement"]:
                    if isinstance(scores.get(key), (int, float)):
                        chat_metrics.setdefault(key, []).append(scores[key])

        return {
            "run_id": run_id,
            "git_hash": run["git_hash"],
            "avg_det": run["avg_deterministic"],
            "avg_llm": run["avg_llm_score"],
            "lesson_metrics": {k: sum(v)/len(v) for k, v in lesson_metrics.items()},
            "chat_metrics": {k: sum(v)/len(v) for k, v in chat_metrics.items()},
        }

    a = _run_stats(run_id_a)
    b = _run_stats(run_id_b)
    db.close()

    if not a or not b:
        return {"error": "Run not found"}

    # Calculate deltas
    deltas = {"lessons": {}, "chats": {}}
    for key in a["lesson_metrics"]:
        if key in b["lesson_metrics"]:
            delta = b["lesson_metrics"][key] - a["lesson_metrics"][key]
            deltas["lessons"][key] = {
                "baseline": round(a["lesson_metrics"][key], 2),
                "current": round(b["lesson_metrics"][key], 2),
                "delta": round(delta, 2),
                "regression": delta < -0.5,
            }

    for key in a["chat_metrics"]:
        if key in b["chat_metrics"]:
            delta = b["chat_metrics"][key] - a["chat_metrics"][key]
            deltas["chats"][key] = {
                "baseline": round(a["chat_metrics"][key], 2),
                "current": round(b["chat_metrics"][key], 2),
                "delta": round(delta, 2),
                "regression": delta < -0.5,
            }

    det_delta = None
    if a["avg_det"] is not None and b["avg_det"] is not None:
        det_delta = round(b["avg_det"] - a["avg_det"], 3)

    regressions = []
    for category in ["lessons", "chats"]:
        for key, info in deltas[category].items():
            if info["regression"]:
                regressions.append(f"{category}.{key}: {info['baseline']} -> {info['current']} ({info['delta']:+.2f})")

    return {
        "baseline": a,
        "current": b,
        "deltas": deltas,
        "det_delta": det_delta,
        "regressions": regressions,
        "has_regressions": len(regressions) > 0,
    }


def get_run_details(run_id: int) -> dict | None:
    """Get full details of an eval run for dashboard."""
    db = _get_eval_db()
    run = db.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        db.close()
        return None

    lessons = db.execute(
        "SELECT * FROM eval_lesson_results WHERE run_id=? ORDER BY test_case_id",
        (run_id,)
    ).fetchall()

    chats = db.execute(
        "SELECT * FROM eval_chat_results WHERE run_id=? ORDER BY test_case_id",
        (run_id,)
    ).fetchall()

    db.close()

    return {
        "run": dict(run),
        "lessons": [dict(r) for r in lessons],
        "chats": [dict(r) for r in chats],
    }


def run_real_data_eval(db_path: str = None) -> int:
    """Evaluate existing lessons from the production DB. No new generation — almost free."""
    import glob as glob_mod

    if db_path is None:
        db_path = os.path.join(_BASE_DIR, "kidion.db")

    content_dir = os.path.join(_BASE_DIR, "content")
    json_files = sorted(glob_mod.glob(os.path.join(content_dir, "*.json")))

    if not json_files:
        print("No lesson JSON files found in content/. Generate some lessons first.")
        return -1

    eval_db = _get_eval_db()
    now = datetime.now(timezone.utc).isoformat()
    git_hash = _get_git_hash()

    eval_db.execute(
        "INSERT INTO eval_runs (started_at, git_hash, version, status) VALUES (?, ?, ?, 'running')",
        (now, git_hash, f"real-data ({len(json_files)} lessons)"),
    )
    eval_db.commit()
    run_id = eval_db.execute("SELECT last_insert_rowid()").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  Real-Data Eval Run #{run_id} | {len(json_files)} lessons")
    print(f"{'='*60}\n")

    lesson_results_for_recs = []
    lesson_det_scores = []
    lesson_llm_scores = []

    for i, jf in enumerate(json_files):
        fname = os.path.basename(jf)
        print(f"  [{i+1}/{len(json_files)}] {fname} ...", end=" ", flush=True)
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)

            lesson_json = data.get("lesson_json", {})
            topic = data.get("topic", "")
            subject = data.get("subject", "")
            grade = data.get("grade", 1)
            universe = data.get("universe", "")
            difficulty = data.get("difficulty_level", 2)
            lesson_id = data.get("lesson_id", 0)

            test_case = {
                "id": f"real_{lesson_id}",
                "subject": subject,
                "grade": grade,
                "topic": topic,
                "universe": universe,
                "difficulty_level": difficulty,
                "expected": {
                    "min_tasks": 5,
                    "min_story_blocks": 3,
                    "universe_in_text": bool(universe),
                    "math_check": subject == "math",
                },
            }

            # Level 1: deterministic
            det_results = run_all_validators(lesson_json, test_case)
            det_score = deterministic_score(det_results)
            lesson_det_scores.append(det_score)

            # Level 2: LLM judge
            llm_scores = judge_lesson(lesson_json, test_case)
            llm_avg = None
            if llm_scores:
                numeric = [v for k, v in llm_scores.items()
                           if isinstance(v, (int, float)) and k not in ("strengths", "weaknesses", "suggestion")]
                llm_avg = sum(numeric) / len(numeric) if numeric else None
                if llm_avg:
                    lesson_llm_scores.append(llm_avg)

            eval_db.execute(
                """INSERT INTO eval_lesson_results
                   (run_id, test_case_id, subject, grade, topic, universe,
                    lesson_json, methodologist_output,
                    deterministic_json, deterministic_score,
                    llm_scores_json, llm_avg_score, generation_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, f"real_{lesson_id}", subject, grade, topic, universe,
                 json.dumps(lesson_json, ensure_ascii=False),
                 data.get("methodologist_output", ""),
                 json.dumps(det_results, ensure_ascii=False),
                 det_score,
                 json.dumps(llm_scores, ensure_ascii=False) if llm_scores else None,
                 llm_avg, 0),
            )

            lesson_results_for_recs.append({
                "test_case_id": f"real_{lesson_id}",
                "deterministic": det_results,
                "llm_scores": llm_scores,
            })

            status = f"det={det_score:.0%}"
            if llm_avg:
                status += f" llm={llm_avg:.1f}/5"
            print(f"OK — {status}")

        except Exception as e:
            logger.error("Real data eval error for %s: %s", fname, e)
            eval_db.execute(
                """INSERT INTO eval_lesson_results
                   (run_id, test_case_id, error)
                   VALUES (?, ?, ?)""",
                (run_id, fname, str(e)),
            )
            print(f"ERROR: {e}")

        eval_db.commit()

    # Recommendations
    print("\n  Generating recommendations...", end=" ", flush=True)
    recommendations = generate_recommendations(lesson_results_for_recs, [])
    print(f"OK ({len(recommendations)} recommendations)")

    # Finalize
    finished = datetime.now(timezone.utc).isoformat()
    avg_det = sum(lesson_det_scores) / len(lesson_det_scores) if lesson_det_scores else None
    avg_llm = sum(lesson_llm_scores) / len(lesson_llm_scores) if lesson_llm_scores else None

    eval_db.execute(
        """UPDATE eval_runs SET
           finished_at=?, lesson_count=?, chat_count=0,
           avg_deterministic=?, avg_llm_score=?,
           recommendations_json=?, status='completed'
           WHERE id=?""",
        (finished, len(json_files),
         avg_det, avg_llm,
         json.dumps(recommendations, ensure_ascii=False),
         run_id),
    )
    eval_db.commit()
    eval_db.close()

    print(f"\n{'='*60}")
    print(f"  Real-Data Run #{run_id} complete! ({len(json_files)} lessons)")
    if avg_det is not None:
        print(f"  Deterministic avg: {avg_det:.0%}")
    if avg_llm is not None:
        print(f"  LLM judge avg: {avg_llm:.1f}/5")
    print(f"  Dashboard: /evals/dashboard")
    print(f"{'='*60}\n")

    return run_id


def get_all_runs() -> list[dict]:
    """Get summary of all eval runs."""
    db = _get_eval_db()
    runs = db.execute(
        "SELECT * FROM eval_runs ORDER BY id DESC"
    ).fetchall()
    db.close()
    return [dict(r) for r in runs]
