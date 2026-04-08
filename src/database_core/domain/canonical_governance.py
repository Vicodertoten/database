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
class CanonicalAuthorityDelta:
    source_taxon_id_previous: str | None
    source_taxon_id_current: str | None
    name_previous: str | None
    name_current: str | None
    is_active_previous: bool | None
    is_active_current: bool | None
    provisional_previous: bool | None
    provisional_current: bool | None
    parent_id_previous: str | None
    parent_id_current: str | None
    ancestor_ids_previous: tuple[str, ...]
    ancestor_ids_current: tuple[str, ...]
    taxon_changes_count_previous: int | None
    taxon_changes_count_current: int | None
    current_synonymous_taxon_ids_previous: tuple[str, ...]
    current_synonymous_taxon_ids_current: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "source_taxon_id_previous": self.source_taxon_id_previous,
            "source_taxon_id_current": self.source_taxon_id_current,
            "name_previous": self.name_previous,
            "name_current": self.name_current,
            "is_active_previous": self.is_active_previous,
            "is_active_current": self.is_active_current,
            "provisional_previous": self.provisional_previous,
            "provisional_current": self.provisional_current,
            "parent_id_previous": self.parent_id_previous,
            "parent_id_current": self.parent_id_current,
            "ancestor_ids_previous": list(self.ancestor_ids_previous),
            "ancestor_ids_current": list(self.ancestor_ids_current),
            "taxon_changes_count_previous": self.taxon_changes_count_previous,
            "taxon_changes_count_current": self.taxon_changes_count_current,
            "current_synonymous_taxon_ids_previous": list(
                self.current_synonymous_taxon_ids_previous
            ),
            "current_synonymous_taxon_ids_current": list(
                self.current_synonymous_taxon_ids_current
            ),
        }

    def candidate_source_taxon_ids(self) -> set[str]:
        return {
            item
            for item in (
                self.source_taxon_id_current,
                self.source_taxon_id_previous,
                self.parent_id_current,
                self.parent_id_previous,
            )
            if item
        } | set(self.current_synonymous_taxon_ids_current) | set(
            self.current_synonymous_taxon_ids_previous
        )


@dataclass(frozen=True)
class CanonicalGovernanceDecision:
    event: CanonicalTaxonEvent
    decision_status: CanonicalGovernanceDecisionStatus
    decision_reason: DecisionReason
    signal_breakdown: CanonicalTransitionSignal
    source_delta: CanonicalAuthorityDelta


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
        source_delta = _build_source_delta(
            previous_taxon=previous,
            current_taxon=taxon,
        )
        non_transition_signal = CanonicalTransitionSignal.default_non_transition(
            source_authority_consistent=_source_authority_consistent(
                taxon,
                source_taxon_id_hint=source_delta.source_taxon_id_current,
            )
        )
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
                    source_delta=source_delta,
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
                    source_delta=source_delta,
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
                    source_delta=source_delta,
                )
            )

        previous_split_targets = set(previous.split_into)
        current_split_targets = set(taxon.split_into)
        for target_id in sorted(current_split_targets - previous_split_targets):
            decision_status, reason, signal, transition_delta = _decision_for_transition_target(
                source_taxon=taxon,
                previous_source_taxon=previous,
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
                    source_delta=transition_delta,
                )
            )

        if taxon.merged_into and taxon.merged_into != previous.merged_into:
            decision_status, reason, signal, transition_delta = _decision_for_transition_target(
                source_taxon=taxon,
                previous_source_taxon=previous,
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
                    source_delta=transition_delta,
                )
            )

        if taxon.replaced_by and taxon.replaced_by != previous.replaced_by:
            decision_status, reason, signal, transition_delta = _decision_for_transition_target(
                source_taxon=taxon,
                previous_source_taxon=previous,
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
                    source_delta=transition_delta,
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
    previous_source_taxon: CanonicalTaxon | None,
    target_taxon_id: str,
    current_by_id: dict[str, CanonicalTaxon],
    requires_derived_from: bool,
) -> tuple[
    CanonicalGovernanceDecisionStatus,
    DecisionReason,
    CanonicalTransitionSignal,
    CanonicalAuthorityDelta,
]:
    target_taxon = current_by_id.get(target_taxon_id)
    source_delta = _build_source_delta(
        previous_taxon=previous_source_taxon,
        current_taxon=source_taxon,
    )
    signal = _build_transition_signal(
        source_taxon=source_taxon,
        target_taxon=target_taxon,
        requires_derived_from=requires_derived_from,
        source_delta=source_delta,
    )
    if target_taxon is None:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_missing_target",
            signal,
            source_delta,
        )
    if not signal.target_not_provisional:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_target_provisional",
            signal,
            source_delta,
        )
    if requires_derived_from and not signal.lineage_consistent:
        return (
            CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
            "ambiguous_transition_inconsistent_lineage",
            signal,
            source_delta,
        )
    if signal.score >= 3:
        return (
            CanonicalGovernanceDecisionStatus.AUTO_CLEAR,
            "weighted_transition_clear",
            signal,
            source_delta,
        )
    return (
        CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
        "ambiguous_transition_low_signal_score",
        signal,
        source_delta,
    )


