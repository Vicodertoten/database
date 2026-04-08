from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from database_core.domain.enums import (
    CanonicalEventType,
    CanonicalGovernanceDecisionStatus,
    SourceName,
    TaxonStatus,
)
from database_core.domain.models import CanonicalTaxon, CanonicalTaxonEvent

DecisionReason = Literal[
    "new_taxon_detected",
    "name_changed",
    "status_changed",
    "deterministic_transition",
    "deterministic_source_priority_resolution",
    "ambiguous_transition_missing_target",
    "ambiguous_transition_inconsistent_lineage",
    "ambiguous_transition_target_provisional",
    "ambiguous_source_mapping_conflict",
]

SOURCE_PRIORITY: dict[SourceName, int] = {
    SourceName.INATURALIST: 300,
    SourceName.GBIF: 200,
    SourceName.WIKIMEDIA_COMMONS: 100,
}


@dataclass(frozen=True)
class CanonicalGovernanceDecision:
    event: CanonicalTaxonEvent
    decision_status: CanonicalGovernanceDecisionStatus
    decision_reason: DecisionReason


def derive_canonical_governance_decisions(
    previous_taxa: list[CanonicalTaxon],
    current_taxa: list[CanonicalTaxon],
    *,
    effective_at: datetime,
) -> list[CanonicalGovernanceDecision]:
    previous_by_id = {item.canonical_taxon_id: item for item in previous_taxa}
    current_by_id = {item.canonical_taxon_id: item for item in current_taxa}
    decisions: list[CanonicalGovernanceDecision] = []

    for taxon in sorted(current_taxa, key=lambda item: item.canonical_taxon_id):
        previous = previous_by_id.get(taxon.canonical_taxon_id)
        if previous is None:
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.CREATE,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={
                            "accepted_scientific_name": taxon.accepted_scientific_name,
                            "taxon_status": taxon.taxon_status,
                        },
                        detail="create",
                    ),
                    decision_status=CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
                    decision_reason="new_taxon_detected",
                )
            )
            continue

        if previous.accepted_scientific_name != taxon.accepted_scientific_name:
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.NAME_UPDATE,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={
                            "previous_accepted_scientific_name": previous.accepted_scientific_name,
                            "current_accepted_scientific_name": taxon.accepted_scientific_name,
                        },
                        detail=f"name:{previous.accepted_scientific_name}->{taxon.accepted_scientific_name}",
                    ),
                    decision_status=CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
                    decision_reason="name_changed",
                )
            )

        if previous.taxon_status != taxon.taxon_status:
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.STATUS_CHANGE,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={
                            "previous_status": previous.taxon_status,
                            "current_status": taxon.taxon_status,
                        },
                        detail=f"status:{previous.taxon_status}->{taxon.taxon_status}",
                    ),
                    decision_status=CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
                    decision_reason="status_changed",
                )
            )

        previous_split_targets = set(previous.split_into)
        current_split_targets = set(taxon.split_into)
        for target_id in sorted(current_split_targets - previous_split_targets):
            decision_status, reason = _decision_for_transition_target(
                source_taxon=taxon,
                target_taxon_id=target_id,
                current_by_id=current_by_id,
                requires_derived_from=True,
            )
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.SPLIT,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={"target_canonical_taxon_id": target_id},
                        detail=f"split:{target_id}",
                    ),
                    decision_status=decision_status,
                    decision_reason=reason,
                )
            )

        if taxon.merged_into and taxon.merged_into != previous.merged_into:
            decision_status, reason = _decision_for_transition_target(
                source_taxon=taxon,
                target_taxon_id=taxon.merged_into,
                current_by_id=current_by_id,
                requires_derived_from=False,
            )
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.MERGE,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={"target_canonical_taxon_id": taxon.merged_into},
                        detail=f"merge:{taxon.merged_into}",
                    ),
                    decision_status=decision_status,
                    decision_reason=reason,
                )
            )

        if taxon.replaced_by and taxon.replaced_by != previous.replaced_by:
            decision_status, reason = _decision_for_transition_target(
                source_taxon=taxon,
                target_taxon_id=taxon.replaced_by,
                current_by_id=current_by_id,
                requires_derived_from=False,
            )
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.REPLACE,
                        source_name=str(taxon.authority_source),
                        effective_at=effective_at,
                        payload={"target_canonical_taxon_id": taxon.replaced_by},
                        detail=f"replace:{taxon.replaced_by}",
                    ),
                    decision_status=decision_status,
                    decision_reason=reason,
                )
                )

    decisions.extend(
        _derive_mapping_conflict_decisions(
            current_taxa=current_taxa,
            effective_at=effective_at,
        )
    )

    return sorted(decisions, key=lambda item: item.event.event_id)


