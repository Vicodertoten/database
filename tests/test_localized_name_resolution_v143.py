from __future__ import annotations

from database_core.enrichment.localized_names import (
    NameEvidence,
    RuntimeTaxon,
    build_localized_name_apply_plan,
    normalize_compare_text,
    resolve_localized_name_decision,
)


def _taxon(existing: dict[str, list[str]] | None = None, *, active: bool = True) -> RuntimeTaxon:
    return RuntimeTaxon(
        taxon_kind="canonical_taxon",
        taxon_id="taxon:birds:1",
        scientific_name="Vulpes vulpes",
        existing_names=existing or {},
        source_taxon_id="42069",
        is_active=active,
    )


def _evidence(
    value: str, *, method: str = "taxa_locale", source: str = "inaturalist"
) -> NameEvidence:
    confidence = "high" if method == "taxa_locale" else "medium_high"
    if source in {"wikipedia", "wikidata"}:
        confidence = "medium"
    if method == "alias":
        confidence = "low"
    return NameEvidence(
        taxon_kind="canonical_taxon",
        taxon_id="taxon:birds:1",
        scientific_name="Vulpes vulpes",
        locale="fr",
        value=value,
        source=source,
        method=method,
        confidence=confidence,  # type: ignore[arg-type]
    )


def test_normalization_compare_is_accent_case_hyphen_insensitive() -> None:
    assert normalize_compare_text("Écureuil-roux ") == normalize_compare_text("ecureuil roux")


def test_empty_field_inaturalist_preferred_auto_accepts() -> None:
    decision = resolve_localized_name_decision(_taxon(), "fr", [_evidence("Renard roux")])
    assert decision.decision == "auto_accept"
    assert decision.reason == "inaturalist_taxa_locale_empty_field"


def test_same_value_does_not_write() -> None:
    decision = resolve_localized_name_decision(
        _taxon({"fr": ["Renard roux"]}), "fr", [_evidence("renard-roux")]
    )
    assert decision.decision == "same_value"


def test_existing_different_inaturalist_preferred_overrides() -> None:
    decision = resolve_localized_name_decision(
        _taxon({"fr": ["Ancien nom"]}), "fr", [_evidence("Renard roux")]
    )
    assert decision.decision == "auto_accept"
    assert decision.reason == "inaturalist_preferred_override_existing_value"


def test_existing_different_inaturalist_all_names_goes_to_review() -> None:
    decision = resolve_localized_name_decision(
        _taxon({"fr": ["Ancien nom"]}), "fr", [_evidence("Renard roux", method="all_names")]
    )
    assert decision.decision == "needs_review"
    assert decision.reason == "existing_value_conflict_inaturalist_all_names"


def test_existing_different_wikimedia_goes_to_review() -> None:
    decision = resolve_localized_name_decision(
        _taxon({"fr": ["Ancien nom"]}),
        "fr",
        [
            _evidence(
                "Renard roux", method="langlink_from_inaturalist_wikipedia_url", source="wikipedia"
            )
        ],
    )
    assert decision.decision == "needs_review"
    assert decision.reason == "existing_value_conflict_wikimedia"


def test_missing_required_locale_goes_to_review() -> None:
    decision = resolve_localized_name_decision(_taxon(), "fr", [])
    assert decision.decision == "needs_review"
    assert decision.reason == "missing_required_locale"


def test_missing_optional_nl_is_non_blocking() -> None:
    decision = resolve_localized_name_decision(_taxon(), "nl", [])
    assert decision.decision == "skip_optional_missing"
    assert decision.reason == "optional_locale_missing"


def test_scientific_fallback_never_auto_accepts() -> None:
    decision = resolve_localized_name_decision(_taxon(), "fr", [_evidence("Vulpes vulpes")])
    assert decision.decision == "needs_review"
    assert decision.reason == "scientific_fallback"


def test_inactive_taxon_goes_to_review() -> None:
    decision = resolve_localized_name_decision(
        _taxon(active=False), "fr", [_evidence("Renard roux")]
    )
    assert decision.decision == "needs_review"
    assert decision.reason == "taxon_inactive"


def test_wikidata_alias_is_evidence_only() -> None:
    decision = resolve_localized_name_decision(
        _taxon(), "fr", [_evidence("Renard", method="alias", source="wikidata")]
    )
    assert decision.decision == "needs_review"
    assert decision.reason == "missing_required_locale"


def test_source_priority_keeps_inaturalist_and_alternative_wikimedia() -> None:
    decision = resolve_localized_name_decision(
        _taxon(),
        "fr",
        [
            _evidence(
                "Renard roux", method="langlink_from_inaturalist_wikipedia_url", source="wikipedia"
            ),
            _evidence("Renard commun"),
        ],
    )
    assert decision.decision == "auto_accept"
    assert decision.chosen_value == "Renard commun"
    assert decision.alternatives[0].source == "wikipedia"


def test_apply_plan_hash_is_stable_across_rebuilds() -> None:
    first = build_localized_name_apply_plan()
    second = build_localized_name_apply_plan()
    assert first.plan_hash == second.plan_hash
    assert (
        first.metrics["safe_ready_target_count_from_plan"]
        == second.metrics["safe_ready_target_count_from_plan"]
    )
