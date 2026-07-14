"""
universe.py — Generate personalized universes, characters, and shop items for children.

Uses Gemini for text generation and Gemini Flash for image generation.
In stub mode (no GOOGLE_CLOUD_PROJECT), returns predefined defaults.
"""

import json
import logging
import os
import re
from json import JSONDecodeError

logger = logging.getLogger("kidion")


def _get_text_model():
    """Get Gemini model for text generation. Returns None in stub mode."""
    from services.ai_client import get_model
    return get_model("gemini-3.5-flash", feature="universe")


def _stub_universe(child_name: str, interests_str: str) -> dict:
    """Return a predefined structured universe for stub/test mode."""
    return {
        "name": "Мастерская Искателей",
        "premise": (
            f"Мастерская Искателей — уютная база на вершине дерева, "
            f"где юные исследователи изучают мир вокруг. "
            f"Здесь всё связано с тем, что любит {child_name}: {interests_str}."
        ),
        "tone": "приключенческий, дружелюбный",
        "subject_zones": {
            "math": {
                "zone_name": "Конструкторский цех",
                "description": "Здесь проектируют и строят изобретения — нужны точные расчёты.",
                "lesson_frame": "Чтобы построить новое изобретение, нужно разобраться в [тема урока]",
            },
            "russian": {
                "zone_name": "Радиорубка",
                "description": "Отсюда передают сообщения по всему миру — нужно писать чётко и грамотно.",
                "lesson_frame": "Чтобы передать важное сообщение, нужно знать [тема урока]",
            },
            "english": {
                "zone_name": "Портал Дальних Земель",
                "description": "Портал связывает с англоговорящими друзьями из другого мира.",
                "lesson_frame": "Чтобы поговорить с друзьями из Дальних Земель, нужно выучить [тема урока]",
            },
            "world": {
                "zone_name": "Экспедиционный штаб",
                "description": "Отсюда уходят исследовательские группы изучать природу и окружающий мир.",
                "lesson_frame": "Чтобы подготовиться к экспедиции, нужно узнать про [тема урока]",
            },
        },
        "year_mission": "Построить Летающий Корабль и отправиться в Большую Экспедицию",
        "progression": "Каждые 5 уроков — новый модуль корабля собран",
        "npcs": [
            {"name": "Тинкер", "role": "наставник", "personality": "мудрый, терпеливый", "appearance": "старый ёж в очках и фартуке с инструментами"},
            {"name": "Зипка", "role": "друг", "personality": "весёлая, любопытная", "appearance": "маленькая белка с рюкзачком и картой"},
        ],
        "character_name": "Искорка",
        "character_prompt": (
            "A cute friendly fox character, wearing a wizard hat and a backpack with books. "
            "The fox has bright orange fur, big green eyes, and a fluffy tail with a star-shaped tip. "
            "Style: cute cartoon, Pixar-like, friendly. Full body, white background."
        ),
    }


def _universe_to_description(data: dict) -> str:
    """Convert structured universe dict to a rich text description for storage."""
    import json as _json
    return _json.dumps(data, ensure_ascii=False)


