"""Worksheet generator: calls Gemini to get task data, renders to HTML, saves to content/."""

import json
import logging
import os
import re
import uuid

from jinja2 import Environment, FileSystemLoader

from services.worksheet.grids import build_crossword_grid, build_word_search_grid
from services.worksheet.prompts import (
    build_child_context,
    get_activity_prompt,
    get_worksheet_prompt,
    pick_activity_type,
)

logger = logging.getLogger("kidion")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONTENT_DIR = os.path.join(_BASE_DIR, "content")
_TEMPLATES_DIR = os.path.join(_BASE_DIR, "templates", "worksheets")

_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))
_jinja_env.filters["tojson"] = json.dumps


def _extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _postprocess_tasks(tasks: list[dict]) -> list[dict]:
    """Run code generators for tasks that need them (word search, crossword)."""
    for task in tasks:
        t = task.get("type")
        if t == "word_search" and "grid" not in task:
            task["grid"] = build_word_search_grid(
                task.get("words", []),
                task.get("grid_size", 8),
            )
        elif t == "crossword_mini" and "crossword" not in task:
            task["crossword"] = build_crossword_grid(
                task.get("words", []),
                task.get("clues", []),
            )
    return tasks


def generate_worksheet(child: dict, topic: str, subject: str,
                       lesson_number: int, server_url: str) -> str | None:
    """
    Generate a printable worksheet for a lesson.

    For lessons 1-4: regular 4-task worksheet.
    For lesson 5: full-page activity (cafe/shop/cipher).

    Returns worksheet URL or None on failure.
    """
    try:
        os.makedirs(_CONTENT_DIR, exist_ok=True)
        content_id = str(uuid.uuid4())[:8]

        if lesson_number == 5:
            return _generate_activity(child, topic, subject, content_id, server_url)
        else:
            return _generate_regular_worksheet(child, topic, subject, lesson_number, content_id, server_url)
    except Exception:
        logger.exception("Worksheet generation failed for child %s, topic '%s'", child.get("id"), topic)
        return None


