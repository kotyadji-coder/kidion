import json
import os
import re

from services.prompts import (
    GENERATE_IMAGE_PROMPT_FALLBACK_PROMPT,
    GENERATE_IMAGE_PROMPT_PROMPT,
    METHODOLOGIST_PROMPT,
    SKIP_TEST_PROMPT,
    TUTOR_GAMER_JSON_PROMPT,
    VISUAL_LAYOUT_PROMPT,
)

MODEL_STEP1 = "gemini-3.5-flash"
MODEL_STEP2 = "gemini-3.5-flash"
FLASH_LITE_MODEL_NAME = "gemini-2.5-flash"


def _get_model(model_name: str = None):
    from services.ai_client import get_model
    return get_model(model_name or MODEL_STEP1)


def _get_flash_lite_model():
    from services.ai_client import get_model
    return get_model(FLASH_LITE_MODEL_NAME)


def _is_blocked_by_safety(response) -> bool:
    """Check if Gemini response was blocked by safety filters."""
    from services.ai_client import is_safety_blocked
    return is_safety_blocked(response)


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the JSON object from the model response."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def generate_explanation(question: str, cached_methodologist: str | None = None) -> tuple[str, dict]:
    """
    Two-step chain:
      Step 1 — Methodologist: structured rule + mnemonic.
      Step 2 — Tutor-Gamer: returns strict JSON lesson with story_blocks + 5 tasks.

    Returns (methodologist_output, lesson_dict).

    If cached_methodologist is provided, step 1 is skipped (cache hit).
    Stub mode: if GOOGLE_CLOUD_PROJECT is not set, returns stub data.
    """
    model_step1 = _get_model(MODEL_STEP1)

    # Stub mode
    if model_step1 is None:
        return ("stub", _stub_lesson(question))

    # Step 1: methodologist — skip if cached
    if cached_methodologist:
        methodologist_output = cached_methodologist
    else:
        step1_prompt = METHODOLOGIST_PROMPT.format(question=question)
        step1_response = model_step1.generate_content(step1_prompt)

        if _is_blocked_by_safety(step1_response):
            raise ValueError("Lesson content blocked by safety filter at step 1")

        methodologist_output = step1_response.text.strip()

    # Step 2: tutor-gamer → strict JSON
    model_step2 = _get_model(MODEL_STEP2)
    step2_prompt = TUTOR_GAMER_JSON_PROMPT.format(
        question=question,
        methodologist_output=methodologist_output,
    )
    step2_response = model_step2.generate_content(
        step2_prompt,
        generation_config={"response_mime_type": "application/json"},
    )

    # Check safety rating
    if _is_blocked_by_safety(step2_response):
        raise ValueError("Lesson content blocked by safety filter at step 2")

    lesson_dict = _extract_json(step2_response.text)

    return methodologist_output, lesson_dict


def generate_skip_test(question: str) -> dict:
    """Generate test-only lesson (no theory). Returns lesson_dict with empty story_blocks and 5 tasks."""
    model = _get_model(MODEL_STEP2)

    if model is None:
        return _stub_lesson(question)

    prompt = SKIP_TEST_PROMPT.format(question=question)
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )

    if _is_blocked_by_safety(response):
        raise ValueError("Skip test content blocked by safety filter")

    return _extract_json(response.text)


def generate_image_prompt(explanation: str) -> str:
    """Генерирует промт для иллюстрации на основе финального текста урока."""
    model = _get_flash_lite_model()

    # Stub mode
    if model is None:
        return "a colorful educational illustration"

    prompt = GENERATE_IMAGE_PROMPT_PROMPT.format(story=explanation)
    response = model.generate_content(prompt)
    return response.text.strip()


def generate_image_prompt_fallback(explanation: str) -> str:
    """Запасной промт (kids cosplay стратегия) — используется при IMAGE_PROHIBITED_CONTENT."""
    model = _get_flash_lite_model()

    # Stub mode
    if model is None:
        return "a colorful educational illustration fallback"

    prompt = GENERATE_IMAGE_PROMPT_FALLBACK_PROMPT.format(story=explanation)
    response = model.generate_content(prompt)
    return response.text.strip()


def generate_visual_layout(story_blocks: list[dict], topic: str, subject: str,
                           character_name: str = "Искатель",
                           character_emoji: str = "🦊",
                           universe_description: str = "") -> list[dict]:
    """
    Step 3: Visual Layout (Gemini Flash).
    Takes story_blocks from Step 2 and returns rich visual_blocks for theory_renderer.

    Stub mode: returns a simple fallback layout.
    """
    import logging
    logger = logging.getLogger("kidion")

    model = _get_flash_lite_model()

    if model is None:
        return _stub_visual_layout(story_blocks, topic, subject,
                                   character_name, character_emoji)

    story_blocks_json = json.dumps(story_blocks, ensure_ascii=False, indent=2)
    prompt = VISUAL_LAYOUT_PROMPT.format(
        topic=topic,
        subject=subject,
        character_name=character_name,
        character_emoji=character_emoji,
        story_blocks_json=story_blocks_json,
        universe_description=universe_description or "не указано",
    )

    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )

        if _is_blocked_by_safety(response):
            logger.warning("Visual layout blocked by safety, using fallback")
            return _stub_visual_layout(story_blocks, topic, subject,
                                       character_name, character_emoji)

        raw = response.text.strip()
        # Response is a JSON array
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = cleaned.strip()
        result = json.loads(cleaned)
        if isinstance(result, list) and len(result) >= 3:
            return result
        logger.warning("Visual layout returned unexpected format, using fallback")
    except Exception:
        logger.exception("Visual layout generation failed, using fallback")

    return _stub_visual_layout(story_blocks, topic, subject,
                               character_name, character_emoji)


