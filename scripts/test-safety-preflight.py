#!/usr/bin/env python3
"""Fail fast if test mode can reach paid providers or Telegram."""

from __future__ import annotations

import os


def _force_risky_env() -> None:
    os.environ["TESTING"] = "1"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "real-project-must-not-be-used"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/real-creds-must-not-be-used.json"
    os.environ["NOTIFY_BOT_TOKEN"] = "real-token-must-not-be-used"
    os.environ["NOTIFY_CHAT_ID"] = "123"
    os.environ["NOTIFY_RELAY_URL"] = "https://telegram-relay-must-not-be-used.example"
    os.environ["TOGETHER_API_KEY"] = "real-key-must-not-be-used"


def _assert_no_genai() -> None:
    import services.ai_client as ai_client

    ai_client._clients.clear()
    ai_client._init_done.clear()
    ai_client._project = None

    assert ai_client.get_client("global") is None
    assert ai_client.get_client("us-central1") is None
    assert ai_client.get_model("gemini-3.5-flash", feature="lessons") is None


def _assert_no_dashboard_post() -> None:
    import services.ai_client as ai_client

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("LLM dashboard HTTP call attempted in TESTING=1")

    ai_client.httpx.post = fake_post

    class Usage:
        prompt_token_count = 10
        candidates_token_count = 5

    class Response:
        usage_metadata = Usage()

    ai_client._send_to_dashboard("gemini-3.5-flash", Response(), feature="lessons")
    ai_client.report_usage("gemini-3.5-flash", Response(), feature="lessons")
    assert calls == []


def _assert_no_telegram_post() -> None:
    import services.notify as notify

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Telegram HTTP call attempted in TESTING=1")

    notify.httpx.post = fake_post
    notify.notify_error("preflight test alert")
    assert calls == []


def _assert_no_together_post() -> None:
    import httpx
    import services.image_generator as image_generator

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Together AI HTTP call attempted in TESTING=1")

    httpx.post = fake_post
    assert image_generator._stylize_photo_flux(b"fake-image", "cartoon") is None
    assert calls == []


def main() -> None:
    _force_risky_env()
    _assert_no_genai()
    _assert_no_dashboard_post()
    _assert_no_telegram_post()
    _assert_no_together_post()
    print("OK: TESTING=1 blocks GenAI, LLM dashboard, Telegram, and Together AI")


if __name__ == "__main__":
    main()
