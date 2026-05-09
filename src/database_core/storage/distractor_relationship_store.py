from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Sequence

import psycopg

from database_core.domain.models import DistractorRelationship


class PostgresDistractorRelationshipStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    def save_distractor_relationships(
        self,
        relationships: Sequence[DistractorRelationship],
        *,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self._connect() as owned_connection:
                self.save_distractor_relationships(
                    relationships,
                    connection=owned_connection,
                )
            return

        for relationship in relationships:
            payload = relationship.model_dump(mode="json")
            connection.execute(
                """
                INSERT INTO distractor_relationships (
                    relationship_id,
                    target_canonical_taxon_id,
                    target_scientific_name,
                    candidate_taxon_ref_type,
                    candidate_taxon_ref_id,
                    candidate_scientific_name,
                    source,
                    source_rank,
                    confusion_types_json,
                    pedagogical_value,
                    difficulty_level,
                    learner_level,
                    reason,
                    status,
                    constraints_json,
                    created_at,
                    updated_at,
                    payload_json
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (relationship_id)
                DO UPDATE SET
                    target_canonical_taxon_id = EXCLUDED.target_canonical_taxon_id,
                    target_scientific_name = EXCLUDED.target_scientific_name,
                    candidate_taxon_ref_type = EXCLUDED.candidate_taxon_ref_type,
                    candidate_taxon_ref_id = EXCLUDED.candidate_taxon_ref_id,
                    candidate_scientific_name = EXCLUDED.candidate_scientific_name,
                    source = EXCLUDED.source,
                    source_rank = EXCLUDED.source_rank,
                    confusion_types_json = EXCLUDED.confusion_types_json,
                    pedagogical_value = EXCLUDED.pedagogical_value,
                    difficulty_level = EXCLUDED.difficulty_level,
                    learner_level = EXCLUDED.learner_level,
                    reason = EXCLUDED.reason,
                    status = EXCLUDED.status,
                    constraints_json = EXCLUDED.constraints_json,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    relationship.relationship_id,
                    relationship.target_canonical_taxon_id,
                    relationship.target_scientific_name,
                    str(relationship.candidate_taxon_ref_type),
                    relationship.candidate_taxon_ref_id,
                    relationship.candidate_scientific_name,
                    str(relationship.source),
                    relationship.source_rank,
                    _json(relationship.confusion_types),
                    str(relationship.pedagogical_value),
                    str(relationship.difficulty_level),
                    str(relationship.learner_level),
                    relationship.reason,
                    str(relationship.status),
                    _json(relationship.constraints),
                    relationship.created_at.isoformat(),
                    relationship.updated_at.isoformat()
                    if relationship.updated_at is not None
                    else None,
                    _json(payload),
                ),
            )

    def fetch_validated_distractors_by_target(
        self,
        *,
        target_canonical_taxon_ids: Sequence[str] | None = None,
    ) -> dict[str, list[DistractorRelationship]]:
        with self._connect() as connection:
            params: list[object] = []
            target_clause = ""
            if target_canonical_taxon_ids:
                target_clause = "AND target_canonical_taxon_id = ANY(%s)"
                params.append(list(dict.fromkeys(target_canonical_taxon_ids)))
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM distractor_relationships
                WHERE status = 'validated'
                  AND candidate_taxon_ref_type = 'canonical_taxon'
                  {target_clause}
                ORDER BY target_canonical_taxon_id, source_rank, relationship_id
                """,
                params,
            ).fetchall()

        grouped: dict[str, list[DistractorRelationship]] = {}
        for row in rows:
            relationship = DistractorRelationship(**json.loads(str(row["payload_json"])))
            grouped.setdefault(relationship.target_canonical_taxon_id, []).append(
                relationship
            )
        return grouped

    def audit_distractor_relationship_coverage(
        self,
        *,
        target_canonical_taxon_ids: Sequence[str] | None = None,
        min_distractors_per_target: int = 3,
    ) -> dict[str, object]:
        with self._connect() as connection:
            params: list[object] = []
            target_clause = ""
            if target_canonical_taxon_ids:
                target_clause = "AND target_canonical_taxon_id = ANY(%s)"
                params.append(list(dict.fromkeys(target_canonical_taxon_ids)))
            rows = connection.execute(
                f"""
                SELECT
                    relationship_id,
                    target_canonical_taxon_id,
                    candidate_taxon_ref_type,
                    source,
                    status,
                    payload_json
                FROM distractor_relationships
                WHERE 1 = 1
                  {target_clause}
                ORDER BY target_canonical_taxon_id, relationship_id
                """,
                params,
            ).fetchall()

        source_counts = Counter(str(row["source"]) for row in rows)
        status_counts = Counter(str(row["status"]) for row in rows)
        ref_type_counts = Counter(str(row["candidate_taxon_ref_type"]) for row in rows)
        per_target_counts = Counter(
            str(row["target_canonical_taxon_id"])
            for row in rows
            if row["status"] == "validated"
            and row["candidate_taxon_ref_type"] == "canonical_taxon"
        )
        target_ids = list(dict.fromkeys(target_canonical_taxon_ids or per_target_counts))
        targets_below_min = [
            {
                "target_canonical_taxon_id": target_id,
                "validated_canonical_distractor_count": int(
                    per_target_counts.get(target_id, 0)
                ),
            }
            for target_id in sorted(target_ids)
            if per_target_counts.get(target_id, 0) < min_distractors_per_target
        ]
        blockers: list[str] = []
        if not rows:
            blockers.append("no_distractor_relationships")
        if ref_type_counts.get("unresolved_taxon", 0):
            blockers.append("unresolved_relationships_persisted")
        if source_counts.get("emergency_diversity_fallback", 0):
            blockers.append("emergency_fallback_relationships_persisted")
        if any(status != "validated" for status in status_counts):
            blockers.append("non_validated_relationships_persisted")

        status = "GO"
        if blockers:
            status = "NO_GO"
        elif targets_below_min:
            status = "GO_WITH_WARNINGS"

        return {
            "status": status,
            "blockers": blockers,
            "warnings": (
                ["targets_below_min_validated_canonical_distractors"]
                if targets_below_min
                else []
            ),
            "relationship_count": len(rows),
            "source_counts": dict(sorted(source_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "candidate_taxon_ref_type_counts": dict(sorted(ref_type_counts.items())),
            "targets_below_min": targets_below_min,
        }


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
