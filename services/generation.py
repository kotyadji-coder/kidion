import uuid
import logging
from datetime import date

from services.gemini_client import generate_explanation, generate_image_prompt, generate_image_prompt_fallback
from services.image_generator import generate_image
from services.content_generator import save_lesson_html

logger = logging.getLogger("kidion")


def build_question(child: dict, topic: str, subject: str, prev_lesson_titles: list[str]) -> str:
    """Build the question string for METHODOLOGIST_PROMPT."""
    # Compute age from birth_date
    birth = date.fromisoformat(child["birth_date"])
    today = date.today()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))

    gender_text = "девочка" if child["gender"] == "girl" else "мальчик"

    difficulty_instructions = {
        1: "Уровень сложности: ЛЁГКИЙ. Меньше вариантов ответа, добавляй подсказки, используй простые формулировки.",
        2: "Уровень сложности: СРЕДНИЙ. Стандартные задания.",
        3: "Уровень сложности: СЛОЖНЫЙ. Больше вариантов ответа, добавляй ловушки, задания на применение знаний.",
    }
    difficulty_text = difficulty_instructions.get(child["difficulty_level"], difficulty_instructions[2])

    context_text = ""
    if prev_lesson_titles:
        context_text = f"\nПредыдущие уроки (не повторять): {', '.join(prev_lesson_titles)}"

    return (
        f"Пол: {gender_text}. Возраст: {age} лет. "
        f"Класс: {child['grade']}. Любимая вселенная: {child['universe']}. "
        f"Тема урока: {topic}. Предмет: {subject}. "
        f"{difficulty_text}{context_text}"
    )


def generate_lesson_content(lesson_id: int, child: dict, topic: str, subject: str,
                             db_path: str, server_url: str,
                             lesson_number: int = 1) -> None:
    """Background task: generate lesson and save content_url to DB.

    lesson_number: 1-5 within topic (5 = activity worksheet instead of regular).
    """
    import sqlite3
    from db import get_connection, update_lesson_content, get_recent_lesson_titles

    try:
        conn = get_connection(db_path)
        prev_titles = get_recent_lesson_titles(conn, child["id"], limit=3)
        question = build_question(child, topic, subject, prev_titles)

        _, lesson_json = generate_explanation(question)

        # Substitute {child_name} placeholder with actual child name
        child_name = child.get("name", "")
        for block in lesson_json.get("story_blocks", []):
            if "text" in block:
                block["text"] = block["text"].replace("{child_name}", child_name)
        for task in lesson_json.get("tasks", []):
            if "question" in task:
                task["question"] = task["question"].replace("{child_name}", child_name)

        story_text = "\n".join(b["text"] for b in lesson_json.get("story_blocks", []))

        try:
            img_prompt = generate_image_prompt(story_text)
            image_bytes = generate_image(img_prompt)
        except Exception:
            try:
                img_prompt_fallback = generate_image_prompt_fallback(story_text)
                image_bytes = generate_image(img_prompt_fallback)
            except Exception:
                image_bytes = None

        content_id = str(uuid.uuid4())[:8]
        content_url = save_lesson_html(image_bytes, lesson_json, content_id, server_url)
        print_url = f"{server_url}/content/{content_id}_print.html"

        # Generate printable worksheet
        worksheet_url = None
        try:
            from services.worksheet.generator import generate_worksheet
            worksheet_url = generate_worksheet(child, topic, subject, lesson_number, server_url)
        except Exception:
            logger.exception("Worksheet generation failed for lesson %s", lesson_id)

        update_lesson_content(conn, lesson_id, content_url, print_url, "done",
                              worksheet_url=worksheet_url)
    except Exception as e:
        logger.exception("Generation failed for lesson %s", lesson_id)
        try:
            conn = get_connection(db_path)
            update_lesson_content(conn, lesson_id, None, None, "error")
        except Exception:
            pass
