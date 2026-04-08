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
    "weighted_transition_clear",
    "deterministic_source_priority_resolution",
    "ambiguous_transition_missing_target",
    "ambiguous_transition_inconsistent_lineage",
    "ambiguous_transition_target_provisional",
    "ambiguous_transition_low_signal_score",
    "ambiguous_source_mapping_conflict",
]

SOURCE_PRIORITY: dict[SourceName, int] = {
    SourceName.INATURALIST: 300,
    SourceName.GBIF: 200,
    SourceName.WIKIMEDIA_COMMONS: 100,
}


@dataclass(frozen=True)
class CanonicalTransitionSignal:
    target_exists_and_active: bool
    target_not_provisional: bool
    lineage_consistent: bool
    source_authority_consistent: bool
    mapping_conflict_uniquely_resolved: bool

    @property
    def score(self) -> int:
        return sum(
            (
                self.target_exists_and_active,
                self.target_not_provisional,
                self.lineage_consistent,
                self.source_authority_consistent,
                self.mapping_conflict_uniquely_resolved,
            )
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "target_exists_and_active": self.target_exists_and_active,
            "target_not_provisional": self.target_not_provisional,
            "lineage_consistent": self.lineage_consistent,
            "source_authority_consistent": self.source_authority_consistent,
            "mapping_conflict_uniquely_resolved": self.mapping_conflict_uniquely_resolved,
            "score": self.score,
        }

    @classmethod
    def default_non_transition(
        cls,
        *,
        source_authority_consistent: bool,
    ) -> CanonicalTransitionSignal:
        return cls(
            target_exists_and_active=True,
            target_not_provisional=True,
            lineage_consistent=True,
            source_authority_consistent=source_authority_consistent,
            mapping_conflict_uniquely_resolved=True,
        )


@dataclass(frozen=True)
class CanonicalGovernanceDecision:
    event: CanonicalTaxonEvent
    decision_status: CanonicalGovernanceDecisionStatus
    decision_reason: DecisionReason
    signal_breakdown: CanonicalTransitionSignal


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
        source_authority_consistent = _source_authority_consistent(taxon)
        non_transition_signal = CanonicalTransitionSignal.default_non_transition(
            source_authority_consistent=source_authority_consistent
        )
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
                    signal_breakdown=non_transition_signal,
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
                    signal_breakdown=non_transition_signal,
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
                    signal_breakdown=non_transition_signal,
                )
            )

        previous_split_targets = set(previous.split_into)
        current_split_targets = set(taxon.split_into)
        for target_id in sorted(current_split_targets - previous_split_targets):
            decision_status, reason, signal = _decision_for_transition_target(
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
                    signal_breakdown=signal,
                )
            )

        if taxon.merged_into and taxon.merged_into != previous.merged_into:
            decision_status, reason, signal = _decision_for_transition_target(
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
                    signal_breakdown=signal,
                )
            )

        if taxon.replaced_by and taxon.replaced_by != previous.replaced_by:
            decision_status, reason, signal = _decision_for_transition_target(
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
                    signal_breakdown=signal,
                )
            )

    decisions.extend(
        _derive_mapping_conflict_decisions(
            previous_taxa=previous_taxa,
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
) -> tuple[CanonicalGovernanceDecisionStatus, DecisionReason, CanonicalTransitionSignal]:
    target_taxon = current_by_id.get(target_taxon_id)
    signal = _build_transition_signal(
        source_taxon=source_taxon,
        target_taxon=target_taxon,
        requires_derived_from=requires_derived_from,
    )
    if target_taxon is None:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_missing_target",
            signal,
        )
    if not signal.target_not_provisional:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_target_provisional",
            signal,
        )
    if requires_derived_from and not signal.lineage_consistent:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_inconsistent_lineage",
            signal,
        )
    if signal.score >= 3:
        return (
            CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
            "weighted_transition_clear",
            signal,
        )
    return (
        CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
        "ambiguous_transition_low_signal_score",
        signal,
    )


