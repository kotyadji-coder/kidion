"""Pydantic models for worksheet task mechanics and activities."""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


# ── UNIVERSAL TASKS (all subjects) ──────────────────────────────────────────

class ColoringTask(BaseModel):
    type: Literal["coloring"]
    instruction: str = Field(description="Short instruction (max 60 chars)")
    prompt_text: str = Field(description="Task related to the coloring image")
    line_count: int = Field(default=3, ge=2, le=4)


class MatchingTask(BaseModel):
    type: Literal["matching"]
    instruction: str
    left_column: list[str] = Field(min_length=4, max_length=4)
    right_column: list[str] = Field(min_length=4, max_length=4)


class FillBlanksTask(BaseModel):
    type: Literal["fill_blanks"]
    instruction: str
    text_with_blanks: str = Field(description="Text with ____ for blanks")
    correct: list[str] = Field(description="Correct answers in order")


class SortingTableTask(BaseModel):
    type: Literal["sorting_table"]
    instruction: str
    column_headers: list[str] = Field(min_length=2, max_length=2)
    word_bank: list[str] = Field(min_length=4, max_length=8)


class OddOneOutTask(BaseModel):
    type: Literal["odd_one_out"]
    instruction: str
    items: list[str] = Field(min_length=4, max_length=4)


# ── MATH TASKS ──────────────────────────────────────────────────────────────

class GridMazeTask(BaseModel):
    type: Literal["grid_maze"]
    instruction: str
    grid_size: Literal[4] = 4
    cells: list[str] = Field(min_length=16, max_length=16)
    correct_path: list[int]


class NumberPyramidTask(BaseModel):
    type: Literal["number_pyramid"]
    instruction: str
    rows: list[list[str]]


class MagicSquareTask(BaseModel):
    type: Literal["magic_square"]
    instruction: str
    grid: list[list[str]]
    target_sum: int


class ComparisonChainTask(BaseModel):
    type: Literal["comparison_chain"]
    instruction: str
    pairs: list[list[str]] = Field(min_length=3, max_length=6)


class ExpressionBuilderTask(BaseModel):
    type: Literal["expression_builder"]
    instruction: str
    equations: list[str] = Field(min_length=3, max_length=4)


class NumberSequenceTask(BaseModel):
    type: Literal["number_sequence"]
    instruction: str
    sequences: list[list[str]] = Field(min_length=2, max_length=3)


# ── RUSSIAN LANGUAGE TASKS ──────────────────────────────────────────────────

class AnagramTask(BaseModel):
    type: Literal["anagram"]
    instruction: str
    scrambled: str
    hint: str
    answer_length: int


class WordSearchTask(BaseModel):
    type: Literal["word_search"]
    instruction: str
    words: list[str] = Field(min_length=3, max_length=5)
    grid_size: Literal[8] = 8


class SyllableBuilderTask(BaseModel):
    type: Literal["syllable_builder"]
    instruction: str
    syllable_groups: list[list[str]] = Field(min_length=3, max_length=4)


class SentenceOrderTask(BaseModel):
    type: Literal["sentence_order"]
    instruction: str
    scrambled_sentences: list[list[str]] = Field(min_length=2, max_length=3)


class WordChainTask(BaseModel):
    type: Literal["word_chain"]
    instruction: str
    given_words: list[str] = Field(min_length=2, max_length=3)
    chain_length: int = Field(ge=4, le=6)


class MissingVowelsTask(BaseModel):
    type: Literal["missing_vowels"]
    instruction: str
    words_with_gaps: list[str] = Field(min_length=4, max_length=6)


# ── ENGLISH LANGUAGE TASKS ──────────────────────────────────────────────────

class LetterUnscrambleTask(BaseModel):
    type: Literal["letter_unscramble"]
    instruction: str
    scrambled_words: list[str] = Field(min_length=3, max_length=5)
    hints: list[str]


class SentenceBuildTask(BaseModel):
    type: Literal["sentence_build"]
    instruction: str
    scrambled_sentences: list[list[str]] = Field(min_length=2, max_length=3)


class CrosswordMiniTask(BaseModel):
    type: Literal["crossword_mini"]
    instruction: str
    words: list[str] = Field(min_length=3, max_length=4)
    clues: list[str]