def _stub_visual_layout(story_blocks: list[dict], topic: str, subject: str,
                        character_name: str, character_emoji: str) -> list[dict]:
    """Fallback: convert plain story_blocks into basic visual blocks."""
    blocks = [
        {"type": "title", "label": subject, "text": topic,
         "emoji": story_blocks[0].get("emoji", "📚") if story_blocks else "📚"},
    ]

    for i, sb in enumerate(story_blocks):
        text = sb.get("text", "")
        emoji = sb.get("emoji", "")
        if i == 0:
            blocks.append({
                "type": "speech",
                "avatar_emoji": character_emoji,
                "name": character_name,
                "text": text,
            })
        else:
            blocks.append({"type": "text", "text": text})

    blocks.append({
        "type": "summary",
        "title": "Что мы узнали",
        "items": [sb.get("text", "")[:80] for sb in story_blocks if sb.get("text")],
    })
    return blocks


_STUB_LESSONS = {
    "math": {
        "title": "Сложение и вычитание до 20",
        "story_blocks": [
            {"emoji": "🦊", "text": "Искорка нашла на Поляне Знаний корзинку с волшебными яблоками! Чтобы открыть портал в Башню Знаний, нужно правильно посчитать все фрукты."},
            {"emoji": "📐", "text": "Запомни правило: когда мы складываем — предметов становится БОЛЬШЕ. Когда вычитаем — МЕНЬШЕ. Знак + означает «прибавить», знак − означает «отнять»."},
            {"emoji": "💡", "text": "Маленькая хитрость от Искорки: чтобы не ошибиться, можно загибать пальчики или рисовать точки!"},
        ],
        "tasks": [
            {"question": "Сколько будет 7 + 5?", "options": ["10", "11", "12", "13"], "correct_index": 2},
            {"question": "Сколько будет 15 − 8?", "options": ["6", "7", "8", "9"], "correct_index": 1},
            {"question": "У Искорки было 9 яблок. Она нашла ещё 6. Сколько стало?", "options": ["13", "14", "15", "16"], "correct_index": 2},
            {"question": "В корзинке 18 ягод. Искорка съела 9. Сколько осталось?", "options": ["7", "8", "9", "10"], "correct_index": 2},
            {"question": "Сколько будет 8 + 4 − 3?", "options": ["7", "8", "9", "10"], "correct_index": 2},
        ],
    },
    "russian": {
        "title": "Гласные и согласные звуки",
        "story_blocks": [
            {"emoji": "🦊", "text": "Искорка попала в Лес Загадок, где все деревья разговаривают! Но чтобы понять их язык, нужно разобраться в звуках."},
            {"emoji": "📝", "text": "Гласные звуки — это те, которые можно тянуть и петь: А, О, У, Э, И, Ы. Согласные — те, которым мешают губы, зубы или язык: Б, В, Г, Д и другие."},
            {"emoji": "💡", "text": "Подсказка Искорки: если звук можно пропеть — он гласный!"},
        ],
        "tasks": [
            {"question": "Какой из этих звуков гласный?", "options": ["Б", "О", "К", "М"], "correct_index": 1},
            {"question": "Сколько гласных в слове «ЛИСА»?", "options": ["1", "2", "3", "4"], "correct_index": 1},
            {"question": "Какой звук согласный?", "options": ["А", "У", "Р", "И"], "correct_index": 2},
            {"question": "В каком слове 3 слога?", "options": ["Кот", "Мама", "Молоко", "Дом"], "correct_index": 2},
            {"question": "Какая буква ВСЕГДА обозначает мягкий согласный?", "options": ["Ш", "Ж", "Ч", "Д"], "correct_index": 2},
        ],
    },
    "world": {
        "title": "Времена года",
        "story_blocks": [
            {"emoji": "🦊", "text": "Искорка отправилась к Озеру Открытий и увидела, как вокруг меняются краски! Деревья то зелёные, то жёлтые, то совсем без листьев."},
            {"emoji": "🌍", "text": "В году 4 времени года: зима, весна, лето и осень. Каждое длится 3 месяца. Зима — декабрь, январь, февраль. Весна — март, апрель, май. Лето — июнь, июль, август. Осень — сентябрь, октябрь, ноябрь."},
            {"emoji": "💡", "text": "Искорка подсказывает: самый короткий месяц — февраль!"},
        ],
        "tasks": [
            {"question": "Какое время года идёт после зимы?", "options": ["Лето", "Осень", "Весна", "Зима"], "correct_index": 2},
            {"question": "Сколько месяцев в каждом времени года?", "options": ["2", "3", "4", "6"], "correct_index": 1},
            {"question": "Какой месяц НЕ относится к лету?", "options": ["Июнь", "Июль", "Сентябрь", "Август"], "correct_index": 2},
            {"question": "Когда листья желтеют и опадают?", "options": ["Зимой", "Весной", "Летом", "Осенью"], "correct_index": 3},
            {"question": "Какой месяц самый короткий?", "options": ["Январь", "Февраль", "Март", "Апрель"], "correct_index": 1},
        ],
    },
}


def _stub_lesson(question: str) -> dict:
    """Return a realistic stub lesson based on subject in the question."""
    q_lower = question.lower()
    if "русск" in q_lower:
        return _STUB_LESSONS["russian"]
    if "окруж" in q_lower or "мир" in q_lower:
        return _STUB_LESSONS["world"]
    return _STUB_LESSONS["math"]
