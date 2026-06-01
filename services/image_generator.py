"""
image_generator.py - Generate illustrations using Gemini Flash Image.
Used for lesson images and chat image generation.

Image models use google-genai SDK with location="us-central1".
Imagen 3 fallback uses old vertexai SDK.
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
    """Use Gemini to describe a photo for re-generation in a different style."""
    from services.ai_client import get_client

    client = get_client("us-central1")
    if not client:
        logger.info("No GenAI client — stub mode, no photo describe")
        return None

    prompt_text = (
        "Describe this photo in detail for an AI image generator. "
        "Focus on: the person's appearance (hair color, length, style, eye color, "
        "skin tone, facial features, expression), clothing, pose, and background. "
        "Be very specific and detailed. Output ONLY the description, no commentary. "
        "Keep it child-safe. Write in English. Max 150 words."
    )

    try:
        from google.genai import types

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[prompt_text, image_part],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            ),
        )

        from services.ai_client import report_usage
        report_usage("gemini-3.5-flash", response, feature="chat-images")

        if response.text:
            logger.info("Photo described via GenAI: %s", response.text[:100])
            return response.text.strip()
        return None
    except Exception as e:
        logger.exception("Photo description failed")
        from services.notify import notify_error
        notify_error(f"Photo description failed: {e}")
        return None


def stylize_photo(image_bytes: bytes, style_en: str) -> bytes | None:
    """Style-transfer a photo: try Gemini 2.5 Flash Image first, fallback to FLUX."""
    # Try Gemini first
    result = _stylize_photo_gemini(image_bytes, style_en)
    if result:
        return result

    # Fallback to Together AI FLUX
    logger.info("Gemini stylization failed, falling back to FLUX")
    return _stylize_photo_flux(image_bytes, style_en)


def _stylize_photo_flux(image_bytes: bytes, style_en: str) -> bytes | None:
    """Style-transfer a photo using Together AI FLUX.1-kontext-pro (fallback).

    Takes original photo bytes and a style description, returns styled PNG bytes.
    """
    import base64
    import httpx

    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        logger.info("No TOGETHER_API_KEY — cannot stylize photo via FLUX")
        return None

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64_image}"

    prompt = (
        f"Transform this photo into {style_en}. "
        f"Keep the same person, pose, and composition. "
        f"Make it child-friendly and colorful."
    )

    try:
        resp = httpx.post(
            "https://api.together.xyz/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "black-forest-labs/FLUX.1-kontext-pro",
                "prompt": prompt,
                "image_url": data_url,
                "steps": 40,
                "n": 1,
                "response_format": "b64_json",
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("data") and result["data"][0].get("b64_json"):
            image_b64 = result["data"][0]["b64_json"]
            logger.info("Photo stylized via Together AI FLUX (%s)", style_en)
            import base64 as b64mod
            return b64mod.b64decode(image_b64)

        logger.warning("Together AI returned no image data: %s", str(result)[:200])
        return None
    except Exception as e:
        logger.exception("Photo stylization via Together AI failed")
        from services.notify import notify_error
        notify_error(f"FLUX stylization failed: {e}")
        return None


def _extract_image_bytes(response) -> bytes | None:
    """Extract image bytes from Gemini response."""
    try:
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                mime = getattr(part.inline_data, "mime_type", "")
                if mime.startswith("image/"):
                    return part.inline_data.data
    except (IndexError, AttributeError):
        pass
    return None


def _generate_image_gemini(prompt: str) -> bytes | None:
    """Generate image using Gemini 2.5 Flash Image via GenAI SDK."""
    from services.ai_client import get_client

    client = get_client("us-central1")
    if not client:
        return None
    try:
        from google.genai import types

        response = client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        from services.ai_client import report_usage
        report_usage("gemini-2.5-flash-image-preview", response, feature="chat-images")

        image_bytes = _extract_image_bytes(response)
        if image_bytes:
            logger.info("Image generated via Gemini 2.5 Flash Image")
            return image_bytes
        logger.warning("Gemini Flash Image returned no image for: %s", prompt[:100])
        return None
    except Exception as e:
        logger.exception("Gemini Flash Image generation failed")
        from services.notify import notify_error
        notify_error(f"Gemini image generation failed: {e}")
        return None


def _stylize_photo_gemini(image_bytes: bytes, style_en: str) -> bytes | None:
    """Style-transfer a photo using Gemini 2.5 Flash Image."""
    from services.ai_client import get_client

    client = get_client("us-central1")
    if not client:
        return None
    try:
        from google.genai import types

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        prompt = (
            f"Transform this photo into {style_en}. "
            f"Keep the same person, pose, and composition. "
            f"Make it child-friendly and colorful."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash-image-preview",
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        from services.ai_client import report_usage
        report_usage("gemini-2.5-flash-image-preview", response, feature="chat-images")

        result = _extract_image_bytes(response)
        if result:
            logger.info("Photo stylized via Gemini Flash Image (%s)", style_en)
            return result
        logger.warning("Gemini Flash Image returned no styled image")
        return None
    except Exception as e:
        logger.exception("Gemini Flash Image stylization failed")
        from services.notify import notify_error
        notify_error(f"Gemini stylization failed: {e}")
        return None


def generate_image(prompt: str) -> bytes | None:
    """Generate image: try Gemini 2.5 Flash Image first, fallback to Imagen 3."""
    from services.ai_client import get_client

    client = get_client("us-central1")
    if not client:
        logger.info("No GenAI client — stub mode, no image")
        return None

    # Try Gemini 2.5 Flash Image first
    result = _generate_image_gemini(prompt)
    if result:
        return result

    # Fallback to Imagen 3 (uses old vertexai SDK)
    logger.info("Gemini Flash Image failed, falling back to Imagen 3")
    try:
        import vertexai
        from vertexai.preview.vision_models import ImageGenerationModel

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(credentials_path)
            vertexai.init(project=project, location="us-central1", credentials=credentials)
        else:
            vertexai.init(project=project, location="us-central1")

        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_most",
            person_generation="allow_adult",
        )

        if response.images:
            logger.info("Image generated via Vertex AI Imagen (fallback)")
            return response.images[0]._image_bytes

        logger.warning("Imagen returned no images for prompt: %s", prompt[:100])
        return None
    except Exception as e:
        logger.exception("Image generation failed (Imagen fallback)")
        from services.notify import notify_error
        notify_error(f"Imagen fallback failed: {e}")
        return None
