"""Tests for worksheet generation service."""

import os
import sys
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWorksheetModels:
    def test_worksheet_tasks_model(self):
        from services.worksheet.models import WorksheetTasks
        data = {
            "tasks": [
                {"type": "coloring", "instruction": "Раскрась", "prompt_text": "Что видишь?", "line_count": 2},
                {"type": "matching", "instruction": "Соедини",
                 "left_column": ["A", "B", "C", "D"], "right_column": ["1", "2", "3", "4"]},
                {"type": "fill_blanks", "instruction": "Вставь",
                 "text_with_blanks": "Текст с ____.", "correct": ["ответ"]},
                {"type": "odd_one_out", "instruction": "Найди лишнее",
                 "items": ["a", "b", "c", "d"]},
            ]
        }
        result = WorksheetTasks(**data)
        assert len(result.tasks) == 4
        assert result.tasks[0].type == "coloring"

    def test_cipher_activity_model(self):
        from services.worksheet.models import CipherActivity
        data = {
            "type": "cipher",
            "story": "История",
            "title": "Шифровка",
            "instruction": "Расшифруй",
            "cipher_key": {"5": "П", "8": "Р"},
            "encoded_lines": ["2+3 4+4", "1+2 6+6"],
            "fun_answer_hint": "Подсказка",
        }
        result = CipherActivity(**data)
        assert result.type == "cipher"
        assert len(result.cipher_key) == 2

    def test_cafe_activity_model(self):
        from services.worksheet.models import CafeActivity
        data = {
            "type": "cafe",
            "story": "История",
            "title": "Кафе",
            "cafe_name": "Кафе тест",
            "menu": [
                {"name": "Блин", "price": 10, "emoji": "🥞"},
                {"name": "Чай", "price": 5, "emoji": "☕"},
                {"name": "Сок", "price": 7, "emoji": "🧃"},
                {"name": "Пирог", "price": 15, "emoji": "🥧"},
                {"name": "Каша", "price": 8, "emoji": "🥣"},
            ],
            "tasks": [
                {"question": "Сколько за блин?", "answer_lines": 1},
                {"question": "Сколько за чай?", "answer_lines": 1},
                {"question": "Сколько за сок?", "answer_lines": 1},
            ],
            "budget_task": "Бюджет:",
            "budget_amount": 50,
        }
        result = CafeActivity(**data)
        assert result.cafe_name == "Кафе тест"

    def test_subject_task_pools(self):
        from services.worksheet.models import SUBJECT_TASK_POOLS
        assert "math" in SUBJECT_TASK_POOLS
        assert "russian" in SUBJECT_TASK_POOLS
        assert "world" in SUBJECT_TASK_POOLS
        assert "matching" in SUBJECT_TASK_POOLS["math"]


class TestWorksheetGrids:
    def test_word_search_grid(self):
        from services.worksheet.grids import build_word_search_grid
        grid = build_word_search_grid(["КОТ", "ДОМ"], grid_size=8)
        assert len(grid) == 8
        assert len(grid[0]) == 8
        # Every cell should be filled
        for row in grid:
            for cell in row:
                assert cell != ""

    def test_crossword_grid(self):
        from services.worksheet.grids import build_crossword_grid
        result = build_crossword_grid(["КОТ", "ТОМ"], ["Животное", "Имя"])
        assert "grid" in result
        assert "across" in result
        assert "down" in result
        assert result["grid_rows"] > 0
        assert result["grid_cols"] > 0


class TestWorksheetPrompts:
    def test_build_child_context(self):
        from services.worksheet.prompts import build_child_context
        child = {
            "name": "Маша",
            "gender": "girl",
            "birth_date": "2018-05-15",
            "grade": 2,
            "universe": "Minecraft",
            "interests": '["рисование", "динозавры"]',
        }
        ctx = build_child_context(child)
        assert "девочка" in ctx
        assert "Minecraft" in ctx
        assert "рисование" in ctx

    def test_get_worksheet_prompt(self):
        from services.worksheet.prompts import get_worksheet_prompt
        child = {
            "name": "Петя",
            "gender": "boy",
            "birth_date": "2017-03-10",
            "grade": 3,
            "universe": "Roblox",
            "interests": None,
        }
        prompt = get_worksheet_prompt(child, "Сложение", "math")
        assert "Математика" in prompt
        assert "Сложение" in prompt

    def test_pick_activity_type(self):
        from services.worksheet.prompts import pick_activity_type
        # Math should return cafe, shop, or cipher
        for _ in range(20):
            at = pick_activity_type("math")
            assert at in ("cafe", "shop", "cipher")
        # Russian should always return cipher
        assert pick_activity_type("russian") == "cipher"


class TestWorksheetGenerator:
    def test_stub_worksheet_tasks(self):
        from services.worksheet.generator import _stub_worksheet_tasks
        for subject in ["math", "russian", "world"]:
            result = _stub_worksheet_tasks(subject)
            assert "tasks" in result
            assert len(result["tasks"]) == 4
            assert result["tasks"][0]["type"] == "coloring"

    def test_stub_activity(self):
        from services.worksheet.generator import _stub_activity
        for at in ["cafe", "shop", "cipher"]:
            result = _stub_activity(at)
            assert result["type"] == at
            assert "story" in result
            assert "title" in result

    def test_generate_worksheet_stub_mode(self):
        """In stub mode (no GOOGLE_CLOUD_PROJECT), should return a URL."""
        # Ensure stub mode
        old = os.environ.get("GOOGLE_CLOUD_PROJECT")
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        try:
            from services.worksheet.generator import generate_worksheet
            child = {
                "id": 999,
                "name": "Тест",
                "gender": "boy",
                "birth_date": "2018-01-01",
                "grade": 1,
                "universe": "Тестовый мир",
                "interests": None,
            }
            # Regular worksheet (lesson 1-4)
            url = generate_worksheet(child, "Сложение", "math", 1, "http://testserver")
            assert url is not None
            assert "worksheet.html" in url
            assert "testserver" in url

            # Activity worksheet (lesson 5)
            url5 = generate_worksheet(child, "Сложение", "math", 5, "http://testserver")
            assert url5 is not None
            assert "worksheet.html" in url5
        finally:
            if old:
                os.environ["GOOGLE_CLOUD_PROJECT"] = old

    def test_generate_batch_print_html(self):
        from services.worksheet.generator import generate_batch_print_html
        worksheets = [
            {"lesson_number": 1, "worksheet_url": "/content/abc_worksheet.html", "topic_title": "Сложение"},
            {"lesson_number": 2, "worksheet_url": "/content/def_worksheet.html", "topic_title": "Вычитание"},
        ]
        html = generate_batch_print_html(worksheets)
        assert "batch-page" in html
        assert "/content/abc_worksheet.html" in html
        assert "/content/def_worksheet.html" in html
        assert "2 шт." in html


class TestDBMigration:
    def test_worksheet_url_column_exists(self):
        """After init_db, lessons table should have worksheet_url column."""
        import tempfile
        from db import init_db, get_connection
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            init_db(db_path)
            conn = get_connection(db_path)
            cols = [row[1] for row in conn.execute("PRAGMA table_info(lessons)").fetchall()]
            assert "worksheet_url" in cols
        finally:
            os.unlink(db_path)
