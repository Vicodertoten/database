from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

from database_core.domain.models import CanonicalTaxon, MediaAsset, QualifiedResource, ReviewItem, SourceObservation
from database_core.storage.schema import SCHEMA_SQL


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
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def reset(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
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
                    scientific_name,
                    canonical_rank,
                    common_names_json,
                    bird_scope_compatible,
                    external_source_mappings_json,
                    similar_taxon_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.canonical_taxon_id,
                        item.scientific_name,
                        item.canonical_rank,
                        _json(item.common_names),
                        int(item.bird_scope_compatible),
                        _json([mapping.model_dump(mode="json") for mapping in item.external_source_mappings]),
                        _json(item.similar_taxon_ids),
                    )
                    for item in taxa
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
                    review_status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.review_item_id,
                        item.media_asset_id,
                        item.canonical_taxon_id,
                        item.review_reason,
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
                table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
                for table in tables
            }

    def fetch_review_queue(self) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT review_item_id, media_asset_id, canonical_taxon_id, review_reason, review_status
                FROM review_queue
                ORDER BY review_item_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_exportable_resources(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT qualified_resource_id, canonical_taxon_id, media_asset_id, qualification_status
                FROM qualified_resources
                WHERE export_eligible = 1
                ORDER BY qualified_resource_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_qualification_metrics(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT qualification_status, provenance_summary_json
                FROM qualified_resources
                """
            ).fetchall()
            accepted_resources = 0
            ai_qualified_images = 0
            for row in rows:
                if row["qualification_status"] == "accepted":
                    accepted_resources += 1
                provenance = json.loads(row["provenance_summary_json"])
                if provenance.get("ai_model"):
                    ai_qualified_images += 1

            review_queue_count = connection.execute(
                "SELECT COUNT(*) AS count FROM review_queue"
            ).fetchone()["count"]
            return {
                "accepted_resources": accepted_resources,
                "ai_qualified_images": ai_qualified_images,
                "review_queue_count": review_queue_count,
            }


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
