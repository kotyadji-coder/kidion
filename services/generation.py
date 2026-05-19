import json
import os
import re
import uuid
import logging
from datetime import date

from services.gemini_client import generate_explanation, generate_image_prompt, generate_image_prompt_fallback, generate_skip_test, generate_visual_layout
from services.image_generator import generate_image
from services.content_generator import save_lesson_html

logger = logging.getLogger("kidion")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")
_LOGS_DIR = os.path.join(_BASE_DIR, "logs")

# ── File logger for generation validation ──
os.makedirs(_LOGS_DIR, exist_ok=True)
_val_logger = logging.getLogger("kidion.validation")
_val_logger.setLevel(logging.INFO)
_val_handler = logging.FileHandler(os.path.join(_LOGS_DIR, "generation.log"), encoding="utf-8")
_val_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
if not _val_logger.handlers:
    _val_logger.addHandler(_val_handler)


def _eval_simple_expr(expr_str: str) -> int | None:
    """Safely evaluate simple arithmetic: '20 + 30', '70 - 40'. Returns None if can't parse."""
    expr_str = expr_str.strip()
    m = re.match(r'^(\d+)\s*([+\-*/])\s*(\d+)$', expr_str)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == '+': return a + b
    if op == '-': return a - b
    if op == '*': return a * b
    if op == '/' and b != 0: return a // b
    return None


def _count_emoji(s: str) -> dict:
    """Count emoji groups separated by +, -, =. Returns {'left': [...counts], 'result': count}."""
    import unicodedata
    def count_in(part):
        return sum(1 for ch in part if unicodedata.category(ch).startswith(('So', 'Sk')))

    parts = re.split(r'\s*=\s*', s)
    if len(parts) != 2:
        return {}
    left_parts = re.split(r'\s*[+]\s*', parts[0])
    return {
        'left': [count_in(p) for p in left_parts],
        'result': count_in(parts[1]),
    }


def validate_lesson(lesson_json: dict, visual_blocks: list[dict] | None,
                     lesson_id: int, topic: str) -> None:
    """Validate generated lesson content and log errors to generation.log."""
    errors = []

    # ── Validate tasks ──
    for i, task in enumerate(lesson_json.get("tasks", [])):
        task_type = task.get("type", "unknown")
        question = task.get("question", "")

        if task_type in ("quiz", "fill_in_the_blank"):
            correct = task.get("correct", "")
            # Check if question contains an arithmetic expression we can verify
            expr_match = re.search(r'(\d+)\s*([+\-])\s*(\d+)\s*=\s*[_?]', question)
            if expr_match:
                expected = _eval_simple_expr(f"{expr_match.group(1)} {expr_match.group(2)} {expr_match.group(3)}")
                if expected is not None:
                    try:
                        answer_num = int(re.sub(r'[^\d\-]', '', str(correct)))
                        if answer_num != expected:
                            errors.append(
                                f"Task {i+1} ({task_type}): arithmetic mismatch in question. "
                                f"'{expr_match.group(1)} {expr_match.group(2)} {expr_match.group(3)}' = {expected}, "
                                f"but correct_answer = '{correct}'"
                            )
                    except (ValueError, TypeError):
                        pass

            # Check correct answer is in options (quiz)
            if task_type == "quiz":
                options = task.get("options", [])
                if correct and options and correct not in options:
                    errors.append(
                        f"Task {i+1} (quiz): correct answer '{correct}' not in options {options}"
                    )

        elif task_type == "multiple_choice":
            correct_list = task.get("correct", [])
            options = task.get("options", [])
            for c in correct_list:
                if c not in options:
                    errors.append(
                        f"Task {i+1} (multiple_choice): correct answer '{c}' not in options {options}"
                    )

        elif task_type == "drag_and_drop":
            items = task.get("items", [])
            zones = task.get("zones", [])
            correct_map = task.get("correct", {})
            if len(items) != len(zones):
                errors.append(
                    f"Task {i+1} (drag_and_drop): items ({len(items)}) != zones ({len(zones)})"
                )
            if isinstance(correct_map, dict) and len(correct_map) != len(items):
                errors.append(
                    f"Task {i+1} (drag_and_drop): correct map has {len(correct_map)} entries, expected {len(items)}"
                )

    # ── Validate visual blocks (emoji_hero) ──
    if visual_blocks:
        for i, block in enumerate(visual_blocks):
            if block.get("type") != "emoji_hero":
                continue
            emoji_str = block.get("emoji", "")
            caption = block.get("caption", "")

            # Check caption arithmetic
            cap_match = re.search(r'(\d+)\s*([+\-])\s*(\d+)\s*=\s*(\d+)', caption)
            if cap_match:
                expected = _eval_simple_expr(f"{cap_match.group(1)} {cap_match.group(2)} {cap_match.group(3)}")
                actual = int(cap_match.group(4))
                if expected is not None and expected != actual:
                    errors.append(
                        f"emoji_hero block {i}: caption arithmetic wrong. "
                        f"'{cap_match.group(1)} {cap_match.group(2)} {cap_match.group(3)}' = {expected}, "
                        f"but caption says = {actual}"
                    )

            # Check emoji counts match
            if '=' in emoji_str and cap_match:
                counts = _count_emoji(emoji_str)
                if counts and counts.get('left'):
                    emoji_sum = sum(counts['left'])
                    emoji_result = counts.get('result', 0)
                    if emoji_sum != emoji_result:
                        errors.append(
                            f"emoji_hero block {i}: emoji count mismatch. "
                            f"left side sums to {emoji_sum} emoji, but result has {emoji_result}"
                        )

    # ── Log results ──
    if errors:
        _val_logger.warning(
            "Lesson %s (topic='%s'): %d validation error(s):\n  %s",
            lesson_id, topic, len(errors), "\n  ".join(errors)
        )
    else:
        _val_logger.info("Lesson %s (topic='%s'): validation passed", lesson_id, topic)


