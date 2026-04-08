from datetime import UTC, datetime

from database_core.domain.canonical_governance import derive_canonical_governance_decisions
from database_core.domain.models import CanonicalTaxon, ExternalMapping


def test_name_and_status_changes_are_auto_clear() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            status="active",
        )
    ]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major updated",
            status="deprecated",
        )
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    by_event_type = {item.event.event_type: item for item in decisions}

    assert by_event_type["name_update"].decision_status == "auto_clear"
    assert by_event_type["status_change"].decision_status == "auto_clear"


def test_split_with_missing_target_is_manual_reviewed() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:999999"],
        )
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    split_decision = [item for item in decisions if item.event.event_type == "split"][0]

    assert split_decision.decision_status == "manual_reviewed"
    assert split_decision.decision_reason == "ambiguous_transition_missing_target"


def test_split_with_consistent_lineage_is_auto_clear() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:000002"],
        ),
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus minor",
            derived_from="taxon:birds:000001",
        ),
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    split_decision = [item for item in decisions if item.event.event_type == "split"][0]

    assert split_decision.decision_status == "auto_clear"
    assert split_decision.decision_reason == "weighted_transition_clear"
    assert split_decision.signal_breakdown.score >= 3


def test_merge_to_provisional_target_is_manual_reviewed() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            merged_into="taxon:birds:000002",
        ),
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus aggregate",
            status="provisional",
        ),
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    merge_decision = [item for item in decisions if item.event.event_type == "merge"][0]

    assert merge_decision.decision_status == "manual_reviewed"
    assert merge_decision.decision_reason == "ambiguous_transition_target_provisional"


def test_mapping_conflict_with_clear_source_priority_is_auto_clear() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        ),
    ]
    current = previous + [
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major legacy",
            status="deprecated",
            authority_source="gbif",
            external_source_mappings=[("inaturalist", "12716")],
        )
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    conflict_decisions = [item for item in decisions if item.event.event_type == "mapping_conflict"]

    assert len(conflict_decisions) == 1
    assert conflict_decisions[0].event.canonical_taxon_id == "taxon:birds:000002"
    assert conflict_decisions[0].decision_status == "auto_clear"
    assert conflict_decisions[0].decision_reason == "deterministic_source_priority_resolution"


def test_mapping_conflict_with_tie_is_manual_reviewed() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        ),
    ]
    current = previous + [
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major duplicate",
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        )
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    conflict_decisions = [item for item in decisions if item.event.event_type == "mapping_conflict"]

    assert len(conflict_decisions) == 2
    assert {item.decision_status for item in conflict_decisions} == {"manual_reviewed"}
    assert {item.decision_reason for item in conflict_decisions} == {
        "ambiguous_source_mapping_conflict"
    }


def _taxon(
    *,
    canonical_taxon_id: str,
    name: str,
    status: str = "active",
    authority_source: str = "inaturalist",
    external_source_mappings: list[tuple[str, str]] | None = None,
    split_into: list[str] | None = None,
    merged_into: str | None = None,
    derived_from: str | None = None,
) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=canonical_taxon_id,
        accepted_scientific_name=name,
        canonical_rank="species",
        taxon_group="birds",
        taxon_status=status,
        authority_source=authority_source,
        display_slug=name.lower().replace(" ", "-"),
        synonyms=[],
        common_names=[],
        key_identification_features=[],
        source_enrichment_status="seeded",
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=source_name, external_id=external_id)
            for source_name, external_id in (external_source_mappings or [])
        ],
        external_similarity_hints=[],
        similar_taxa=[],
        similar_taxon_ids=[],
        split_into=split_into or [],
        merged_into=merged_into,
        replaced_by=None,
        derived_from=derived_from,
    )
