import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _login_child(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "voice-parent@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    child_resp = await client.post(
        "/api/children",
        json={
            "name": "Маша",
            "gender": "girl",
            "birth_date": "2018-01-01",
            "grade": 1,
            "universe": "Космос",
            "source": "chat",
        },
    )
    assert child_resp.status_code == 201
    auth_resp = await client.post("/api/kid/auth", json={"child_id": child_resp.json()["id"]})
    assert auth_resp.status_code == 200


async def test_chat_landing_registers_pwa_assets(client: AsyncClient):
    resp = await client.get("/", headers={"host": "chat.kidion.ru"})
    assert resp.status_code == 200
    assert '<link rel="manifest" href="/manifest.json">' in resp.text
    assert "/static/spark/pwa.js" in resp.text


async def test_chat_login_and_register_keep_pwa_assets(client: AsyncClient):
    login = await client.get("/chat/login")
    register = await client.get("/chat/register")

    assert login.status_code == 200
    assert register.status_code == 200
    assert '<link rel="manifest" href="/manifest.json">' in login.text
    assert '<link rel="manifest" href="/manifest.json">' in register.text
    assert "/static/spark/pwa.js" in login.text
    assert "/static/spark/pwa.js" in register.text


async def test_manifest_has_android_icons(client: AsyncClient):
    resp = await client.get("/manifest.json")
    assert resp.status_code == 200
    data = resp.json()
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"}.issubset(sizes)


async def test_chat_voice_transcribe_requires_child_session(client: AsyncClient):
    resp = await client.post(
        "/api/kid/chat/transcribe",
        files={"audio": ("voice.webm", b"fake-audio", "audio/webm")},
    )
    assert resp.status_code == 401


async def test_chat_voice_transcribe_returns_text(client: AsyncClient, monkeypatch):
    await _login_child(client)
    monkeypatch.setattr("services.speech.transcribe_audio", lambda _data, _mime: "привет киди")

    resp = await client.post(
        "/api/kid/chat/transcribe",
        files={"audio": ("voice.webm", b"fake-audio", "audio/webm")},
    )

    assert resp.status_code == 200
    assert resp.json() == {"text": "привет киди"}
