from __future__ import annotations

from collections import defaultdict

from database_core.enrichment.localized_names.models import NameDecision, NameEvidence, RuntimeTaxon
from database_core.enrichment.localized_names.normalization import (
    OPTIONAL_LOCALES,
    REQUIRED_LOCALES,
    first_name,
    is_internal_placeholder,
    is_scientific_fallback,
    names_equivalent,
    normalize_localized_name_for_compare,
)

SOURCE_RANK = {
    ("inaturalist", "taxa_locale"): 0,
    ("inaturalist", "all_names"): 1,
    ("wikipedia", "langlink_from_inaturalist_wikipedia_url"): 2,
    ("wikidata", "sitelink_title"): 3,
    ("wikidata", "label"): 4,
    ("wikidata", "alias"): 9,
    ("commons", "metadata"): 10,
}

DISPLAYABLE_DECISIONS = {"auto_accept", "same_value"}


def is_runtime_relevant_taxon(taxon: RuntimeTaxon) -> bool:
    return bool(taxon.runtime_relevant and taxon.taxon_id and taxon.scientific_name)


def _candidate_rank(evidence: NameEvidence) -> tuple[int, str]:
    return (SOURCE_RANK.get((evidence.source, evidence.method), 99), evidence.value)


def _is_preferred_inaturalist(evidence: NameEvidence) -> bool:
    return (
        evidence.source == "inaturalist"
        and evidence.method == "taxa_locale"
        and evidence.confidence == "high"
    )


def _is_inaturalist_all_names(evidence: NameEvidence) -> bool:
    return evidence.source == "inaturalist" and evidence.method == "all_names"


def _is_wikimedia(evidence: NameEvidence) -> bool:
    return evidence.source in {"wikipedia", "wikidata"}


def _is_evidence_only(evidence: NameEvidence) -> bool:
    if str(evidence.raw_ref.get("locale", evidence.locale)).lower() == "und":
        return True
    if evidence.confidence == "low":
        return True
    if evidence.source == "wikidata" and evidence.method == "alias":
        return True
    if evidence.source == "commons":
        return True
    return False


def resolve_localized_name_decision(
    taxon: RuntimeTaxon,
    locale: str,
    evidences: list[NameEvidence],
    *,
    allow_scientific_fallback_for_missing_common_name: bool = False,
) -> NameDecision:
    existing_value = first_name(taxon.existing_names, locale) or None
    locale_evidence = [
        item for item in evidences if item.taxon_id == taxon.taxon_id and item.locale == locale
    ]
    usable = [
        item for item in locale_evidence if item.value.strip() and not _is_evidence_only(item)
    ]
    usable = sorted(usable, key=_candidate_rank)
    evidence_tuple = tuple(locale_evidence)

    if not is_runtime_relevant_taxon(taxon):
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "needs_review",
            None,
            "not_runtime_relevant",
            None,
            None,
            evidence_tuple,
        )

    if taxon.is_active is False:
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "needs_review",
            None,
            "taxon_inactive",
            None,
            None,
            evidence_tuple,
        )

    if existing_value and is_internal_placeholder(existing_value):
        existing_value = None

    if existing_value and is_scientific_fallback(existing_value, taxon.scientific_name):
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "needs_review",
            None,
            "scientific_fallback",
            None,
            None,
            evidence_tuple,
        )

    chosen = usable[0] if usable else None
    alternatives = tuple(usable[1:])

    if chosen and is_scientific_fallback(chosen.value, taxon.scientific_name):
        if not allow_scientific_fallback_for_missing_common_name:
            return NameDecision(
                taxon.taxon_kind,
                taxon.taxon_id,
                taxon.scientific_name,
                locale,
                existing_value,
                "needs_review" if locale in REQUIRED_LOCALES else "skip_optional_missing",
                None,
                "scientific_fallback",
                chosen.source_identity,
                chosen.value,
                evidence_tuple,
                alternatives,
            )

    if chosen and existing_value and names_equivalent(existing_value, chosen.value):
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "same_value",
            existing_value,
            "same_value",
            chosen.source_identity,
            chosen.value,
            evidence_tuple,
            alternatives,
        )

    if chosen and not existing_value:
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "auto_accept",
            chosen.value,
            f"{chosen.source}_{chosen.method}_empty_field",
            chosen.source_identity,
            chosen.value,
            evidence_tuple,
            alternatives,
        )

    if chosen and existing_value and not names_equivalent(existing_value, chosen.value):
        if _is_preferred_inaturalist(chosen):
            return NameDecision(
                taxon.taxon_kind,
                taxon.taxon_id,
                taxon.scientific_name,
                locale,
                existing_value,
                "auto_accept",
                chosen.value,
                "inaturalist_preferred_override_existing_value",
                chosen.source_identity,
                chosen.value,
                evidence_tuple,
                alternatives,
            )
        reason = "existing_value_conflict"
        if _is_inaturalist_all_names(chosen):
            reason = "existing_value_conflict_inaturalist_all_names"
        elif _is_wikimedia(chosen):
            reason = "existing_value_conflict_wikimedia"
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "needs_review",
            None,
            reason,
            chosen.source_identity,
            chosen.value,
            evidence_tuple,
            alternatives,
        )

    if existing_value:
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "same_value",
            existing_value,
            "existing_value_retained",
            "manual_or_curated_existing",
            existing_value,
            evidence_tuple,
        )

    evidence_only = [item for item in locale_evidence if _is_evidence_only(item)]
    if evidence_only and locale not in REQUIRED_LOCALES:
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "evidence_only",
            None,
            "locale_und_evidence_only",
            evidence_only[0].source_identity,
            evidence_only[0].value,
            evidence_tuple,
        )

    if locale in OPTIONAL_LOCALES:
        return NameDecision(
            taxon.taxon_kind,
            taxon.taxon_id,
            taxon.scientific_name,
            locale,
            existing_value,
            "skip_optional_missing",
            None,
            "optional_locale_missing",
            None,
            None,
            evidence_tuple,
        )

    return NameDecision(
        taxon.taxon_kind,
        taxon.taxon_id,
        taxon.scientific_name,
        locale,
        existing_value,
        "needs_review",
        None,
        "missing_required_locale",
        None,
        None,
        evidence_tuple,
    )


def resolve_taxa(taxa: list[RuntimeTaxon], evidences: list[NameEvidence]) -> list[NameDecision]:
    by_taxon: dict[str, list[NameEvidence]] = defaultdict(list)
    for evidence in evidences:
        by_taxon[evidence.taxon_id].append(evidence)

    decisions: list[NameDecision] = []
    for taxon in sorted(taxa, key=lambda item: (item.taxon_kind, item.taxon_id)):
        for locale in (*REQUIRED_LOCALES, *OPTIONAL_LOCALES):
            decisions.append(
                resolve_localized_name_decision(taxon, locale, by_taxon[taxon.taxon_id])
            )
    return decisions


def decision_is_displayable(decision: NameDecision) -> bool:
    return decision.decision in DISPLAYABLE_DECISIONS and bool(decision.chosen_value)


def normalized_decision_value(decision: NameDecision) -> str:
    return normalize_localized_name_for_compare(decision.chosen_value or "")
