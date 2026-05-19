"""
validators.py — Level 1: Deterministic validators for generated lessons and chat responses.

Each validator returns a dict: {"name": str, "passed": bool, "details": str}
"""

import re


VALID_TASK_TYPES = {
    "quiz", "fill_in_the_blank", "drag_and_drop", "multiple_choice",
    "true_false", "sorting", "matching", "emoji_count", "input_number",
}


def validate_json_structure(lesson: dict) -> dict:
    """Check that all required top-level fields exist."""
    required = ["story_blocks", "tasks"]
    missing = [f for f in required if f not in lesson]
    if missing:
        return {"name": "json_structure", "passed": False,
                "details": f"Missing fields: {missing}"}
    if not isinstance(lesson["story_blocks"], list):
        return {"name": "json_structure", "passed": False,
                "details": "story_blocks is not a list"}
    if not isinstance(lesson["tasks"], list):
        return {"name": "json_structure", "passed": False,
                "details": "tasks is not a list"}
    return {"name": "json_structure", "passed": True, "details": "OK"}


def validate_task_count(lesson: dict, expected_min: int = 5) -> dict:
    """Check that lesson has at least expected_min tasks."""
    count = len(lesson.get("tasks", []))
    passed = count >= expected_min
    return {"name": "task_count", "passed": passed,
            "details": f"{count} tasks (min {expected_min})"}


def validate_story_block_count(lesson: dict, expected_min: int = 3) -> dict:
    """Check that lesson has at least expected_min story blocks."""
    count = len(lesson.get("story_blocks", []))
    passed = count >= expected_min
    return {"name": "story_block_count", "passed": passed,
            "details": f"{count} blocks (min {expected_min})"}


def validate_task_types(lesson: dict) -> dict:
    """Check all task types are valid."""
    invalid = []
    for i, task in enumerate(lesson.get("tasks", [])):
        t = task.get("type", "")
        if t and t not in VALID_TASK_TYPES:
            invalid.append(f"task {i+1}: '{t}'")
    if invalid:
        return {"name": "task_types", "passed": False,
                "details": f"Invalid types: {', '.join(invalid)}"}
    return {"name": "task_types", "passed": True, "details": "All types valid"}


def validate_quiz_answers(lesson: dict) -> dict:
    """Check that quiz correct answers are in options."""
    errors = []
    for i, task in enumerate(lesson.get("tasks", [])):
        if task.get("type") != "quiz":
            continue
        correct = task.get("correct", "")
        options = task.get("options", [])
        # Handle correct_index pattern
        if "correct_index" in task and isinstance(task["correct_index"], int):
            idx = task["correct_index"]
            if idx < 0 or idx >= len(options):
                errors.append(f"task {i+1}: correct_index {idx} out of range (options={len(options)})")
        elif correct and options and correct not in options:
            errors.append(f"task {i+1}: '{correct}' not in options")
    if errors:
        return {"name": "quiz_answers", "passed": False,
                "details": "; ".join(errors)}
    return {"name": "quiz_answers", "passed": True, "details": "OK"}


def validate_math_correctness(lesson: dict) -> dict:
    """Check arithmetic in math questions."""
    errors = []
    for i, task in enumerate(lesson.get("tasks", [])):
        question = task.get("question", "")
        # Find patterns like "7 + 5 = ?" or "15 - 8 = _"
        expr_match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)\s*=\s*[_?]', question)
        if not expr_match:
            continue
        a, op, b = int(expr_match.group(1)), expr_match.group(2), int(expr_match.group(3))
        if op == '+':
            expected = a + b
        elif op == '-':
            expected = a - b
        elif op == '*':
            expected = a * b
        elif op == '/' and b != 0:
            expected = a // b
        else:
            continue

        # Get the correct answer
        correct = task.get("correct", "")
        if "correct_index" in task:
            options = task.get("options", [])
            idx = task.get("correct_index", 0)
            if 0 <= idx < len(options):
                correct = options[idx]

        try:
            answer_num = int(re.sub(r'[^\d\-]', '', str(correct)))
            if answer_num != expected:
                errors.append(f"task {i+1}: {a}{op}{b}={expected}, but answer='{correct}'")
        except (ValueError, TypeError):
            pass

    if errors:
        return {"name": "math_correctness", "passed": False,
                "details": "; ".join(errors)}
    return {"name": "math_correctness", "passed": True, "details": "OK"}


