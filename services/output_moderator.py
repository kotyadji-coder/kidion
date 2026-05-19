"""
output_moderator.py — Post-generation moderation for AI responses.

Checks AI output for PII leaks, URLs, profanity, and dangerous content.
Returns cleaned text or a safe fallback if the response is unsafe.
"""

import re

from services.pii_scrubber import contains_pii, scrub_pii

_SAFE_FALLBACK = "Ой, мне нужно подумать получше. Давай поговорим о чём-нибудь другом! 😊"

# --- URL detection ---
_URL_PATTERN = re.compile(r'https?://[^\s]+|www\.[^\s]+', re.IGNORECASE)

# --- Russian profanity (mat) - common roots ---
_PROFANITY_ROOTS = re.compile(
    r'(?:^|\b|(?<=\s))'
    r'(?:'
    r'[хx][уyu][йеёяijye]|'
    r'[пp][иieё][зz3][дd]|'
    r'[бb][лl][яыaй]|'
    r'[еe][бb6][аaлтиоу]|'
    r'[сs][уyu][кk][аaиi]|'
    r'[мm][уyu][дd][аaоoиiлк]|'
    r'[дd][рp][оo0][чc][иiаa]|'
    r'[зz][аa][лl][уyu][пp]|'
    r'[гg][оo0][вv][нnh][оo0яа]|'
    r'[жzg][оo0][пp][аaуy]|'
    r'[шщ][лl][юy][хx]|'
    r'[пp][иi][дd][оo0][рp]|'
    r'[пp][еe][дd][иi][кk]|'
    r'[тt][вv][аa][рp][ьъ]|'
    r'[дd][еe][бb][иi][лl]|'
    r'[иi][дd][иi][оo0][тt]'
    r')',
    re.IGNORECASE
)

# --- Dangerous content patterns ---
_DANGEROUS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'(?:как|способ|инструкция)\s+(?:сделать|изготовить|собрать)\s+(?:бомбу|взрывчатку|оружие|яд|отраву)',
        r'(?:как|способ)\s+(?:убить|отравить|задушить)',
        r'(?:как|где)\s+(?:купить|достать)\s+(?:наркотик|оружие|пистолет)',
        r'(?:рецепт|состав|формула)\s+(?:взрывчатк|наркотик|яд|отрав)',
        r'(?:как|способ)\s+(?:покончить|совершить\s+суицид)',
    ]
]


def moderate_output(text: str) -> tuple[str, bool, list[str]]:
    """
    Check AI response for unsafe content.

    Returns:
        (final_text, was_modified, list_of_issues)
    """
    if not text:
        return text, False, []

    issues: list[str] = []

    # 1. Check for URLs (should never appear in child chat)
    if _URL_PATTERN.search(text):
        text = _URL_PATTERN.sub("[ссылка удалена]", text)
        issues.append("url_in_output")

    # 2. Check for PII leaks in response
    if contains_pii(text):
        text, pii_types = scrub_pii(text)
        issues.append(f"pii_leak:{','.join(pii_types)}")

    # 3. Check for profanity
    if _PROFANITY_ROOTS.search(text):
        # Replace entire response — partial cleanup of mat is unreliable
        return _SAFE_FALLBACK, True, ["profanity"]

    # 4. Check for dangerous content
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(text):
            return _SAFE_FALLBACK, True, ["dangerous_content"]

    was_modified = len(issues) > 0
    return text, was_modified, issues
