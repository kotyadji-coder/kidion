"""
image_generator.py - Generate lesson illustrations using Gemini 2.5 Flash.
"""

import os
import logging

logger = logging.getLogger("kidion")


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
