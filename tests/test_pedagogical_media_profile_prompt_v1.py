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


def test_prompt_lists_post_answer_feedback_as_forbidden() -> None:
    # post_answer_feedback must appear explicitly in the forbidden fields section,
    # not as a field the model is asked to output.
    prompt = _build_prompt().lower()

    assert "post_answer_feedback" in prompt
    assert "forbidden" in prompt


# --- Sprint 3 hardening tests ---


def test_prompt_includes_output_skeleton() -> None:
    prompt = _build_prompt()

    assert "Output skeleton" in prompt
    assert "technical_profile" in prompt
    assert "observation_profile" in prompt
    assert "biological_profile_visible" in prompt
    assert "identification_profile" in prompt
    assert "pedagogical_profile" in prompt
    assert "group_specific_profile" in prompt


def test_prompt_includes_valid_raw_example() -> None:
    prompt = _build_prompt()

    assert "Valid raw output example" in prompt
    assert '"review_status": "valid"' in prompt
    assert '"group_specific_profile"' in prompt
    assert '"bird"' in prompt


def test_prompt_includes_failed_raw_example() -> None:
    prompt = _build_prompt()

    assert "Failed raw output example" in prompt
    assert '"review_status": "failed"' in prompt
    assert '"failure_reason"' in prompt


def test_prompt_says_raw_output_may_omit_scores() -> None:
    prompt = _build_prompt().lower()

    assert "raw ai output may omit scores" in prompt


def test_prompt_forbids_scores_in_ai_output() -> None:
    prompt = _build_prompt().lower()

    assert "do not output a scores block" in prompt


def test_prompt_forbids_selection_fields() -> None:
    prompt = _build_prompt().lower()

    assert "selected_for_quiz" in prompt
    assert "palier_1_core_eligible" in prompt
    assert "recommended_use" in prompt
    assert "runtime_ready" in prompt
    assert "playable" in prompt


def test_prompt_forbidden_fields_list_explicit() -> None:
    prompt = _build_prompt().lower()

    assert "forbidden fields" in prompt
    assert "scores" in prompt


def test_prompt_includes_bird_group_specific_rule() -> None:
    prompt = _build_prompt().lower()

    assert "if organism_group is bird" in prompt
    assert "group_specific_profile.bird is required" in prompt

