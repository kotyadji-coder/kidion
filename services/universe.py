"""
universe.py — Generate personalized universes, characters, and shop items for children.

Uses Gemini for text generation and Gemini Flash for image generation.
In stub mode (no GOOGLE_CLOUD_PROJECT), returns predefined defaults.
"""

import json
import logging
import os
import re

logger = logging.getLogger("kidion")


def _get_text_model():
    """Get Gemini model for text generation. Returns None in stub mode."""
    from services.ai_client import get_studio_model
    studio = get_studio_model("gemini-2.5-flash")
    if studio is not None:
        return studio
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return None
    import vertexai
    from vertexai.generative_models import GenerativeModel
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        vertexai.init(project=project, location="global", credentials=credentials)
    else:
        vertexai.init(project=project, location="global")
    return GenerativeModel("gemini-3.1-pro-preview")


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract JSON."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    match = re.search(r"[\[{].*[\]}]", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


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

    prompt = f"""Ты — сценарист детских образовательных вселенных.

БЕЗОПАСНОСТЬ КОНТЕНТА (ОБЯЗАТЕЛЬНО):
- ЗАПРЕЩЕНО генерировать контент с насилием, жестокостью, оружием, кровью.
- ЗАПРЕЩЕНО генерировать контент с сексуальным подтекстом или взрослыми темами.
- ЗАПРЕЩЕНО генерировать контент с дискриминацией, буллингом, оскорблениями.
- Весь контент ДОЛЖЕН быть безопасным и позитивным для детей 6-10 лет.

Ребёнок: {gender_ru}, {grade} класс.
Интересы: {interests_str}

## Задача 1: Описание вселенной
Придумай уникальную учебную вселенную для этого ребёнка, где переплетаются все его интересы.
Вселенная должна быть яркой, дружелюбной и подходить для образовательных уроков по математике, русскому языку, английскому языку, окружающему миру.
Опиши 2-3 абзаца: как устроен этот мир, какие там есть локации, ключевые персонажи-помощники.

## Задача 2: Персонаж-проводник
Придумай персонажа-проводника для ребёнка в этой вселенной. Опиши его внешность максимально подробно:
- Тип существа (человек, зверь, фантастическое существо)
- Рост, телосложение
- Цвет волос/шерсти, глаз
- Стиль одежды (в тематике вселенной)
- Отличительные черты (шрам, очки, крылья и т.д.)
- Характер (2-3 слова)

## Формат ответа (строго JSON):
{{
  "universe_description": "Описание вселенной, 2-3 абзаца",
  "character_name": "Имя персонажа",
  "character_prompt": "Детальное описание внешности персонажа на АНГЛИЙСКОМ языке для генерации картинки. Формат: A [type] character named [name], [detailed appearance]. Style: cute cartoon, Pixar-like, friendly, educational theme. Full body, white background.",
  "locations": ["Локация 1", "Локация 2", "Локация 3"],
  "helpers": ["Помощник 1", "Помощник 2"]
}}"""

    if model is None:
        # Stub mode
        return {
            "universe_description": (
                f"Добро пожаловать в Мир Знаний — волшебную вселенную, созданную специально для {child_name}! "
                f"Здесь живут удивительные существа, которые обожают {interests_str}. "
                "В этом мире каждый урок — это новое приключение, а каждая задача — загадка, "
                "которую нужно разгадать, чтобы открыть новые территории."
            ),
            "character_name": "Искорка",
            "character_prompt": (
                f"A cute friendly fox character named Iskorka, wearing a wizard hat and a backpack with books. "
                f"The fox has bright orange fur, big green eyes, and a fluffy tail with a star-shaped tip. "
                f"Style: cute cartoon, Pixar-like, friendly, educational theme. Full body, white background."
            ),
            "locations": ["Башня Знаний", "Лес Загадок", "Озеро Открытий"],
            "helpers": ["Мудрая Сова", "Весёлый Робот"],
        }

    try:
        from vertexai.generative_models import GenerationConfig, HarmBlockThreshold, HarmCategory, SafetySetting
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
        ]
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json"),
            safety_settings=safety_settings,
        )
        # Check safety ratings
        if response.candidates and response.candidates[0].finish_reason and response.candidates[0].finish_reason.name == "SAFETY":
            logger.warning("Universe generation blocked by safety filter for child interests: %s", interests_str)
            return generate_universe(child_name, gender, grade, ["приключения", "природа"])
        result = _extract_json(response.text)
        # Ensure required keys
        result.setdefault("universe_description", "")
        result.setdefault("character_prompt", "")
        result.setdefault("character_name", "Проводник")
        return result
    except Exception:
        logger.exception("Universe generation failed, using stub")
        return generate_universe.__wrapped__(child_name, gender, grade, interests) if hasattr(generate_universe, '__wrapped__') else {
            "universe_description": f"Волшебный мир для {child_name}",
            "character_name": "Искорка",
            "character_prompt": "A cute friendly fox character, cartoon style, white background",
            "locations": [],
            "helpers": [],
        }


def generate_character_image(character_prompt: str, equipped_items: list[dict] | None = None) -> bytes | None:
    """
    Generate character image using Gemini Flash.
    If equipped_items is provided, adds them to the prompt.
    Returns PNG bytes or None in stub mode.
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        logger.info("GOOGLE_CLOUD_PROJECT not set - skipping character generation (stub mode)")
        return None

    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project, location="us-central1")
        model = GenerativeModel("gemini-2.5-flash")

        full_prompt = character_prompt
        if equipped_items:
            items_desc = ", ".join(
                f"{item.get('emoji', '')} {item['title_ru']}" for item in equipped_items
            )
            full_prompt += f" The character is now wearing/holding: {items_desc}."

        from vertexai.generative_models import HarmBlockThreshold, HarmCategory, SafetySetting
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
        ]
        response = model.generate_content(
            f"Generate a child-safe, friendly character illustration: {full_prompt}",
            generation_config={"response_mime_type": "image/png"},
            safety_settings=safety_settings,
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    return part.inline_data.data
        return None
    except Exception:
        logger.exception("Character image generation failed")
        return None


def generate_shop_items(universe_description: str, character_name: str) -> list[dict]:
    """
    Generate a catalog of ~20 shop items themed to the child's universe.
    Returns list of dicts with: category, title_ru, description_ru, emoji, price_stars.
    """
    from services.ai_client import get_studio_model
    model = get_studio_model("gemini-2.5-flash")
    if model is None:
        # Try Vertex AI
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if project:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                vertexai.init(project=project, location="global", credentials=credentials)
            else:
                vertexai.init(project=project, location="global")
            model = GenerativeModel("gemini-2.5-flash")

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

    try:
        from vertexai.generative_models import GenerationConfig, HarmBlockThreshold, HarmCategory, SafetySetting
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
        ]
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(response_mime_type="application/json"),
            safety_settings=safety_settings,
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
        return validated if validated else generate_shop_items("", "")  # fallback to stubs
    except Exception:
        logger.exception("Shop items generation failed, using stubs")
        return generate_shop_items.__wrapped__("", "") if hasattr(generate_shop_items, '__wrapped__') else [
            {"category": "outfit", "title_ru": "Футболка героя", "description_ru": "Яркая футболка", "emoji": "👕", "price_stars": 5},
        ]
