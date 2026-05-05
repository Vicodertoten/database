from __future__ import annotations

from scripts.enrich_taxon_localized_names_multisource_v1 import (
    is_empty_name,
    is_internal_placeholder,
    is_scientific_name_as_common_name,
    looks_like_latin_binomial,
    names_equivalent,
    normalize_compare_text,
    normalize_whitespace,
)


def test_normalization_helpers() -> None:
    assert normalize_whitespace("  Pigeon   ramier ") == "Pigeon ramier"
    assert normalize_compare_text("Pigeon   ramier") == normalize_compare_text("pigeon ramier")
    assert is_empty_name("   ")
    assert names_equivalent("Pigeon  ramier", "pigeon ramier")


def test_latin_binomial_detection() -> None:
    assert looks_like_latin_binomial("Parus major")
    assert not looks_like_latin_binomial("Mésange charbonnière")


def test_scientific_name_as_common_name_detection() -> None:
    assert is_scientific_name_as_common_name("Parus major", "Parus major")
    assert not is_scientific_name_as_common_name("Mésange charbonnière", "Parus major")


def test_placeholder_detection() -> None:
    assert is_internal_placeholder("placeholder")
    assert is_internal_placeholder("Nom", "provisional seed")
    assert not is_internal_placeholder("Pigeon ramier")
