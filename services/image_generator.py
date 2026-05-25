"""
image_generator.py - Generate illustrations using Gemini 2.5 Flash.
Used for lesson images and chat image generation.
"""

import os
import logging
import re

logger = logging.getLogger("kidion")

# Patterns indicating the child wants an image drawn
_DRAW_PATTERNS = [
    r"\bнарисуй\b", r"\bпокажи\b", r"\bнарисуй мне\b", r"\bпокажи мне\b",
    r"\bнарисуй картинк", r"\bсделай рисунок", r"\bсделай картинк",
    r"\bможешь нарисовать", r"\bнарисуешь\b", r"\bпокажешь\b",
]


def is_draw_request(text: str) -> bool:
    """Check if message is asking to draw/show an image."""
    lower = text.lower()
    return any(re.search(p, lower) for p in _DRAW_PATTERNS)


def generate_chat_image(description: str) -> bytes | None:
    """Generate a child-safe image from a text description. Returns PNG bytes or None."""
    safe_prompt = (
        f"Generate a cute, colorful, child-friendly illustration. "
        f"Style and subject: {description}. "
        f"The image must be safe for children — no violence, no scary content, no text."
    )
    return generate_image(safe_prompt)


def describe_photo_for_styling(image_bytes: bytes) -> str | None:
    """Use Gemini to describe a photo in detail for re-generation in a different style.
    Tries AI Studio first (API key), then Vertex AI."""
    prompt_text = (
        "Describe this photo in detail for an AI image generator. "
        "Focus on: the person's appearance (hair color, length, style, eye color, "
        "skin tone, facial features, expression), clothing, pose, and background. "
        "Be very specific and detailed. Output ONLY the description, no commentary. "
        "Keep it child-safe. Write in English. Max 150 words."
    )

    api_key = os.environ.get("GEMINI_API_KEY")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if not api_key and not project:
        logger.info("No GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT — stub mode, no photo describe")
        return None

    # Try AI Studio first
    if api_key:
        try:
            import base64
            from google import genai

            client = genai.Client(api_key=api_key)
            b64 = base64.b64encode(image_bytes).decode()

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[{"parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                ]}],
            )

            if response.text:
                logger.info("Photo described via AI Studio: %s", response.text[:100])
                return response.text.strip()
        except Exception:
            logger.exception("AI Studio photo description failed, trying Vertex")

    # Fallback to Vertex AI
    if project:
        try:
            import base64
            import vertexai
            from vertexai.generative_models import GenerativeModel, Part, Image

            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                vertexai.init(project=project, location="us-central1", credentials=credentials)
            else:
                vertexai.init(project=project, location="us-central1")

            model = GenerativeModel("gemini-2.5-flash")
            image_part = Part.from_data(image_bytes, mime_type="image/jpeg")
            response = model.generate_content([prompt_text, image_part])

            if response.text:
                logger.info("Photo described via Vertex AI: %s", response.text[:100])
                return response.text.strip()
        except Exception:
            logger.exception("Vertex AI photo description failed")

    return None


def generate_image(prompt: str) -> bytes | None:
    """Generate image. Tries AI Studio first (API key), then Vertex AI, then returns None."""
    api_key = os.environ.get("GEMINI_API_KEY")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if not api_key and not project:
        logger.info("No GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT — stub mode, no image")
        return None

    try:
        # Try AI Studio first (supports image generation with newer SDK)
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="image/png",
                    ),
                )
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            logger.info("Image generated via AI Studio")
                            return part.inline_data.data
            except Exception as e:
                logger.warning("AI Studio image generation failed, trying Vertex: %s", e)

        # Fallback to Vertex AI
        if project:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if credentials_path:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(credentials_path)
                vertexai.init(project=project, location="us-central1", credentials=credentials)
            else:
                vertexai.init(project=project, location="us-central1")

            model = GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "image/png"},
            )

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        logger.info("Image generated via Vertex AI")
                        return part.inline_data.data

        return None
    except Exception:
        logger.exception("Image generation failed")
        return None
