#!/usr/bin/env python3
"""Print non-PII curriculum diagnostics for Kidion.

The script is intentionally read-only by default and reports aggregate counts
only. It is safe to run against production when operators need to verify route
curriculum data after a deploy.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


ACTIVE_SUBJECTS = ("math", "russian")
ACTIVE_GRADES = range(1, 7)


def _default_db_path() -> str:
    return os.environ.get("DATABASE_PATH", "./kidion.db")


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    resolved = Path(db_path).expanduser()
    uri = f"file:{resolved}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def print_diagnostics(conn: sqlite3.Connection) -> None:
    active_subjects = tuple(ACTIVE_SUBJECTS)
    print("curriculum_templates_total", _count(conn, "SELECT COUNT(*) FROM curriculum_templates"))
    print(
        "curriculum_templates_active",
        _count(
            conn,
            "SELECT COUNT(*) FROM curriculum_templates "
            "WHERE subject IN (?, ?) AND grade BETWEEN 1 AND 6",
            active_subjects,
        ),
    )
    print(
        "curriculum_topics_active",
        _count(
            conn,
            "SELECT COUNT(*) FROM curriculum_topics "
            "WHERE subject IN (?, ?) AND grade BETWEEN 1 AND 6",
            active_subjects,
        ),
    )
    print(
        "curriculum_lessons_active",
        _count(
            conn,
            "SELECT COUNT(*) FROM curriculum_lessons cl "
            "JOIN curriculum_topics ct ON ct.id = cl.topic_id "
            "WHERE ct.subject IN (?, ?) AND ct.grade BETWEEN 1 AND 6",
            active_subjects,
        ),
    )
    print("curriculum_enrollments_total", _count(conn, "SELECT COUNT(*) FROM curriculum_enrollments"))
    print("child_lesson_progress_total", _count(conn, "SELECT COUNT(*) FROM child_lesson_progress"))

    print("routes_by_subject_grade")
    rows = conn.execute(
        "SELECT ct.subject, ct.grade, COUNT(DISTINCT ct.id) AS topics, COUNT(cl.id) AS lessons "
        "FROM curriculum_topics ct "
        "LEFT JOIN curriculum_lessons cl ON cl.topic_id = ct.id "
        "WHERE ct.subject IN (?, ?) AND ct.grade BETWEEN 1 AND 6 "
        "GROUP BY ct.subject, ct.grade "
        "ORDER BY ct.subject, ct.grade",
        active_subjects,
    ).fetchall()
    for row in rows:
        print(f"{row['subject']} {row['grade']} topics={row['topics']} lessons={row['lessons']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=_default_db_path(), help="SQLite DB path. Defaults to DATABASE_PATH or ./kidion.db")
    args = parser.parse_args()

    conn = _connect_readonly(args.db)
    try:
        print_diagnostics(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
