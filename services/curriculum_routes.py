"""Validation and loading for Kidion route-based curricula.

Route curricula are the content contract for the "school map + game mission"
model. They are intentionally independent from the database and LLM calls so
content can be checked before it is connected to product flows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
ROUTE_CURRICULA_DIR = BASE_DIR / "data" / "curricula" / "routes"

ACTIVE_ROUTE_SUBJECTS = ("math", "russian")
ROUTE_GRADES = tuple(range(1, 7))
LESSONS_PER_BLOCK = 5
LESSON_ROLES = ("arrival", "explore", "practice", "challenge", "victory")
ROUTE_BLOCKS_BY_GRADE = {
    1: 33,
    2: 34,
    3: 34,
    4: 34,
    5: 34,
    6: 34,
}


class CurriculumRouteError(ValueError):
    """Raised when a route curriculum does not match the Kidion contract."""


def _require_dict(value: Any, label: str, source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CurriculumRouteError(f"{source}: {label} must be an object")
    return value


def _require_text(value: Any, label: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CurriculumRouteError(f"{source}: {label} must be a non-empty string")
    return value.strip()


def _require_text_list(value: Any, label: str, source: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CurriculumRouteError(f"{source}: {label} must be a non-empty list")

    items: list[str] = []
    for index, item in enumerate(value, start=1):
        items.append(_require_text(item, f"{label}[{index}]", source))
    return items


def _require_positive_int(value: Any, label: str, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CurriculumRouteError(f"{source}: {label} must be a positive integer")
    return value


def _normalize_lesson(
    lesson: Any,
    *,
    block_index: int,
    expected_order: int,
    expected_role: str,
    source: str,
) -> dict[str, Any]:
    lesson_data = _require_dict(
        lesson,
        f"blocks[{block_index}].lessons[{expected_order}]",
        source,
    )

    order = _require_positive_int(
        lesson_data.get("order"),
        f"blocks[{block_index}].lessons[{expected_order}].order",
        source,
    )
    if order != expected_order:
        raise CurriculumRouteError(
            f"{source}: blocks[{block_index}].lessons[{expected_order}].order "
            f"must be {expected_order}"
        )

    role = _require_text(
        lesson_data.get("role"),
        f"blocks[{block_index}].lessons[{expected_order}].role",
        source,
    )
    if role != expected_role:
        raise CurriculumRouteError(
            f"{source}: blocks[{block_index}].lessons[{expected_order}].role "
            f"must be {expected_role!r}"
        )

    normalized: dict[str, Any] = {
        "order": order,
        "role": role,
        "title": _require_text(
            lesson_data.get("title"),
            f"blocks[{block_index}].lessons[{expected_order}].title",
            source,
        ),
    }

    for optional_key in ("school_focus", "prompt_hint"):
        value = lesson_data.get(optional_key)
        if value is not None:
            normalized[optional_key] = _require_text(
                value,
                f"blocks[{block_index}].lessons[{expected_order}].{optional_key}",
                source,
            )

    return normalized


def _normalize_block(
    block: Any,
    *,
    block_index: int,
    expected_week: int,
    source: str,
) -> dict[str, Any]:
    block_data = _require_dict(block, f"blocks[{block_index}]", source)
    week = _require_positive_int(
        block_data.get("week"),
        f"blocks[{block_index}].week",
        source,
    )
    if week != expected_week:
        raise CurriculumRouteError(
            f"{source}: blocks[{block_index}].week must be {expected_week}"
        )

    lessons = block_data.get("lessons")
    if not isinstance(lessons, list):
        raise CurriculumRouteError(f"{source}: blocks[{block_index}].lessons must be a list")
    if len(lessons) != LESSONS_PER_BLOCK:
        raise CurriculumRouteError(
            f"{source}: blocks[{block_index}].lessons must contain "
            f"{LESSONS_PER_BLOCK} lessons"
        )

    return {
        "week": week,
        "school_theme": _require_text(
            block_data.get("school_theme"),
            f"blocks[{block_index}].school_theme",
            source,
        ),
        "skills": _require_text_list(
            block_data.get("skills"),
            f"blocks[{block_index}].skills",
            source,
        ),
        "mission_title": _require_text(
            block_data.get("mission_title"),
            f"blocks[{block_index}].mission_title",
            source,
        ),
        "mission_goal": _require_text(
            block_data.get("mission_goal"),
            f"blocks[{block_index}].mission_goal",
            source,
        ),
        "lessons": [
            _normalize_lesson(
                lesson,
                block_index=block_index,
                expected_order=lesson_index,
                expected_role=LESSON_ROLES[lesson_index - 1],
                source=source,
            )
            for lesson_index, lesson in enumerate(lessons, start=1)
        ],
    }


def expected_blocks_for_grade(grade: int) -> int:
    """Return the required number of weekly mission blocks for a grade."""

    if grade not in ROUTE_BLOCKS_BY_GRADE:
        raise CurriculumRouteError("grade must be between 1 and 6")
    return ROUTE_BLOCKS_BY_GRADE[grade]


def expected_lessons_for_grade(grade: int) -> int:
    """Return the required number of Kidion lessons for one subject route."""

    return expected_blocks_for_grade(grade) * LESSONS_PER_BLOCK


def validate_route_curriculum(data: Any, source: str = "<memory>") -> dict[str, Any]:
    """Validate and normalize a route curriculum dict.

    The validator is strict about the stable product contract: 1st grade has
    33 weekly missions, grades 2-6 have 34 weekly missions, and every mission
    has exactly five Kidion lessons.
    """

    route = _require_dict(data, "route curriculum", source)

    subject = _require_text(route.get("subject"), "subject", source)
    if subject not in ACTIVE_ROUTE_SUBJECTS:
        raise CurriculumRouteError(
            f"{source}: subject must be one of {', '.join(ACTIVE_ROUTE_SUBJECTS)}"
        )

    grade = _require_positive_int(route.get("grade"), "grade", source)
    if grade not in ROUTE_GRADES:
        raise CurriculumRouteError(f"{source}: grade must be between 1 and 6")

    blocks = route.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise CurriculumRouteError(f"{source}: blocks must be a non-empty list")

    expected_block_count = expected_blocks_for_grade(grade)
    if len(blocks) != expected_block_count:
        raise CurriculumRouteError(
            f"{source}: grade {grade} route must contain "
            f"{expected_block_count} weekly blocks"
        )

    normalized_blocks = [
        _normalize_block(
            block,
            block_index=block_index,
            expected_week=block_index,
            source=source,
        )
        for block_index, block in enumerate(blocks, start=1)
    ]

    return {
        "subject": subject,
        "grade": grade,
        "title": _require_text(route.get("title"), "title", source),
        "blocks": normalized_blocks,
    }


def route_key(route: dict[str, Any]) -> tuple[str, int]:
    """Return the stable key for a validated or raw route curriculum."""

    return str(route["subject"]), int(route["grade"])


def expected_route_keys() -> set[tuple[str, int]]:
    """Return every active subject/grade pair that must have a route file."""

    return {
        (subject, grade)
        for subject in ACTIVE_ROUTE_SUBJECTS
        for grade in ROUTE_GRADES
    }


def route_to_template_curriculum(route: dict[str, Any]) -> dict[str, Any]:
    """Convert a validated route curriculum to the legacy template shape.

    The current weekly-plan helpers still expect `units[].topics[]`. Keeping
    this adapter here lets route files become an import source without forcing
    the existing database flows to switch in the same release.
    """

    normalized = validate_route_curriculum(route, source=f"{route.get('subject')}:{route.get('grade')}")
    subject = normalized["subject"]
    grade = normalized["grade"]

    return {
        "subject": subject,
        "grade": grade,
        "title": normalized["title"],
        "units": [
            {
                "id": f"{subject}-{grade}-week-{block['week']:02d}",
                "title": block["school_theme"],
                "mission_title": block["mission_title"],
                "mission_goal": block["mission_goal"],
                "skills": block["skills"],
                "topics": [
                    {
                        "id": (
                            f"{subject}-{grade}-week-{block['week']:02d}-"
                            f"lesson-{lesson['order']}"
                        ),
                        "title": lesson["title"],
                        "skill": block["skills"][0],
                        "role": lesson["role"],
                        "school_focus": lesson.get("school_focus", ""),
                        "prompt_hint": lesson.get("prompt_hint", ""),
                    }
                    for lesson in block["lessons"]
                ],
            }
            for block in normalized["blocks"]
        ],
    }


def load_route_curriculum(path: str | Path) -> dict[str, Any]:
    """Load one route curriculum JSON file and validate it."""

    route_path = Path(path)
    with route_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return validate_route_curriculum(data, source=str(route_path))


def load_route_curricula(
    directory: str | Path = ROUTE_CURRICULA_DIR,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Load all route curriculum JSON files from a directory."""

    route_dir = Path(directory)
    if not route_dir.exists():
        return {}

    routes: dict[tuple[str, int], dict[str, Any]] = {}
    for route_path in sorted(route_dir.glob("*.json")):
        route = load_route_curriculum(route_path)
        key = route_key(route)
        if key in routes:
            raise CurriculumRouteError(
                f"{route_path}: duplicate route for {key[0]} grade {key[1]}"
            )
        routes[key] = route
    return routes
