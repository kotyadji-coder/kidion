"""Prompts for generating worksheet tasks and activities, adapted for kidion context."""

from services.worksheet.models import SUBJECT_NAMES_RU, SUBJECT_TASK_POOLS

WORKSHEET_TASKS_PROMPT = """РОЛЬ:
Ты — креативный педагог-дизайнер рабочих листов для начальной школы РФ (1-4 класс).

БЕЗОПАСНОСТЬ КОНТЕНТА (ОБЯЗАТЕЛЬНО):
- ЗАПРЕЩЕНО генерировать контент с насилием, жестокостью, оружием, кровью.
- ЗАПРЕЩЕНО генерировать контент с сексуальным подтекстом или взрослыми темами.
- ЗАПРЕЩЕНО генерировать контент с дискриминацией, буллингом, оскорблениями.
- Весь контент ДОЛЖЕН быть безопасным и позитивным для детей 6-10 лет.

ЗАДАЧА:
Сгенерируй ровно 4 задания для печатного рабочего листа.
- Задание 1: ВСЕГДА тип "coloring" (раскраска + задание по картинке).
- Задания 2-4: из библиотеки механик по предмету (все разные типы).

КОНТЕКСТ РЕБЁНКА:
{child_context}

ТЕМА УРОКА: {topic}
ПРЕДМЕТ: {subject_ru}

РАСПРЕДЕЛЕНИЕ ТЕМ:
- Все 3 задания по одной теме.
- Задание coloring по общей вселенной ребёнка.

ЦЕЛЕВАЯ АУДИТОРИЯ: начальная школа (1-4 класс, 7-10 лет).
- Простые короткие предложения. Никаких сложных слов.
- Обращайся на "ты", тон дружеский и игровой.
- ВСЕ примеры и контент — из вселенной ребёнка (персонажи, предметы, локации).
- Контент строго по школьной программе для указанного класса.

═══════════════════════════════════════════════════════════════
БИБЛИОТЕКА МЕХАНИК
═══════════════════════════════════════════════════════════════

Выбирай из: {task_pool}

═══════════════════════════════════════════════════════════════
JSON-СХЕМЫ МЕХАНИК
═══════════════════════════════════════════════════════════════

0. coloring — ВСЕГДА первое.
   {{"type": "coloring", "instruction": "<короткая инструкция>", "prompt_text": "<задание по картинке>", "line_count": 3}}

1. matching — Соедини пары (4 элемента).
   {{"type": "matching", "instruction": "<инструкция>", "left_column": ["A","B","C","D"], "right_column": ["1","2","3","4"]}}

2. fill_blanks — Вставь пропущенное.
   {{"type": "fill_blanks", "instruction": "<инструкция>", "text_with_blanks": "Текст с ____ и ____.", "correct": ["слово1", "слово2"]}}

3. sorting_table — Рассортируй по 2 колонкам.
   {{"type": "sorting_table", "instruction": "<инструкция>", "column_headers": ["Заголовок 1", "Заголовок 2"], "word_bank": ["слово1","слово2","слово3","слово4"]}}

4. odd_one_out — Найди лишнее (4 элемента).
   {{"type": "odd_one_out", "instruction": "<инструкция>", "items": ["a","b","c","d"]}}

5. grid_maze — Лабиринт 4x4.
   {{"type": "grid_maze", "instruction": "<инструкция>", "grid_size": 4, "cells": ["16 значений"], "correct_path": [0,1,5,9,13,14,15]}}

6. number_pyramid — Пирамида.
   {{"type": "number_pyramid", "instruction": "<инструкция>", "rows": [[""], ["",""], ["5","","3"]]}}

7. magic_square — Магический квадрат 3x3.
   {{"type": "magic_square", "instruction": "<инструкция>", "grid": [["8","","6"],["","5",""],["4","","2"]], "target_sum": 15}}

8. comparison_chain — Поставь >, <, =.
   {{"type": "comparison_chain", "instruction": "<инструкция>", "pairs": [["15","12"],["8+3","10"],["6x2","13"],["20-5","14"]]}}

9. expression_builder — Расставь знаки.
   {{"type": "expression_builder", "instruction": "<инструкция>", "equations": ["3 O 2 O 1 = 4", "8 O 4 O 2 = 6"]}}

10. number_sequence — Продолжи закономерность.
    {{"type": "number_sequence", "instruction": "<инструкция>", "sequences": [["2","4","6","",""],["10","8","6","",""]]}}

11. anagram — Собери слово.
    {{"type": "anagram", "instruction": "<инструкция>", "scrambled": "ОЛШАК", "hint": "Подсказка", "answer_length": 5}}

12. word_search — Найди слова в сетке.
    {{"type": "word_search", "instruction": "<инструкция>", "words": ["СЛОВО","ДВА","ТРИ"], "grid_size": 8}}

13. syllable_builder — Собери слова из слогов.
    {{"type": "syllable_builder", "instruction": "<инструкция>", "syllable_groups": [["МО","ЛО","КО"],["КО","РО","ВА"],["СО","БА","КА"]]}}

14. sentence_order — Расставь слова.
    {{"type": "sentence_order", "instruction": "<инструкция>", "scrambled_sentences": [["кот","на","сидит","окне"],["идёт","в","школу","Маша"]]}}

15. word_chain — Цепочка слов.
    {{"type": "word_chain", "instruction": "<инструкция>", "given_words": ["молоко","огонь"], "chain_length": 5}}

16. missing_vowels — Впиши гласные.
    {{"type": "missing_vowels", "instruction": "<инструкция>", "words_with_gaps": ["к_р_в_","м_л_к_","с_б_к_"]}}

17. sequence_order — Расставь по порядку.
    {{"type": "sequence_order", "instruction": "<инструкция>", "items": ["гусеница","яйцо","бабочка","куколка"]}}

18. true_false_fix — Найди ошибку.
    {{"type": "true_false_fix", "instruction": "<инструкция>", "statements": ["У паука 6 ног","Солнце — звезда","Рыбы дышат лёгкими"]}}

19. cause_effect — Причина и следствие.
    {{"type": "cause_effect", "instruction": "<инструкция>", "causes": ["мороз","дождь","ветер","солнце"], "effects": ["вода замерзает","лужи","деревья качаются","снег тает"]}}

20. riddle_boxes — Загадки.
    {{"type": "riddle_boxes", "instruction": "<инструкция>", "riddles": ["Зимой белый, летом серый","Сто одёжек"], "answer_lengths": [4,7]}}

═══════════════════════════════════════════════════════════════
ПРАВИЛА
═══════════════════════════════════════════════════════════════

1. Задание #1 — ВСЕГДА coloring.
2. Задания #2, #3, #4 — РАЗНЫЕ типы из пула предмета.
3. ВСЕ задания в тематике вселенной ребёнка.
4. Инструкции КОРОТКИЕ (до 60 символов).
5. Контент по школьной программе для указанного класса.
6. Запрещены: звёздочки, LaTeX, знак $.
7. КОМПАКТНОСТЬ: всё на 1 страницу A4.

JSON-СТРУКТУРА ОТВЕТА:
{{
  "tasks": [
    {{"type": "coloring", ...}},
    <задание 2>,
    <задание 3>,
    <задание 4>
  ]
}}

Верни ТОЛЬКО JSON. Без markdown, без пояснений."""