def build_question(child: dict, topic: str, subject: str, prev_lesson_titles: list[str]) -> str:
    """Build the question string for METHODOLOGIST_PROMPT."""
    # Compute age from birth_date or estimate from grade
    birth_str = child.get("birth_date", "")
    if birth_str:
        birth = date.fromisoformat(birth_str)
        today = date.today()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    else:
        age = child.get("grade", 1) + 6  # estimate: grade 1 ≈ 7 years old

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

    universe_desc = child.get("universe_description") or ""
    universe_line = f" Описание вселенной: {universe_desc}" if universe_desc else ""

    return (
        f"Пол: {gender_text}. Возраст: {age} лет. "
        f"Класс: {child['grade']}. Любимая вселенная: {child['universe']}.{universe_line} "
        f"Тема урока: {topic}. Предмет: {subject}. "
        f"{difficulty_text}{context_text}"
    )


def _get_or_generate_topic_image(conn, child: dict, topic: str, subject: str,
                                  story_text: str, server_url: str) -> bytes | None:
    """Return image bytes for a topic, reusing cached image if available."""
    from db import get_topic_image, save_topic_image

    grade = child["grade"]
    cached_filename = get_topic_image(conn, subject, grade, topic)

    if cached_filename:
        # Reuse existing image
        cached_path = os.path.join(_CONTENT_DIR, cached_filename)
        if os.path.exists(cached_path):
            with open(cached_path, "rb") as f:
                return f.read()
        logger.warning("Cached topic image file missing: %s", cached_path)

    # Generate new image
    image_bytes = None
    try:
        img_prompt = generate_image_prompt(story_text)
        image_bytes = generate_image(img_prompt)
    except Exception:
        try:
            img_prompt_fallback = generate_image_prompt_fallback(story_text)
            image_bytes = generate_image(img_prompt_fallback)
        except Exception:
            pass

    # Save to cache if generated
    if image_bytes:
        os.makedirs(_CONTENT_DIR, exist_ok=True)
        filename = f"topic_{subject}_{grade}_{uuid.uuid4().hex[:8]}.png"
        img_path = os.path.join(_CONTENT_DIR, filename)
        with open(img_path, "wb") as f:
            f.write(image_bytes)
        save_topic_image(conn, subject, grade, topic, filename)

    return image_bytes


