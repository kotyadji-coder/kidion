"""
ai_client.py — Google GenAI client for Kidion (Vertex AI mode).

Uses google-genai SDK v2+ with vertexai=True.
Falls back to stub mode (None) if google-credentials.json is not available.

LLM Dashboard integration: sends token usage after each call.
"""

import json
import logging
import os
import threading

import httpx

logger = logging.getLogger("kidion")

LLM_DASHBOARD_URL = "http://5.42.101.215:8005/api/usage"

# ── Client initialization (cached per location) ──

_clients: dict = {}
_init_done: dict = {}
_project: str | None = None


def _get_project() -> str:
    """Detect project ID from env or google-credentials.json."""
    global _project
    if _project is not None:
        return _project

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    if not project and os.path.exists("google-credentials.json"):
        try:
            with open("google-credentials.json") as f:
                creds_data = json.load(f)
            project = creds_data.get("project_id", "")
            if not creds_path:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google-credentials.json"
        except Exception:
            pass

    _project = project or ""
    return _project


def get_client(location: str = "global"):
    """Get a GenAI client for a specific location. Returns None in stub mode."""
    if os.getenv("TESTING") == "1":
        logger.info("TESTING=1 — GenAI disabled")
        return None

    if location in _init_done:
        return _clients.get(location)

    _init_done[location] = True
    project = _get_project()

    if not project:
        logger.info("No Vertex AI credentials — running in stub mode")
        return None

    try:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
        _clients[location] = client
        logger.info("GenAI client initialized: project=%s, location=%s", project, location)
        return client
    except Exception as e:
        logger.warning("GenAI client init failed: %s", e)
        return None


# ── Public API ──

def get_model(model_name: str, system_instruction=None, feature: str = ""):
    """
    Returns a ModelWrapper, or None if not configured (stub mode).

    Args:
        feature: tag for LLM Dashboard (e.g. "chat", "lessons", "universe").
    """
    client = get_client("global")
    if client is None:
        return None
    return ModelWrapper(client, model_name, system_instruction, feature=feature)


def is_safety_blocked(response) -> bool:
    """Check if a Gemini response was blocked by safety filters."""
    if not response.candidates:
        return True
    candidate = response.candidates[0]
    fr = getattr(candidate, "finish_reason", None)
    if not fr:
        return False
    return getattr(fr, "name", str(fr)) == "SAFETY"


# ── LLM Dashboard reporting ──

def _send_to_dashboard(model: str, response, feature: str = ""):
    """Fire-and-forget token usage reporting."""
    if os.getenv("TESTING") == "1":
        logger.debug("TESTING=1 - LLM dashboard usage reporting disabled")
        return

    try:
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        if not (input_tokens or output_tokens):
            return
        payload = {
            "project": "kidion",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        if feature:
            payload["feature"] = feature
        httpx.post(LLM_DASHBOARD_URL, json=payload, timeout=5)
    except Exception:
        logger.debug("Failed to send usage to LLM dashboard", exc_info=True)


def report_usage(model_name: str, response, feature: str = ""):
    """Report token usage to LLM Dashboard in background thread."""
    if os.getenv("TESTING") == "1":
        logger.debug("TESTING=1 - LLM dashboard usage reporting disabled")
        return

    threading.Thread(
        target=_send_to_dashboard,
        args=(model_name, response, feature),
        daemon=True,
    ).start()


# ── Model Wrapper ──

class ModelWrapper:
    """Wraps google-genai client to provide generate_content() and start_chat()."""

    def __init__(self, client, model_name: str, system_instruction=None, feature: str = ""):
        self._client = client
        self._model_name = model_name
        self._system_instruction = system_instruction
        self._feature = feature

    def _build_config(self, generation_config=None):
        from google.genai import types

        kw: dict = {}
        if self._system_instruction:
            kw["system_instruction"] = self._system_instruction

        # Thinking config for thinking models (3.5+)
        if "3.5" in self._model_name:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")

        # Merge caller's generation_config
        if isinstance(generation_config, dict):
            kw.update(generation_config)

        return types.GenerateContentConfig(**kw) if kw else None

    def generate_content(self, contents, generation_config=None, **_ignored):
        config = self._build_config(generation_config)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )
        report_usage(self._model_name, response, self._feature)
        return response

    def start_chat(self, history=None):
        from google.genai import types

        kw: dict = {}
        if self._system_instruction:
            kw["system_instruction"] = self._system_instruction
        if "3.5" in self._model_name:
            kw["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")

        config = types.GenerateContentConfig(**kw) if kw else None

        chat = self._client.chats.create(
            model=self._model_name,
            config=config,
            history=history,
        )
        return _ChatWrapper(chat, self._model_name, self._feature)


class _ChatWrapper:
    """Wraps google-genai chat session with usage reporting."""

    def __init__(self, chat, model_name: str, feature: str = ""):
        self._chat = chat
        self._model_name = model_name
        self._feature = feature

    def send_message(self, message):
        response = self._chat.send_message(message)
        report_usage(self._model_name, response, self._feature)
        return response
