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
