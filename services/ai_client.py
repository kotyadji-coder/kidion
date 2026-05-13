"""
ai_client.py - Google AI Studio wrapper compatible with Vertex AI GenerativeModel API.

If GEMINI_API_KEY is set, returns StudioModel (mimics GenerativeModel interface).
Existing code calls model.generate_content() the same way - no other changes needed.
Falls back to Vertex AI if AI Studio call fails.
"""

import logging
import os

logger = logging.getLogger("kidion")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class _StudioFinishReason:
    def __init__(self, name):
        self.name = name


class _StudioCandidate:
    def __init__(self, candidate):
        self._candidate = candidate
        fr = getattr(candidate, "finish_reason", None)
        if fr is not None:
            self.finish_reason = _StudioFinishReason(str(fr))
        else:
            self.finish_reason = None
        self.content = getattr(candidate, "content", None)


class _StudioResponse:
    """Wraps google-genai response to look like Vertex AI response."""
    def __init__(self, response):
        self._response = response
        self.candidates = [_StudioCandidate(c) for c in (response.candidates or [])]

    @property
    def text(self):
        return self._response.text


class StudioModel:
    """Drop-in replacement for vertexai GenerativeModel using AI Studio API key."""

    def __init__(self, model_name, system_instruction=None):
        from google import genai
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._model_name = model_name
        self._system_instruction = system_instruction

    def generate_content(self, prompt, generation_config=None, safety_settings=None):
        config = {}
        if self._system_instruction:
            config["system_instruction"] = self._system_instruction
        if generation_config is not None:
            # Accept both Vertex GenerationConfig objects and plain dicts
            if hasattr(generation_config, "response_mime_type"):
                mime = generation_config.response_mime_type
            elif isinstance(generation_config, dict):
                mime = generation_config.get("response_mime_type")
            else:
                mime = None
            if mime and mime != "image/png":
                config["response_mime_type"] = mime

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config if config else None,
            )
            return _StudioResponse(response)
        except Exception as e:
            logger.warning("AI Studio generate_content failed: %s", e)
            raise

    def start_chat(self, history=None):
        return _StudioChat(self._client, self._model_name, self._system_instruction, history)


class _StudioChat:
    """Wraps google-genai chat to mimic Vertex AI chat interface."""

    def __init__(self, client, model_name, system_instruction, history):
        from google.genai import types
        self._client = client
        self._model_name = model_name
        self._system_instruction = system_instruction
        # Convert Vertex-style history to genai contents
        self._contents = []
        if history:
            for h in history:
                role = getattr(h, "role", "user")
                parts = getattr(h, "parts", [])
                text = parts[0].text if parts else ""
                self._contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=text)],
                ))

    def send_message(self, message, safety_settings=None):
        from google.genai import types
        self._contents.append(types.Content(
            role="user",
            parts=[types.Part(text=message)],
        ))
        config = {}
        if self._system_instruction:
            config["system_instruction"] = self._system_instruction
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=self._contents,
            config=config if config else None,
        )
        return _StudioResponse(response)


def get_studio_model(model_name, system_instruction=None):
    """Returns StudioModel if GEMINI_API_KEY is set, else None."""
    if not GEMINI_API_KEY:
        return None
    try:
        return StudioModel(model_name, system_instruction=system_instruction)
    except Exception as e:
        logger.warning("Failed to create StudioModel: %s", e)
        return None
