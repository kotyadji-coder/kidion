"""
chat_report.py — Generate weekly AI summaries of children's chat activity.

Called by cron (weekly) or manually. Produces a parent-facing summary
of topics discussed, interests shown, and overall activity.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("kidion")

_REPORT_PROMPT = """Ты — ассистент для родителей на платформе Kidion.
Ребёнок {child_name} ({grade} класс) общался с AI-персонажами на этой неделе.

Ниже — все сообщения за неделю. Напиши КРАТКИЙ отчёт для родителя (на русском):

1. **Основные темы** — о чём говорил ребёнок (3-5 пунктов)
2. **Интересы** — что его увлекает больше всего
3. **Настроение** — общее настроение общения (позитивное/нейтральное/тревожное)
4. **Рекомендация** — один совет родителю (например, какую тему можно обсудить вместе)

Формат: чистый текст, без markdown заголовков, компактно (до 300 слов).
Не упоминай технические детали (AI, модели, токены).

Сообщения:
{messages}
"""


def generate_weekly_report(
    child_name: str,
    grade: int,
    messages: list[dict],
) -> dict:
    """Generate an AI summary of a week's chat messages.

    Returns {"summary": str, "topics": list[str], "message_count": int}.
    """
    if not messages:
        return {
            "summary": "На этой неделе ребёнок не общался с персонажами.",
            "topics": [],
            "message_count": 0,
        }

    # Format messages for the prompt
    formatted = []
    for m in messages:
        role = "Ребёнок" if m["role"] == "user" else "Персонаж"
        char = m.get("character_key", "spark")
        formatted.append(f"[{role} → {char}]: {m['content'][:300]}")

    messages_text = "\n".join(formatted[-100:])  # last 100 messages max

    prompt = _REPORT_PROMPT.format(
        child_name=child_name,
        grade=grade,
        messages=messages_text,
    )

    from services.ai_client import get_model

    model = get_model("gemini-2.5-flash", system_instruction="Ты помощник для родителей.")
    if model is None:
        return {
            "summary": f"На этой неделе {child_name} отправил(а) {len(messages)} сообщений персонажам.",
            "topics": [],
            "message_count": len(messages),
        }

    try:
        response = model.generate_content(prompt)
        summary = response.text.strip() if response.text else ""
    except Exception as e:
        logger.error("Report generation error: %s", e)
        summary = f"На этой неделе {child_name} отправил(а) {len(messages)} сообщений персонажам."

    # Extract topics from messages (simple keyword approach)
    topics = _extract_topics(messages)

    return {
        "summary": summary,
        "topics": topics,
        "message_count": len(messages),
    }


def _extract_topics(messages: list[dict]) -> list[str]:
    """Extract topic keywords from user messages."""
    user_texts = " ".join(
        m["content"] for m in messages if m["role"] == "user"
    ).lower()

    topic_keywords = {
        "математика": ["математик", "задач", "пример", "считай", "сложи", "умнож"],
        "русский язык": ["русский", "слово", "буква", "предложени", "правило"],
        "окружающий мир": ["животн", "природ", "планет", "космос", "растени"],
        "история": ["истори", "царь", "король", "война", "древн"],
        "сказки": ["сказк", "истори", "расскаж", "придумай", "герой"],
        "наука": ["наук", "опыт", "эксперимент", "физик", "хими"],
        "рисование": ["нарисуй", "картинк", "рисунок", "покажи"],
        "игры": ["игр", "играть", "загадк", "викторин"],
    }

    found = []
    for topic, keywords in topic_keywords.items():
        if any(kw in user_texts for kw in keywords):
            found.append(topic)

    return found[:5]


def run_weekly_reports():
    """Generate reports for all children who chatted in the last 7 days.

    Called by cron or CLI: python -c "from services.chat_report import run_weekly_reports; run_weekly_reports()"
    """
    import sqlite3
    from db import (
        get_db_connection,
        get_kid_chats_by_child,
        get_kid_chat_messages,
        create_chat_report,
    )

    conn = get_db_connection()

    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    today_str = now.strftime("%Y-%m-%d")

    # Find all children who have chats
    rows = conn.execute(
        "SELECT DISTINCT c.id, c.name, c.grade FROM children c "
        "JOIN kid_chats kc ON kc.child_id = c.id "
        "WHERE kc.updated_at >= ?",
        (week_ago,),
    ).fetchall()

    generated = 0
    for row in rows:
        child_id = row["id"]
        child_name = row["name"]
        grade = row["grade"]

        # Check if report already exists for this week
        existing = conn.execute(
            "SELECT id FROM chat_reports WHERE child_id = ? AND date = ?",
            (child_id, today_str),
        ).fetchone()
        if existing:
            continue

        # Collect all messages from the last 7 days
        chats = get_kid_chats_by_child(conn, child_id)
        all_messages = []
        for chat in chats:
            msgs = get_kid_chat_messages(conn, chat["id"], limit=200)
            # Filter to last 7 days
            for m in msgs:
                if m.get("created_at", "") >= week_ago:
                    m["character_key"] = chat.get("character_key", "spark")
                    all_messages.append(m)

        if not all_messages:
            continue

        # Generate report
        report = generate_weekly_report(child_name, grade, all_messages)

        create_chat_report(
            conn,
            child_id=child_id,
            date=today_str,
            summary=report["summary"],
            topics_json=json.dumps(report["topics"], ensure_ascii=False),
            message_count=report["message_count"],
        )
        generated += 1
        logger.info("Generated weekly report for child %d (%s)", child_id, child_name)

    logger.info("Weekly reports done: %d generated", generated)
    return generated
