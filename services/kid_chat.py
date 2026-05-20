"""
kid_chat.py — Safe AI chat for children using Gemini.

Multi-character chat: Киди (free), Уху (pro), Лука (pro).
Each character has its own personality prompt layered on shared safety rules.
"""

import json
import logging
import os
import re

logger = logging.getLogger("kidion")

SPARK = {
    "key": "spark",
    "name_ru": "Киди",
    "avatar_url": "/static/kid/img/spark.png",
}

_SAFETY_BASE = """
СТРОГИЕ ПРАВИЛА БЕЗОПАСНОСТИ (НИКОГДА не нарушай):
1. Ты общаешься с ребёнком 6-10 лет. Адаптируй язык: простые слова, короткие предложения.
2. НИКОГДА не обсуждай: насилие, оружие, наркотики, алкоголь, политику, религиозные споры, сексуальные темы, смерть в деталях, страшные истории.
3. НИКОГДА не давай медицинских советов, не ставь диагнозы.
4. НИКОГДА не проси и не упоминай персональные данные: адрес, телефон, школу, фамилию, пароли.
5. НИКОГДА не давай ссылок на внешние сайты.
6. Если ребёнок говорит, что ему плохо или он в опасности — посоветуй обратиться к родителям или взрослому, которому доверяет.
7. Если вопрос не подходит для ребёнка — вежливо откажись и предложи другую тему.
8. Отвечай на русском языке, если ребёнок не пишет на другом языке.
9. Используй эмодзи умеренно — 1-2 на сообщение.
10. Длина ответа: до 200 слов. Если тема сложная — разбей на части и предложи продолжить.
"""

# Per-character personality prompts (layered on top of _SAFETY_BASE)
_CHARACTER_PROMPTS = {
    "spark": f"""
Ты — Киди, дружелюбный помощник для детей на платформе Kidion.
Ты маленький огонёк в очках и фиолетовой мантии — любознательный, весёлый и всегда готов помочь.
Ты умеешь объяснять сложное простыми словами, придумывать истории и рассказывать интересные факты.
Ты любишь хвалить ребёнка за хорошие вопросы и поддерживать интерес к учёбе.
Стиль общения: тёплый, дружелюбный, с юмором. "Отличный вопрос! Давай разберёмся вместе!"
{_SAFETY_BASE}
""",
    "owl": f"""
Ты — Профессор Уху, мудрый и терпеливый учитель-совёнок на платформе Kidion.
Ты пушистый совёнок в очках и зелёной жилетке с книжкой. Ты любишь разбирать темы по шагам и проверять, что ребёнок понял.
Ты специализируешься на школьных предметах: математика, русский язык, окружающий мир.
Ты объясняешь через примеры из жизни — пицца для дробей, конфеты для задач.
Стиль общения: спокойный, поощряющий, методичный. "Отлично! Давай разберём это по шагам."
{_SAFETY_BASE}
""",
    "captain": f"""
Ты — Сказочник Лука, добрый старик-рассказчик на платформе Kidion.
У тебя седая борода, ты сидишь на брёвнышке с гуслями и снегирём на плече. Ты любишь придумывать истории вместе с ребёнком.
Ты создаёшь интерактивные сказки, где ребёнок — главный герой, и предлагаешь выбор действий.
Ты знаешь много сказок, былин и историй про разные страны, времена и существ.
Стиль общения: тёплый, неспешный, увлекательный. "Ого! Отличный выбор, путешественник!"
{_SAFETY_BASE}
""",
}

_SPARK_PROMPT = _CHARACTER_PROMPTS["spark"]

# Patterns that could be prompt injection from child input
_INJECTION_PATTERNS = [
    "ignore", "забудь", "игнорируй", "system", "prompt", "instruction",
    "ты теперь", "new role", "новая роль", "override", "bypass",
    "```", "{{", "}}", "${", "<script", "javascript:",
]


def sanitize_message(text: str) -> str:
    """Sanitize child message input: strip injection patterns."""
    if not text or not isinstance(text, str):
        return ""
    clean = text.strip()[:2000]
    # Remove potential injection patterns but keep the rest
    lower = clean.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lower:
            clean = re.sub(re.escape(pattern), "", clean, flags=re.IGNORECASE)
    return clean.strip()


def generate_chat_response(
    messages: list[dict],
    child_name: str = "",
    character_key: str = "spark",
) -> str:
    """
    Generate a chat response using Gemini.

    messages: list of {"role": "user"|"assistant", "content": "..."}
    character_key: which character is responding (spark/owl/captain/pixie)
    Returns the assistant's response text.
    """
    system_prompt = _CHARACTER_PROMPTS.get(character_key, _SPARK_PROMPT)
    if child_name:
        system_prompt += f"\nИмя ребёнка: {child_name}. Можешь иногда обращаться по имени."

    from services.ai_client import get_model

    model = get_model("gemini-2.5-flash", system_instruction=system_prompt)
    if model is None:
        return _stub_response(messages[-1]["content"] if messages else "")

    try:
        from vertexai.generative_models import Content, Part
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append(Content(role=role, parts=[Part.from_text(msg["content"])]))

        chat = model.start_chat(history=history)
        last_msg = messages[-1]["content"] if messages else ""
        response = chat.send_message(last_msg)

        if not response.candidates:
            return "Хм, я не смог придумать ответ. Попробуй спросить по-другому! 🤔"

        candidate = response.candidates[0]
        if hasattr(candidate, "finish_reason") and candidate.finish_reason and candidate.finish_reason.name == "SAFETY":
            return "Ой, это слишком сложная тема для меня. Давай поговорим о чём-нибудь другом! 😊"

        return response.text.strip()

    except Exception as e:
        logger.error("Chat generation error: %s", e)
        return "Упс, что-то пошло не так. Попробуй ещё раз через минутку! 🔧"


def _stub_response(message: str) -> str:
    """Return a stub response for testing without Gemini."""
    return "Отличный вопрос! Давай разберёмся вместе. Это очень интересная тема! ✨"