def generate_lesson_content(lesson_id: int, child: dict, topic: str, subject: str,
                             db_path: str, server_url: str,
                             lesson_number: int = 1, mode: str = "normal") -> None:
    """Background task: generate lesson and save content_url to DB.

    lesson_number: 1-5 within topic (5 = activity worksheet instead of regular).
    """
    from db import (
        get_connection, update_lesson_content, get_recent_lesson_titles,
        get_cached_methodologist, save_methodologist_cache,
    )

    try:
        conn = get_connection(db_path)
        prev_titles = get_recent_lesson_titles(conn, child["id"], limit=3)
        question = build_question(child, topic, subject, prev_titles)

        if mode == "skip_test":
            # Skip test: only generate 5 tasks, no theory/images/worksheets
            lesson_json = generate_skip_test(question)
            lesson_json["story_blocks"] = []

            content_id = str(uuid.uuid4())[:8]
            content_url = save_lesson_html(None, lesson_json, content_id, server_url,
                                           visual_blocks=[])
            update_lesson_content(conn, lesson_id, content_url, None, "done")
        else:
            # Full lesson: methodologist + tutor-gamer + visual layout + image + worksheet
            grade = child["grade"]
            cached_method = get_cached_methodologist(conn, subject, grade, topic)

            methodologist_output, lesson_json = generate_explanation(
                question, cached_methodologist=cached_method
            )

            if not cached_method and methodologist_output != "stub":
                save_methodologist_cache(conn, subject, grade, topic, methodologist_output)
                logger.info("Cached methodologist for %s/%s/%s", subject, grade, topic)

            child_name = child.get("name", "")
            for block in lesson_json.get("story_blocks", []):
                if "text" in block:
                    block["text"] = block["text"].replace("{child_name}", child_name)
            for task in lesson_json.get("tasks", []):
                if "question" in task:
                    task["question"] = task["question"].replace("{child_name}", child_name)

            story_text = "\n".join(b["text"] for b in lesson_json.get("story_blocks", []))

            character_name = child.get("character_name") or "Искатель"
            character_emoji = "🦊"
            universe_desc = child.get("universe_description") or ""
            visual_blocks = generate_visual_layout(
                lesson_json.get("story_blocks", []),
                topic, subject,
                character_name=character_name,
                character_emoji=character_emoji,
                universe_description=universe_desc,
            )

            validate_lesson(lesson_json, visual_blocks, lesson_id, topic)

            image_bytes = _get_or_generate_topic_image(
                conn, child, topic, subject, story_text, server_url
            )

            content_id = str(uuid.uuid4())[:8]
            content_url = save_lesson_html(image_bytes, lesson_json, content_id, server_url,
                                           visual_blocks=visual_blocks)

            # Save raw JSON for eval system
            json_path = os.path.join(_CONTENT_DIR, f"{content_id}.json")
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "lesson_id": lesson_id,
                        "child_id": child["id"],
                        "topic": topic,
                        "subject": subject,
                        "grade": child.get("grade", 1),
                        "universe": child.get("universe", ""),
                        "difficulty_level": child.get("difficulty_level", 2),
                        "lesson_json": lesson_json,
                        "methodologist_output": methodologist_output,
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.debug("Failed to save lesson JSON for evals", exc_info=True)

            worksheet_url = None
            try:
                from services.worksheet.generator import generate_worksheet
                worksheet_url = generate_worksheet(child, topic, subject, lesson_number, server_url)
            except Exception:
                logger.exception("Worksheet generation failed for lesson %s", lesson_id)

            lesson_icon = None
            story_blocks = lesson_json.get("story_blocks", [])
            if story_blocks:
                lesson_icon = story_blocks[0].get("emoji")

            update_lesson_content(conn, lesson_id, content_url, worksheet_url, "done",
                                  worksheet_url=worksheet_url, icon=lesson_icon)
    except Exception:
        logger.exception("Generation failed for lesson %s", lesson_id)
        try:
            conn = get_connection(db_path)
            update_lesson_content(conn, lesson_id, None, None, "error")
        except Exception:
            pass