def validate_text_length(lesson: dict, grade: int) -> dict:
    """Check text length is appropriate for grade."""
    max_words = {1: 80, 2: 100, 3: 120, 4: 140}.get(grade, 120)
    issues = []
    for i, block in enumerate(lesson.get("story_blocks", [])):
        text = block.get("text", "")
        word_count = len(text.split())
        if word_count > max_words:
            issues.append(f"block {i+1}: {word_count} words (max {max_words})")
    if issues:
        return {"name": "text_length", "passed": False,
                "details": "; ".join(issues)}
    return {"name": "text_length", "passed": True, "details": "OK"}


def validate_universe_reference(lesson: dict, universe: str) -> dict:
    """Check that the child's universe is referenced in the lesson text."""
    all_text = ""
    for block in lesson.get("story_blocks", []):
        all_text += " " + block.get("text", "")
    for task in lesson.get("tasks", []):
        all_text += " " + task.get("question", "")

    universe_lower = universe.lower()
    found = universe_lower in all_text.lower()
    return {"name": "universe_reference", "passed": found,
            "details": f"'{universe}' {'found' if found else 'NOT found'} in lesson text"}


def validate_no_unsafe_content(lesson: dict) -> dict:
    """Check for unsafe content patterns."""
    unsafe_patterns = [
        r'\b(убить|убей|смерть|умереть|кровь|оружие|пистолет|нож)\b',
        r'\b(секс|порн|наркотик|алкоголь|водка|пиво)\b',
        r'\b(дурак|идиот|тупой|урод)\b',
    ]
    all_text = ""
    for block in lesson.get("story_blocks", []):
        all_text += " " + block.get("text", "")
    for task in lesson.get("tasks", []):
        all_text += " " + task.get("question", "")
        for opt in task.get("options", []):
            all_text += " " + str(opt)

    found = []
    for pattern in unsafe_patterns:
        matches = re.findall(pattern, all_text.lower())
        if matches:
            found.extend(matches)

    if found:
        return {"name": "content_safety", "passed": False,
                "details": f"Unsafe words: {found}"}
    return {"name": "content_safety", "passed": True, "details": "OK"}


def validate_task_diversity(lesson: dict) -> dict:
    """Check that tasks have at least 2 different types."""
    types = set()
    for task in lesson.get("tasks", []):
        t = task.get("type", "")
        if t:
            types.add(t)
    passed = len(types) >= 2
    return {"name": "task_diversity", "passed": passed,
            "details": f"{len(types)} unique types: {types}"}


def run_all_validators(lesson: dict, test_case: dict) -> list[dict]:
    """Run all validators on a lesson and return list of results."""
    results = [
        validate_json_structure(lesson),
        validate_task_count(lesson, test_case.get("expected", {}).get("min_tasks", 5)),
        validate_story_block_count(lesson, test_case.get("expected", {}).get("min_story_blocks", 3)),
        validate_task_types(lesson),
        validate_quiz_answers(lesson),
        validate_no_unsafe_content(lesson),
        validate_task_diversity(lesson),
        validate_text_length(lesson, test_case.get("grade", 1)),
    ]
    if test_case.get("expected", {}).get("math_check"):
        results.append(validate_math_correctness(lesson))
    if test_case.get("expected", {}).get("universe_in_text"):
        results.append(validate_universe_reference(lesson, test_case.get("universe", "")))

    return results


def deterministic_score(results: list[dict]) -> float:
    """Calculate overall deterministic score (0.0 - 1.0)."""
    if not results:
        return 0.0
    passed = sum(1 for r in results if r["passed"])
    return passed / len(results)
