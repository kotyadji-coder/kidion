"""
pii_scrubber.py — Strip personally identifiable information before sending to external AI.

Regex-based PII detection for Russian and English text.
Replaces detected PII with [УДАЛЕНО] placeholder.
"""

import re

# Replacement token
_REDACTED = "[УДАЛЕНО]"

# --- Phone numbers ---
# Russian: +7, 8 followed by 10 digits (with optional separators)
_PHONE_RU = re.compile(
    r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
)
# International: +<country code> followed by digits
_PHONE_INTL = re.compile(r'\+\d{1,3}[\s\-]?\d[\d\s\-]{6,14}\d')
# Bare 10-11 digit sequences that look like phone numbers
_PHONE_BARE = re.compile(r'\b[78]\d{10}\b')

# --- Email ---
_EMAIL = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}')

# --- URLs ---
_URL = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)
_URL_WWW = re.compile(r'www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s]*', re.IGNORECASE)

# --- Russian street addresses ---
_ADDRESS_RU = re.compile(
    r'(?:ул\.|улица|пр\.|проспект|пер\.|переулок|бульвар|б-р|набережная|наб\.|шоссе|ш\.)'
    r'\s*[А-ЯЁа-яё\w\s\-\.]{2,30}'
    r'(?:,?\s*д\.?\s*\d+[а-яА-Я]?(?:\s*(?:корп?\.|к\.)\s*\d+)?'
    r'(?:\s*(?:кв?\.|квартира)\s*\d+)?)?',
    re.IGNORECASE
)

# --- School/institution names ---
_SCHOOL = re.compile(
    r'(?:школа|гимназия|лицей|детский сад|садик|колледж|техникум)'
    r'\s*(?:№|номер)?\s*\d+[а-яА-Я]?',
    re.IGNORECASE
)
_SCHOOL_NAMED = re.compile(
    r'(?:школа|гимназия|лицей)\s+(?:им\.|имени)\s+[А-ЯЁ][а-яё]+',
    re.IGNORECASE
)

# --- Russian passport / document numbers ---
_PASSPORT = re.compile(r'\b\d{2}\s?\d{2}\s?\d{6}\b')
_SNILS = re.compile(r'\b\d{3}-\d{3}-\d{3}\s?\d{2}\b')
_INN = re.compile(r'\b\d{10,12}\b')  # Only matches standalone 10-12 digit numbers

# --- Social media handles ---
_SOCIAL = re.compile(r'@[a-zA-Z0-9_]{3,30}\b')

# --- Russian full names (Фамилия Имя Отчество) ---
# Pattern: Capitalized word ending in common Russian surname suffixes
_SURNAME_SUFFIXES = (
    r'(?:ов|ова|ев|ева|ёв|ёва|ин|ина|ский|ская|цкий|цкая|ый|ая|ий|'
    r'ко|енко|юк|чук|ян|янц|дзе|швили|ашвили|идзе)'
)
_FULLNAME_RU = re.compile(
    r'\b[А-ЯЁ][а-яё]+' + _SURNAME_SUFFIXES +
    r'\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+ович|евич|ич|овна|евна|ична)?\b'
)

# Compile all patterns in order of priority
_PII_PATTERNS = [
    ("email", _EMAIL),
    ("phone_ru", _PHONE_RU),
    ("phone_intl", _PHONE_INTL),
    ("phone_bare", _PHONE_BARE),
    ("url", _URL),
    ("url_www", _URL_WWW),
    ("address", _ADDRESS_RU),
    ("school", _SCHOOL),
    ("school_named", _SCHOOL_NAMED),
    ("fullname", _FULLNAME_RU),
    ("passport", _PASSPORT),
    ("snils", _SNILS),
    ("social", _SOCIAL),
]


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """
    Remove PII from text.

    Returns:
        (cleaned_text, list_of_detected_categories)
        e.g., ("Привет, я учусь в [УДАЛЕНО]", ["school"])
    """
    if not text:
        return text, []

    detected: list[str] = []
    result = text

    for category, pattern in _PII_PATTERNS:
        if pattern.search(result):
            result = pattern.sub(_REDACTED, result)
            if category not in detected:
                detected.append(category)

    # Clean up multiple consecutive redactions
    result = re.sub(r'(\[УДАЛЕНО\]\s*){2,}', _REDACTED + ' ', result)

    return result.strip(), detected


def contains_pii(text: str) -> bool:
    """Quick check if text contains any PII patterns."""
    if not text:
        return False
    for _, pattern in _PII_PATTERNS:
        if pattern.search(text):
            return True
    return False