def _build_transition_signal(
    *,
    source_taxon: CanonicalTaxon,
    target_taxon: CanonicalTaxon | None,
    requires_derived_from: bool,
    source_delta: CanonicalAuthorityDelta,
) -> CanonicalTransitionSignal:
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
    else:
        lineage_consistent = _lineage_consistent_from_source_delta(
            source_taxon=source_taxon,
            target_taxon=target_taxon,
            target_profile=target_profile,
            requires_derived_from=requires_derived_from,
            source_delta=source_delta,
        )
    return CanonicalTransitionSignal(
        target_exists_and_active=target_exists and target_is_active,
        target_not_provisional=target_exists and target_not_provisional,
        lineage_consistent=lineage_consistent,
        source_authority_consistent=_source_authority_consistent(
            source_taxon,
            source_taxon_id_hint=source_delta.source_taxon_id_current,
        ),
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
    previous_by_id = {item.canonical_taxon_id: item for item in previous_taxa}

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
                source_delta = _build_source_delta(
                    previous_taxon=previous_by_id.get(taxon.canonical_taxon_id),
                    current_taxon=taxon,
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
                                f":{source_name}:{external_id}:{taxon.canonical_taxon_id}:ambiguous"
                            ),
                        ),
                        decision_status=CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED,
                        decision_reason="ambiguous_source_mapping_conflict",
                        signal_breakdown=CanonicalTransitionSignal(
                            target_exists_and_active=True,
                            target_not_provisional=True,
                            lineage_consistent=True,
                            source_authority_consistent=_source_authority_consistent(
                                taxon,
                                source_taxon_id_hint=source_delta.source_taxon_id_current,
                            ),
                            mapping_conflict_uniquely_resolved=False,
                        ),
                        source_delta=source_delta,
                    )
                )
            continue

        for taxon in unique_candidates:
            if taxon.canonical_taxon_id == preferred_canonical_taxon_id:
                continue
            source_delta = _build_source_delta(
                previous_taxon=previous_by_id.get(taxon.canonical_taxon_id),
                current_taxon=taxon,
            )
            signal = CanonicalTransitionSignal(
                target_exists_and_active=True,
                target_not_provisional=True,
                lineage_consistent=True,
                source_authority_consistent=_source_authority_consistent(
                    taxon,
                    source_taxon_id_hint=source_delta.source_taxon_id_current,
                ),
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
                    source_delta=source_delta,
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


def _profile_parent_id(profile: dict[str, object]) -> str | None:
    value = profile.get("parent_id")
    if value in {None, ""}:
        return None
    return str(value)


def _profile_ancestor_ids(profile: dict[str, object]) -> set[str]:
    raw = profile.get("ancestor_ids")
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw if item is not None and str(item).strip()}


def _profile_synonymous_taxon_ids(profile: dict[str, object]) -> tuple[str, ...]:
    raw = profile.get("current_synonymous_taxon_ids")
    if not isinstance(raw, list):
        return ()
    return tuple(sorted({str(item) for item in raw if item is not None and str(item).strip()}))


def _profile_bool(profile: dict[str, object], key: str) -> bool | None:
    value = profile.get(key)
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _profile_int(profile: dict[str, object], key: str) -> int | None:
    value = profile.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if value in {None, ""}:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _profile_name(profile: dict[str, object]) -> str | None:
    value = profile.get("name")
    if value in {None, ""}:
        return None
    return str(value).strip()


def _authority_mapping_external_id(taxon: CanonicalTaxon | None) -> str | None:
    if taxon is None:
        return None
    mapping = next(
        (
            item
            for item in taxon.external_source_mappings
            if item.source_name == taxon.authority_source
        ),
        None,
    )
    if mapping is None:
        return None
    return mapping.external_id