def _build_transition_signal(
    *,
    source_taxon: CanonicalTaxon,
    target_taxon: CanonicalTaxon | None,
    requires_derived_from: bool,
) -> CanonicalTransitionSignal:
    source_profile = _authority_taxonomy_profile(source_taxon)
    target_profile = _authority_taxonomy_profile(target_taxon) if target_taxon else {}
    target_exists = target_taxon is not None
    target_is_active = (
        bool(target_profile.get("is_active"))
        if target_profile.get("is_active") is not None
        else target_taxon is not None and target_taxon.taxon_status == TaxonStatus.ACTIVE
    )
    target_not_provisional = (
        not bool(target_profile.get("provisional"))
        if target_profile.get("provisional") is not None
        else target_taxon is not None and target_taxon.taxon_status != TaxonStatus.PROVISIONAL
    )
    lineage_consistent = True
    if target_taxon is None:
        lineage_consistent = False
    elif requires_derived_from:
        source_taxon_id = _profile_source_taxon_id(source_profile)
        target_ancestors = _profile_ancestor_ids(target_profile)
        lineage_consistent = (
            target_taxon.derived_from == source_taxon.canonical_taxon_id
            or (
                source_taxon_id is not None
                and source_taxon_id in target_ancestors
            )
        )
    return CanonicalTransitionSignal(
        target_exists_and_active=target_exists and target_is_active,
        target_not_provisional=target_exists and target_not_provisional,
        lineage_consistent=lineage_consistent,
        source_authority_consistent=_source_authority_consistent(source_taxon),
        mapping_conflict_uniquely_resolved=True,
    )


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
    previous_taxa: list[CanonicalTaxon],
    current_taxa: list[CanonicalTaxon],
    effective_at: datetime,
) -> list[CanonicalGovernanceDecision]:
    by_source_external = _group_taxa_by_source_external(current_taxa)
    previous_by_source_external = _group_taxa_by_source_external(previous_taxa)

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
        previous_candidates = sorted(
            {
                item.canonical_taxon_id: item
                for item in previous_by_source_external.get(key, [])
            }.values(),
            key=lambda item: item.canonical_taxon_id,
        )
        if len(previous_candidates) >= 2 and [
            item.canonical_taxon_id for item in previous_candidates
        ] == [item.canonical_taxon_id for item in unique_candidates]:
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
                        signal_breakdown=CanonicalTransitionSignal(
                            target_exists_and_active=True,
                            target_not_provisional=True,
                            lineage_consistent=True,
                            source_authority_consistent=_source_authority_consistent(taxon),
                            mapping_conflict_uniquely_resolved=False,
                        ),
                    )
                )
            continue

        for taxon in unique_candidates:
            if taxon.canonical_taxon_id == preferred_canonical_taxon_id:
                continue
            signal = CanonicalTransitionSignal(
                target_exists_and_active=True,
                target_not_provisional=True,
                lineage_consistent=True,
                source_authority_consistent=_source_authority_consistent(taxon),
                mapping_conflict_uniquely_resolved=True,
            )
            decision_status = (
                CanonicalGovernanceDecisionStatus.AUTO_CLEAR
                if signal.score >= 3
                else CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED
            )
            decision_reason: DecisionReason = (
                "deterministic_source_priority_resolution"
                if decision_status == CanonicalGovernanceDecisionStatus.AUTO_CLEAR
                else "ambiguous_transition_low_signal_score"
            )
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
                    decision_status=decision_status,
                    decision_reason=decision_reason,
                    signal_breakdown=signal,
                )
            )

    return decisions


def _group_taxa_by_source_external(
    taxa: list[CanonicalTaxon],
) -> dict[tuple[SourceName, str], list[CanonicalTaxon]]:
    grouped: dict[tuple[SourceName, str], list[CanonicalTaxon]] = {}
    for taxon in taxa:
        for mapping in taxon.external_source_mappings:
            key = (mapping.source_name, mapping.external_id.strip())
            grouped.setdefault(key, []).append(taxon)
    return grouped


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


def _authority_taxonomy_profile(taxon: CanonicalTaxon | None) -> dict[str, object]:
    if taxon is None:
        return {}
    return dict(taxon.authority_taxonomy_profile or {})


def _profile_source_taxon_id(profile: dict[str, object]) -> str | None:
    value = profile.get("source_taxon_id")
    if value in {None, ""}:
        return None
    return str(value)


def _profile_ancestor_ids(profile: dict[str, object]) -> set[str]:
    raw = profile.get("ancestor_ids")
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw if item is not None and str(item).strip()}


def _source_authority_consistent(taxon: CanonicalTaxon) -> bool:
    authority_mapping = next(
        (
            mapping
            for mapping in taxon.external_source_mappings
            if mapping.source_name == taxon.authority_source
        ),
        None,
    )
    if authority_mapping is None:
        return False
    profile = _authority_taxonomy_profile(taxon)
    profile_source_taxon_id = _profile_source_taxon_id(profile)
    if profile_source_taxon_id is None:
        return True
    return authority_mapping.external_id == profile_source_taxon_id