# ── SCIENCE TASKS ──────────────────────────────────────────────────────────

class SequenceOrderTask(BaseModel):
    type: Literal["sequence_order"]
    instruction: str
    items: list[str] = Field(min_length=4, max_length=6)


class TrueFalseFixTask(BaseModel):
    type: Literal["true_false_fix"]
    instruction: str
    statements: list[str] = Field(min_length=3, max_length=4)


class CauseEffectTask(BaseModel):
    type: Literal["cause_effect"]
    instruction: str
    causes: list[str] = Field(min_length=4, max_length=4)
    effects: list[str] = Field(min_length=4, max_length=4)


class RiddleBoxesTask(BaseModel):
    type: Literal["riddle_boxes"]
    instruction: str
    riddles: list[str] = Field(min_length=3, max_length=4)
    answer_lengths: list[int]


# ── UNION TYPE ──────────────────────────────────────────────────────────────

WorksheetTask = Union[
    ColoringTask, MatchingTask, FillBlanksTask, SortingTableTask, OddOneOutTask,
    GridMazeTask, NumberPyramidTask, MagicSquareTask, ComparisonChainTask,
    ExpressionBuilderTask, NumberSequenceTask,
    AnagramTask, WordSearchTask, SyllableBuilderTask, SentenceOrderTask,
    WordChainTask, MissingVowelsTask,
    LetterUnscrambleTask, SentenceBuildTask, CrosswordMiniTask,
    SequenceOrderTask, TrueFalseFixTask, CauseEffectTask, RiddleBoxesTask,
]


class WorksheetTasks(BaseModel):
    tasks: list[WorksheetTask] = Field(min_length=4, max_length=4)


# ── ACTIVITY MODELS ────────────────────────────────────────────────────────

class ActivityBase(BaseModel):
    story: str = Field(default="")
    title: str


class CipherActivity(ActivityBase):
    type: Literal["cipher"] = "cipher"
    instruction: str
    cipher_key: dict[str, str]
    encoded_lines: list[str] = Field(min_length=2, max_length=4)
    fun_answer_hint: str


class CafeMenuItem(BaseModel):
    name: str
    price: int
    emoji: str


class CafeTask(BaseModel):
    question: str
    answer_lines: int = Field(default=1, ge=1, le=3)


class CafeActivity(ActivityBase):
    type: Literal["cafe"] = "cafe"
    cafe_name: str
    menu: list[CafeMenuItem] = Field(min_length=5, max_length=8)
    tasks: list[CafeTask] = Field(min_length=3, max_length=5)
    budget_task: str
    budget_amount: int


class ShopItem(BaseModel):
    name: str
    price: int
    emoji: str


class ShopTask(BaseModel):
    question: str
    answer_lines: int = Field(default=1, ge=1, le=3)


class ShopActivity(ActivityBase):
    type: Literal["shop"] = "shop"
    shop_name: str
    items: list[ShopItem] = Field(min_length=5, max_length=8)
    tasks: list[ShopTask] = Field(min_length=3, max_length=5)
    shopping_list_task: str
    budget_amount: int


# ── SUBJECT TASK POOLS ──────────────────────────────────────────────────────

MATH_TASKS = [
    "matching", "fill_blanks", "sorting_table", "odd_one_out",
    "grid_maze", "number_pyramid", "magic_square", "comparison_chain",
    "expression_builder", "number_sequence",
]

RUSSIAN_TASKS = [
    "matching", "fill_blanks", "sorting_table", "odd_one_out",
    "anagram", "word_search", "syllable_builder", "sentence_order",
    "word_chain", "missing_vowels",
]

SCIENCE_TASKS = [
    "matching", "fill_blanks", "sorting_table", "odd_one_out",
    "word_search", "sequence_order", "true_false_fix", "cause_effect",
    "riddle_boxes",
]

SUBJECT_TASK_POOLS = {
    "math": MATH_TASKS,
    "russian": RUSSIAN_TASKS,
    "world": SCIENCE_TASKS,
}

# Maps kidion subject key to Russian name for prompts
SUBJECT_NAMES_RU = {
    "math": "Математика",
    "russian": "Русский язык",
    "world": "Окружающий мир",
}
