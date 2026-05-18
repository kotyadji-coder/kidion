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
        f"Generate a cute, colorful, child-friendly cartoon illustration for a child aged 6-10. "
        f"Style: bright colors, rounded shapes, friendly characters, no scary elements. "
        f"Subject: {description}. "
        f"The image must be safe for children — no violence, no scary content, no text."
    )
    return generate_image(safe_prompt)


def generate_image(prompt: str) -> bytes | None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        logger.info("GOOGLE_CLOUD_PROJECT not set - skipping image generation (stub mode)")
        return None

    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project, location="us-central1")
        model = GenerativeModel("gemini-2.5-flash")

        response = model.generate_content(
            f"Generate an educational children illustration: {prompt}",
            generation_config={"response_mime_type": "image/png"},
        )

        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    return part.inline_data.data

        return None
    except Exception:
        logger.exception("Image generation failed")
        return None
