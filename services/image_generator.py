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
    """Use Gemini via Vertex AI to describe a photo for re-generation in a different style."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        logger.info("No GOOGLE_CLOUD_PROJECT — stub mode, no photo describe")
        return None

    prompt_text = (
        "Describe this photo in detail for an AI image generator. "
        "Focus on: the person's appearance (hair color, length, style, eye color, "
        "skin tone, facial features, expression), clothing, pose, and background. "
        "Be very specific and detailed. Output ONLY the description, no commentary. "
        "Keep it child-safe. Write in English. Max 150 words."
    )

    try:
        _init_vertex(project)
        from vertexai.generative_models import GenerativeModel, Part

        model = GenerativeModel("gemini-2.5-flash")
        image_part = Part.from_data(image_bytes, mime_type="image/jpeg")
        response = model.generate_content([prompt_text, image_part])

        if response.text:
            logger.info("Photo described via Vertex AI: %s", response.text[:100])
            return response.text.strip()
        return None
    except Exception:
        logger.exception("Photo description failed")
        return None


def stylize_photo(image_bytes: bytes, style_en: str) -> bytes | None:
    """Style-transfer a photo using Together AI FLUX.1-kontext-pro.

    Takes original photo bytes and a style description, returns styled PNG bytes.
    """
    import base64
    import httpx

    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        logger.info("No TOGETHER_API_KEY — cannot stylize photo")
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
                "steps": 28,
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
            return base64.b64decode(image_b64)

        logger.warning("Together AI returned no image data: %s", str(result)[:200])
        return None
    except Exception:
        logger.exception("Photo stylization via Together AI failed")
        return None


def _init_vertex(project: str):
    """Initialize Vertex AI with credentials."""
    import vertexai
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        vertexai.init(project=project, location="us-central1", credentials=credentials)
    else:
        vertexai.init(project=project, location="us-central1")


def generate_image(prompt: str) -> bytes | None:
    """Generate image using Vertex AI Imagen 3."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        logger.info("No GOOGLE_CLOUD_PROJECT — stub mode, no image")
        return None

    try:
        _init_vertex(project)
        from vertexai.preview.vision_models import ImageGenerationModel

        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="1:1",
            safety_filter_level="block_most",
            person_generation="allow_adult",
        )

        if response.images:
            logger.info("Image generated via Vertex AI Imagen")
            return response.images[0]._image_bytes

        logger.warning("Imagen returned no images for prompt: %s", prompt[:100])
        return None
    except Exception:
        logger.exception("Image generation failed")
        return None
