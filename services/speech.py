"""Speech-to-text helper for kid chat voice fallback."""

import logging

from services.ai_client import get_client, report_usage

logger = logging.getLogger("kidion")

SPEECH_MODEL = "gemini-2.5-flash"


def _extract_text(response) -> str:
    text = getattr(response, "text", "") or ""
    if text.strip():
        return text.strip()

    try:
        parts = response.candidates[0].content.parts
    except (AttributeError, IndexError):
        return ""

    chunks = []
    for part in parts:
        part_text = getattr(part, "text", "") or ""
        if part_text:
            chunks.append(part_text)
    return " ".join(chunks).strip()


def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Transcribe a short child voice message. Returns plain text or empty string."""
    client = get_client("global")
    if not client:
        logger.info("No GenAI client - speech transcription unavailable")
        return ""

    try:
        from google.genai import types

        audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        prompt = (
            "Распознай русскую детскую речь из аудио. "
            "Верни только текст без кавычек, комментариев и Markdown. "
            "Если речь неразборчива, верни пустую строку."
        )
        response = client.models.generate_content(
            model=SPEECH_MODEL,
            contents=[prompt, audio_part],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )
        report_usage(SPEECH_MODEL, response, feature="chat-voice")
        return _extract_text(response)
    except Exception as exc:
        logger.exception("Speech transcription failed")
        from services.notify import notify_error
        notify_error(f"Speech transcription failed: {exc}")
        return ""
