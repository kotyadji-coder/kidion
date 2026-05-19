"""
ai_client.py - Google AI Studio wrapper compatible with Vertex AI GenerativeModel API.

If GEMINI_API_KEY is set, returns StudioModel (mimics GenerativeModel interface).
Existing code calls model.generate_content() the same way - no other changes needed.
On 429/quota errors, automatically falls back to Vertex AI if credentials are available.
"""

import logging
import os
import threading

import httpx

logger = logging.getLogger("kidion")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LLM_DASHBOARD_URL = "http://5.42.101.215:8005/api/usage"


def _is_quota_error(exc: Exception) -> bool:
    """Check if exception is a 429 / RESOURCE_EXHAUSTED quota error."""
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()


def _get_vertex_fallback(model_name: str, system_instruction=None):
    """Try to create a Vertex AI model for fallback. Returns None if not configured."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    # Also check for commented-out vars: try the credentials file directly
    if not project and os.path.exists("google-credentials.json"):
        import json
        try:
            with open("google-credentials.json") as f:
                creds_data = json.load(f)
            project = creds_data.get("project_id")
            creds_path = "google-credentials.json"
        except Exception:
            pass
    if not project:
        return None
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        if creds_path:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            vertexai.init(project=project, location="global", credentials=credentials)
        else:
            vertexai.init(project=project, location="global")
        if system_instruction:
            return GenerativeModel(model_name, system_instruction=system_instruction)
        return GenerativeModel(model_name)
    except Exception as e:
        logger.warning("Vertex AI fallback init failed: %s", e)
        return None


def _send_to_dashboard(model: str, response):
    try:
        raw = getattr(response, "_response", response)
        input_tokens = getattr(getattr(raw, "usage_metadata", None), "prompt_token_count", 0) or 0
        output_tokens = getattr(getattr(raw, "usage_metadata", None), "candidates_token_count", 0) or 0
        if not (input_tokens or output_tokens):
            return
        httpx.post(LLM_DASHBOARD_URL, json={
            "project": "kidion",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }, timeout=5)
    except Exception:
        logger.debug("Failed to send usage to LLM dashboard", exc_info=True)


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
            wrapped = _StudioResponse(response)
            threading.Thread(target=_send_to_dashboard, args=(self._model_name, response), daemon=True).start()
            return wrapped
        except Exception as e:
            if _is_quota_error(e):
                logger.warning("AI Studio quota hit, trying Vertex AI fallback...")
                vertex = _get_vertex_fallback(self._model_name, self._system_instruction)
                if vertex:
                    return vertex.generate_content(
                        prompt,
                        generation_config=generation_config,
                        safety_settings=safety_settings,
                    )
                logger.error("Vertex AI fallback not available either")
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
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=self._contents,
                config=config if config else None,
            )
            threading.Thread(target=_send_to_dashboard, args=(self._model_name, response), daemon=True).start()
            return _StudioResponse(response)
        except Exception as e:
            if _is_quota_error(e):
                logger.warning("AI Studio chat quota hit, trying Vertex AI fallback...")
                vertex = _get_vertex_fallback(self._model_name, self._system_instruction)
                if vertex:
                    # Rebuild history for Vertex and send
                    from vertexai.generative_models import Content, Part
                    history = []
                    for c in self._contents[:-1]:
                        role = c.role if c.role != "model" else "model"
                        text = c.parts[0].text if c.parts else ""
                        history.append(Content(role=role, parts=[Part.from_text(text)]))
                    chat = vertex.start_chat(history=history)
                    return chat.send_message(message, safety_settings=safety_settings)
            raise


def get_studio_model(model_name, system_instruction=None):
    """Returns StudioModel if GEMINI_API_KEY is set, else None."""
    if not GEMINI_API_KEY:
        return None
    try:
        return StudioModel(model_name, system_instruction=system_instruction)
    except Exception as e:
        logger.warning("Failed to create StudioModel: %s", e)
        return None
