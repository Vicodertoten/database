from __future__ import annotations

import re
import unicodedata

REQUIRED_LOCALES = ("fr", "en")
OPTIONAL_LOCALES = ("nl",)
ALL_LOCALES = REQUIRED_LOCALES + OPTIONAL_LOCALES

PLACEHOLDER_HINTS = ("placeholder", "provisional", "seed_fr_then_human_review")
LATIN_BINOMIAL_RE = re.compile(r"^[A-Z][a-z]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?$")


def normalize_whitespace(value: str) -> str:
    return " ".join(str(value).strip().split())


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_localized_name_for_compare(value: str) -> str:
    text = strip_accents(normalize_whitespace(value)).casefold()
    text = text.replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_compare_text(value: str) -> str:
    return normalize_localized_name_for_compare(value)


def is_empty_name(value: str) -> bool:
    return not normalize_whitespace(value)


def names_equivalent(a: str, b: str) -> bool:
    return normalize_localized_name_for_compare(a) == normalize_localized_name_for_compare(b)


def looks_like_latin_binomial(value: str) -> bool:
    return bool(LATIN_BINOMIAL_RE.match(normalize_whitespace(value)))


def is_scientific_name_as_common_name(value: str, scientific_name: str) -> bool:
    return names_equivalent(value, scientific_name)


def is_scientific_fallback(value: str, scientific_name: str) -> bool:
    cleaned = normalize_whitespace(value)
    if not cleaned:
        return False
    if is_scientific_name_as_common_name(cleaned, scientific_name):
        return True
    if not looks_like_latin_binomial(cleaned):
        return False
    value_genus = cleaned.split()[0]
    scientific_genus = normalize_whitespace(scientific_name).split()[0]
    return value_genus == scientific_genus


def is_internal_placeholder(value: str, notes: str = "") -> bool:
    normalized_value = normalize_compare_text(value)
    normalized_notes = normalize_compare_text(notes)
    return any(hint in normalized_value or hint in normalized_notes for hint in PLACEHOLDER_HINTS)


def first_name(name_map: dict[str, object], locale: str) -> str:
    values = name_map.get(locale, []) if isinstance(name_map, dict) else []
    if not isinstance(values, list):
        return ""
    for value in values:
        if isinstance(value, str) and normalize_whitespace(value):
            return normalize_whitespace(value)
    return ""


def normalize_name_map(name_map: dict[str, object]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for locale in ALL_LOCALES:
        values = name_map.get(locale, []) if isinstance(name_map, dict) else []
        if not isinstance(values, list):
            values = []
        cleaned = [
            normalize_whitespace(str(value)) for value in values if normalize_whitespace(str(value))
        ]
        if cleaned:
            out[locale] = cleaned
    return out
