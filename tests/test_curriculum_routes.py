import json

import pytest

from services.curriculum_routes import (
    ACTIVE_ROUTE_SUBJECTS,
    LESSON_ROLES,
    ROUTE_GRADES,
    CurriculumRouteError,
    expected_blocks_for_grade,
    expected_lessons_for_grade,
    expected_route_keys,
    load_route_curricula,
    load_route_curriculum,
    route_to_template_curriculum,
    validate_route_curriculum,
)


def make_block(week):
    return {
        "week": week,
        "school_theme": f"Тема недели {week}",
        "skills": [f"умение {week}"],
        "mission_title": f"Миссия {week}",
        "mission_goal": f"Цель миссии {week}",
        "lessons": [
            {
                "order": index,
                "role": role,
                "title": f"Урок {week}.{index}",
                "school_focus": f"Фокус недели {week}",
                "prompt_hint": f"Связать задания с миссией {week}",
            }
            for index, role in enumerate(LESSON_ROLES, start=1)
        ],
    }


def make_route(*, subject="math", grade=1, blocks_count=None, **overrides):
    if blocks_count is None:
        blocks_count = expected_blocks_for_grade(grade)

    route = {
        "subject": subject,
        "grade": grade,
        "title": f"Математика {grade} класс",
        "blocks": [make_block(week) for week in range(1, blocks_count + 1)],
    }
    route.update(overrides)
    return route


def test_expected_route_size_is_uniform_by_school_year():
    assert expected_blocks_for_grade(1) == 33
    assert expected_lessons_for_grade(1) == 165
    assert expected_blocks_for_grade(2) == 34
    assert expected_lessons_for_grade(6) == 170


def test_validate_route_curriculum_accepts_normal_route():
    route = validate_route_curriculum(make_route(), source="test")

    assert route["subject"] == "math"
    assert route["grade"] == 1
    assert len(route["blocks"]) == 33
    assert [lesson["role"] for lesson in route["blocks"][0]["lessons"]] == list(LESSON_ROLES)


def test_validate_route_curriculum_accepts_grade_two_year_route():
    route = validate_route_curriculum(make_route(grade=2), source="test")

    assert route["grade"] == 2
    assert len(route["blocks"]) == 34


def test_validate_route_curriculum_rejects_inactive_subject():
    with pytest.raises(CurriculumRouteError, match="subject"):
        validate_route_curriculum(make_route(subject="english"), source="test")


def test_validate_route_curriculum_rejects_grade_outside_active_range():
    route = make_route()
    route["grade"] = 7

    with pytest.raises(CurriculumRouteError, match="grade"):
        validate_route_curriculum(route, source="test")


def test_validate_route_curriculum_requires_full_year_block_count():
    with pytest.raises(CurriculumRouteError, match="33 weekly blocks"):
        validate_route_curriculum(make_route(blocks_count=12), source="test")


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


def test_repository_route_curricula_cover_all_active_subjects_and_grades():
    routes = load_route_curricula()

    assert set(routes) == expected_route_keys()
    assert expected_route_keys() == {
        (subject, grade)
        for subject in ACTIVE_ROUTE_SUBJECTS
        for grade in ROUTE_GRADES
    }

    for (subject, grade), route in routes.items():
        assert route["subject"] == subject
        assert route["grade"] == grade
        assert len(route["blocks"]) == expected_blocks_for_grade(grade)
        assert sum(len(block["lessons"]) for block in route["blocks"]) == expected_lessons_for_grade(grade)


def test_route_to_template_curriculum_preserves_weekly_mission_shape():
    route = load_route_curricula()[("math", 1)]

    template = route_to_template_curriculum(route)

    assert template["subject"] == "math"
    assert template["grade"] == 1
    assert len(template["units"]) == 33
    assert all(len(unit["topics"]) == 5 for unit in template["units"])
    assert template["units"][0]["id"] == "math-1-week-01"
    assert template["units"][0]["mission_title"]
    assert template["units"][0]["topics"][0]["role"] == "arrival"
    assert template["units"][0]["topics"][4]["role"] == "victory"