def _build_source_delta(
    *,
    previous_taxon: CanonicalTaxon | None,
    current_taxon: CanonicalTaxon | None,
) -> CanonicalAuthorityDelta:
    previous_profile = _authority_taxonomy_profile(previous_taxon)
    current_profile = _authority_taxonomy_profile(current_taxon)
    previous_source_taxon_id = _profile_source_taxon_id(
        previous_profile
    ) or _authority_mapping_external_id(previous_taxon)
    current_source_taxon_id = _profile_source_taxon_id(
        current_profile
    ) or _authority_mapping_external_id(current_taxon)
    return CanonicalAuthorityDelta(
        source_taxon_id_previous=previous_source_taxon_id,
        source_taxon_id_current=current_source_taxon_id,
        name_previous=_profile_name(previous_profile)
        or (previous_taxon.accepted_scientific_name if previous_taxon else None),
        name_current=_profile_name(current_profile)
        or (current_taxon.accepted_scientific_name if current_taxon else None),
        is_active_previous=_profile_bool(previous_profile, "is_active")
        if _profile_bool(previous_profile, "is_active") is not None
        else (
            previous_taxon.taxon_status == TaxonStatus.ACTIVE
            if previous_taxon is not None
            else None
        ),
        is_active_current=_profile_bool(current_profile, "is_active")
        if _profile_bool(current_profile, "is_active") is not None
        else (
            current_taxon.taxon_status == TaxonStatus.ACTIVE
            if current_taxon is not None
            else None
        ),
        provisional_previous=_profile_bool(previous_profile, "provisional")
        if _profile_bool(previous_profile, "provisional") is not None
        else (
            previous_taxon.taxon_status == TaxonStatus.PROVISIONAL
            if previous_taxon is not None
            else None
        ),
        provisional_current=_profile_bool(current_profile, "provisional")
        if _profile_bool(current_profile, "provisional") is not None
        else (
            current_taxon.taxon_status == TaxonStatus.PROVISIONAL
            if current_taxon is not None
            else None
        ),
        parent_id_previous=_profile_parent_id(previous_profile),
        parent_id_current=_profile_parent_id(current_profile),
        ancestor_ids_previous=tuple(sorted(_profile_ancestor_ids(previous_profile))),
        ancestor_ids_current=tuple(sorted(_profile_ancestor_ids(current_profile))),
        taxon_changes_count_previous=_profile_int(previous_profile, "taxon_changes_count"),
        taxon_changes_count_current=_profile_int(current_profile, "taxon_changes_count"),
        current_synonymous_taxon_ids_previous=_profile_synonymous_taxon_ids(previous_profile),
        current_synonymous_taxon_ids_current=_profile_synonymous_taxon_ids(current_profile),
    )


def _lineage_consistent_from_source_delta(
    *,
    source_taxon: CanonicalTaxon,
    target_taxon: CanonicalTaxon,
    target_profile: dict[str, object],
    requires_derived_from: bool,
    source_delta: CanonicalAuthorityDelta,
) -> bool:
    if target_taxon.derived_from == source_taxon.canonical_taxon_id:
        return True

    source_candidates = source_delta.candidate_source_taxon_ids()
    target_ancestor_ids = _profile_ancestor_ids(target_profile)
    target_parent_id = _profile_parent_id(target_profile)
    target_source_taxon_id = _profile_source_taxon_id(
        target_profile
    ) or _authority_mapping_external_id(target_taxon)

    if requires_derived_from:
        if source_candidates and bool(target_ancestor_ids.intersection(source_candidates)):
            return True
        if target_parent_id and target_parent_id in source_candidates:
            return True
        return False

    synonymous_target_ids = set(source_delta.current_synonymous_taxon_ids_current) | set(
        source_delta.current_synonymous_taxon_ids_previous
    )
    if target_source_taxon_id and target_source_taxon_id in synonymous_target_ids:
        return True
    if target_source_taxon_id and (
        target_source_taxon_id == source_delta.parent_id_current
        or target_source_taxon_id == source_delta.parent_id_previous
    ):
        return True
    if source_candidates and bool(target_ancestor_ids.intersection(source_candidates)):
        return True
    if target_parent_id and target_parent_id in source_candidates:
        return True
    return not source_candidates


def _source_authority_consistent(
    taxon: CanonicalTaxon,
    *,
    source_taxon_id_hint: str | None = None,
) -> bool:
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
    profile_source_taxon_id = source_taxon_id_hint or _profile_source_taxon_id(profile)
    if profile_source_taxon_id is None:
        return True
    return authority_mapping.external_id == profile_source_taxon_id
