from __future__ import annotations

from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
    PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
    build_pedagogical_media_profile_prompt_v1,
)


def _build_prompt() -> str:
    return build_pedagogical_media_profile_prompt_v1(
        expected_scientific_name="Columba palumbus",
        common_names={"en": "Common Woodpigeon", "fr": "Pigeon ramier"},
        organism_group="bird",
        media_reference="https://example.test/media/123.jpg",
        source_metadata={"source": "inaturalist", "observation_id": "obs_123"},
        observation_context={"habitat": "woodland edge"},
        locale_notes="Prefer concise, controlled output vocabulary.",
    )


def test_prompt_includes_schema_and_prompt_versions() -> None:
    prompt = _build_prompt()

    assert "schema_version=pedagogical_media_profile.v1" in prompt
    assert f"prompt_version={PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION}" in prompt


def test_prompt_says_no_feedback() -> None:
    prompt = _build_prompt().lower()

    assert "do not generate feedback" in prompt


def test_prompt_says_no_taxon_override() -> None:
    prompt = _build_prompt().lower()

    assert "do not rename, override, or correct the provided taxon" in prompt


def test_prompt_says_system_computes_scores() -> None:
    prompt = _build_prompt().lower()

    assert "do not compute final numeric scores" in prompt
    assert "system computes" in prompt


def test_prompt_includes_evidence_type_enum() -> None:
    prompt = _build_prompt()

    assert "Allowed evidence_type values" in prompt
    assert "whole_organism" in prompt
    assert "feather" in prompt
    assert "burrow" in prompt


def test_prompt_includes_biological_visible_basis_rule() -> None:
    prompt = _build_prompt().lower()

    assert "if value is neither unknown nor not_applicable" in prompt
    assert "visible_basis must be non-empty" in prompt


def test_prompt_includes_indirect_evidence_rule() -> None:
    prompt = _build_prompt().lower()

    assert "for indirect evidence types feather, egg, nest, track, scat, burrow" in prompt
    assert "subject_presence=indirect" in prompt


def test_prompt_does_not_include_post_answer_feedback_field_name() -> None:
    prompt = _build_prompt()

    assert "post_answer_feedback" not in prompt
