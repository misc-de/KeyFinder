"""Translations.

Source strings are English. Catalogs in keyfinder/lang/<code>.json map the
English text to its translation; a missing entry falls back to English. The
language is the user's choice in the app menu, by default the system language.
"""

import json
import os
from pathlib import Path

LANGUAGES = {"en": "English", "de": "Deutsch", "es": "Español", "fr": "Français"}
DEFAULT = "en"
LANG_DIR = Path(__file__).resolve().parent / "lang"

_catalog = {}
_code = DEFAULT


def system_language():
    """First supported language from the usual locale variables, else English."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if not value or value in ("C", "POSIX") or value.startswith("C."):
            continue
        for part in value.split(":"):
            code = part[:2].lower()
            if code in LANGUAGES:
                return code
        return DEFAULT
    return DEFAULT


def load_catalog(code):
    if code == DEFAULT:
        return {}
    try:
        return json.loads((LANG_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def setup(choice="system"):
    """choice: "system" or a code from LANGUAGES."""
    global _catalog, _code
    code = system_language() if choice in (None, "", "system") else choice
    if code not in LANGUAGES:
        code = DEFAULT
    _code = code
    _catalog = load_catalog(code)
    return code


def current():
    return _code


def _(text):
    return _catalog.get(text, text)


def number(value, digits=1):
    """Decimal number in the style of the current language (2.3 / 2,3)."""
    text = f"{value:.{digits}f}"
    return text if _code == "en" else text.replace(".", ",")
