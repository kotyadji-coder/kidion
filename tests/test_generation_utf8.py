from services.generation import _sanitize_utf8


def test_sanitize_utf8_converts_surrogate_pair_to_character():
    data = {"story_blocks": [{"text": "Привет \ud83d\ude0a"}]}

    cleaned = _sanitize_utf8(data)

    assert cleaned["story_blocks"][0]["text"] == "Привет 😊"
    cleaned["story_blocks"][0]["text"].encode("utf-8")


def test_sanitize_utf8_replaces_lone_surrogate():
    data = {"tasks": [{"question": "Найди знак \ud83d"}]}

    cleaned = _sanitize_utf8(data)

    assert "\ud83d" not in cleaned["tasks"][0]["question"]
    cleaned["tasks"][0]["question"].encode("utf-8")
