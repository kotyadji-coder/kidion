"""
services/curricula.py — curriculum loading and search for kidion.

Loads route curricula files into curriculum_templates table and provides
get_curriculum() and search_unit() helpers.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("kidion")


def load_curricula(db_path: str) -> None:
    """Load active route curricula into curriculum_templates table."""
    from db import get_connection
    from services.curriculum_routes import load_route_curricula, route_to_template_curriculum

    conn = get_connection(db_path)
    for (subject, grade), route in sorted(load_route_curricula().items()):
        data = route_to_template_curriculum(route)
        topics_json = json.dumps(data, ensure_ascii=False)
        row = conn.execute(
            "SELECT id FROM curriculum_templates WHERE subject=? AND grade=?",
            (subject, grade),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE curriculum_templates SET title=?, topics_json=?, updated_at=datetime('now') "
                "WHERE id=?",
                (data["title"], topics_json, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO curriculum_templates (subject, grade, title, topics_json) "
                "VALUES (?, ?, ?, ?)",
                (subject, grade, data["title"], topics_json),
            )
    conn.commit()
    logger.info("Route curricula loaded into DB")


def get_curriculum(conn, subject: str, grade: int) -> Optional[dict]:
    """Return full curriculum dict for (subject, grade) or None.
    
    Returned dict includes all DB columns plus a 'data' key with parsed JSON.
    """
    row = conn.execute(
        "SELECT * FROM curriculum_templates WHERE subject=? AND grade=?",
        (subject, grade),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["data"] = json.loads(result["topics_json"])
    return result


def search_unit(conn, subject: str, grade: int, query: str) -> Optional[dict]:
    """Find best matching unit in curriculum for (subject, grade) by substring search.
    
    Args:
        conn: SQLite connection
        subject: 'math' or 'russian'
        grade: class number (1-11)
        query: search string, e.g. 'сложение'
    
    Returns:
        unit dict {id, title, topics} or None if curriculum not found or no match.
    
    Search logic (no AI):
        - Tokenizes query by whitespace
        - Scores each unit:
          * +10 if full query substring found in unit title
          * +3 per token found in unit title
          * +5 if full query found in any topic title
          * +1 per token found in any topic title
        - Returns unit with highest score (> 0), else None
    """
    curriculum = get_curriculum(conn, subject, grade)
    if not curriculum:
        return None
    units = curriculum["data"].get("units", [])
    if not units:
        return None

    query_lower = query.lower().strip()
    if not query_lower:
        return None
    query_tokens = query_lower.split()

    best_unit = None
    best_score = -1

    for unit in units:
        score = 0
        unit_title_lower = unit["title"].lower()

        # Full query in unit title
        if query_lower in unit_title_lower:
            score += 10

        # Token matches in unit title
        for token in query_tokens:
            if token in unit_title_lower:
                score += 3

        # Topic title matches
        for topic in unit.get("topics", []):
            topic_title_lower = topic["title"].lower()
            if query_lower in topic_title_lower:
                score += 5
            for token in query_tokens:
                if token in topic_title_lower:
                    score += 1

        if score > best_score:
            best_score = score
            best_unit = unit

    # Return best unit only if there was at least one match
    if best_score > 0:
        return best_unit
    return None