def _generate_regular_worksheet(child: dict, topic: str, subject: str,
                                lesson_number: int, content_id: str,
                                server_url: str) -> str:
    """Generate a 4-task worksheet."""
    from services.gemini_client import _get_model, CHILD_SAFETY_SETTINGS
    from vertexai.generative_models import GenerationConfig

    model = _get_model()

    if model is None:
        tasks_data = _stub_worksheet_tasks(subject)
    else:
        prompt = get_worksheet_prompt(child, topic, subject)
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json"),
            safety_settings=CHILD_SAFETY_SETTINGS,
        )
        tasks_data = _extract_json(response.text)

    tasks = tasks_data.get("tasks", [])
    tasks = _postprocess_tasks(tasks)

    from services.worksheet.models import SUBJECT_NAMES_RU
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)

    context = {
        "title": f"Квест к уроку {lesson_number}",
        "subject": subject_ru,
        "grade": child.get("grade", ""),
        "topic": topic,
        "child_name": child.get("name"),
        "lesson_number": lesson_number,
        "coloring_image_url": None,
        "has_coloring_task": any(t.get("type") == "coloring" for t in tasks),
        "tasks": tasks,
    }

    html = _jinja_env.get_template("worksheet.html").render(**context)
    html_path = os.path.join(_CONTENT_DIR, f"{content_id}_worksheet.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return f"{server_url}/content/{content_id}_worksheet.html"


def _generate_activity(child: dict, topic: str, subject: str,
                       content_id: str, server_url: str) -> str:
    """Generate a full-page activity for lesson 5."""
    from services.gemini_client import _get_model, CHILD_SAFETY_SETTINGS
    from vertexai.generative_models import GenerationConfig

    activity_type = pick_activity_type(subject)
    model = _get_model()

    if model is None:
        activity_data = _stub_activity(activity_type)
    else:
        prompt = get_activity_prompt(child, topic, subject, activity_type)
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json"),
            safety_settings=CHILD_SAFETY_SETTINGS,
        )
        activity_data = _extract_json(response.text)

    from services.worksheet.models import SUBJECT_NAMES_RU
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)

    context = {
        "subject": subject_ru,
        "grade": child.get("grade", ""),
        "topic": topic,
        "child_name": child.get("name"),
        "lesson_number": 5,
        **activity_data,
    }

    template_name = f"{activity_type}.html"
    html = _jinja_env.get_template(template_name).render(**context)
    html_path = os.path.join(_CONTENT_DIR, f"{content_id}_worksheet.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return f"{server_url}/content/{content_id}_worksheet.html"


# ── STUBS ──────────────────────────────────────────────────────────────────

def _stub_worksheet_tasks(subject: str) -> dict:
    """Return sample tasks for stub mode."""
    if subject == "russian":
        return {"tasks": [
            {"type": "coloring", "instruction": "Раскрась и ответь", "prompt_text": "Что делает герой на картинке?", "line_count": 3},
            {"type": "matching", "instruction": "Соедини слово и значение",
             "left_column": ["Берёза", "Ромашка", "Волк", "Солнце"],
             "right_column": ["Цветок", "Дерево", "Звезда", "Животное"]},
            {"type": "fill_blanks", "instruction": "Вставь пропущенные буквы",
             "text_with_blanks": "М__л__ко. К__р__ва. С__б__ка.", "correct": ["о", "о", "о", "о", "о", "а"]},
            {"type": "odd_one_out", "instruction": "Найди лишнее слово",
             "items": ["Стол", "Стул", "Шкаф", "Кошка"]},
        ]}
    if subject == "world":
        return {"tasks": [
            {"type": "coloring", "instruction": "Раскрась и ответь", "prompt_text": "Какое время года на картинке?", "line_count": 2},
            {"type": "sorting_table", "instruction": "Распредели по временам года",
             "column_headers": ["Зима", "Лето"],
             "word_bank": ["Снег", "Жара", "Лыжи", "Купание", "Мороз", "Пляж"]},
            {"type": "sequence_order", "instruction": "Расставь по порядку",
             "items": ["Яйцо", "Гусеница", "Куколка", "Бабочка"]},
            {"type": "true_false_fix", "instruction": "Найди ошибку и исправь",
             "statements": ["У паука 6 ног", "Солнце — это звезда", "Рыбы дышат лёгкими"]},
        ]}
    # math default
    return {"tasks": [
        {"type": "coloring", "instruction": "Раскрась и посчитай", "prompt_text": "Сколько предметов на картинке?", "line_count": 2},
        {"type": "comparison_chain", "instruction": "Поставь знак >, < или =",
         "pairs": [["15", "12"], ["8+3", "10"], ["6+6", "13"], ["20-5", "14"]]},
        {"type": "number_sequence", "instruction": "Продолжи ряд",
         "sequences": [["2", "4", "6", "", ""], ["10", "8", "6", "", ""]]},
        {"type": "expression_builder", "instruction": "Расставь знаки +, - чтобы получилось верно",
         "equations": ["3 O 2 O 1 = 4", "8 O 4 O 2 = 6", "5 O 3 O 1 = 7"]},
    ]}


def _stub_activity(activity_type: str) -> dict:
    """Return sample activity data for stub mode."""
    if activity_type == "cafe":
        return {
            "type": "cafe",
            "story": "Ты — главный повар в волшебном кафе! Сегодня у тебя полно заказов.",
            "title": "Волшебное кафе",
            "cafe_name": "Кафе Искорки",
            "menu": [
                {"name": "Блинчики", "price": 10, "emoji": "🥞"},
                {"name": "Какао", "price": 5, "emoji": "☕"},
                {"name": "Пирожок", "price": 8, "emoji": "🥧"},
                {"name": "Сок", "price": 7, "emoji": "🧃"},
                {"name": "Мороженое", "price": 12, "emoji": "🍦"},
            ],
            "tasks": [
                {"question": "Мама заказала блинчики и какао. Сколько она заплатит?", "answer_lines": 1},
                {"question": "Папа взял 2 пирожка. Какая сдача с 20 монет?", "answer_lines": 1},
                {"question": "Что дешевле — какао или сок? На сколько?", "answer_lines": 1},
            ],
            "budget_task": "Составь заказ для семьи из 3 человек. Бюджет:",
            "budget_amount": 50,
        }
    if activity_type == "shop":
        return {
            "type": "shop",
            "story": "Ты попал в магазин школьных принадлежностей! Собери всё нужное.",
            "title": "Магазин Знаний",
            "shop_name": "Магазин Искорки",
            "items": [
                {"name": "Тетрадь", "price": 5, "emoji": "📓"},
                {"name": "Ручка", "price": 3, "emoji": "🖊️"},
                {"name": "Ластик", "price": 2, "emoji": "🧹"},
                {"name": "Линейка", "price": 4, "emoji": "📏"},
                {"name": "Карандаш", "price": 3, "emoji": "✏️"},
            ],
            "tasks": [
                {"question": "Купи тетрадь и ручку. Сколько заплатишь?", "answer_lines": 1},
                {"question": "У тебя 15 монет. Хватит ли на 2 тетради и ластик?", "answer_lines": 1},
                {"question": "Что дороже — ластик или карандаш? На сколько?", "answer_lines": 1},
            ],
            "shopping_list_task": "Собери набор школьника. Бюджет:",
            "budget_amount": 30,
        }
    # cipher default
    return {
        "type": "cipher",
        "story": "Ты — тайный агент! Расшифруй послание от командира.",
        "title": "Секретное послание",
        "instruction": "Реши пример, найди ответ в ключе и запиши букву!",
        "cipher_key": {"5": "П", "8": "Р", "3": "И", "12": "В", "7": "Е", "10": "Т"},
        "encoded_lines": ["2+3 4+4 1+2 6+6 3+4 5+5"],
        "fun_answer_hint": "Подсказка: так говорят при встрече",
    }


def generate_batch_print_html(worksheets: list[dict]) -> str:
    """
    Combine multiple worksheet URLs into a single printable HTML document.

    worksheets: list of dicts with keys: lesson_number, worksheet_url, topic_title
    Returns HTML string with page breaks between worksheets.
    """
    pages = []
    for ws in worksheets:
        pages.append(f"""
        <div class="batch-page">
            <iframe src="{ws['worksheet_url']}" class="batch-iframe"></iframe>
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Рабочие листы</title>
<style>
@page {{ size: A4 portrait; margin: 0; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #f0f0f5; }}
.batch-page {{
    width: 210mm; height: 297mm;
    page-break-after: always;
    overflow: hidden;
    margin: 0 auto;
}}
.batch-page:last-child {{ page-break-after: auto; }}
.batch-iframe {{
    width: 100%; height: 100%;
    border: none;
}}
.print-bar {{
    display: flex; justify-content: center; padding: 16px;
    background: #fff; position: sticky; top: 0; z-index: 100;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}}
.print-btn {{
    background: #6366f1; color: #fff; border: none;
    padding: 12px 32px; border-radius: 50px;
    font-family: 'Nunito', sans-serif; font-size: 16px; font-weight: 800;
    cursor: pointer;
}}
.print-btn:hover {{ background: #4f46e5; }}
@media print {{
    .print-bar {{ display: none !important; }}
    body {{ background: #fff; }}
}}
</style>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@700;800&display=swap" rel="stylesheet">
</head>
<body>
<div class="print-bar">
    <button class="print-btn" onclick="window.print()">Распечатать все листы ({len(worksheets)} шт.)</button>
</div>
{''.join(pages)}
</body>
</html>"""
