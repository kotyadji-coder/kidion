import json

import pytest

from services.curriculum_routes import (
    LESSON_ROLES,
    CurriculumRouteError,
    load_route_curricula,
    load_route_curriculum,
    validate_route_curriculum,
)


def make_route(**overrides):
    route = {
        "subject": "math",
        "grade": 1,
        "title": "Математика 1 класс",
        "blocks": [
            {
                "week": 1,
                "school_theme": "Счет предметов",
                "skills": ["считать предметы", "сравнивать группы"],
                "mission_title": "Открыть ворота счетного города",
                "mission_goal": "Найти пять числовых ключей",
                "lessons": [
                    {
                        "order": index,
                        "role": role,
                        "title": f"Урок {index}",
                        "school_focus": "Счет в пределах 10",
                        "prompt_hint": "Связать задания с поиском ключей",
                    }
                    for index, role in enumerate(LESSON_ROLES, start=1)
                ],
            },
            {
                "week": 2,
                "school_theme": "Сравнение чисел",
                "skills": ["использовать больше и меньше"],
                "mission_title": "Починить числовые весы",
                "mission_goal": "Сравнить сигналы башен",
                "lessons": [
                    {
                        "order": index,
                        "role": role,
                        "title": f"Весы {index}",
                    }
                    for index, role in enumerate(LESSON_ROLES, start=1)
                ],
            },
        ],
    }
    route.update(overrides)
    return route


def test_validate_route_curriculum_accepts_normal_route():
    route = validate_route_curriculum(make_route(), source="test")

    assert route["subject"] == "math"
    assert route["grade"] == 1
    assert len(route["blocks"]) == 2
    assert [lesson["role"] for lesson in route["blocks"][0]["lessons"]] == list(LESSON_ROLES)


def test_validate_route_curriculum_rejects_inactive_subject():
    with pytest.raises(CurriculumRouteError, match="subject"):
        validate_route_curriculum(make_route(subject="english"), source="test")


def test_validate_route_curriculum_rejects_grade_outside_active_range():
    with pytest.raises(CurriculumRouteError, match="grade"):
        validate_route_curriculum(make_route(grade=7), source="test")


def test_validate_route_curriculum_rejects_boolean_week():
    route = make_route()
    route["blocks"][0]["week"] = True

    with pytest.raises(CurriculumRouteError, match="positive integer"):
        validate_route_curriculum(route, source="test")


def test_validate_route_curriculum_requires_sequential_weeks():
    route = make_route()
    route["blocks"][1]["week"] = 3

    with pytest.raises(CurriculumRouteError, match="week must be 2"):
        validate_route_curriculum(route, source="test")


def test_validate_route_curriculum_requires_five_lessons_per_block():
    route = make_route()
    route["blocks"][0]["lessons"].pop()

    with pytest.raises(CurriculumRouteError, match="5 lessons"):
        validate_route_curriculum(route, source="test")


def test_validate_route_curriculum_requires_lesson_role_order():
    route = make_route()
    route["blocks"][0]["lessons"][2]["role"] = "victory"

    with pytest.raises(CurriculumRouteError, match="practice"):
        validate_route_curriculum(route, source="test")


def test_load_route_curriculum_from_file(tmp_path):
    path = tmp_path / "math_1.json"
    path.write_text(json.dumps(make_route(), ensure_ascii=False), encoding="utf-8")

    route = load_route_curriculum(path)

    assert route["title"] == "Математика 1 класс"


def test_load_route_curricula_rejects_duplicate_subject_grade(tmp_path):
    for filename in ("math_1_a.json", "math_1_b.json"):
        (tmp_path / filename).write_text(
            json.dumps(make_route(), ensure_ascii=False),
            encoding="utf-8",
        )

    with pytest.raises(CurriculumRouteError, match="duplicate"):
        load_route_curricula(tmp_path)
