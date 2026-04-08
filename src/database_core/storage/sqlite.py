from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from database_core.domain.enums import CanonicalChangeRelationType, CanonicalEventType
from database_core.domain.models import (
    CanonicalTaxon,
    CanonicalTaxonEvent,
    CanonicalTaxonRelationship,
    MediaAsset,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.storage.schema import SCHEMA_SQL
from database_core.versioning import SCHEMA_VERSION


class SQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        if self._requires_schema_reset():
            self.db_path.unlink(missing_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def reset(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                DELETE FROM canonical_taxon_events;
                DELETE FROM canonical_taxon_relationships;
                DELETE FROM review_queue;
                DELETE FROM qualified_resources;
                DELETE FROM media_assets;
                DELETE FROM source_observations;
                DELETE FROM canonical_taxa;
                """
            )

    def save_canonical_taxa(self, taxa: Sequence[CanonicalTaxon]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO canonical_taxa (
                    canonical_taxon_id,
                    accepted_scientific_name,
                    canonical_rank,
                    taxon_group,
                    taxon_status,
                    authority_source,
                    display_slug,
                    synonyms_json,
                    common_names_json,
                    key_identification_features_json,
                    source_enrichment_status,
                    bird_scope_compatible,
                    external_source_mappings_json,
                    external_similarity_hints_json,
                    similar_taxa_json,
                    similar_taxon_ids_json,
                    split_into_json,
                    merged_into,
                    replaced_by,
                    derived_from
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.canonical_taxon_id,
                        item.accepted_scientific_name,
                        item.canonical_rank,
                        item.taxon_group,
                        item.taxon_status,
                        item.authority_source,
                        item.display_slug,
                        _json(item.synonyms),
                        _json(item.common_names),
                        _json(item.key_identification_features),
                        item.source_enrichment_status,
                        int(item.bird_scope_compatible),
                        _json(
                            [
                                mapping.model_dump(mode="json")
                                for mapping in item.external_source_mappings
                            ]
                        ),
                        _json(
                            [
                                hint.model_dump(mode="json")
                                for hint in item.external_similarity_hints
                            ]
                        ),
                        _json([relation.model_dump(mode="json") for relation in item.similar_taxa]),
                        _json(item.similar_taxon_ids),
                        _json(item.split_into),
                        item.merged_into,
                        item.replaced_by,
                        item.derived_from,
                    )
                    for item in taxa
                ],
            )
            relationships, events = _build_canonical_relationships_and_events(taxa)
            connection.execute("DELETE FROM canonical_taxon_relationships")
            connection.execute("DELETE FROM canonical_taxon_events")
            connection.executemany(
                """
                INSERT INTO canonical_taxon_relationships (
                    source_canonical_taxon_id,
                    relationship_type,
                    target_canonical_taxon_id,
                    source_name,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.source_canonical_taxon_id,
                        item.relationship_type,
                        item.target_canonical_taxon_id,
                        item.source_name,
                        item.created_at.isoformat(),
                    )
                    for item in relationships
                ],
            )
            connection.executemany(
                """
                INSERT INTO canonical_taxon_events (
                    event_id,
                    event_type,
                    canonical_taxon_id,
                    source_name,
                    effective_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.event_id,
                        item.event_type,
                        item.canonical_taxon_id,
                        item.source_name,
                        item.effective_at.isoformat(),
                        _json(item.payload),
                    )
                    for item in events
                ],
            )

    def save_source_observations(self, observations: Sequence[SourceObservation]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO source_observations (
                    observation_uid,
                    source_name,
                    source_observation_id,
                    source_taxon_id,
                    observed_at,
                    location_json,
                    source_quality_json,
                    raw_payload_ref,
                    canonical_taxon_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.observation_uid,
                        item.source_name,
                        item.source_observation_id,
                        item.source_taxon_id,
                        item.observed_at.isoformat() if item.observed_at else None,
                        _json(item.location.model_dump(mode="json")),
                        _json(item.source_quality.model_dump(mode="json")),
                        item.raw_payload_ref,
                        item.canonical_taxon_id,
                    )
                    for item in observations
                ],
            )

    def save_media_assets(self, media_assets: Sequence[MediaAsset]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO media_assets (
                    media_id,
                    source_name,
                    source_media_id,
                    media_type,
                    source_url,
                    attribution,
                    author,
                    license,
                    mime_type,
                    file_extension,
                    width,
                    height,
                    checksum,
                    source_observation_uid,
                    canonical_taxon_id,
                    raw_payload_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.media_id,
                        item.source_name,
                        item.source_media_id,
                        item.media_type,
                        item.source_url,
                        item.attribution,
                        item.author,
                        item.license,
                        item.mime_type,
                        item.file_extension,
                        item.width,
                        item.height,
                        item.checksum,
                        item.source_observation_uid,
                        item.canonical_taxon_id,
                        item.raw_payload_ref,
                    )
                    for item in media_assets
                ],
            )

    def save_qualified_resources(self, resources: Sequence[QualifiedResource]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO qualified_resources (
                    qualified_resource_id,
                    canonical_taxon_id,
                    source_observation_uid,
                    source_observation_id,
                    media_asset_id,
                    qualification_status,
                    qualification_version,
                    technical_quality,
                    pedagogical_quality,
                    life_stage,
                    sex,
                    visible_parts_json,
                    view_angle,
                    qualification_notes,
                    qualification_flags_json,
                    provenance_summary_json,
                    license_safety_result,
                    export_eligible
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.qualified_resource_id,
                        item.canonical_taxon_id,
                        item.source_observation_uid,
                        item.source_observation_id,
                        item.media_asset_id,
                        item.qualification_status,
                        item.qualification_version,
                        item.technical_quality,
                        item.pedagogical_quality,
                        item.life_stage,
                        item.sex,
                        _json(item.visible_parts),
                        item.view_angle,
                        item.qualification_notes,
                        _json(item.qualification_flags),
                        _json(item.provenance_summary.model_dump(mode="json")),
                        item.license_safety_result,
                        int(item.export_eligible),
                    )
                    for item in resources
                ],
            )

    def save_review_items(self, review_items: Sequence[ReviewItem]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO review_queue (
                    review_item_id,
                    media_asset_id,
                    canonical_taxon_id,
                    review_reason,
                    review_reason_code,
                    review_note,
                    stage_name,
                    priority,
                    review_status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.review_item_id,
                        item.media_asset_id,
                        item.canonical_taxon_id,
                        item.review_reason,
                        item.review_reason_code,
                        item.review_note,
                        item.stage_name,
                        item.priority,
                        item.review_status,
                        item.created_at.isoformat(),
                    )
                    for item in review_items
                ],
            )

    def fetch_summary(self) -> dict[str, int]:
        with self.connect() as connection:
            tables = [
                "canonical_taxa",
                "source_observations",
                "media_assets",
                "qualified_resources",
                "review_queue",
            ]
            return {
                table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()[
                    "count"
                ]
                for table in tables
            }

    def fetch_review_queue(
        self,
        *,
        review_reason_code: str | None = None,
        stage_name: str | None = None,
        review_status: str | None = None,
        canonical_taxon_id: str | None = None,
        priority: str | None = None,
    ) -> list[dict[str, str]]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[str] = []
            if review_reason_code:
                clauses.append("review_reason_code = ?")
                params.append(review_reason_code)
            if stage_name:
                clauses.append("stage_name = ?")
                params.append(stage_name)
            if review_status:
                clauses.append("review_status = ?")
                params.append(review_status)
            if canonical_taxon_id:
                clauses.append("canonical_taxon_id = ?")
                params.append(canonical_taxon_id)
            if priority:
                clauses.append("priority = ?")
                params.append(priority)
            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT
                    review_item_id,
                    media_asset_id,
                    canonical_taxon_id,
                    review_reason,
                    review_reason_code,
                    review_note,
                    stage_name,
                    priority,
                    review_status
                FROM review_queue
                {where_clause}
                ORDER BY
                    CASE priority
                        WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2
                        ELSE 3
                    END,
                    review_item_id
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_exportable_resources(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    qualified_resource_id,
                    canonical_taxon_id,
                    media_asset_id,
                    qualification_status
                FROM qualified_resources
                WHERE export_eligible = 1
                ORDER BY qualified_resource_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_qualification_metrics(self) -> dict[str, object]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    qualification_status,
                    provenance_summary_json,
                    qualification_flags_json,
                    license_safety_result,
                    export_eligible
                FROM qualified_resources
                """
            ).fetchall()
            accepted_resources = 0
            rejected_resources = 0
            review_required_resources = 0
            ai_qualified_images = 0
            exportable_resources = 0
            flag_counts: Counter[str] = Counter()
            license_distribution: Counter[str] = Counter()
            ai_model_distribution: Counter[str] = Counter()
            for row in rows:
                if row["qualification_status"] == "accepted":
                    accepted_resources += 1
                elif row["qualification_status"] == "rejected":
                    rejected_resources += 1
                elif row["qualification_status"] == "review_required":
                    review_required_resources += 1
                provenance = json.loads(row["provenance_summary_json"])
                if provenance.get("ai_model"):
                    ai_qualified_images += 1
                    ai_model_distribution[str(provenance["ai_model"])] += 1
                if row["export_eligible"]:
                    exportable_resources += 1
                license_distribution[row["license_safety_result"]] += 1
                for flag in json.loads(row["qualification_flags_json"]):
                    flag_counts[flag] += 1

            review_queue_count = connection.execute(
                "SELECT COUNT(*) AS count FROM review_queue"
            ).fetchone()["count"]
            return {
                "accepted_resources": accepted_resources,
                "rejected_resources": rejected_resources,
                "review_required_resources": review_required_resources,
                "ai_qualified_images": ai_qualified_images,
                "exportable_resources": exportable_resources,
                "review_queue_count": review_queue_count,
                "top_rejection_flags": dict(flag_counts.most_common(5)),
                "license_distribution": dict(sorted(license_distribution.items())),
                "ai_model_distribution": dict(sorted(ai_model_distribution.items())),
            }

    def _requires_schema_reset(self) -> bool:
        if not self.db_path.exists():
            return False
        with self.connect() as connection:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            has_tables = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchone()["count"]
        return bool(has_tables) and current_version != SCHEMA_VERSION


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _build_canonical_relationships_and_events(
    taxa: Sequence[CanonicalTaxon],
) -> tuple[list[CanonicalTaxonRelationship], list[CanonicalTaxonEvent]]:
    now = datetime.now(UTC)
    relationships: list[CanonicalTaxonRelationship] = []
    events: list[CanonicalTaxonEvent] = []

    for taxon in sorted(taxa, key=lambda item: item.canonical_taxon_id):
        events.append(
            CanonicalTaxonEvent(
                event_id=f"event:{taxon.canonical_taxon_id}:upsert",
                event_type=CanonicalEventType.CREATE,
                canonical_taxon_id=taxon.canonical_taxon_id,
                source_name=taxon.authority_source,
                effective_at=now,
                payload={
                    "accepted_scientific_name": taxon.accepted_scientific_name,
                    "taxon_status": taxon.taxon_status,
                    "display_slug": taxon.display_slug,
                },
            )
        )

        for target_id in taxon.split_into:
            relationships.append(
                CanonicalTaxonRelationship(
                    source_canonical_taxon_id=taxon.canonical_taxon_id,
                    relationship_type=CanonicalChangeRelationType.SPLIT_INTO,
                    target_canonical_taxon_id=target_id,
                    source_name=taxon.authority_source,
                    created_at=now,
                )
            )
        if taxon.merged_into:
            relationships.append(
                CanonicalTaxonRelationship(
                    source_canonical_taxon_id=taxon.canonical_taxon_id,
                    relationship_type=CanonicalChangeRelationType.MERGED_INTO,
                    target_canonical_taxon_id=taxon.merged_into,
                    source_name=taxon.authority_source,
                    created_at=now,
                )
            )
        if taxon.replaced_by:
            relationships.append(
                CanonicalTaxonRelationship(
                    source_canonical_taxon_id=taxon.canonical_taxon_id,
                    relationship_type=CanonicalChangeRelationType.REPLACED_BY,
                    target_canonical_taxon_id=taxon.replaced_by,
                    source_name=taxon.authority_source,
                    created_at=now,
                )
            )
        if taxon.derived_from:
            relationships.append(
                CanonicalTaxonRelationship(
                    source_canonical_taxon_id=taxon.canonical_taxon_id,
                    relationship_type=CanonicalChangeRelationType.DERIVED_FROM,
                    target_canonical_taxon_id=taxon.derived_from,
                    source_name=taxon.authority_source,
                    created_at=now,
                )
            )

    deduped_relationships = sorted(
        {
            (
                item.source_canonical_taxon_id,
                item.relationship_type,
                item.target_canonical_taxon_id,
                item.source_name,
            ): item
            for item in relationships
        }.values(),
        key=lambda item: (
            item.source_canonical_taxon_id,
            item.relationship_type,
            item.target_canonical_taxon_id,
            item.source_name,
        ),
    )
    return deduped_relationships, events
