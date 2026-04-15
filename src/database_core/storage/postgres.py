from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

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
    PackRevisionParameters,
    PlayableItem,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.storage.confusion_store import PostgresConfusionStore
from database_core.storage.enrichment_store import PostgresEnrichmentStore
from database_core.storage.inspection_store import PostgresInspectionStore
from database_core.storage.pack_store import MIN_PACK_TOTAL_QUESTIONS, PostgresPackStore
from database_core.storage.playable_store import PostgresPlayableStore
from database_core.storage.postgres_migrations import (
    apply_migrations,
    current_schema_version,
    reset_schema,
)
from database_core.versioning import (
    ENRICHMENT_VERSION,
    EXPORT_VERSION,
    QUALIFICATION_VERSION,
    SCHEMA_VERSION,
    SCHEMA_VERSION_LABEL,
)


class RepositorySchemaVersionMismatchError(ValueError):
    """Raised when an existing PostgreSQL schema has a schema version mismatch."""


class PostgresStorageInternal:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.pack_store = PostgresPackStore(connect=self.connect)
        self.enrichment_store = PostgresEnrichmentStore(
            connect=self.connect,
            pack_store=self.pack_store,
        )
        self.confusion_store = PostgresConfusionStore(connect=self.connect)
        self.inspection_store = PostgresInspectionStore(connect=self.connect)
        self.playable_store = PostgresPlayableStore(connect=self.connect)

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        self._ensure_postgis_schema_in_search_path(connection)
        try:
            yield connection
        except Exception:  # pragma: no cover - rollback path is validated in integration tests.
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _ensure_postgis_schema_in_search_path(self, connection: psycopg.Connection) -> None:
        extension_row = connection.execute(
            """
            SELECT n.nspname AS schema_name
            FROM pg_extension e
            JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE e.extname = 'postgis'
            """
        ).fetchone()
        if extension_row is None:
            return

        extension_schema = str(extension_row["schema_name"])
        schemas_row = connection.execute(
            "SELECT current_schemas(false) AS schemas"
        ).fetchone()
        current_schemas = [str(schema_name) for schema_name in schemas_row["schemas"]]
        if extension_schema in current_schemas:
            return

        resolved_schemas = [*current_schemas, extension_schema]
        connection.execute(
            sql.SQL("SET search_path TO {}").format(
                sql.SQL(", ").join(sql.Identifier(schema_name) for schema_name in resolved_schemas)
            )
        )

    def initialize(self, *, allow_schema_reset: bool = False) -> None:
        with self.connect() as connection:
            version_before = current_schema_version(connection)
            if version_before and version_before != SCHEMA_VERSION and not allow_schema_reset:
                raise RepositorySchemaVersionMismatchError(
                    "Database schema version mismatch for "
                    f"{self.database_url}. Expected version={SCHEMA_VERSION}, "
                    f"got {version_before}. Run `database-core migrate --database-url ...` "
                    "or use explicit local-dev reset (allow_schema_reset=True)."
                )
            if version_before and version_before != SCHEMA_VERSION and allow_schema_reset:
                reset_schema(connection)
            apply_migrations(connection, target_version=SCHEMA_VERSION)

    def migrate_to_latest(self) -> tuple[int, ...]:
        with self.connect() as connection:
            applied_versions = apply_migrations(connection, target_version=SCHEMA_VERSION)
            if current_schema_version(connection) != SCHEMA_VERSION:
                raise RepositorySchemaVersionMismatchError(
                    "Database migration did not reach expected schema version "
                    f"{SCHEMA_VERSION} for {self.database_url}"
                )
        return applied_versions

    def current_schema_version(self) -> int:
        with self.connect() as connection:
            return current_schema_version(connection)

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
                WHERE run_id = %s
                ORDER BY canonical_taxon_id
                """,
                (str(row["run_id"]),),
            ).fetchall()
            return [
                CanonicalTaxon(**json.loads(str(payload_row["payload_json"])))
                for payload_row in payload_rows
            ]

    def reset_materialized_state(self, *, connection: psycopg.Connection | None = None) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.reset_materialized_state(connection=owned_connection)
            return

        for statement in (
            "DELETE FROM canonical_taxon_relationships",
            "DELETE FROM review_queue",
            "DELETE FROM qualified_resources",
            "DELETE FROM media_assets",
            "DELETE FROM source_observations",
            "DELETE FROM canonical_taxa",
        ):
            connection.execute(statement)

    def reset(self, *, connection: psycopg.Connection | None = None) -> None:
        self.reset_materialized_state(connection=connection)

    def save_canonical_taxa(
        self,
        taxa: Sequence[CanonicalTaxon],
        *,
        run_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_canonical_taxa(taxa, run_id=run_id, connection=owned_connection)
            return
        if run_id is None:
            raise ValueError("run_id is required to persist canonical state events")
        connection.execute("DELETE FROM canonical_taxa")

        _executemany(connection, 
            """
            INSERT INTO canonical_taxa (
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
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
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
                    item.bird_scope_compatible,
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
        _executemany(connection, 
            """
            INSERT INTO canonical_taxon_relationships (
                source_canonical_taxon_id,
                relationship_type,
                target_canonical_taxon_id,
                source_name,
                created_at
            ) VALUES (%s, %s, %s, %s, %s)
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
        _executemany(connection, 
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_source_observations(observations, connection=owned_connection)
            return
        connection.execute("DELETE FROM source_observations")

        _executemany(connection, 
            """
            INSERT INTO source_observations (
                observation_uid,
                source_name,
                source_observation_id,
                source_taxon_id,
                observed_at,
                location_json,
                source_quality_json,
                raw_payload_ref,
                canonical_taxon_id,
                country_code,
                location_point,
                location_bbox,
                location_radius_meters
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE
                    WHEN %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                    THEN ST_SetSRID(
                        ST_MakePoint(%s::DOUBLE PRECISION, %s::DOUBLE PRECISION),
                        4326
                    )
                    ELSE NULL
                END,
                NULL,
                NULL
            )
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
                    item.location.country_code,
                    item.location.longitude,
                    item.location.latitude,
                    item.location.longitude,
                    item.location.latitude,
                )
                for item in observations
            ],
        )

    def save_media_assets(
        self,
        media_assets: Sequence[MediaAsset],
        *,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_media_assets(media_assets, connection=owned_connection)
            return
        connection.execute("DELETE FROM media_assets")

        _executemany(connection, 
            """
            INSERT INTO media_assets (
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_qualified_resources(resources, connection=owned_connection)
            return
        connection.execute("DELETE FROM qualified_resources")

        _executemany(connection, 
            """
            INSERT INTO qualified_resources (
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
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
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
                    item.export_eligible,
                    item.ai_confidence,
                )
                for item in resources
            ],
        )

    def save_review_items(
        self,
        review_items: Sequence[ReviewItem],
        *,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_review_items(review_items, connection=owned_connection)
            return
        connection.execute("DELETE FROM review_queue")

        _executemany(connection, 
            """
            INSERT INTO review_queue (
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    def save_playable_items(
        self,
        playable_items: Sequence[PlayableItem],
        *,
        run_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> None:
        return self.playable_store.save_playable_items(
            playable_items,
            run_id=run_id,
            connection=connection,
        )

    def start_pipeline_run(
        self,
        *,
        run_id: str,
        source_mode: str,
        dataset_id: str,
        snapshot_id: str | None,
        started_at: datetime,
        connection: psycopg.Connection | None = None,
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, 'running')
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
        connection: psycopg.Connection | None = None,
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
            SET completed_at = %s, run_status = %s
            WHERE run_id = %s
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
        playable_items: Sequence[PlayableItem] = (),
        connection: psycopg.Connection | None = None,
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
                    playable_items=playable_items,
                    connection=owned_connection,
                )
            return

        _executemany(connection, 
            """
            INSERT INTO canonical_taxa_history (run_id, canonical_taxon_id, payload_json)
            VALUES (%s, %s, %s)
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
        _executemany(connection, 
            """
            INSERT INTO source_observations_history (
                run_id,
                observation_uid,
                source_name,
                source_observation_id,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s)
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
        _executemany(connection, 
            """
            INSERT INTO media_assets_history (
                run_id,
                media_id,
                source_name,
                source_media_id,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s)
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
        _executemany(connection, 
            """
            INSERT INTO qualified_resources_history (run_id, qualified_resource_id, payload_json)
            VALUES (%s, %s, %s)
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
        _executemany(connection, 
            """
            INSERT INTO review_queue_history (run_id, review_item_id, payload_json)
            VALUES (%s, %s, %s)
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
        _executemany(
            connection,
            """
            INSERT INTO playable_items_history (run_id, playable_item_id, payload_json)
            VALUES (%s, %s, %s)
            """,
            [
                (
                    run_id,
                    item.playable_item_id,
                    _json(item.model_dump(mode="json")),
                )
                for item in playable_items
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
        _executemany(connection, 
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        _executemany(connection, 
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            _executemany(connection, 
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    "playable_items": "playable_items_history",
                }
                return {
                    key: connection.execute(
                        f"SELECT COUNT(*) AS count FROM {table_name} WHERE run_id = %s",
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
                "playable_items",
                "compiled_pack_builds",
                "pack_materializations",
                "enrichment_requests",
                "enrichment_executions",
                "confusion_events",
                "confusion_aggregates_global",
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
                clauses.append("review_reason_code = %s")
                params.append(review_reason_code)
            if stage_name:
                clauses.append("stage_name = %s")
                params.append(stage_name)
            if review_status:
                clauses.append("review_status = %s")
                params.append(review_status)
            if canonical_taxon_id:
                clauses.append("canonical_taxon_id = %s")
                params.append(canonical_taxon_id)
            if priority:
                clauses.append("priority = %s")
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
                clauses.append("run_id = %s")
                params.append(run_id)
            if reason_code:
                clauses.append("reason_code = %s")
                params.append(reason_code)
            if review_status:
                clauses.append("review_status = %s")
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
                WHERE governance_review_item_id = %s
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
                    review_status = %s,
                    resolved_at = %s,
                    resolved_note = %s,
                    resolved_by = %s
                WHERE governance_review_item_id = %s
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
                WHERE governance_review_item_id = %s
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
                clauses.append("run_id = %s")
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
                        AVG((EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0) * 24.0),
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
                    WHERE run_id = %s
                    ORDER BY created_at DESC, state_event_id
                    LIMIT %s
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
                    LIMIT %s
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
                    WHERE run_id = %s
                    ORDER BY created_at DESC, change_event_id
                    LIMIT %s
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
                    LIMIT %s
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
                    WHERE run_id = %s
                    ORDER BY created_at DESC, governance_event_id
                    LIMIT %s
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
                    LIMIT %s
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
                WHERE export_eligible = TRUE
                ORDER BY qualified_resource_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_source_observations_in_bbox(
        self,
        *,
        min_longitude: float,
        min_latitude: float,
        max_longitude: float,
        max_latitude: float,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observation_uid,
                    source_name,
                    source_observation_id,
                    country_code
                FROM source_observations
                WHERE (
                    location_bbox IS NOT NULL
                    AND ST_Intersects(
                        location_bbox,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    )
                ) OR (
                    location_point IS NOT NULL
                    AND ST_Intersects(
                        location_point,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    )
                )
                ORDER BY source_observation_id
                """,
                (
                    min_longitude,
                    min_latitude,
                    max_longitude,
                    max_latitude,
                    min_longitude,
                    min_latitude,
                    max_longitude,
                    max_latitude,
                ),
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_source_observations_within_radius(
        self,
        *,
        longitude: float,
        latitude: float,
        radius_meters: float,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    observation_uid,
                    source_name,
                    source_observation_id,
                    country_code
                FROM source_observations
                WHERE location_point IS NOT NULL
                  AND ST_DWithin(
                        location_point::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                  )
                ORDER BY source_observation_id
                """,
                (longitude, latitude, radius_meters),
            ).fetchall()
            return [dict(row) for row in rows]

    def fetch_playable_corpus(
        self,
        *,
        canonical_taxon_id: str | None = None,
        country_code: str | None = None,
        difficulty_level: str | None = None,
        media_role: str | None = None,
        learning_suitability: str | None = None,
        confusion_relevance: str | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        point_radius: tuple[float, float, float] | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.playable_store.fetch_playable_corpus(
            canonical_taxon_id=canonical_taxon_id,
            country_code=country_code,
            difficulty_level=difficulty_level,
            media_role=media_role,
            learning_suitability=learning_suitability,
            confusion_relevance=confusion_relevance,
            observed_from=observed_from,
            observed_to=observed_to,
            bbox=bbox,
            point_radius=point_radius,
            limit=limit,
        )
    def fetch_playable_corpus_payload(
        self,
        *,
        canonical_taxon_id: str | None = None,
        country_code: str | None = None,
        difficulty_level: str | None = None,
        media_role: str | None = None,
        learning_suitability: str | None = None,
        confusion_relevance: str | None = None,
        observed_from: datetime | None = None,
        observed_to: datetime | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        point_radius: tuple[float, float, float] | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        return self.playable_store.fetch_playable_corpus_payload(
            canonical_taxon_id=canonical_taxon_id,
            country_code=country_code,
            difficulty_level=difficulty_level,
            media_role=media_role,
            learning_suitability=learning_suitability,
            confusion_relevance=confusion_relevance,
            observed_from=observed_from,
            observed_to=observed_to,
            bbox=bbox,
            point_radius=point_radius,
            limit=limit,
        )
    def fetch_playable_invalidations(
        self,
        *,
        invalidated_run_id: str | None = None,
        invalidation_reason: str | None = None,
        lifecycle_status: str = "invalidated",
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.playable_store.fetch_playable_invalidations(
            invalidated_run_id=invalidated_run_id,
            invalidation_reason=invalidation_reason,
            lifecycle_status=lifecycle_status,
            limit=limit,
        )
    def create_pack(
        self,
        *,
        parameters: PackRevisionParameters | dict[str, object],
        pack_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.pack_store.create_pack(
            parameters=parameters,
            pack_id=pack_id,
            connection=connection,
        )

    def revise_pack(
        self,
        *,
        pack_id: str,
        parameters: PackRevisionParameters | dict[str, object],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.pack_store.revise_pack(
            pack_id=pack_id,
            parameters=parameters,
            connection=connection,
        )

    def fetch_pack_specs(
        self,
        *,
        pack_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.pack_store.fetch_pack_specs(pack_id=pack_id, limit=limit)

    def fetch_pack_revisions(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.pack_store.fetch_pack_revisions(
            pack_id=pack_id,
            revision=revision,
            limit=limit,
        )

    def diagnose_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.pack_store.diagnose_pack(
            pack_id=pack_id,
            revision=revision,
            connection=connection,
        )

    def compile_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.pack_store.compile_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
            connection=connection,
        )

    def materialize_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        purpose: str = "assignment",
        ttl_hours: int | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.pack_store.materialize_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
            purpose=purpose,
            ttl_hours=ttl_hours,
            connection=connection,
        )

    def fetch_pack_diagnostics(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.pack_store.fetch_pack_diagnostics(
            pack_id=pack_id,
            revision=revision,
            limit=limit,
        )

    def fetch_compiled_pack_builds(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.pack_store.fetch_compiled_pack_builds(
            pack_id=pack_id,
            revision=revision,
            limit=limit,
        )

    def fetch_pack_materializations(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        purpose: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        return self.pack_store.fetch_pack_materializations(
            pack_id=pack_id,
            revision=revision,
            purpose=purpose,
            limit=limit,
        )

    def enqueue_enrichment_for_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.enrichment_store.enqueue_enrichment_for_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
            connection=connection,
        )

    def create_or_merge_enrichment_request(
        self,
        *,
        pack_id: str,
        revision: int,
        reason_code: str,
        targets: Sequence[dict[str, object]],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.enrichment_store.create_or_merge_enrichment_request(
            pack_id=pack_id,
            revision=revision,
            reason_code=reason_code,
            targets=targets,
            connection=connection,
        )

    def fetch_enrichment_requests(
        self,
        *,
        enrichment_request_id: str | None = None,
        request_status: str | None = None,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        return self.enrichment_store.fetch_enrichment_requests(
            enrichment_request_id=enrichment_request_id,
            request_status=request_status,
            pack_id=pack_id,
            revision=revision,
            limit=limit,
            connection=connection,
        )

    def fetch_enrichment_request_targets(
        self,
        *,
        enrichment_request_id: str,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        return self.enrichment_store.fetch_enrichment_request_targets(
            enrichment_request_id=enrichment_request_id,
            connection=connection,
        )

    def fetch_enrichment_executions(
        self,
        *,
        enrichment_request_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        return self.enrichment_store.fetch_enrichment_executions(
            enrichment_request_id=enrichment_request_id,
            limit=limit,
            connection=connection,
        )

    def record_enrichment_execution(
        self,
        *,
        enrichment_request_id: str,
        execution_status: str,
        execution_context: dict[str, object] | None = None,
        error_info: str | None = None,
        trigger_recompile: bool = False,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.enrichment_store.record_enrichment_execution(
            enrichment_request_id=enrichment_request_id,
            execution_status=execution_status,
            execution_context=execution_context,
            error_info=error_info,
            trigger_recompile=trigger_recompile,
            connection=connection,
        )

    def ingest_confusion_batch(
        self,
        *,
        batch_id: str,
        events: Sequence[dict[str, object]],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.confusion_store.ingest_confusion_batch(
            batch_id=batch_id,
            events=events,
            connection=connection,
        )

    def fetch_confusion_events(
        self,
        *,
        batch_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        return self.confusion_store.fetch_confusion_events(
            batch_id=batch_id,
            limit=limit,
            connection=connection,
        )

    def recompute_confusion_aggregates_global(
        self,
        *,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        return self.confusion_store.recompute_confusion_aggregates_global(
            connection=connection,
        )

    def fetch_confusion_aggregates_global(
        self,
        *,
        taxon_confused_for_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        return self.confusion_store.fetch_confusion_aggregates_global(
            taxon_confused_for_id=taxon_confused_for_id,
            limit=limit,
            connection=connection,
        )

    def fetch_enrichment_queue_metrics(self) -> dict[str, object]:
        return self.enrichment_store.fetch_enrichment_queue_metrics()

    def fetch_confusion_metrics(self, *, top_pair_limit: int = 5) -> dict[str, object]:
        return self.confusion_store.fetch_confusion_metrics(top_pair_limit=top_pair_limit)

    def fetch_qualification_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        return self.inspection_store.fetch_qualification_metrics(run_id=run_id)

    def fetch_run_level_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        summary = self.fetch_summary(run_id=run_id)
        qualification = self.inspection_store.fetch_qualification_metrics(run_id=run_id)
        with self.connect() as connection:
            governance_where_clause = "WHERE run_id = %s" if run_id else ""
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
                    WHERE run_id = %s
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
                            AVG((EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0) * 24.0),
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
        connection: psycopg.Connection,
    ) -> list[CanonicalTaxon]:
        row = connection.execute(
            """
            SELECT run_id
            FROM pipeline_runs
            WHERE run_id != %s AND run_status = 'completed' AND completed_at IS NOT NULL
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
            WHERE run_id = %s
            ORDER BY canonical_taxon_id
            """,
            (previous_run_id,),
        ).fetchall()
        return [
            CanonicalTaxon(**json.loads(str(payload_row["payload_json"])))
            for payload_row in payload_rows
        ]

def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _executemany(
    connection: psycopg.Connection,
    query: str,
    params_seq: Sequence[tuple[object, ...]],
) -> None:
    if not params_seq:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, params_seq)



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
