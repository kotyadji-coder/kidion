import os


def test_testing_env_disables_genai(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "real-project-must-not-be-used")

    import services.ai_client as ai_client
    ai_client._clients.clear()
    ai_client._init_done.clear()
    ai_client._project = None

    assert ai_client.get_client("global") is None
    assert ai_client.get_model("gemini-3.5-flash", feature="lessons") is None


def test_testing_env_suppresses_telegram_notify(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("NOTIFY_BOT_TOKEN", "real-token-must-not-be-used")
    monkeypatch.setenv("NOTIFY_CHAT_ID", "123")

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("services.notify.httpx.post", fake_post)

    from services.notify import notify_error
    notify_error("test alert")

    assert calls == []


def test_testing_env_suppresses_dashboard_usage(monkeypatch):
    monkeypatch.setenv("TESTING", "1")

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("services.ai_client.httpx.post", fake_post)

    class Usage:
        prompt_token_count = 10
        candidates_token_count = 5

    class Response:
        usage_metadata = Usage()

    import services.ai_client as ai_client
    ai_client._send_to_dashboard("gemini-3.5-flash", Response(), feature="lessons")
    ai_client.report_usage("gemini-3.5-flash", Response(), feature="lessons")

    assert calls == []


def test_testing_env_suppresses_together_flux(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("TOGETHER_API_KEY", "real-key-must-not-be-used")

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("httpx.post", fake_post)

    from services.image_generator import _stylize_photo_flux
    assert _stylize_photo_flux(b"fake-image", "cartoon") is None
    assert calls == []
