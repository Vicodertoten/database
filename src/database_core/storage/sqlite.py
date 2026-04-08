from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from database_core.domain.canonical_governance import derive_canonical_governance_decisions
from database_core.domain.enums import (
    CanonicalChangeRelationType,
    CanonicalEventType,
    CanonicalGovernanceDecisionStatus,
    ReviewStatus,
)
from database_core.domain.models import (
    CanonicalGovernanceReviewItem,
    CanonicalTaxon,
    CanonicalTaxonEvent,
    CanonicalTaxonRelationship,
    MediaAsset,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.storage.migrations import apply_migrations, has_user_tables, read_user_version
from database_core.storage.schema import SCHEMA_SQL
from database_core.versioning import (
    ENRICHMENT_VERSION,
    EXPORT_VERSION,
    QUALIFICATION_VERSION,
    SCHEMA_VERSION,
    SCHEMA_VERSION_LABEL,
)


class RepositorySchemaVersionMismatchError(ValueError):
    """Raised when an existing SQLite file has a schema version mismatch."""


class SQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        except Exception:  # pragma: no cover - rollback path is validated in integration tests.
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def initialize(self, *, allow_schema_reset: bool = False) -> None:
        if self._requires_schema_migration():
            if not allow_schema_reset:
                current_version = self.current_schema_version()
                raise RepositorySchemaVersionMismatchError(
                    "Database schema version mismatch for "
                    f"{self.db_path}. Expected user_version={SCHEMA_VERSION}, "
                    f"got {current_version}. Run `database-core migrate --db-path {self.db_path}` "
                    "or use explicit local-dev reset (allow_schema_reset=True)."
                )
            self.db_path.unlink(missing_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def migrate_to_latest(self) -> tuple[int, ...]:
        with self.connect() as connection:
            if not has_user_tables(connection):
                connection.executescript(SCHEMA_SQL)
                return (SCHEMA_VERSION,)
            applied_versions = apply_migrations(connection, target_version=SCHEMA_VERSION)
            if read_user_version(connection) != SCHEMA_VERSION:
                raise RepositorySchemaVersionMismatchError(
                    "Database migration did not reach expected schema version "
                    f"{SCHEMA_VERSION} for {self.db_path}"
                )
        return applied_versions

    def current_schema_version(self) -> int:
        if not self.db_path.exists():
            return 0
        with self.connect() as connection:
            return read_user_version(connection)

    def fetch_latest_completed_canonical_taxa(self) -> list[CanonicalTaxon]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT run_id
                FROM pipeline_runs
                WHERE run_status = 'completed' AND completed_at IS NOT NULL
                ORDER BY completed_at DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return []
            payload_rows = connection.execute(
                """
                SELECT payload_json
                FROM canonical_taxa_history
                WHERE run_id = ?
                ORDER BY canonical_taxon_id
                """,
                (str(row["run_id"]),),
            ).fetchall()
            return [
                CanonicalTaxon(**json.loads(str(payload_row["payload_json"])))
                for payload_row in payload_rows
            ]

    def reset_materialized_state(self, *, connection: sqlite3.Connection | None = None) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.reset_materialized_state(connection=owned_connection)
            return

        connection.executescript(
            """
            DELETE FROM canonical_taxon_relationships;
            DELETE FROM review_queue;
            DELETE FROM qualified_resources;
            DELETE FROM media_assets;
            DELETE FROM source_observations;
            DELETE FROM canonical_taxa;
            """
        )

    def reset(self, *, connection: sqlite3.Connection | None = None) -> None:
        self.reset_materialized_state(connection=connection)

    def save_canonical_taxa(
        self,
        taxa: Sequence[CanonicalTaxon],
        *,
        run_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_canonical_taxa(taxa, run_id=run_id, connection=owned_connection)
            return
        if run_id is None:
            raise ValueError("run_id is required to persist canonical state events")

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
                derived_from,
                authority_taxonomy_profile_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        [hint.model_dump(mode="json") for hint in item.external_similarity_hints]
                    ),
                    _json([relation.model_dump(mode="json") for relation in item.similar_taxa]),
                    _json(item.similar_taxon_ids),
                    _json(item.split_into),
                    item.merged_into,
                    item.replaced_by,
                    item.derived_from,
                    _json(item.authority_taxonomy_profile),
                )
                for item in taxa
            ],
        )
        relationships, state_events = _build_canonical_relationships_and_state_events(taxa)
        connection.execute("DELETE FROM canonical_taxon_relationships")
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
            INSERT INTO canonical_state_events (
                state_event_id,
                run_id,
                event_type,
                canonical_taxon_id,
                source_name,
                effective_at,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"{run_id}:{item.event_id}",
                    run_id,
                    item.event_type,
                    item.canonical_taxon_id,
                    item.source_name,
                    item.effective_at.isoformat(),
                    _json(item.payload),
                    datetime.now(UTC).isoformat(),
                )
                for item in state_events
            ],
        )

    def save_source_observations(
        self,
        observations: Sequence[SourceObservation],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_source_observations(observations, connection=owned_connection)
            return

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

    def save_media_assets(
        self,
        media_assets: Sequence[MediaAsset],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_media_assets(media_assets, connection=owned_connection)
            return

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

    def save_qualified_resources(
        self,
        resources: Sequence[QualifiedResource],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_qualified_resources(resources, connection=owned_connection)
            return

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
                difficulty_level,
                media_role,
                confusion_relevance,
                diagnostic_feature_visibility,
                learning_suitability,
                uncertainty_reason,
                qualification_notes,
                qualification_flags_json,
                provenance_summary_json,
                license_safety_result,
                export_eligible,
                ai_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    item.difficulty_level,
                    item.media_role,
                    item.confusion_relevance,
                    item.diagnostic_feature_visibility,
                    item.learning_suitability,
                    item.uncertainty_reason,
                    item.qualification_notes,
                    _json(item.qualification_flags),
                    _json(item.provenance_summary.model_dump(mode="json")),
                    item.license_safety_result,
                    int(item.export_eligible),
                    item.ai_confidence,
                )
                for item in resources
            ],
        )

    def save_review_items(
        self,
        review_items: Sequence[ReviewItem],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_review_items(review_items, connection=owned_connection)
            return

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

    def start_pipeline_run(
        self,
        *,
        run_id: str,
        source_mode: str,
        dataset_id: str,
        snapshot_id: str | None,
        started_at: datetime,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.start_pipeline_run(
                    run_id=run_id,
                    source_mode=source_mode,
                    dataset_id=dataset_id,
                    snapshot_id=snapshot_id,
                    started_at=started_at,
                    connection=owned_connection,
                )
            return

        connection.execute(
            """
            INSERT INTO pipeline_runs (
                run_id,
                source_mode,
                dataset_id,
                snapshot_id,
                schema_version,
                qualification_version,
                enrichment_version,
                export_version,
                started_at,
                completed_at,
                run_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'running')
            """,
            (
                run_id,
                source_mode,
                dataset_id,
                snapshot_id,
                SCHEMA_VERSION_LABEL,
                QUALIFICATION_VERSION,
                ENRICHMENT_VERSION,
                EXPORT_VERSION,
                started_at.isoformat(),
            ),
        )

    def complete_pipeline_run(
        self,
        *,
        run_id: str,
        completed_at: datetime,
        run_status: str = "completed",
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.complete_pipeline_run(
                    run_id=run_id,
                    completed_at=completed_at,
                    run_status=run_status,
                    connection=owned_connection,
                )
            return

        connection.execute(
            """
            UPDATE pipeline_runs
            SET completed_at = ?, run_status = ?
            WHERE run_id = ?
            """,
            (completed_at.isoformat(), run_status, run_id),
        )

    def append_run_history(
        self,
        *,
        run_id: str,
        governance_effective_at: datetime,
        canonical_taxa: Sequence[CanonicalTaxon],
        observations: Sequence[SourceObservation],
        media_assets: Sequence[MediaAsset],
        qualified_resources: Sequence[QualifiedResource],
        review_items: Sequence[ReviewItem],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.append_run_history(
                    run_id=run_id,
                    governance_effective_at=governance_effective_at,
                    canonical_taxa=canonical_taxa,
                    observations=observations,
                    media_assets=media_assets,
                    qualified_resources=qualified_resources,
                    review_items=review_items,
                    connection=owned_connection,
                )
            return

        connection.executemany(
            """
            INSERT INTO canonical_taxa_history (run_id, canonical_taxon_id, payload_json)
            VALUES (?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.canonical_taxon_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in canonical_taxa
            ],
        )
        connection.executemany(
            """
            INSERT INTO source_observations_history (
                run_id,
                observation_uid,
                source_name,
                source_observation_id,
                payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.observation_uid,
                    item.source_name,
                    item.source_observation_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in observations
            ],
        )
        connection.executemany(
            """
            INSERT INTO media_assets_history (
                run_id,
                media_id,
                source_name,
                source_media_id,
                payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.media_id,
                    item.source_name,
                    item.source_media_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in media_assets
            ],
        )
        connection.executemany(
            """
            INSERT INTO qualified_resources_history (run_id, qualified_resource_id, payload_json)
            VALUES (?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.qualified_resource_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in qualified_resources
            ],
        )
        connection.executemany(
            """
            INSERT INTO review_queue_history (run_id, review_item_id, payload_json)
            VALUES (?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.review_item_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in review_items
            ],
        )

        previous_canonical_taxa = self._load_latest_canonical_taxa_before_run(
            run_id=run_id,
            connection=connection,
        )
        governance_decisions = derive_canonical_governance_decisions(
            previous_taxa=previous_canonical_taxa,
            current_taxa=list(canonical_taxa),
            effective_at=governance_effective_at,
        )
        connection.executemany(
            """
            INSERT INTO canonical_change_events (
                change_event_id,
                run_id,
                canonical_taxon_id,
                event_type,
                source_name,
                effective_at,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"{run_id}:{decision.event.event_id}",
                    run_id,
                    decision.event.canonical_taxon_id,
                    decision.event.event_type,
                    decision.event.source_name,
                    decision.event.effective_at.isoformat(),
                    _json(
                        {
                            **decision.event.payload,
                            "signal_breakdown": decision.signal_breakdown.to_payload(),
                            "decision_reason": decision.decision_reason,
                            "source_delta": decision.source_delta.to_payload(),
                        }
                    ),
                    datetime.now(UTC).isoformat(),
                )
                for decision in governance_decisions
            ],
        )
        connection.executemany(
            """
            INSERT INTO canonical_governance_events (
                governance_event_id,
                run_id,
                canonical_taxon_id,
                event_type,
                source_name,
                effective_at,
                decision_status,
                decision_reason,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"{run_id}:{decision.event.event_id}",
                    run_id,
                    decision.event.canonical_taxon_id,
                    decision.event.event_type,
                    decision.event.source_name,
                    decision.event.effective_at.isoformat(),
                    decision.decision_status,
                    decision.decision_reason,
                    _json(
                        {
                            **decision.event.payload,
                            "signal_breakdown": decision.signal_breakdown.to_payload(),
                            "source_delta": decision.source_delta.to_payload(),
                        }
                    ),
                    datetime.now(UTC).isoformat(),
                )
                for decision in governance_decisions
            ],
        )

        governance_review_items = [
            CanonicalGovernanceReviewItem(
                governance_review_item_id=f"cgr:{run_id}:{decision.event.event_id}",
                run_id=run_id,
                governance_event_id=f"{run_id}:{decision.event.event_id}",
                canonical_taxon_id=decision.event.canonical_taxon_id,
                decision_status=decision.decision_status,
                reason_code=decision.decision_reason,
                review_note=(
                    "requires operator validation for ambiguous canonical transition: "
                    f"{decision.decision_reason}"
                ),
                review_status=ReviewStatus.OPEN,
                created_at=datetime.now(UTC),
            )
            for decision in governance_decisions
            if decision.decision_status == CanonicalGovernanceDecisionStatus.MANUAL_REVIEWED
        ]
        if governance_review_items:
            connection.executemany(
                """
                INSERT INTO canonical_governance_review_queue (
                    governance_review_item_id,
                    run_id,
                    governance_event_id,
                    canonical_taxon_id,
                    reason_code,
                    review_note,
                    review_status,
                    created_at,
                    resolved_at,
                    resolved_note,
                    resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.governance_review_item_id,
                        item.run_id,
                        item.governance_event_id,
                        item.canonical_taxon_id,
                        item.reason_code,
                        item.review_note,
                        item.review_status,
                        item.created_at.isoformat(),
                        item.resolved_at.isoformat() if item.resolved_at else None,
                        item.resolved_note,
                        item.resolved_by,
                    )
                    for item in governance_review_items
                ],
            )

    def fetch_summary(self, *, run_id: str | None = None) -> dict[str, int]:
        with self.connect() as connection:
            if run_id:
                table_mapping = {
                    "canonical_taxa": "canonical_taxa_history",
                    "source_observations": "source_observations_history",
                    "media_assets": "media_assets_history",
                    "qualified_resources": "qualified_resources_history",
                    "review_queue": "review_queue_history",
                }
                return {
                    key: connection.execute(
                        f"SELECT COUNT(*) AS count FROM {table_name} WHERE run_id = ?",
                        (run_id,),
                    ).fetchone()["count"]
                    for key, table_name in table_mapping.items()
                }

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

    def fetch_canonical_governance_review_queue(
        self,
        *,
        run_id: str | None = None,
        reason_code: str | None = None,
        review_status: str | None = None,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[str] = []
            if run_id:
                clauses.append("run_id = ?")
                params.append(run_id)
            if reason_code:
                clauses.append("reason_code = ?")
                params.append(reason_code)
            if review_status:
                clauses.append("review_status = ?")
                params.append(review_status)

            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT
                    governance_review_item_id,
                    run_id,
                    governance_event_id,
                    canonical_taxon_id,
                    reason_code,
                    review_note,
                    review_status,
                    created_at,
                    resolved_at,
                    resolved_note,
                    resolved_by
                FROM canonical_governance_review_queue
                {where_clause}
                ORDER BY created_at DESC, governance_review_item_id
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def resolve_canonical_governance_review_item(
        self,
        *,
        governance_review_item_id: str,
        resolved_note: str,
        resolved_by: str,
        resolved_at: datetime | None = None,
    ) -> dict[str, object]:
        if not governance_review_item_id.strip():
            raise ValueError("governance_review_item_id must not be blank")
        if not resolved_note.strip():
            raise ValueError("resolved_note must not be blank")
        if not resolved_by.strip():
            raise ValueError("resolved_by must not be blank")

        resolved_timestamp = resolved_at or datetime.now(UTC)
        with self.connect() as connection:
            current_row = connection.execute(
                """
                SELECT
                    governance_review_item_id,
                    run_id,
                    governance_event_id,
                    canonical_taxon_id,
                    reason_code,
                    review_note,
                    review_status,
                    created_at,
                    resolved_at,
                    resolved_note,
                    resolved_by
                FROM canonical_governance_review_queue
                WHERE governance_review_item_id = ?
                """,
                (governance_review_item_id,),
            ).fetchone()
            if current_row is None:
                raise ValueError(
                    "Unknown canonical governance review item: "
                    f"{governance_review_item_id}"
                )
            if current_row["review_status"] == ReviewStatus.CLOSED:
                raise ValueError(
                    "Canonical governance review item already closed: "
                    f"{governance_review_item_id}"
                )

            connection.execute(
                """
                UPDATE canonical_governance_review_queue
                SET
                    review_status = ?,
                    resolved_at = ?,
                    resolved_note = ?,
                    resolved_by = ?
                WHERE governance_review_item_id = ?
                """,
                (
                    ReviewStatus.CLOSED,
                    resolved_timestamp.isoformat(),
                    resolved_note,
                    resolved_by,
                    governance_review_item_id,
                ),
            )

            updated_row = connection.execute(
                """
                SELECT
                    governance_review_item_id,
                    run_id,
                    governance_event_id,
                    canonical_taxon_id,
                    reason_code,
                    review_note,
                    review_status,
                    created_at,
                    resolved_at,
                    resolved_note,
                    resolved_by
                FROM canonical_governance_review_queue
                WHERE governance_review_item_id = ?
                """,
                (governance_review_item_id,),
            ).fetchone()
            if updated_row is None:  # pragma: no cover - protected by primary key update.
                raise ValueError(
                    "Failed to load updated canonical governance review item: "
                    f"{governance_review_item_id}"
                )
            return dict(updated_row)

    def fetch_canonical_governance_review_backlog(
        self,
        *,
        run_id: str | None = None,
    ) -> dict[str, object]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[str] = []
            if run_id:
                clauses.append("run_id = ?")
                params.append(run_id)
            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            open_clause = (
                f"{where_clause} AND review_status = 'open'"
                if where_clause
                else "WHERE review_status = 'open'"
            )

            review_rows = connection.execute(
                f"""
                SELECT review_status, reason_code, COUNT(*) AS count
                FROM canonical_governance_review_queue
                {where_clause}
                GROUP BY review_status, reason_code
                ORDER BY review_status, reason_code
                """,
                params,
            ).fetchall()
            open_age_row = connection.execute(
                f"""
                SELECT
                    ROUND(
                        AVG((julianday('now') - julianday(created_at)) * 24.0),
                        2
                    ) AS avg_age_hours
                FROM canonical_governance_review_queue
                {open_clause}
                """,
                params,
            ).fetchone()

        open_count = 0
        resolved_count = 0
        open_by_reason: Counter[str] = Counter()
        resolved_by_reason: Counter[str] = Counter()
        for row in review_rows:
            count = int(row["count"])
            reason_code = str(row["reason_code"])
            if row["review_status"] == ReviewStatus.OPEN:
                open_count += count
                open_by_reason[reason_code] += count
            elif row["review_status"] == ReviewStatus.CLOSED:
                resolved_count += count
                resolved_by_reason[reason_code] += count

        return {
            "open_count": open_count,
            "resolved_count": resolved_count,
            "avg_open_age_hours": (
                float(open_age_row["avg_age_hours"]) if open_age_row["avg_age_hours"] else 0.0
            ),
            "open_by_reason": dict(sorted(open_by_reason.items())),
            "resolved_by_reason": dict(sorted(resolved_by_reason.items())),
        }

    def fetch_canonical_state_events(
        self,
        *,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT
                        state_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        payload_json,
                        created_at
                    FROM canonical_state_events
                    WHERE run_id = ?
                    ORDER BY created_at DESC, state_event_id
                    LIMIT ?
                    """,
                    (run_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        state_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        payload_json,
                        created_at
                    FROM canonical_state_events
                    ORDER BY created_at DESC, state_event_id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]

    def fetch_canonical_change_events(
        self,
        *,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT
                        change_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        payload_json,
                        created_at
                    FROM canonical_change_events
                    WHERE run_id = ?
                    ORDER BY created_at DESC, change_event_id
                    LIMIT ?
                    """,
                    (run_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        change_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        payload_json,
                        created_at
                    FROM canonical_change_events
                    ORDER BY created_at DESC, change_event_id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]

    def fetch_canonical_governance_events(
        self,
        *,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT
                        governance_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        decision_status,
                        decision_reason,
                        payload_json,
                        created_at
                    FROM canonical_governance_events
                    WHERE run_id = ?
                    ORDER BY created_at DESC, governance_event_id
                    LIMIT ?
                    """,
                    (run_id, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        governance_event_id,
                        run_id,
                        canonical_taxon_id,
                        event_type,
                        source_name,
                        effective_at,
                        decision_status,
                        decision_reason,
                        payload_json,
                        created_at
                    FROM canonical_governance_events
                    ORDER BY created_at DESC, governance_event_id
                    LIMIT ?
                    """,
                    (limit,),
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

    def fetch_qualification_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM qualified_resources_history
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchall()
                payloads = [
                    json.loads(str(row["payload_json"]))
                    for row in rows
                ]
            else:
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
                payloads = [
                    {
                        "qualification_status": row["qualification_status"],
                        "provenance_summary": json.loads(str(row["provenance_summary_json"])),
                        "qualification_flags": json.loads(str(row["qualification_flags_json"])),
                        "license_safety_result": row["license_safety_result"],
                        "export_eligible": bool(row["export_eligible"]),
                    }
                    for row in rows
                ]
            accepted_resources = 0
            rejected_resources = 0
            review_required_resources = 0
            ai_qualified_images = 0
            exportable_resources = 0
            flag_counts: Counter[str] = Counter()
            license_distribution: Counter[str] = Counter()
            ai_model_distribution: Counter[str] = Counter()
            for payload in payloads:
                qualification_status = str(payload.get("qualification_status", ""))
                if qualification_status == "accepted":
                    accepted_resources += 1
                elif qualification_status == "rejected":
                    rejected_resources += 1
                elif qualification_status == "review_required":
                    review_required_resources += 1
                provenance = payload.get("provenance_summary")
                if not isinstance(provenance, dict):
                    provenance = {}
                if provenance.get("ai_model"):
                    ai_qualified_images += 1
                    ai_model_distribution[str(provenance["ai_model"])] += 1
                if bool(payload.get("export_eligible")):
                    exportable_resources += 1
                license_distribution[str(payload.get("license_safety_result", "unknown"))] += 1
                qualification_flags = payload.get("qualification_flags")
                if not isinstance(qualification_flags, list):
                    qualification_flags = []
                for flag in qualification_flags:
                    flag_counts[flag] += 1

            if run_id:
                review_queue_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM review_queue_history
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()["count"]
            else:
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

    def fetch_run_level_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        summary = self.fetch_summary(run_id=run_id)
        qualification = self.fetch_qualification_metrics(run_id=run_id)
        with self.connect() as connection:
            governance_where_clause = "WHERE run_id = ?" if run_id else ""
            governance_params: tuple[object, ...] = (run_id,) if run_id else ()
            governance_rows = connection.execute(
                f"""
                SELECT decision_status, decision_reason, COUNT(*) AS count
                FROM canonical_governance_events
                {governance_where_clause}
                GROUP BY decision_status, decision_reason
                ORDER BY decision_status, decision_reason
                """,
                governance_params,
            ).fetchall()
            if run_id:
                review_rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM review_queue_history
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchall()
                review_payloads = [json.loads(str(row["payload_json"])) for row in review_rows]
                open_review_items = [
                    item
                    for item in review_payloads
                    if str(item.get("review_status") or "") == "open"
                ]
                open_review_count = len(open_review_items)
                if open_review_items:
                    age_hours_values: list[float] = []
                    now = datetime.now(UTC)
                    for payload in open_review_items:
                        created_at_raw = payload.get("created_at")
                        if not isinstance(created_at_raw, str):
                            continue
                        try:
                            created_at = datetime.fromisoformat(created_at_raw)
                        except ValueError:
                            continue
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=UTC)
                        age_hours_values.append((now - created_at).total_seconds() / 3600.0)
                    avg_review_age_hours = (
                        round(sum(age_hours_values) / len(age_hours_values), 2)
                        if age_hours_values
                        else 0.0
                    )
                else:
                    avg_review_age_hours = 0.0
            else:
                review_age_row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS open_count,
                        ROUND(
                            AVG((julianday('now') - julianday(created_at)) * 24.0),
                            2
                        ) AS avg_age_hours
                    FROM review_queue
                    WHERE review_status = 'open'
                    """
                ).fetchone()
                open_review_count = int(review_age_row["open_count"] or 0)
                avg_review_age_hours = (
                    float(review_age_row["avg_age_hours"])
                    if review_age_row["avg_age_hours"] is not None
                    else 0.0
                )

        governance_status_counts: Counter[str] = Counter()
        governance_reason_counts: Counter[str] = Counter()
        for row in governance_rows:
            governance_status_counts[str(row["decision_status"])] += int(row["count"])
            governance_reason_counts[str(row["decision_reason"])] += int(row["count"])
        governance_backlog = self.fetch_canonical_governance_review_backlog(run_id=run_id)

        ai_qualified_images = int(qualification["ai_qualified_images"])
        estimated_ai_cost_eur = round(ai_qualified_images * 0.0012, 4)
        return {
            "run_id": run_id,
            "volume": {
                "canonical_taxa": summary["canonical_taxa"],
                "source_observations": summary["source_observations"],
                "media_assets": summary["media_assets"],
                "qualified_resources": summary["qualified_resources"],
                "exportable_resources": qualification["exportable_resources"],
            },
            "quality": {
                "accepted_resources": qualification["accepted_resources"],
                "review_required_resources": qualification["review_required_resources"],
                "rejected_resources": qualification["rejected_resources"],
                "top_rejection_flags": qualification["top_rejection_flags"],
            },
            "governance": {
                "decision_status_counts": dict(sorted(governance_status_counts.items())),
                "decision_reason_counts": dict(sorted(governance_reason_counts.items())),
                "open_governance_review_items": governance_backlog["open_count"],
                "resolved_governance_review_items": governance_backlog["resolved_count"],
                "avg_open_governance_review_age_hours": governance_backlog["avg_open_age_hours"],
                "open_governance_backlog_by_reason": governance_backlog["open_by_reason"],
                "resolved_governance_backlog_by_reason": governance_backlog["resolved_by_reason"],
            },
            "review_load": {
                "open_review_queue_items": open_review_count,
                "avg_open_review_age_hours": avg_review_age_hours,
            },
            "cost": {
                "ai_qualified_images": ai_qualified_images,
                "estimated_ai_cost_eur": estimated_ai_cost_eur,
            },
        }

    def _load_latest_canonical_taxa_before_run(
        self,
        *,
        run_id: str,
        connection: sqlite3.Connection,
    ) -> list[CanonicalTaxon]:
        row = connection.execute(
            """
            SELECT run_id
            FROM pipeline_runs
            WHERE run_id != ? AND run_status = 'completed' AND completed_at IS NOT NULL
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return []

        previous_run_id = str(row["run_id"])
        payload_rows = connection.execute(
            """
            SELECT payload_json
            FROM canonical_taxa_history
            WHERE run_id = ?
            ORDER BY canonical_taxon_id
            """,
            (previous_run_id,),
        ).fetchall()
        return [
            CanonicalTaxon(**json.loads(str(payload_row["payload_json"])))
            for payload_row in payload_rows
        ]

    def _requires_schema_migration(self) -> bool:
        if not self.db_path.exists():
            return False
        with self.connect() as connection:
            current_version = read_user_version(connection)
            has_tables_now = has_user_tables(connection)
        return has_tables_now and current_version != SCHEMA_VERSION


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _build_canonical_relationships_and_state_events(
    taxa: Sequence[CanonicalTaxon],
) -> tuple[list[CanonicalTaxonRelationship], list[CanonicalTaxonEvent]]:
    now = datetime.now(UTC)
    relationships: list[CanonicalTaxonRelationship] = []
    state_events: list[CanonicalTaxonEvent] = []

    for taxon in sorted(taxa, key=lambda item: item.canonical_taxon_id):
        state_events.append(
            CanonicalTaxonEvent(
                event_id=f"state:{taxon.canonical_taxon_id}:upsert",
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
    return deduped_relationships, state_events
