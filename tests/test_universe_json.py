import pytest

from services.universe import _extract_json


def test_extract_json_ignores_text_after_object():
    data = _extract_json('{"name": "Космоферма", "npcs": []}\n\nГотово!')

    assert data == {"name": "Космоферма", "npcs": []}


def test_extract_json_repairs_trailing_commas():
    data = _extract_json(
        """
        ```json
        {
          "name": "Остров задач",
          "subject_zones": {
            "math": {
              "zone_name": "Верфь",
            },
          },
          "npcs": [
            {"name": "Мая", "role": "друг",},
          ],
        }
        ```
        """
    )

    assert data["subject_zones"]["math"]["zone_name"] == "Верфь"
    assert data["npcs"][0]["name"] == "Мая"


def test_extract_json_repairs_simple_bare_keys():
    data = _extract_json(
        """
        {
          name: "Лаборатория Дино-Тех",
          subject_zones: {
            math: {"zone_name": "Цех"},
          },
          npcs: []
        }
        """
    )

    assert data["name"] == "Лаборатория Дино-Тех"
    assert data["subject_zones"]["math"]["zone_name"] == "Цех"


def test_extract_json_keeps_invalid_json_as_error():
    with pytest.raises(Exception):
        _extract_json("{not valid")
