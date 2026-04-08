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


def test_replace_to_active_target_is_auto_clear() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            replaced_by="taxon:birds:000002",
        ),
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major updated",
        ),
    ]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    replace_decision = [item for item in decisions if item.event.event_type == "replace"][0]

    assert replace_decision.decision_status == "auto_clear"
    assert replace_decision.decision_reason == "weighted_transition_clear"


def test_transition_decisions_always_include_source_delta() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            authority_taxonomy_profile={
                "source_taxon_id": "12716",
                "name": "Parus major",
                "is_active": True,
                "provisional": False,
                "parent_id": "1260",
                "ancestor_ids": ["1", "2", "1260"],
                "taxon_changes_count": 3,
                "current_synonymous_taxon_ids": ["12716"],
            },
        )
    ]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:000002"],
            authority_taxonomy_profile={
                "source_taxon_id": "12716",
                "name": "Parus major",
                "is_active": False,
                "provisional": False,
                "parent_id": "1260",
                "ancestor_ids": ["1", "2", "1260"],
                "taxon_changes_count": 4,
                "current_synonymous_taxon_ids": ["12716", "99999"],
            },
        ),
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus minor",
            derived_from="taxon:birds:000001",
            authority_taxonomy_profile={
                "source_taxon_id": "99999",
                "ancestor_ids": ["1", "2", "1260", "12716"],
                "is_active": True,
                "provisional": False,
            },
        ),
    ]
    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    split_decision = [item for item in decisions if item.event.event_type == "split"][0]

    payload = split_decision.source_delta.to_payload()
    assert payload["source_taxon_id_previous"] == "12716"
    assert payload["source_taxon_id_current"] == "12716"
    assert payload["taxon_changes_count_previous"] == 3
    assert payload["taxon_changes_count_current"] == 4
    assert payload["current_synonymous_taxon_ids_current"] == ["12716", "99999"]


def test_decision_matrix_is_deterministic() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        )
    ]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:000999"],
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        ),
        _taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major duplicate",
            authority_source="inaturalist",
            external_source_mappings=[("inaturalist", "12716")],
        ),
    ]

    first = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    second = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )

    first_signature = [
        (
            item.event.event_id,
            item.decision_status,
            item.decision_reason,
            item.signal_breakdown.to_payload(),
            item.source_delta.to_payload(),
        )
        for item in first
    ]
    second_signature = [
        (
            item.event.event_id,
            item.decision_status,
            item.decision_reason,
            item.signal_breakdown.to_payload(),
            item.source_delta.to_payload(),
        )
        for item in second
    ]
    assert first_signature == second_signature


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
    replaced_by: str | None = None,
    authority_taxonomy_profile: dict[str, object] | None = None,
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
        replaced_by=replaced_by,
        derived_from=derived_from,
        authority_taxonomy_profile=authority_taxonomy_profile or {},
    )