ACTIVITY_PROMPT = """РОЛЬ:
Ты — креативный автор рабочих тетрадей для начальной школы в стиле «Банда умников».
Ты создаёшь увлекательные задания на ЦЕЛУЮ СТРАНИЦУ A4 с мини-историей.

БЕЗОПАСНОСТЬ КОНТЕНТА (ОБЯЗАТЕЛЬНО):
- ЗАПРЕЩЕНО генерировать контент с насилием, жестокостью, оружием, кровью.
- ЗАПРЕЩЕНО генерировать контент с сексуальным подтекстом или взрослыми темами.
- Весь контент ДОЛЖЕН быть безопасным и позитивным для детей 6-10 лет.

ЗАДАЧА:
Сгенерируй данные для активности типа "{activity_type}" в формате JSON.

КОНТЕКСТ РЕБЁНКА:
{child_context}

ТЕМА УРОКА: {topic}
ПРЕДМЕТ: {subject_ru}

═══════════════════════════════════════════════════════════════
ОБЯЗАТЕЛЬНЫЕ ПОЛЯ:
═══════════════════════════════════════════════════════════════

- "story": мини-история на 2-3 предложения. Стиль «Банда умников»: весело, от второго лица ("Ты...").
- "title": яркое название во вселенной ребёнка.

═══════════════════════════════════════════════════════════════
ТИПЫ АКТИВНОСТЕЙ:
═══════════════════════════════════════════════════════════════

▸ cipher — Шифровка. Реши пример → число → буква.
  {{
    "type": "cipher",
    "story": "<мини-история>",
    "title": "<название>",
    "instruction": "Реши пример, найди ответ в ключе и запиши букву!",
    "cipher_key": {{"5": "П", "8": "Р", "3": "И", "12": "В", "7": "Е", "10": "Т"}},
    "encoded_lines": ["2+3 4+4 1+2 6+6 3+4 5+5", "6+6 3+4 5+5 3+4 4+4"],
    "fun_answer_hint": "Подсказка: так говорят при встрече"
  }}
  Правила: ключей 6-10. Примеры по школьной программе.

▸ cafe — Тематическое кафе. Меню + задачи.
  {{
    "type": "cafe",
    "story": "<мини-история>",
    "title": "<название>",
    "cafe_name": "Кафе Три Метлы",
    "menu": [{{"name": "Сливочное пиво", "price": 15, "emoji": "🍺"}}],
    "tasks": [{{"question": "Гарри заказал 2 пива. Сколько?", "answer_lines": 1}}],
    "budget_task": "Составь заказ для 3 друзей. Бюджет:",
    "budget_amount": 100
  }}
  Правила: 5-8 блюд. Цены простые.

▸ shop — Магазин. Ценники + задачи.
  {{
    "type": "shop",
    "story": "<мини-история>",
    "title": "<название>",
    "shop_name": "Магазин Олливандера",
    "items": [{{"name": "Палочка", "price": 30, "emoji": "🪄"}}],
    "tasks": [{{"question": "Купи палочку и мантию. Сколько?", "answer_lines": 1}}],
    "shopping_list_task": "Собери набор. Бюджет:",
    "budget_amount": 120
  }}
  Правила: 5-8 предметов.

═══════════════════════════════════════════════════════════════
ПРАВИЛА
═══════════════════════════════════════════════════════════════

1. Всё во вселенной ребёнка.
2. История — от 2-го лица, с интригой.
3. ФГОС для класса. Не сложнее.
4. Язык простой. Обращение на "ты".
5. Запрещены: звёздочки, LaTeX, $.
6. Всё на 1 страницу A4.

Верни ТОЛЬКО JSON. Без markdown, без пояснений."""