def _decision_for_transition_target(
    *,
    source_taxon: CanonicalTaxon,
    target_taxon_id: str,
    current_by_id: dict[str, CanonicalTaxon],
    requires_derived_from: bool,
) -> tuple[CanonicalGovernanceDecisionStatus, DecisionReason]:
    target_taxon = current_by_id.get(target_taxon_id)
    if target_taxon is None:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_missing_target",
        )
    if requires_derived_from and target_taxon.derived_from != source_taxon.canonical_taxon_id:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_inconsistent_lineage",
        )
    if target_taxon.taxon_status == TaxonStatus.PROVISIONAL:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_target_provisional",
        )
    return (CanonicalGovernanceDecisionStatus.AUTO_CLEAR, "deterministic_transition")


def _build_event(
    *,
    canonical_taxon_id: str,
    event_type: CanonicalEventType,
    source_name: str,
    effective_at: datetime,
    payload: dict[str, object],
    detail: str,
) -> CanonicalTaxonEvent:
    token = _to_token(detail)
    return CanonicalTaxonEvent(
        event_id=f"event:{canonical_taxon_id}:{event_type}:{token}",
        event_type=event_type,
        canonical_taxon_id=canonical_taxon_id,
        source_name=source_name,
        effective_at=effective_at,
        payload=payload,
    )


def _to_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "na"


def _derive_mapping_conflict_decisions(
    *,
    current_taxa: list[CanonicalTaxon],
    effective_at: datetime,
) -> list[CanonicalGovernanceDecision]:
    by_source_external: dict[tuple[SourceName, str], list[CanonicalTaxon]] = {}
    for taxon in current_taxa:
        for mapping in taxon.external_source_mappings:
            key = (mapping.source_name, mapping.external_id.strip())
            by_source_external.setdefault(key, []).append(taxon)

    decisions: list[CanonicalGovernanceDecision] = []
    for key, candidates in sorted(
        by_source_external.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        source_name, external_id = key
        unique_candidates = sorted(
            {item.canonical_taxon_id: item for item in candidates}.values(),
            key=lambda item: item.canonical_taxon_id,
        )
        if len(unique_candidates) < 2:
            continue

        preferred_canonical_taxon_id = _resolve_mapping_conflict_preferred_taxon(
            source_name=source_name,
            candidates=unique_candidates,
        )
        payload_base = {
            "source_name": source_name,
            "external_id": external_id,
            "conflicting_canonical_taxon_ids": [
                item.canonical_taxon_id for item in unique_candidates
            ],
            "preferred_canonical_taxon_id": preferred_canonical_taxon_id,
        }

        if preferred_canonical_taxon_id is None:
            for taxon in unique_candidates:
                decisions.append(
                    CanonicalGovernanceDecision(
                        event=_build_event(
                            canonical_taxon_id=taxon.canonical_taxon_id,
                            event_type=CanonicalEventType.MAPPING_CONFLICT,
                            source_name=str(source_name),
                            effective_at=effective_at,
                            payload=payload_base,
                            detail=(
                                "mapping_conflict"
                                f":{source_name}:{external_id}:{taxon.canonical_taxon_id}:ambiguous"
                            ),
                        ),
                        decision_status=CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
                        decision_reason="ambiguous_source_mapping_conflict",
                    )
                )
            continue

        for taxon in unique_candidates:
            if taxon.canonical_taxon_id == preferred_canonical_taxon_id:
                continue
            decisions.append(
                CanonicalGovernanceDecision(
                    event=_build_event(
                        canonical_taxon_id=taxon.canonical_taxon_id,
                        event_type=CanonicalEventType.MAPPING_CONFLICT,
                        source_name=str(source_name),
                        effective_at=effective_at,
                        payload=payload_base,
                        detail=(
                            "mapping_conflict"
                            f":{source_name}:{external_id}:{taxon.canonical_taxon_id}:"
                            f"{preferred_canonical_taxon_id}:auto_clear"
                        ),
                    ),
                    decision_status=CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
                    decision_reason="deterministic_source_priority_resolution",
                )
            )

    return decisions


def _resolve_mapping_conflict_preferred_taxon(
    *,
    source_name: SourceName,
    candidates: list[CanonicalTaxon],
) -> str | None:
    scored_candidates = sorted(
        candidates,
        key=lambda item: (
            _mapping_conflict_score(source_name=source_name, taxon=item),
            item.canonical_taxon_id,
        ),
        reverse=True,
    )
    top_score = _mapping_conflict_score(source_name=source_name, taxon=scored_candidates[0])
    top_candidates = [
        item for item in scored_candidates
        if _mapping_conflict_score(source_name=source_name, taxon=item) == top_score
    ]
    if len(top_candidates) != 1:
        return None

    preferred = top_candidates[0]
    if preferred.authority_source != source_name:
        return None
    if preferred.taxon_status != TaxonStatus.ACTIVE:
        return None
    return preferred.canonical_taxon_id


def _mapping_conflict_score(*, source_name: SourceName, taxon: CanonicalTaxon) -> int:
    score = SOURCE_PRIORITY.get(taxon.authority_source, 0)
    if taxon.authority_source == source_name:
        score += 1000
    if taxon.taxon_status == TaxonStatus.ACTIVE:
        score += 100
    elif taxon.taxon_status == TaxonStatus.PROVISIONAL:
        score += 10
    return score
