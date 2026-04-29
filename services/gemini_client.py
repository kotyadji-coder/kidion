import json
import os
import re

import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel, HarmBlockThreshold, HarmCategory, SafetySetting

from services.prompts import (
    GENERATE_IMAGE_PROMPT_FALLBACK_PROMPT,
    GENERATE_IMAGE_PROMPT_PROMPT,
    METHODOLOGIST_PROMPT,
    TUTOR_GAMER_JSON_PROMPT,
)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
REGION = "global"
MODEL_NAME = "gemini-3.1-pro-preview"

CHILD_SAFETY_SETTINGS = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
]


def _get_model() -> GenerativeModel:
    # Stub mode if GOOGLE_CLOUD_PROJECT is not set
    if not PROJECT_ID:
        return None

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        vertexai.init(project=PROJECT_ID, location=REGION, credentials=credentials)
    else:
        vertexai.init(project=PROJECT_ID, location=REGION)
    return GenerativeModel(MODEL_NAME)


def _is_blocked_by_safety(response) -> bool:
    """Check if Gemini response was blocked by safety filters."""
    if not response.candidates:
        return True
    candidate = response.candidates[0]
    if hasattr(candidate, "finish_reason") and candidate.finish_reason:
        return candidate.finish_reason.name == "SAFETY"
    return False


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the JSON object from the model response."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def generate_explanation(question: str) -> tuple[str, dict]:
    """
    Two-step chain:
      Step 1 — Methodologist: structured rule + mnemonic.
      Step 2 — Tutor-Gamer: returns strict JSON lesson with story_blocks + 5 tasks.

    Returns (methodologist_output, lesson_dict).

    Stub mode: if GOOGLE_CLOUD_PROJECT is not set, returns stub data.
    """
    model = _get_model()

    # Stub mode
    if model is None:
        return ("stub", _stub_lesson(question))

    # Step 1: methodologist (plain text)
    step1_prompt = METHODOLOGIST_PROMPT.format(question=question)
    step1_response = model.generate_content(step1_prompt, safety_settings=CHILD_SAFETY_SETTINGS)

    # Check safety rating
    if _is_blocked_by_safety(step1_response):
        raise ValueError("Lesson content blocked by safety filter at step 1")

    methodologist_output = step1_response.text.strip()

    # Step 2: tutor-gamer → strict JSON
    step2_prompt = TUTOR_GAMER_JSON_PROMPT.format(
        question=question,
        methodologist_output=methodologist_output,
    )
    step2_response = model.generate_content(
        step2_prompt,
        generation_config=GenerationConfig(response_mime_type="application/json"),
        safety_settings=CHILD_SAFETY_SETTINGS,
    )

    # Check safety rating
    if _is_blocked_by_safety(step2_response):
        raise ValueError("Lesson content blocked by safety filter at step 2")

    lesson_dict = _extract_json(step2_response.text)

    return methodologist_output, lesson_dict


def generate_image_prompt(explanation: str) -> str:
    """Генерирует промт для иллюстрации на основе финального текста урока."""
    model = _get_model()

    # Stub mode
    if model is None:
        return "a colorful educational illustration"

    prompt = GENERATE_IMAGE_PROMPT_PROMPT.format(story=explanation)
    response = model.generate_content(prompt, safety_settings=CHILD_SAFETY_SETTINGS)
    return response.text.strip()


def generate_image_prompt_fallback(explanation: str) -> str:
    """Запасной промт (kids cosplay стратегия) — используется при IMAGE_PROHIBITED_CONTENT."""
    model = _get_model()

    # Stub mode
    if model is None:
        return "a colorful educational illustration fallback"

    prompt = GENERATE_IMAGE_PROMPT_FALLBACK_PROMPT.format(story=explanation)
    response = model.generate_content(prompt, safety_settings=CHILD_SAFETY_SETTINGS)
    return response.text.strip()


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