def _strip_markdown_fence(raw: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    return cleaned.strip()


def _first_balanced_json(raw: str) -> str:
    """Return the first balanced JSON object/array, ignoring model text after it."""
    start = -1
    opening = ""
    for idx, char in enumerate(raw):
        if char in "{[":
            start = idx
            opening = char
            break
    if start < 0:
        return raw.strip()

    closing = "}" if opening == "{" else "]"
    stack = [closing]
    in_string = False
    escaped = False

    for idx in range(start + 1, len(raw)):
        char = raw[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or char != stack[-1]:
                break
            stack.pop()
            if not stack:
                return raw[start:idx + 1].strip()

    return raw[start:].strip()


def _repair_json(candidate: str) -> str:
    """Repair common LLM JSON slips without changing values."""
    repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
    repaired = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', repaired)
    return repaired


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and parse the first JSON object from a model response."""
    cleaned = _first_balanced_json(_strip_markdown_fence(raw))
    try:
        return json.loads(cleaned)
    except JSONDecodeError:
        repaired = _repair_json(cleaned)
        if repaired != cleaned:
            return json.loads(repaired)
        raise


def generate_universe(
    child_name: str,
    gender: str,
    grade: int,
    interests: list[str],
) -> dict:
    """
    Generate a personalized universe description based on child's interests.

    Returns dict with keys:
    - universe_description: str (2-3 paragraphs describing the universe)
    - character_prompt: str (detailed prompt for consistent character generation)
    """
    model = _get_text_model()

    interests_str = ", ".join(interests) if interests else "приключения, природа"
    gender_ru = "мальчик" if gender == "boy" else "девочка"

    prompt = f"""Ты — сценарист детских образовательных вселенных и геймдизайнер.

БЕЗОПАСНОСТЬ КОНТЕНТА (ОБЯЗАТЕЛЬНО):
- ЗАПРЕЩЕНО генерировать контент с насилием, жестокостью, оружием, кровью.
- ЗАПРЕЩЕНО генерировать контент с сексуальным подтекстом или взрослыми темами.
- ЗАПРЕЩЕНО генерировать контент с дискриминацией, буллингом, оскорблениями.
- Весь контент ДОЛЖЕН быть безопасным и позитивным для детей 6-10 лет.

Ребёнок: {gender_ru}, {grade} класс.
Интересы: {interests_str}

## ГЛАВНАЯ ЗАДАЧА
Придумай СТРУКТУРИРОВАННУЮ учебную вселенную, которая:
1. Объединяет ВСЕ интересы ребёнка в одном ярком, конкретном мире (не "волшебный мир знаний", а конкретный сеттинг: лаборатория, корабль, остров, станция и т.д.)
2. Имеет 4 предметные зоны (по одной для каждого школьного предмета)
3. Имеет годовую миссию — глобальную цель, к которой ребёнок идёт весь учебный год
4. Имеет NPC-персонажей с именами и ролями

## ПРАВИЛА СОЗДАНИЯ ВСЕЛЕННОЙ
- Название вселенной должно быть КОНКРЕТНЫМ и отражать интересы (не "Мир Знаний", а "Лаборатория Дино-Тех" или "Космическая Ферма Роботов")
- Каждая предметная зона — это МЕСТО в мире, логически связанное с предметом:
  * math — место, где считают, строят, проектируют (мастерская, верфь, лаборатория)
  * russian — место, где работают со словами (архив, радиостанция, библиотека, редакция)
  * english — место контакта с другим миром/культурой (порт, посольство, портал) — логичный повод для другого языка
  * world — место наблюдения за природой (экспедиционная база, обсерватория, сад, заповедник)
- lesson_frame для каждой зоны — шаблон, как вписать ЛЮБУЮ школьную тему в контекст этой зоны
- Годовая миссия должна быть конкретной и достижимой: построить корабль, подготовить экспедицию, спасти остров, открыть все земли
- NPC: 2-3 персонажа с УНИКАЛЬНЫМИ именами (не "Мудрая Сова"), один из них — наставник, один — друг-ровесник

## ПЕРСОНАЖ-ПРОВОДНИК
Придумай персонажа-проводника. Опиши внешность подробно: тип существа, телосложение, цвет, одежда в тематике вселенной, отличительные черты.

## ФОРМАТ ОТВЕТА (строго JSON):
{{
  "name": "Название вселенной (конкретное, яркое)",
  "premise": "Один абзац: суть мира, почему он существует, что в нём происходит. Упомяни ВСЕ интересы ребёнка как части мира.",
  "tone": "стиль мира (научно-приключенческий / сказочный / фэнтези-уютный и т.д.)",
  "subject_zones": {{
    "math": {{
      "zone_name": "Название зоны",
      "description": "Что здесь делают, 1 предложение",
      "lesson_frame": "Чтобы [действие в мире], нужно [тема урока]"
    }},
    "russian": {{
      "zone_name": "Название зоны",
      "description": "Что здесь делают, 1 предложение",
      "lesson_frame": "Чтобы [действие в мире], нужно [тема урока]"
    }},
    "english": {{
      "zone_name": "Название зоны",
      "description": "Что здесь делают, 1 предложение",
      "lesson_frame": "Чтобы [действие в мире], нужно [тема урока]"
    }},
    "world": {{
      "zone_name": "Название зоны",
      "description": "Что здесь делают, 1 предложение",
      "lesson_frame": "Чтобы [действие в мире], нужно [тема урока]"
    }}
  }},
  "year_mission": "Конкретная годовая миссия (построить/открыть/спасти/создать что-то)",
  "progression": "Что происходит каждые 5 уроков (новый модуль/новая земля/новый уровень)",
  "npcs": [
    {{"name": "Имя", "role": "наставник/друг/заказчик", "personality": "2-3 слова", "appearance": "краткое описание внешности"}},
    {{"name": "Имя", "role": "...", "personality": "...", "appearance": "..."}}
  ],
  "character_name": "Имя персонажа-проводника",
  "character_prompt": "Детальное описание внешности персонажа на АНГЛИЙСКОМ для генерации картинки. Формат: A [type] character, [detailed appearance]. Style: cute cartoon, Pixar-like, friendly. Full body, white background."
}}"""

    if model is None:
        # Stub mode
        return _stub_universe(child_name, interests_str)

    try:
        from services.ai_client import is_safety_blocked

        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        if is_safety_blocked(response):
            logger.warning("Universe generation blocked by safety filter for child interests: %s", interests_str)
            return generate_universe(child_name, gender, grade, ["приключения", "природа"])
        result = _extract_json(response.text)
        # Ensure required keys for structured universe
        result.setdefault("name", "Мир Приключений")
        result.setdefault("premise", "")
        result.setdefault("tone", "приключенческий")
        result.setdefault("subject_zones", {})
        result.setdefault("year_mission", "")
        result.setdefault("progression", "")
        result.setdefault("npcs", [])
        result.setdefault("character_prompt", "")
        result.setdefault("character_name", "Проводник")
        # Ensure each subject zone has required fields
        for subj in ("math", "russian", "english", "world"):
            zone = result["subject_zones"].setdefault(subj, {})
            zone.setdefault("zone_name", subj)
            zone.setdefault("description", "")
            zone.setdefault("lesson_frame", "")
        return result
    except Exception as e:
        logger.exception("Universe generation failed, using stub")
        from services.notify import notify_error
        notify_error(f"Universe generation failed: {e}")
        return _stub_universe(child_name, interests_str)


def generate_character_image(character_prompt: str, equipped_items: list[dict] | None = None) -> bytes | None:
    """
    Generate character image using Gemini Flash.
    If equipped_items is provided, adds them to the prompt.
    Returns PNG bytes or None in stub mode.
    """
    from services.ai_client import get_client

    client = get_client("us-central1")
    if client is None:
        logger.info("No GenAI client — skipping character generation (stub mode)")
        return None

    try:
        from google.genai import types

        full_prompt = character_prompt
        if equipped_items:
            items_desc = ", ".join(
                f"{item.get('emoji', '')} {item['title_ru']}" for item in equipped_items
            )
            full_prompt += f" The character is now wearing/holding: {items_desc}."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Generate a child-safe, friendly character illustration: {full_prompt}",
            config=types.GenerateContentConfig(
                response_mime_type="image/png",
            ),
        )
        from services.ai_client import report_usage
        report_usage("gemini-2.5-flash", response, feature="universe")

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    return part.inline_data.data
        return None
    except Exception as e:
        logger.exception("Character image generation failed")
        from services.notify import notify_error
        notify_error(f"Character image generation failed: {e}")
        return None


def generate_shop_items(universe_description: str, character_name: str) -> list[dict]:
    """
    Generate a catalog of ~20 shop items themed to the child's universe.
    Returns list of dicts with: category, title_ru, description_ru, emoji, price_stars.
    """
    from services.ai_client import get_model, is_safety_blocked
    model = get_model("gemini-2.5-flash", feature="universe")

    prompt = f"""Ты — геймдизайнер детской образовательной платформы.

БЕЗОПАСНОСТЬ: весь контент ДОЛЖЕН быть безопасным для детей 6-10 лет. Никакого оружия, насилия, страшных предметов.

Вселенная ребёнка: {universe_description}
Персонаж ребёнка: {character_name}

Придумай каталог из 17 предметов для магазина, где ребёнок может покупать вещи для своего персонажа за звёзды, заработанные на уроках.

Категории:
- outfit (одежда): 5 предметов, цены 5-20
- accessory (аксессуары): 5 предметов, цены 10-25
- pet (питомцы): 4 предмета, цены 20-40
- background (фоны/локации): 3 предмета, цены 15-30

Каждый предмет должен быть тематически связан с вселенной ребёнка.

Формат ответа (строго JSON массив):
[
  {{"category": "outfit", "title_ru": "Плащ звездочёта", "description_ru": "Сияющий плащ с созвездиями", "emoji": "🧥", "price_stars": 15}},
  ...
]"""

    if model is None:
        # Stub items
        return _stub_shop_items()

    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        items = _extract_json(response.text)
        if isinstance(items, dict):
            items = items.get("items", [])
        # Validate each item
        valid_categories = {"outfit", "accessory", "pet", "background"}
        validated = []
        for item in items:
            if isinstance(item, dict) and item.get("category") in valid_categories:
                validated.append({
                    "category": item["category"],
                    "title_ru": item.get("title_ru", "Предмет"),
                    "description_ru": item.get("description_ru", ""),
                    "emoji": item.get("emoji", "🎁"),
                    "price_stars": max(5, min(50, int(item.get("price_stars", 10)))),
                })
        return validated if validated else _stub_shop_items()
    except Exception as e:
        logger.exception("Shop items generation failed, using stubs")
        from services.notify import notify_error
        notify_error(f"Shop items generation failed: {e}")
        return _stub_shop_items()


def _stub_shop_items() -> list[dict]:
    return [
        {"category": "outfit", "title_ru": "Футболка героя", "description_ru": "Яркая футболка с эмблемой", "emoji": "👕", "price_stars": 5},
        {"category": "outfit", "title_ru": "Плащ искателя", "description_ru": "Развевающийся плащ для приключений", "emoji": "🧥", "price_stars": 10},
        {"category": "outfit", "title_ru": "Волшебная мантия", "description_ru": "Мантия с магическими узорами", "emoji": "🥋", "price_stars": 15},
        {"category": "outfit", "title_ru": "Золотые доспехи", "description_ru": "Сверкающие доспехи знаний", "emoji": "🛡️", "price_stars": 20},
        {"category": "outfit", "title_ru": "Корона мудреца", "description_ru": "Корона для самых умных", "emoji": "👑", "price_stars": 20},
        {"category": "accessory", "title_ru": "Волшебная палочка", "description_ru": "Палочка для решения задач", "emoji": "🪄", "price_stars": 10},
        {"category": "accessory", "title_ru": "Щит знаний", "description_ru": "Защищает от ошибок", "emoji": "🛡️", "price_stars": 15},
        {"category": "accessory", "title_ru": "Меч света", "description_ru": "Разрубает сложные задачи", "emoji": "🗡️", "price_stars": 15},
        {"category": "accessory", "title_ru": "Книга заклинаний", "description_ru": "Хранит все формулы", "emoji": "📖", "price_stars": 20},
        {"category": "accessory", "title_ru": "Очки мудрости", "description_ru": "Видят скрытые подсказки", "emoji": "🤓", "price_stars": 25},
        {"category": "pet", "title_ru": "Котёнок-искатель", "description_ru": "Пушистый помощник", "emoji": "🐱", "price_stars": 20},
        {"category": "pet", "title_ru": "Дракончик", "description_ru": "Маленький огнедышащий друг", "emoji": "🐉", "price_stars": 30},
        {"category": "pet", "title_ru": "Совёнок", "description_ru": "Мудрый ночной помощник", "emoji": "🦉", "price_stars": 25},
        {"category": "pet", "title_ru": "Единорог", "description_ru": "Волшебный скакун", "emoji": "🦄", "price_stars": 40},
        {"category": "background", "title_ru": "Волшебный лес", "description_ru": "Зелёный лес с светлячками", "emoji": "🌲", "price_stars": 15},
        {"category": "background", "title_ru": "Космическая станция", "description_ru": "Учимся среди звёзд", "emoji": "🚀", "price_stars": 20},
        {"category": "background", "title_ru": "Подводный замок", "description_ru": "Учёба на дне океана", "emoji": "🏰", "price_stars": 30},
    ]
