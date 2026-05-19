"""
ai_client.py — Vertex AI model provider for Kidion.

Returns Vertex AI GenerativeModel instances. Falls back to stub mode (None)
if google-credentials.json is not available.

LLM Dashboard integration: sends token usage after each call.
"""

import json
import logging
import os
import threading

import httpx

logger = logging.getLogger("kidion")

LLM_DASHBOARD_URL = "http://5.42.101.215:8005/api/usage"

# ── Vertex AI initialization (cached) ──

_vertex_initialized = False
_vertex_project = None


def _ensure_vertex():
    """Initialize Vertex AI once from google-credentials.json."""
    global _vertex_initialized, _vertex_project
    if _vertex_initialized:
        return _vertex_project is not None

    _vertex_initialized = True
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")

    # Auto-detect from google-credentials.json if env vars not set
    if not project and os.path.exists("google-credentials.json"):
        try:
            with open("google-credentials.json") as f:
                creds_data = json.load(f)
            project = creds_data.get("project_id", "")
            creds_path = "google-credentials.json"
        except Exception:
            pass

    if not project:
        logger.info("No Vertex AI credentials — running in stub mode")
        return False

    try:
        import vertexai
        if creds_path:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            vertexai.init(project=project, location="global", credentials=credentials)
        else:
            vertexai.init(project=project, location="global")
        _vertex_project = project
        logger.info("Vertex AI initialized: project=%s", project)
        return True
    except Exception as e:
        logger.warning("Vertex AI init failed: %s", e)
        return False


# ── LLM Dashboard reporting ──

def _send_to_dashboard(model: str, response):
    """Fire-and-forget token usage reporting."""
    try:
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
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


# ── Public API ──

def get_model(model_name: str, system_instruction=None):
    """
    Returns a Vertex AI GenerativeModel, or None if not configured (stub mode).

    Usage:
        model = get_model("gemini-2.5-flash")
        if model is None:
            return stub_response()
        response = model.generate_content(prompt)
    """
    if not _ensure_vertex():
        return None
    try:
        from vertexai.generative_models import GenerativeModel
        if system_instruction:
            return GenerativeModel(model_name, system_instruction=system_instruction)
        return GenerativeModel(model_name)
    except Exception as e:
        logger.warning("Failed to create model %s: %s", model_name, e)
        return None


def report_usage(model_name: str, response):
    """Report token usage to LLM Dashboard in background thread."""
    threading.Thread(
        target=_send_to_dashboard,
        args=(model_name, response),
        daemon=True,
    ).start()


# Backward compatibility alias — all existing callers use this name
get_studio_model = get_model