def build_child_context(child: dict) -> str:
    """Build context string for worksheet prompts from child dict."""
    from datetime import date
    birth_str = child.get("birth_date", "")
    if birth_str:
        birth = date.fromisoformat(birth_str)
        today = date.today()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    else:
        age = child.get("grade", 1) + 6
    gender_text = "девочка" if child["gender"] == "girl" else "мальчик"

    interests = ""
    if child.get("interests"):
        import json
        try:
            interests_list = json.loads(child["interests"]) if isinstance(child["interests"], str) else child["interests"]
            interests = f" Интересы: {', '.join(interests_list)}."
        except (json.JSONDecodeError, TypeError):
            pass

    universe = child.get("universe", "приключения")
    universe_desc = child.get("universe_description") or ""
    universe_line = f" Описание вселенной: {universe_desc}." if universe_desc else ""

    return (
        f"Пол: {gender_text}. Возраст: {age} лет. "
        f"Класс: {child['grade']}. Вселенная: {universe}.{universe_line}{interests}"
    )


def get_worksheet_prompt(child: dict, topic: str, subject: str) -> str:
    """Build complete worksheet generation prompt."""
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)
    task_pool = ", ".join(SUBJECT_TASK_POOLS.get(subject, SUBJECT_TASK_POOLS["math"]))
    context = build_child_context(child)

    return WORKSHEET_TASKS_PROMPT.format(
        child_context=context,
        topic=topic,
        subject_ru=subject_ru,
        task_pool=task_pool,
    )


def get_activity_prompt(child: dict, topic: str, subject: str, activity_type: str) -> str:
    """Build activity generation prompt."""
    subject_ru = SUBJECT_NAMES_RU.get(subject, subject)
    context = build_child_context(child)

    return ACTIVITY_PROMPT.format(
        child_context=context,
        topic=topic,
        subject_ru=subject_ru,
        activity_type=activity_type,
    )


def pick_activity_type(subject: str) -> str:
    """Pick best activity type for lesson 5 based on subject."""
    import random
    if subject == "math":
        return random.choice(["cafe", "shop", "cipher"])
    elif subject == "russian":
        return "cipher"
    else:
        return random.choice(["cipher", "shop"])
