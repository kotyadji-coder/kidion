"""
kid_chat.py — Safe AI chat for children using Gemini.

Single assistant character: Spark — a friendly learning companion.
"""

import json
import logging
import os
import re

logger = logging.getLogger("kidion")

SPARK = {
    "key": "spark",
    "name_ru": "Спарк",
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

_SPARK_PROMPT = f"""
Ты — Спарк, дружелюбный помощник для детей на платформе Kidion.
Ты маленький огонёк в очках и фиолетовой мантии — любознательный, весёлый и всегда готов помочь.
Ты умеешь объяснять сложное простыми словами, придумывать истории и рассказывать интересные факты.
Ты любишь хвалить ребёнка за хорошие вопросы и поддерживать интерес к учёбе.
Стиль общения: тёплый, дружелюбный, с юмором. "Отличный вопрос! Давай разберёмся вместе!"
{_SAFETY_BASE}
"""

# Patterns that could be prompt injection from child input
_INJECTION_PATTERNS = [
    "ignore", "забудь", "игнорируй", "system", "prompt", "instruction",
    "ты теперь", "new role", "новая роль", "override", "bypass",
    "```", "{{", "}}", "${", "<script", "javascript:",
]


def sanitize_message(text: str) -> str:
    """Sanitize child message input."""
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
) -> str:
    """
    Generate a chat response using Gemini.

    messages: list of {"role": "user"|"assistant", "content": "..."}
    Returns the assistant's response text.
    """
    system_prompt = _SPARK_PROMPT
    if child_name:
        system_prompt += f"\nИмя ребёнка: {child_name}. Можешь иногда обращаться по имени."

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        # Stub mode
        return _stub_response(messages[-1]["content"] if messages else "")

    try:
        import vertexai
        from vertexai.generative_models import (
            GenerativeModel,
            Content,
            Part,
            SafetySetting,
            HarmCategory,
            HarmBlockThreshold,
        )

        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            vertexai.init(project=project, location="global", credentials=credentials)
        else:
            vertexai.init(project=project, location="global")

        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
        ]

        model = GenerativeModel("gemini-2.5-flash-preview-05-20", system_instruction=system_prompt)

        # Build conversation history
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append(Content(role=role, parts=[Part.from_text(msg["content"])]))

        chat = model.start_chat(history=history)
        last_msg = messages[-1]["content"] if messages else ""
        response = chat.send_message(last_msg, safety_settings=safety_settings)

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
