from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from database_core.domain.canonical_governance import derive_canonical_governance_decisions
from database_core.domain.enums import (
    CanonicalChangeRelationType,
    CanonicalEventType,
    CanonicalGovernanceDecisionStatus,
    EnrichmentExecutionStatus,
    EnrichmentRequestReasonCode,
    EnrichmentRequestStatus,
    EnrichmentTargetResourceType,
    PackCompilationReasonCode,
    PackMaterializationPurpose,
    ReviewStatus,
)
from database_core.domain.models import (
    CanonicalGovernanceReviewItem,
    CanonicalTaxon,
    CanonicalTaxonEvent,
    CanonicalTaxonRelationship,
    CompiledPackBuild,
    CompiledPackQuestion,
    EnrichmentExecution,
    EnrichmentRequest,
    EnrichmentRequestTarget,
    MaterializedPack,
    MediaAsset,
    PackCompilationAttempt,
    PackCompilationDeficit,
    PackRevision,
    PackRevisionParameters,
    PackSpec,
    PackTaxonDeficit,
    PlayableItem,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.pack import (
    validate_compiled_pack,
    validate_pack_diagnostic,
    validate_pack_materialization,
    validate_pack_spec,
)
from database_core.playable import validate_playable_corpus
from database_core.storage.postgres_migrations import (
    apply_migrations,
    current_schema_version,
    reset_schema,
)
from database_core.versioning import (
    COMPILED_PACK_VERSION,
    ENRICHMENT_VERSION,
    EXPORT_VERSION,
    PACK_DIAGNOSTIC_VERSION,
    PACK_MATERIALIZATION_VERSION,
    PACK_SPEC_VERSION,
    PLAYABLE_CORPUS_VERSION,
    QUALIFICATION_VERSION,
    SCHEMA_VERSION,
    SCHEMA_VERSION_LABEL,
)


class RepositorySchemaVersionMismatchError(ValueError):
    """Raised when an existing PostgreSQL schema has a schema version mismatch."""


MIN_PACK_TAXA_SERVED = 10
MIN_PACK_MEDIA_PER_TAXON = 2
MIN_PACK_TOTAL_QUESTIONS = 20


class PostgresRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
            "DELETE FROM playable_items",
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
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self.connect() as owned_connection:
                self.save_playable_items(playable_items, connection=owned_connection)
            return
        connection.execute("DELETE FROM playable_items")

        _executemany(
            connection,
            """
            INSERT INTO playable_items (
                playable_item_id,
                run_id,
                qualified_resource_id,
                canonical_taxon_id,
                media_asset_id,
                source_observation_uid,
                source_name,
                source_observation_id,
                source_media_id,
                scientific_name,
                common_names_i18n_json,
                difficulty_level,
                media_role,
                learning_suitability,
                confusion_relevance,
                diagnostic_feature_visibility,
                similar_taxon_ids_json,
                what_to_look_at_specific_json,
                what_to_look_at_general_json,
                confusion_hint,
                country_code,
                observed_at,
                location_point,
                location_bbox,
                location_radius_meters
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s,
                CASE
                    WHEN %s::DOUBLE PRECISION IS NOT NULL AND %s::DOUBLE PRECISION IS NOT NULL
                    THEN ST_SetSRID(
                        ST_MakePoint(%s::DOUBLE PRECISION, %s::DOUBLE PRECISION),
                        4326
                    )
                    ELSE NULL
                END,
                CASE
                    WHEN %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                    THEN ST_MakeEnvelope(
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        4326
                    )
                    ELSE NULL
                END,
                %s
            )
            """,
            [
                (
                    item.playable_item_id,
                    item.run_id,
                    item.qualified_resource_id,
                    item.canonical_taxon_id,
                    item.media_asset_id,
                    item.source_observation_uid,
                    item.source_name,
                    item.source_observation_id,
                    item.source_media_id,
                    item.scientific_name,
                    _json(item.common_names_i18n),
                    item.difficulty_level,
                    item.media_role,
                    item.learning_suitability,
                    item.confusion_relevance,
                    item.diagnostic_feature_visibility,
                    _json(item.similar_taxon_ids),
                    _json(item.what_to_look_at_specific),
                    _json(item.what_to_look_at_general),
                    item.confusion_hint,
                    item.country_code,
                    item.observed_at.isoformat() if item.observed_at else None,
                    item.location_point.longitude if item.location_point else None,
                    item.location_point.latitude if item.location_point else None,
                    item.location_point.longitude if item.location_point else None,
                    item.location_point.latitude if item.location_point else None,
                    item.location_bbox.min_longitude if item.location_bbox else None,
                    item.location_bbox.min_latitude if item.location_bbox else None,
                    item.location_bbox.max_longitude if item.location_bbox else None,
                    item.location_bbox.max_latitude if item.location_bbox else None,
                    item.location_bbox.min_longitude if item.location_bbox else None,
                    item.location_bbox.min_latitude if item.location_bbox else None,
                    item.location_bbox.max_longitude if item.location_bbox else None,
                    item.location_bbox.max_latitude if item.location_bbox else None,
                    item.location_radius_meters,
                )
                for item in playable_items
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
        with self.connect() as connection:
            where_clauses: list[str] = []
            params: list[object] = []
            if canonical_taxon_id:
                where_clauses.append("canonical_taxon_id = %s")
                params.append(canonical_taxon_id)
            if country_code:
                where_clauses.append("country_code = %s")
                params.append(country_code)
            if difficulty_level:
                where_clauses.append("difficulty_level = %s")
                params.append(difficulty_level)
            if media_role:
                where_clauses.append("media_role = %s")
                params.append(media_role)
            if learning_suitability:
                where_clauses.append("learning_suitability = %s")
                params.append(learning_suitability)
            if confusion_relevance:
                where_clauses.append("confusion_relevance = %s")
                params.append(confusion_relevance)
            if observed_from:
                where_clauses.append("observed_at >= %s")
                params.append(observed_from.isoformat())
            if observed_to:
                where_clauses.append("observed_at <= %s")
                params.append(observed_to.isoformat())
            if bbox is not None:
                where_clauses.append(
                    """
                    (
                        (
                            location_bbox IS NOT NULL
                            AND ST_Intersects(
                                location_bbox,
                                ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                            )
                        )
                        OR
                        (
                            location_point IS NOT NULL
                            AND ST_Intersects(
                                location_point,
                                ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                            )
                        )
                    )
                    """
                )
                min_longitude, min_latitude, max_longitude, max_latitude = bbox
                params.extend(
                    [
                        min_longitude,
                        min_latitude,
                        max_longitude,
                        max_latitude,
                        min_longitude,
                        min_latitude,
                        max_longitude,
                        max_latitude,
                    ]
                )
            if point_radius is not None:
                longitude, latitude, radius_meters = point_radius
                where_clauses.append(
                    """
                    location_point IS NOT NULL
                    AND ST_DWithin(
                        location_point::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                    )
                    """
                )
                params.extend([longitude, latitude, radius_meters])

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            rows = connection.execute(
                f"""
                SELECT
                    playable_item_id,
                    run_id,
                    qualified_resource_id,
                    canonical_taxon_id,
                    media_asset_id,
                    source_observation_uid,
                    source_name,
                    source_observation_id,
                    source_media_id,
                    scientific_name,
                    common_names_i18n_json,
                    difficulty_level,
                    media_role,
                    learning_suitability,
                    confusion_relevance,
                    diagnostic_feature_visibility,
                    similar_taxon_ids_json,
                    what_to_look_at_specific_json,
                    what_to_look_at_general_json,
                    confusion_hint,
                    country_code,
                    observed_at,
                    CASE
                        WHEN location_point IS NULL THEN NULL
                        ELSE ST_X(location_point)
                    END AS location_longitude,
                    CASE
                        WHEN location_point IS NULL THEN NULL
                        ELSE ST_Y(location_point)
                    END AS location_latitude,
                    CASE
                        WHEN location_bbox IS NULL THEN NULL
                        ELSE ST_XMin(location_bbox)
                    END AS bbox_min_longitude,
                    CASE
                        WHEN location_bbox IS NULL THEN NULL
                        ELSE ST_YMin(location_bbox)
                    END AS bbox_min_latitude,
                    CASE
                        WHEN location_bbox IS NULL THEN NULL
                        ELSE ST_XMax(location_bbox)
                    END AS bbox_max_longitude,
                    CASE
                        WHEN location_bbox IS NULL THEN NULL
                        ELSE ST_YMax(location_bbox)
                    END AS bbox_max_latitude,
                    location_radius_meters
                FROM playable_corpus_v1
                {where_sql}
                ORDER BY playable_item_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()

        parsed_rows: list[dict[str, object]] = []
        for row in rows:
            observed_at = row["observed_at"]
            parsed_rows.append(
                {
                    "playable_item_id": row["playable_item_id"],
                    "qualified_resource_id": row["qualified_resource_id"],
                    "canonical_taxon_id": row["canonical_taxon_id"],
                    "media_asset_id": row["media_asset_id"],
                    "source_name": row["source_name"],
                    "source_observation_id": row["source_observation_id"],
                    "source_media_id": row["source_media_id"],
                    "scientific_name": row["scientific_name"],
                    "common_names_i18n": json.loads(str(row["common_names_i18n_json"])),
                    "difficulty_level": row["difficulty_level"],
                    "media_role": row["media_role"],
                    "learning_suitability": row["learning_suitability"],
                    "confusion_relevance": row["confusion_relevance"],
                    "diagnostic_feature_visibility": row["diagnostic_feature_visibility"],
                    "similar_taxon_ids": json.loads(str(row["similar_taxon_ids_json"])),
                    "what_to_look_at_specific": json.loads(
                        str(row["what_to_look_at_specific_json"])
                    ),
                    "what_to_look_at_general": json.loads(
                        str(row["what_to_look_at_general_json"])
                    ),
                    "confusion_hint": row["confusion_hint"],
                    "country_code": row["country_code"],
                    "observed_at": observed_at.isoformat() if observed_at else None,
                    "location_point": (
                        {
                            "longitude": float(row["location_longitude"]),
                            "latitude": float(row["location_latitude"]),
                        }
                        if row["location_longitude"] is not None
                        and row["location_latitude"] is not None
                        else None
                    ),
                    "location_bbox": (
                        {
                            "min_longitude": float(row["bbox_min_longitude"]),
                            "min_latitude": float(row["bbox_min_latitude"]),
                            "max_longitude": float(row["bbox_max_longitude"]),
                            "max_latitude": float(row["bbox_max_latitude"]),
                        }
                        if row["bbox_min_longitude"] is not None
                        and row["bbox_min_latitude"] is not None
                        and row["bbox_max_longitude"] is not None
                        and row["bbox_max_latitude"] is not None
                        else None
                    ),
                    "location_radius_meters": (
                        float(row["location_radius_meters"])
                        if row["location_radius_meters"] is not None
                        else None
                    ),
                }
            )
        return parsed_rows

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
        items = self.fetch_playable_corpus(
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
        with self.connect() as connection:
            latest_row = connection.execute(
                """
                SELECT run_id, completed_at
                FROM pipeline_runs
                WHERE run_status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """
            ).fetchone()
        payload = {
            "schema_version": SCHEMA_VERSION_LABEL,
            "playable_corpus_version": PLAYABLE_CORPUS_VERSION,
            "generated_at": (
                latest_row["completed_at"].isoformat()
                if latest_row and latest_row["completed_at"]
                else datetime.now(UTC).isoformat()
            ),
            "run_id": str(latest_row["run_id"]) if latest_row else None,
            "items": items,
        }
        validate_playable_corpus(payload)
        return payload

    def create_pack(
        self,
        *,
        parameters: PackRevisionParameters | dict[str, object],
        pack_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.create_pack(
                    parameters=parameters,
                    pack_id=pack_id,
                    connection=owned_connection,
                )

        normalized_parameters = (
            parameters
            if isinstance(parameters, PackRevisionParameters)
            else PackRevisionParameters(**parameters)
        )
        resolved_pack_id = (pack_id or self._generate_pack_id()).strip()
        if not resolved_pack_id:
            raise ValueError("pack_id must not be blank")

        now = datetime.now(UTC)
        try:
            connection.execute(
                """
                INSERT INTO pack_specs (
                    pack_id,
                    latest_revision,
                    created_at,
                    updated_at
                ) VALUES (%s, 1, %s, %s)
                """,
                (resolved_pack_id, now.isoformat(), now.isoformat()),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise ValueError(f"Pack already exists: {resolved_pack_id}") from exc

        self._insert_pack_revision(
            connection,
            pack_id=resolved_pack_id,
            revision=1,
            parameters=normalized_parameters,
            created_at=now,
        )
        return self._fetch_pack_revision_payload(
            connection,
            pack_id=resolved_pack_id,
            revision=1,
        )

    def revise_pack(
        self,
        *,
        pack_id: str,
        parameters: PackRevisionParameters | dict[str, object],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.revise_pack(
                    pack_id=pack_id,
                    parameters=parameters,
                    connection=owned_connection,
                )

        normalized_parameters = (
            parameters
            if isinstance(parameters, PackRevisionParameters)
            else PackRevisionParameters(**parameters)
        )
        row = connection.execute(
            """
            SELECT latest_revision
            FROM pack_specs
            WHERE pack_id = %s
            FOR UPDATE
            """,
            (pack_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown pack_id: {pack_id}")

        new_revision = int(row["latest_revision"]) + 1
        now = datetime.now(UTC)
        self._insert_pack_revision(
            connection,
            pack_id=pack_id,
            revision=new_revision,
            parameters=normalized_parameters,
            created_at=now,
        )
        connection.execute(
            """
            UPDATE pack_specs
            SET latest_revision = %s,
                updated_at = %s
            WHERE pack_id = %s
            """,
            (new_revision, now.isoformat(), pack_id),
        )
        return self._fetch_pack_revision_payload(
            connection,
            pack_id=pack_id,
            revision=new_revision,
        )

    def fetch_pack_specs(
        self,
        *,
        pack_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            where_clause = "WHERE ps.pack_id = %s" if pack_id else ""
            params: list[object] = [pack_id] if pack_id else []
            rows = connection.execute(
                f"""
                SELECT
                    ps.pack_id,
                    ps.latest_revision,
                    ps.created_at AS pack_created_at,
                    ps.updated_at AS pack_updated_at,
                    pr.revision,
                    pr.canonical_taxon_ids_json,
                    pr.difficulty_policy,
                    pr.country_code,
                    pr.observed_from,
                    pr.observed_to,
                    pr.owner_id,
                    pr.org_id,
                    pr.visibility,
                    pr.intended_use,
                    pr.created_at AS revision_created_at,
                    CASE
                        WHEN pr.location_point IS NULL THEN NULL
                        ELSE ST_X(pr.location_point)
                    END AS point_longitude,
                    CASE
                        WHEN pr.location_point IS NULL THEN NULL
                        ELSE ST_Y(pr.location_point)
                    END AS point_latitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_XMin(pr.location_bbox)
                    END AS bbox_min_longitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_YMin(pr.location_bbox)
                    END AS bbox_min_latitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_XMax(pr.location_bbox)
                    END AS bbox_max_longitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_YMax(pr.location_bbox)
                    END AS bbox_max_latitude,
                    pr.location_radius_meters
                FROM pack_specs ps
                JOIN pack_revisions pr
                    ON pr.pack_id = ps.pack_id
                    AND pr.revision = ps.latest_revision
                {where_clause}
                ORDER BY ps.updated_at DESC, ps.pack_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
            return [self._pack_spec_payload_from_row(row) for row in rows]

    def fetch_pack_revisions(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            where_clauses = ["pr.pack_id = %s"]
            params: list[object] = [pack_id]
            if revision is not None:
                where_clauses.append("pr.revision = %s")
                params.append(revision)
            rows = connection.execute(
                f"""
                SELECT
                    ps.pack_id,
                    ps.latest_revision,
                    ps.created_at AS pack_created_at,
                    ps.updated_at AS pack_updated_at,
                    pr.revision,
                    pr.canonical_taxon_ids_json,
                    pr.difficulty_policy,
                    pr.country_code,
                    pr.observed_from,
                    pr.observed_to,
                    pr.owner_id,
                    pr.org_id,
                    pr.visibility,
                    pr.intended_use,
                    pr.created_at AS revision_created_at,
                    CASE
                        WHEN pr.location_point IS NULL THEN NULL
                        ELSE ST_X(pr.location_point)
                    END AS point_longitude,
                    CASE
                        WHEN pr.location_point IS NULL THEN NULL
                        ELSE ST_Y(pr.location_point)
                    END AS point_latitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_XMin(pr.location_bbox)
                    END AS bbox_min_longitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_YMin(pr.location_bbox)
                    END AS bbox_min_latitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_XMax(pr.location_bbox)
                    END AS bbox_max_longitude,
                    CASE
                        WHEN pr.location_bbox IS NULL THEN NULL
                        ELSE ST_YMax(pr.location_bbox)
                    END AS bbox_max_latitude,
                    pr.location_radius_meters
                FROM pack_revisions pr
                JOIN pack_specs ps ON ps.pack_id = pr.pack_id
                WHERE {' AND '.join(where_clauses)}
                ORDER BY pr.revision DESC
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
            return [self._pack_spec_payload_from_row(row) for row in rows]

    def diagnose_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.diagnose_pack(
                    pack_id=pack_id,
                    revision=revision,
                    connection=owned_connection,
                )

        context = self._compute_pack_compilation_context(
            connection,
            pack_id=pack_id,
            revision=revision,
            question_count_requested=MIN_PACK_TOTAL_QUESTIONS,
        )

        attempted_at = datetime.now(UTC)
        attempt = PackCompilationAttempt(
            attempt_id=f"packdiag:{pack_id}:{context['revision']}:{uuid4().hex[:8]}",
            pack_id=pack_id,
            revision=int(context["revision"]),
            attempted_at=attempted_at,
            compilable=bool(context["compilable"]),
            reason_code=context["reason_code"],
            thresholds=context["thresholds"],
            measured=context["measured"],
            deficits=context["deficits"],
            blocking_taxa=context["blocking_taxa"],
        )
        payload = {
            "schema_version": SCHEMA_VERSION_LABEL,
            "pack_diagnostic_version": PACK_DIAGNOSTIC_VERSION,
            **attempt.model_dump(mode="json"),
        }
        validate_pack_diagnostic(payload)
        connection.execute(
            """
            INSERT INTO pack_compilation_attempts (
                attempt_id,
                pack_id,
                revision,
                attempted_at,
                schema_version,
                pack_diagnostic_version,
                compilable,
                reason_code,
                metrics_json,
                deficits_json,
                blocking_taxa_json,
                payload_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                attempt.attempt_id,
                attempt.pack_id,
                attempt.revision,
                attempt.attempted_at.isoformat(),
                SCHEMA_VERSION_LABEL,
                PACK_DIAGNOSTIC_VERSION,
                attempt.compilable,
                attempt.reason_code,
                _json(attempt.measured),
                _json([item.model_dump(mode="json") for item in attempt.deficits]),
                _json([item.model_dump(mode="json") for item in attempt.blocking_taxa]),
                _json(payload),
            ),
        )
        return payload

    def compile_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if question_count < 1:
            raise ValueError("question_count must be >= 1")

        if connection is None:
            with self.connect() as owned_connection:
                return self.compile_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=question_count,
                    connection=owned_connection,
                )

        context = self._compute_pack_compilation_context(
            connection,
            pack_id=pack_id,
            revision=revision,
            question_count_requested=max(question_count, MIN_PACK_TOTAL_QUESTIONS),
        )
        if not context["compilable"]:
            deficits = ", ".join(
                f"{item.code}:{item.current}/{item.required}"
                for item in context["deficits"]
            ) or "none"
            raise ValueError(
                "Pack is not compilable for build persistence "
                f"(reason_code={context['reason_code']}, deficits={deficits})"
            )

        build_id = f"packbuild:{pack_id}:{context['revision']}:{uuid4().hex[:8]}"
        built_at = datetime.now(UTC)
        built_questions = context["questions"][:question_count]
        build = CompiledPackBuild(
            build_id=build_id,
            pack_id=pack_id,
            revision=int(context["revision"]),
            built_at=built_at,
            question_count_requested=question_count,
            question_count_built=len(built_questions),
            distractor_count=3,
            source_run_id=context["source_run_id"],
            questions=built_questions,
        )
        payload = {
            "schema_version": SCHEMA_VERSION_LABEL,
            "pack_compiled_version": COMPILED_PACK_VERSION,
            **build.model_dump(mode="json"),
        }
        validate_compiled_pack(payload)
        connection.execute(
            """
            INSERT INTO compiled_pack_builds (
                build_id,
                pack_id,
                revision,
                built_at,
                schema_version,
                pack_compiled_version,
                question_count_requested,
                question_count_built,
                distractor_count,
                source_run_id,
                payload_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                build.build_id,
                build.pack_id,
                build.revision,
                build.built_at.isoformat(),
                SCHEMA_VERSION_LABEL,
                COMPILED_PACK_VERSION,
                build.question_count_requested,
                build.question_count_built,
                build.distractor_count,
                build.source_run_id,
                _json(payload),
            ),
        )
        return payload

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
        if question_count < 1:
            raise ValueError("question_count must be >= 1")

        if connection is None:
            with self.connect() as owned_connection:
                return self.materialize_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=question_count,
                    purpose=purpose,
                    ttl_hours=ttl_hours,
                    connection=owned_connection,
                )

        revision_payload = self._fetch_pack_revision_payload(
            connection,
            pack_id=pack_id,
            revision=revision,
        )
        revision_value = int(revision_payload["revision"])
        latest_build = self._fetch_latest_compiled_payload(
            connection,
            pack_id=pack_id,
            revision=revision_value,
        )
        if latest_build is None:
            raise ValueError(
                "No compiled build found for materialization. "
                "Run `pack compile` first for this revision."
            )

        available_questions = list(latest_build["questions"])
        if question_count > len(available_questions):
            raise ValueError(
                "Requested materialization question_count exceeds available compiled questions "
                f"(requested={question_count}, available={len(available_questions)})"
            )
        selected_questions = available_questions[:question_count]
        purpose_value = PackMaterializationPurpose(purpose)
        created_at = datetime.now(UTC)

        resolved_ttl_hours: int | None = None
        expires_at: datetime | None = None
        if purpose_value == PackMaterializationPurpose.DAILY_CHALLENGE:
            resolved_ttl_hours = ttl_hours or 24
            if resolved_ttl_hours <= 0:
                raise ValueError("daily_challenge materialization requires ttl_hours > 0")
            expires_at = created_at + timedelta(hours=resolved_ttl_hours)
        elif ttl_hours is not None:
            raise ValueError("assignment materialization cannot define ttl_hours")

        materialization = MaterializedPack(
            materialization_id=(
                f"packmat:{pack_id}:{revision_value}:{purpose_value}:{uuid4().hex[:8]}"
            ),
            pack_id=pack_id,
            revision=revision_value,
            source_build_id=str(latest_build["build_id"]),
            created_at=created_at,
            purpose=purpose_value,
            ttl_hours=resolved_ttl_hours,
            expires_at=expires_at,
            question_count=len(selected_questions),
            questions=[CompiledPackQuestion(**item) for item in selected_questions],
        )
        payload = {
            "schema_version": SCHEMA_VERSION_LABEL,
            "pack_materialization_version": PACK_MATERIALIZATION_VERSION,
            **materialization.model_dump(mode="json"),
        }
        validate_pack_materialization(payload)
        connection.execute(
            """
            INSERT INTO pack_materializations (
                materialization_id,
                pack_id,
                revision,
                source_build_id,
                created_at,
                purpose,
                ttl_hours,
                expires_at,
                schema_version,
                pack_materialization_version,
                question_count,
                payload_json
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                materialization.materialization_id,
                materialization.pack_id,
                materialization.revision,
                materialization.source_build_id,
                materialization.created_at.isoformat(),
                materialization.purpose,
                materialization.ttl_hours,
                materialization.expires_at.isoformat() if materialization.expires_at else None,
                SCHEMA_VERSION_LABEL,
                PACK_MATERIALIZATION_VERSION,
                materialization.question_count,
                _json(payload),
            ),
        )
        return payload

    def fetch_pack_diagnostics(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[object] = []
            if pack_id:
                clauses.append("pack_id = %s")
                params.append(pack_id)
            if revision is not None:
                clauses.append("revision = %s")
                params.append(revision)
            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM pack_compilation_attempts
                {where_clause}
                ORDER BY attempted_at DESC, attempt_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
            payloads = [json.loads(str(row["payload_json"])) for row in rows]
            for payload in payloads:
                validate_pack_diagnostic(payload)
            return payloads

    def fetch_compiled_pack_builds(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[object] = []
            if pack_id:
                clauses.append("pack_id = %s")
                params.append(pack_id)
            if revision is not None:
                clauses.append("revision = %s")
                params.append(revision)
            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM compiled_pack_builds
                {where_clause}
                ORDER BY built_at DESC, build_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
            payloads = [json.loads(str(row["payload_json"])) for row in rows]
            for payload in payloads:
                validate_compiled_pack(payload)
            return payloads

    def fetch_pack_materializations(
        self,
        *,
        pack_id: str | None = None,
        revision: int | None = None,
        purpose: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self.connect() as connection:
            clauses: list[str] = []
            params: list[object] = []
            if pack_id:
                clauses.append("pack_id = %s")
                params.append(pack_id)
            if revision is not None:
                clauses.append("revision = %s")
                params.append(revision)
            if purpose:
                clauses.append("purpose = %s")
                params.append(purpose)
            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM pack_materializations
                {where_clause}
                ORDER BY created_at DESC, materialization_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()
            payloads = [json.loads(str(row["payload_json"])) for row in rows]
            for payload in payloads:
                validate_pack_materialization(payload)
            return payloads

    def enqueue_enrichment_for_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.enqueue_enrichment_for_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=question_count,
                    connection=owned_connection,
                )

        context = self._compute_pack_compilation_context(
            connection,
            pack_id=pack_id,
            revision=revision,
            question_count_requested=max(question_count, MIN_PACK_TOTAL_QUESTIONS),
        )
        if context["compilable"]:
            return {
                "enqueued": False,
                "reason": "pack_compilable",
                "pack_id": pack_id,
                "revision": int(context["revision"]),
            }

        targets = [
            {
                "resource_type": EnrichmentTargetResourceType.CANONICAL_TAXON,
                "resource_id": str(item.canonical_taxon_id),
                "target_attribute": "similar_taxon_ids",
            }
            for item in context["blocking_taxa"]
        ]
        if not targets:
            targets = [
                {
                    "resource_type": EnrichmentTargetResourceType.PACK,
                    "resource_id": pack_id,
                    "target_attribute": "playable_availability",
                }
            ]

        request_payload = self.create_or_merge_enrichment_request(
            pack_id=pack_id,
            revision=int(context["revision"]),
            reason_code=str(context["reason_code"]),
            targets=targets,
            connection=connection,
        )
        return {
            "enqueued": True,
            "pack_id": pack_id,
            "revision": int(context["revision"]),
            "compilation_reason_code": str(context["reason_code"]),
            "request": request_payload,
        }

    def create_or_merge_enrichment_request(
        self,
        *,
        pack_id: str,
        revision: int,
        reason_code: str,
        targets: Sequence[dict[str, object]],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.create_or_merge_enrichment_request(
                    pack_id=pack_id,
                    revision=revision,
                    reason_code=reason_code,
                    targets=targets,
                    connection=owned_connection,
                )

        reason = EnrichmentRequestReasonCode(reason_code)
        normalized_targets = self._normalize_enrichment_targets(targets)
        if not normalized_targets:
            raise ValueError("targets must contain at least one item")

        existing_requests = connection.execute(
            """
            SELECT enrichment_request_id
            FROM enrichment_requests
            WHERE pack_id = %s
              AND revision = %s
              AND reason_code = %s
              AND request_status IN ('pending', 'in_progress')
            ORDER BY created_at DESC, enrichment_request_id
            """,
            (pack_id, revision, reason),
        ).fetchall()
        requested_signature = tuple(normalized_targets)
        for row in existing_requests:
            enrichment_request_id = str(row["enrichment_request_id"])
            current_signature = self._fetch_enrichment_target_signature(
                connection,
                enrichment_request_id=enrichment_request_id,
            )
            if current_signature == requested_signature:
                return {
                    "merged": True,
                    "request": self.fetch_enrichment_requests(
                        enrichment_request_id=enrichment_request_id,
                        limit=1,
                        connection=connection,
                    )[0],
                    "targets": self.fetch_enrichment_request_targets(
                        enrichment_request_id=enrichment_request_id,
                        connection=connection,
                    ),
                }

        created_at = datetime.now(UTC)
        request = EnrichmentRequest(
            enrichment_request_id=f"enrreq:{pack_id}:{revision}:{uuid4().hex[:8]}",
            pack_id=pack_id,
            revision=revision,
            reason_code=reason,
            request_status=EnrichmentRequestStatus.PENDING,
            created_at=created_at,
            completed_at=None,
            execution_attempt_count=0,
        )
        connection.execute(
            """
            INSERT INTO enrichment_requests (
                enrichment_request_id,
                pack_id,
                revision,
                reason_code,
                request_status,
                created_at,
                completed_at,
                execution_attempt_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request.enrichment_request_id,
                request.pack_id,
                request.revision,
                request.reason_code,
                request.request_status,
                request.created_at.isoformat(),
                None,
                request.execution_attempt_count,
            ),
        )
        targets_payload: list[EnrichmentRequestTarget] = []
        for resource_type, resource_id, target_attribute in normalized_targets:
            targets_payload.append(
                EnrichmentRequestTarget(
                    enrichment_request_target_id=f"enrtgt:{uuid4().hex[:12]}",
                    enrichment_request_id=request.enrichment_request_id,
                    resource_type=EnrichmentTargetResourceType(resource_type),
                    resource_id=resource_id,
                    target_attribute=target_attribute,
                    created_at=created_at,
                )
            )

        _executemany(
            connection,
            """
            INSERT INTO enrichment_request_targets (
                enrichment_request_target_id,
                enrichment_request_id,
                resource_type,
                resource_id,
                target_attribute,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    target.enrichment_request_target_id,
                    target.enrichment_request_id,
                    target.resource_type,
                    target.resource_id,
                    target.target_attribute,
                    target.created_at.isoformat(),
                )
                for target in targets_payload
            ],
        )
        return {
            "merged": False,
            "request": {
                "enrichment_request_id": request.enrichment_request_id,
                "pack_id": request.pack_id,
                "revision": request.revision,
                "reason_code": str(request.reason_code),
                "request_status": str(request.request_status),
                "created_at": request.created_at.isoformat(),
                "completed_at": None,
                "execution_attempt_count": request.execution_attempt_count,
            },
            "targets": [item.model_dump(mode="json") for item in targets_payload],
        }

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
        if connection is None:
            with self.connect() as owned_connection:
                return self.fetch_enrichment_requests(
                    enrichment_request_id=enrichment_request_id,
                    request_status=request_status,
                    pack_id=pack_id,
                    revision=revision,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if enrichment_request_id:
            clauses.append("enrichment_request_id = %s")
            params.append(enrichment_request_id)
        if request_status:
            clauses.append("request_status = %s")
            params.append(request_status)
        if pack_id:
            clauses.append("pack_id = %s")
            params.append(pack_id)
        if revision is not None:
            clauses.append("revision = %s")
            params.append(revision)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                enrichment_request_id,
                pack_id,
                revision,
                reason_code,
                request_status,
                created_at,
                completed_at,
                execution_attempt_count
            FROM enrichment_requests
            {where_clause}
            ORDER BY created_at DESC, enrichment_request_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "pack_id": str(row["pack_id"]),
                "revision": int(row["revision"]),
                "reason_code": str(row["reason_code"]),
                "request_status": str(row["request_status"]),
                "created_at": row["created_at"].isoformat(),
                "completed_at": row["completed_at"].isoformat()
                if row["completed_at"] is not None
                else None,
                "execution_attempt_count": int(row["execution_attempt_count"]),
            }
            for row in rows
        ]

    def fetch_enrichment_request_targets(
        self,
        *,
        enrichment_request_id: str,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.fetch_enrichment_request_targets(
                    enrichment_request_id=enrichment_request_id,
                    connection=owned_connection,
                )

        rows = connection.execute(
            """
            SELECT
                enrichment_request_target_id,
                enrichment_request_id,
                resource_type,
                resource_id,
                target_attribute,
                created_at
            FROM enrichment_request_targets
            WHERE enrichment_request_id = %s
            ORDER BY resource_type, resource_id, target_attribute, enrichment_request_target_id
            """,
            (enrichment_request_id,),
        ).fetchall()
        return [
            {
                "enrichment_request_target_id": str(row["enrichment_request_target_id"]),
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "resource_type": str(row["resource_type"]),
                "resource_id": str(row["resource_id"]),
                "target_attribute": str(row["target_attribute"]),
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    def fetch_enrichment_executions(
        self,
        *,
        enrichment_request_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self.connect() as owned_connection:
                return self.fetch_enrichment_executions(
                    enrichment_request_id=enrichment_request_id,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if enrichment_request_id:
            clauses.append("enrichment_request_id = %s")
            params.append(enrichment_request_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                enrichment_execution_id,
                enrichment_request_id,
                execution_status,
                executed_at,
                execution_context_json,
                error_info
            FROM enrichment_executions
            {where_clause}
            ORDER BY executed_at DESC, enrichment_execution_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "enrichment_execution_id": str(row["enrichment_execution_id"]),
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "execution_status": str(row["execution_status"]),
                "executed_at": row["executed_at"].isoformat(),
                "execution_context": json.loads(str(row["execution_context_json"])),
                "error_info": row["error_info"],
            }
            for row in rows
        ]

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
        if connection is None:
            with self.connect() as owned_connection:
                return self.record_enrichment_execution(
                    enrichment_request_id=enrichment_request_id,
                    execution_status=execution_status,
                    execution_context=execution_context,
                    error_info=error_info,
                    trigger_recompile=trigger_recompile,
                    connection=owned_connection,
                )

        request_row = connection.execute(
            """
            SELECT pack_id, revision
            FROM enrichment_requests
            WHERE enrichment_request_id = %s
            """,
            (enrichment_request_id,),
        ).fetchone()
        if request_row is None:
            raise ValueError(f"Unknown enrichment_request_id: {enrichment_request_id}")

        status = EnrichmentExecutionStatus(execution_status)
        executed_at = datetime.now(UTC)
        execution = EnrichmentExecution(
            enrichment_execution_id=f"enrexec:{enrichment_request_id}:{uuid4().hex[:8]}",
            enrichment_request_id=enrichment_request_id,
            execution_status=status,
            executed_at=executed_at,
            execution_context=execution_context or {},
            error_info=error_info,
        )
        connection.execute(
            """
            INSERT INTO enrichment_executions (
                enrichment_execution_id,
                enrichment_request_id,
                execution_status,
                executed_at,
                execution_context_json,
                error_info
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                execution.enrichment_execution_id,
                execution.enrichment_request_id,
                execution.execution_status,
                execution.executed_at.isoformat(),
                _json(execution.execution_context),
                execution.error_info,
            ),
        )

        next_status = (
            EnrichmentRequestStatus.COMPLETED
            if status in (EnrichmentExecutionStatus.SUCCESS, EnrichmentExecutionStatus.PARTIAL)
            else EnrichmentRequestStatus.FAILED
        )
        completed_at = executed_at if next_status == EnrichmentRequestStatus.COMPLETED else None
        connection.execute(
            """
            UPDATE enrichment_requests
            SET request_status = %s,
                completed_at = %s,
                execution_attempt_count = execution_attempt_count + 1
            WHERE enrichment_request_id = %s
            """,
            (
                next_status,
                completed_at.isoformat() if completed_at else None,
                enrichment_request_id,
            ),
        )

        recompilation_result: dict[str, object] | None = None
        if trigger_recompile and status in (
            EnrichmentExecutionStatus.SUCCESS,
            EnrichmentExecutionStatus.PARTIAL,
        ):
            pack_id = str(request_row["pack_id"])
            revision = int(request_row["revision"])
            diagnostic = self.diagnose_pack(
                pack_id=pack_id,
                revision=revision,
                connection=connection,
            )
            recompilation_result = {
                "attempted": True,
                "pack_id": pack_id,
                "revision": revision,
                "diagnostic_reason_code": diagnostic["reason_code"],
                "compiled_build_id": None,
            }
            if diagnostic["compilable"]:
                compiled = self.compile_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=MIN_PACK_TOTAL_QUESTIONS,
                    connection=connection,
                )
                recompilation_result["compiled_build_id"] = compiled["build_id"]

        return {
            "enrichment_execution_id": execution.enrichment_execution_id,
            "enrichment_request_id": execution.enrichment_request_id,
            "execution_status": str(execution.execution_status),
            "executed_at": execution.executed_at.isoformat(),
            "request_status": str(next_status),
            "trigger_recompile": trigger_recompile,
            "recompilation": recompilation_result,
        }

    def _normalize_enrichment_targets(
        self,
        targets: Sequence[dict[str, object]],
    ) -> list[tuple[str, str, str]]:
        normalized: set[tuple[str, str, str]] = set()
        for target in targets:
            resource_type = str(target.get("resource_type") or "").strip()
            resource_id = str(target.get("resource_id") or "").strip()
            target_attribute = str(target.get("target_attribute") or "").strip()
            if not resource_type or not resource_id or not target_attribute:
                continue
            normalized.add((resource_type, resource_id, target_attribute))
        return sorted(normalized)

    def _fetch_enrichment_target_signature(
        self,
        connection: psycopg.Connection,
        *,
        enrichment_request_id: str,
    ) -> tuple[tuple[str, str, str], ...]:
        rows = connection.execute(
            """
            SELECT resource_type, resource_id, target_attribute
            FROM enrichment_request_targets
            WHERE enrichment_request_id = %s
            ORDER BY resource_type, resource_id, target_attribute
            """,
            (enrichment_request_id,),
        ).fetchall()
        return tuple(
            (
                str(row["resource_type"]),
                str(row["resource_id"]),
                str(row["target_attribute"]),
            )
            for row in rows
        )

    def _generate_pack_id(self) -> str:
        return f"pack:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}:{uuid4().hex[:8]}"

    def _insert_pack_revision(
        self,
        connection: psycopg.Connection,
        *,
        pack_id: str,
        revision: int,
        parameters: PackRevisionParameters,
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO pack_revisions (
                pack_id,
                revision,
                canonical_taxon_ids_json,
                difficulty_policy,
                country_code,
                location_bbox,
                location_point,
                location_radius_meters,
                observed_from,
                observed_to,
                owner_id,
                org_id,
                visibility,
                intended_use,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                CASE
                    WHEN %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                        AND %s::DOUBLE PRECISION IS NOT NULL
                    THEN ST_MakeEnvelope(
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        %s::DOUBLE PRECISION,
                        4326
                    )
                    ELSE NULL
                END,
                CASE
                    WHEN %s::DOUBLE PRECISION IS NOT NULL AND %s::DOUBLE PRECISION IS NOT NULL
                    THEN ST_SetSRID(
                        ST_MakePoint(%s::DOUBLE PRECISION, %s::DOUBLE PRECISION),
                        4326
                    )
                    ELSE NULL
                END,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                pack_id,
                revision,
                _json(parameters.canonical_taxon_ids),
                parameters.difficulty_policy,
                parameters.country_code,
                parameters.location_bbox.min_longitude if parameters.location_bbox else None,
                parameters.location_bbox.min_latitude if parameters.location_bbox else None,
                parameters.location_bbox.max_longitude if parameters.location_bbox else None,
                parameters.location_bbox.max_latitude if parameters.location_bbox else None,
                parameters.location_bbox.min_longitude if parameters.location_bbox else None,
                parameters.location_bbox.min_latitude if parameters.location_bbox else None,
                parameters.location_bbox.max_longitude if parameters.location_bbox else None,
                parameters.location_bbox.max_latitude if parameters.location_bbox else None,
                parameters.location_point.longitude if parameters.location_point else None,
                parameters.location_point.latitude if parameters.location_point else None,
                parameters.location_point.longitude if parameters.location_point else None,
                parameters.location_point.latitude if parameters.location_point else None,
                parameters.location_radius_meters,
                parameters.observed_from.isoformat() if parameters.observed_from else None,
                parameters.observed_to.isoformat() if parameters.observed_to else None,
                parameters.owner_id,
                parameters.org_id,
                parameters.visibility,
                parameters.intended_use,
                created_at.isoformat(),
            ),
        )

    def _fetch_pack_revision_payload(
        self,
        connection: psycopg.Connection,
        *,
        pack_id: str,
        revision: int | None = None,
    ) -> dict[str, object]:
        if revision is None:
            row = connection.execute(
                """
                SELECT latest_revision
                FROM pack_specs
                WHERE pack_id = %s
                """,
                (pack_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown pack_id: {pack_id}")
            revision = int(row["latest_revision"])

        row = connection.execute(
            """
            SELECT
                ps.pack_id,
                ps.latest_revision,
                ps.created_at AS pack_created_at,
                ps.updated_at AS pack_updated_at,
                pr.revision,
                pr.canonical_taxon_ids_json,
                pr.difficulty_policy,
                pr.country_code,
                pr.observed_from,
                pr.observed_to,
                pr.owner_id,
                pr.org_id,
                pr.visibility,
                pr.intended_use,
                pr.created_at AS revision_created_at,
                CASE
                    WHEN pr.location_point IS NULL THEN NULL
                    ELSE ST_X(pr.location_point)
                END AS point_longitude,
                CASE
                    WHEN pr.location_point IS NULL THEN NULL
                    ELSE ST_Y(pr.location_point)
                END AS point_latitude,
                CASE
                    WHEN pr.location_bbox IS NULL THEN NULL
                    ELSE ST_XMin(pr.location_bbox)
                END AS bbox_min_longitude,
                CASE
                    WHEN pr.location_bbox IS NULL THEN NULL
                    ELSE ST_YMin(pr.location_bbox)
                END AS bbox_min_latitude,
                CASE
                    WHEN pr.location_bbox IS NULL THEN NULL
                    ELSE ST_XMax(pr.location_bbox)
                END AS bbox_max_longitude,
                CASE
                    WHEN pr.location_bbox IS NULL THEN NULL
                    ELSE ST_YMax(pr.location_bbox)
                END AS bbox_max_latitude,
                pr.location_radius_meters
            FROM pack_revisions pr
            JOIN pack_specs ps ON ps.pack_id = pr.pack_id
            WHERE pr.pack_id = %s
              AND pr.revision = %s
            """,
            (pack_id, revision),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown pack revision: {pack_id}@{revision}")
        return self._pack_spec_payload_from_row(row)

    def _pack_spec_payload_from_row(self, row: dict[str, object]) -> dict[str, object]:
        observed_from = row["observed_from"]
        observed_to = row["observed_to"]
        parameters = PackRevisionParameters(
            canonical_taxon_ids=json.loads(str(row["canonical_taxon_ids_json"])),
            difficulty_policy=str(row["difficulty_policy"]),
            country_code=row["country_code"],
            location_bbox=(
                {
                    "min_longitude": float(row["bbox_min_longitude"]),
                    "min_latitude": float(row["bbox_min_latitude"]),
                    "max_longitude": float(row["bbox_max_longitude"]),
                    "max_latitude": float(row["bbox_max_latitude"]),
                }
                if row["bbox_min_longitude"] is not None
                and row["bbox_min_latitude"] is not None
                and row["bbox_max_longitude"] is not None
                and row["bbox_max_latitude"] is not None
                else None
            ),
            location_point=(
                {
                    "longitude": float(row["point_longitude"]),
                    "latitude": float(row["point_latitude"]),
                }
                if row["point_longitude"] is not None and row["point_latitude"] is not None
                else None
            ),
            location_radius_meters=(
                float(row["location_radius_meters"])
                if row["location_radius_meters"] is not None
                else None
            ),
            observed_from=observed_from,
            observed_to=observed_to,
            owner_id=row["owner_id"],
            org_id=row["org_id"],
            visibility=str(row["visibility"]),
            intended_use=str(row["intended_use"]),
        )
        pack_spec = PackSpec(
            pack_id=str(row["pack_id"]),
            latest_revision=int(row["latest_revision"]),
            created_at=row["pack_created_at"],
            updated_at=row["pack_updated_at"],
        )
        pack_revision = PackRevision(
            pack_id=pack_spec.pack_id,
            revision=int(row["revision"]),
            parameters=parameters,
            created_at=row["revision_created_at"],
        )
        payload = {
            "schema_version": SCHEMA_VERSION_LABEL,
            "pack_spec_version": PACK_SPEC_VERSION,
            "pack_id": pack_revision.pack_id,
            "revision": pack_revision.revision,
            "latest_revision": pack_spec.latest_revision,
            "created_at": pack_revision.created_at.isoformat(),
            "parameters": pack_revision.parameters.model_dump(mode="json"),
        }
        validate_pack_spec(payload)
        return payload

    def _fetch_playable_rows_for_pack(
        self,
        connection: psycopg.Connection,
        *,
        parameters: PackRevisionParameters,
    ) -> list[dict[str, object]]:
        where_clauses = ["canonical_taxon_id = ANY(%s)"]
        query_params: list[object] = [parameters.canonical_taxon_ids]

        if parameters.country_code:
            where_clauses.append("country_code = %s")
            query_params.append(parameters.country_code)
        if parameters.observed_from:
            where_clauses.append("observed_at >= %s")
            query_params.append(parameters.observed_from.isoformat())
        if parameters.observed_to:
            where_clauses.append("observed_at <= %s")
            query_params.append(parameters.observed_to.isoformat())
        if parameters.location_bbox is not None:
            where_clauses.append(
                """
                (
                    (location_bbox IS NOT NULL AND ST_Intersects(
                        location_bbox,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    ))
                    OR
                    (location_point IS NOT NULL AND ST_Intersects(
                        location_point,
                        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                    ))
                )
                """
            )
            query_params.extend(
                [
                    parameters.location_bbox.min_longitude,
                    parameters.location_bbox.min_latitude,
                    parameters.location_bbox.max_longitude,
                    parameters.location_bbox.max_latitude,
                    parameters.location_bbox.min_longitude,
                    parameters.location_bbox.min_latitude,
                    parameters.location_bbox.max_longitude,
                    parameters.location_bbox.max_latitude,
                ]
            )
        if parameters.location_point is not None and parameters.location_radius_meters is not None:
            where_clauses.append(
                """
                location_point IS NOT NULL
                AND ST_DWithin(
                    location_point::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                """
            )
            query_params.extend(
                [
                    parameters.location_point.longitude,
                    parameters.location_point.latitude,
                    parameters.location_radius_meters,
                ]
            )
        where_sql = " AND ".join(where_clauses)
        return [
            self._normalize_playable_pack_row(dict(row))
            for row in connection.execute(
                f"""
                SELECT
                    playable_item_id,
                    canonical_taxon_id,
                    difficulty_level,
                    media_role,
                    confusion_relevance,
                    similar_taxon_ids_json,
                    run_id
                FROM playable_corpus_v1
                WHERE {where_sql}
                ORDER BY canonical_taxon_id, playable_item_id
                """,
                query_params,
            ).fetchall()
        ]

    def _fetch_latest_compiled_payload(
        self,
        connection: psycopg.Connection,
        *,
        pack_id: str,
        revision: int,
    ) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT payload_json
            FROM compiled_pack_builds
            WHERE pack_id = %s AND revision = %s
            ORDER BY built_at DESC, build_id DESC
            LIMIT 1
            """,
            (pack_id, revision),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload_json"]))
        validate_compiled_pack(payload)
        return payload

    def _compute_pack_compilation_context(
        self,
        connection: psycopg.Connection,
        *,
        pack_id: str,
        revision: int | None,
        question_count_requested: int,
    ) -> dict[str, object]:
        revision_payload = self._fetch_pack_revision_payload(
            connection,
            pack_id=pack_id,
            revision=revision,
        )
        revision_value = int(revision_payload["revision"])
        parameters = PackRevisionParameters(**revision_payload["parameters"])
        rows = self._fetch_playable_rows_for_pack(connection, parameters=parameters)
        requested_taxa = list(parameters.canonical_taxon_ids)

        items_per_taxon: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            canonical_taxon_id = str(row["canonical_taxon_id"])
            items_per_taxon[canonical_taxon_id].append(row)

        for canonical_taxon_id in requested_taxa:
            items_per_taxon.setdefault(canonical_taxon_id, [])

        inat_similar_taxa_by_target = self._fetch_inat_similar_taxa_by_target(
            connection,
            canonical_taxon_ids=requested_taxa,
        )

        questions = self._build_compiled_questions(
            items_per_taxon=items_per_taxon,
            requested_taxa=requested_taxa,
            difficulty_policy=str(parameters.difficulty_policy),
            question_count_requested=question_count_requested,
            inat_similar_taxa_by_target=inat_similar_taxa_by_target,
        )

        taxa_served = sum(
            1
            for canonical_taxon_id in requested_taxa
            if items_per_taxon[canonical_taxon_id]
        )
        media_counts = [
            len(items_per_taxon[canonical_taxon_id]) for canonical_taxon_id in requested_taxa
        ]
        min_media_count_per_taxon = min(media_counts) if media_counts else 0
        total_playable_items = sum(media_counts)
        questions_possible = len(questions)

        thresholds = {
            "min_taxa_served": MIN_PACK_TAXA_SERVED,
            "min_media_per_taxon": MIN_PACK_MEDIA_PER_TAXON,
            "min_total_questions": MIN_PACK_TOTAL_QUESTIONS,
        }
        measured = {
            "requested_taxa_count": len(requested_taxa),
            "taxa_served": taxa_served,
            "min_media_count_per_taxon": min_media_count_per_taxon,
            "total_playable_items": total_playable_items,
            "questions_possible": questions_possible,
        }

        deficits: list[PackCompilationDeficit] = []
        if taxa_served < thresholds["min_taxa_served"]:
            deficits.append(
                PackCompilationDeficit(
                    code="min_taxa_served",
                    current=taxa_served,
                    required=thresholds["min_taxa_served"],
                    missing=thresholds["min_taxa_served"] - taxa_served,
                )
            )
        if min_media_count_per_taxon < thresholds["min_media_per_taxon"]:
            deficits.append(
                PackCompilationDeficit(
                    code="min_media_per_taxon",
                    current=min_media_count_per_taxon,
                    required=thresholds["min_media_per_taxon"],
                    missing=thresholds["min_media_per_taxon"] - min_media_count_per_taxon,
                )
            )
        if questions_possible < thresholds["min_total_questions"]:
            deficits.append(
                PackCompilationDeficit(
                    code="min_total_questions",
                    current=questions_possible,
                    required=thresholds["min_total_questions"],
                    missing=thresholds["min_total_questions"] - questions_possible,
                )
            )

        blocking_taxa = [
            PackTaxonDeficit(
                canonical_taxon_id=canonical_taxon_id,
                media_count=len(items_per_taxon[canonical_taxon_id]),
                missing_media_count=max(
                    thresholds["min_media_per_taxon"] - len(items_per_taxon[canonical_taxon_id]),
                    0,
                ),
            )
            for canonical_taxon_id in requested_taxa
            if len(items_per_taxon[canonical_taxon_id]) < thresholds["min_media_per_taxon"]
        ]

        reason_code = PackCompilationReasonCode.COMPILABLE
        if total_playable_items == 0:
            reason_code = PackCompilationReasonCode.NO_PLAYABLE_ITEMS
        elif taxa_served < thresholds["min_taxa_served"]:
            reason_code = PackCompilationReasonCode.INSUFFICIENT_TAXA_SERVED
        elif min_media_count_per_taxon < thresholds["min_media_per_taxon"]:
            reason_code = PackCompilationReasonCode.INSUFFICIENT_MEDIA_PER_TAXON
        elif questions_possible < thresholds["min_total_questions"]:
            reason_code = PackCompilationReasonCode.INSUFFICIENT_TOTAL_QUESTIONS

        source_run_id = str(rows[0]["run_id"]) if rows else None
        compilable = reason_code == PackCompilationReasonCode.COMPILABLE

        return {
            "pack_id": pack_id,
            "revision": revision_value,
            "thresholds": thresholds,
            "measured": measured,
            "deficits": deficits,
            "blocking_taxa": blocking_taxa,
            "reason_code": reason_code,
            "compilable": compilable,
            "source_run_id": source_run_id,
            "questions": questions,
        }

    def _build_compiled_questions(
        self,
        *,
        items_per_taxon: dict[str, list[dict[str, object]]],
        requested_taxa: Sequence[str],
        difficulty_policy: str,
        question_count_requested: int,
        inat_similar_taxa_by_target: dict[str, list[str]] | None = None,
    ) -> list[CompiledPackQuestion]:
        inat_similar_taxa_by_target = inat_similar_taxa_by_target or {}
        sorted_taxon_ids = list(dict.fromkeys(requested_taxa))
        for canonical_taxon_id in sorted_taxon_ids:
            items_per_taxon[canonical_taxon_id].sort(
                key=lambda row: self._distractor_item_sort_key(
                    difficulty_policy=difficulty_policy,
                    row=row,
                )
            )

        target_rows: list[dict[str, object]] = []
        for canonical_taxon_id in sorted_taxon_ids:
            target_rows.extend(items_per_taxon[canonical_taxon_id])
        target_rows.sort(
            key=lambda row: self._pack_item_sort_key(
                difficulty_policy=difficulty_policy,
                canonical_taxon_id=str(row["canonical_taxon_id"]),
                playable_item_id=str(row["playable_item_id"]),
                difficulty_level=str(row["difficulty_level"]),
            )
        )

        questions: list[CompiledPackQuestion] = []
        for target_row in target_rows:
            target_taxon = str(target_row["canonical_taxon_id"])
            target_similar_taxon_ids = {
                taxon_id
                for taxon_id in self._normalize_similar_taxon_ids(target_row)
                if taxon_id != target_taxon
            }
            target_similar_taxon_ids.update(
                taxon_id
                for taxon_id in inat_similar_taxa_by_target.get(target_taxon, [])
                if taxon_id != target_taxon
            )
            distractor_candidates = [
                items_per_taxon[canonical_taxon_id][0]
                for canonical_taxon_id in sorted_taxon_ids
                if canonical_taxon_id != target_taxon and items_per_taxon[canonical_taxon_id]
            ]
            prioritized_candidates = [
                row
                for row in distractor_candidates
                if str(row["canonical_taxon_id"]) in target_similar_taxon_ids
            ]
            fallback_candidates = [
                row
                for row in distractor_candidates
                if str(row["canonical_taxon_id"]) not in target_similar_taxon_ids
            ]
            prioritized_candidates.sort(
                key=lambda row: self._distractor_item_sort_key(
                    difficulty_policy=difficulty_policy,
                    row=row,
                )
            )
            fallback_candidates.sort(
                key=lambda row: self._distractor_item_sort_key(
                    difficulty_policy=difficulty_policy,
                    row=row,
                )
            )

            selected_distractors = prioritized_candidates[:3]
            if len(selected_distractors) < 3:
                selected_distractors.extend(
                    fallback_candidates[: 3 - len(selected_distractors)]
                )
            if len(selected_distractors) < 3:
                continue
            questions.append(
                CompiledPackQuestion(
                    position=len(questions) + 1,
                    target_playable_item_id=str(target_row["playable_item_id"]),
                    target_canonical_taxon_id=target_taxon,
                    distractor_playable_item_ids=[
                        str(item["playable_item_id"]) for item in selected_distractors
                    ],
                    distractor_canonical_taxon_ids=[
                        str(item["canonical_taxon_id"]) for item in selected_distractors
                    ],
                )
            )
            if len(questions) >= question_count_requested:
                break
        return questions

    def _fetch_inat_similar_taxa_by_target(
        self,
        connection: psycopg.Connection,
        *,
        canonical_taxon_ids: Sequence[str],
    ) -> dict[str, list[str]]:
        unique_taxon_ids = list(dict.fromkeys(canonical_taxon_ids))
        if not unique_taxon_ids:
            return {}

        rows = connection.execute(
            """
            SELECT
                canonical_taxon_id,
                external_source_mappings_json,
                external_similarity_hints_json
            FROM canonical_taxa
            WHERE canonical_taxon_id = ANY(%s)
            ORDER BY canonical_taxon_id
            """,
            (unique_taxon_ids,),
        ).fetchall()

        inat_external_id_to_canonical_taxon_id: dict[str, str] = {}
        hints_by_canonical_taxon_id: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            canonical_taxon_id = str(row["canonical_taxon_id"])
            mappings = self._parse_json_list_of_dicts(row["external_source_mappings_json"])
            for mapping in mappings:
                source_name = str(mapping.get("source_name") or "")
                external_id = str(mapping.get("external_id") or "").strip()
                if source_name == "inaturalist" and external_id:
                    inat_external_id_to_canonical_taxon_id[external_id] = canonical_taxon_id

            hints_by_canonical_taxon_id[canonical_taxon_id] = self._parse_json_list_of_dicts(
                row["external_similarity_hints_json"]
            )

        similar_taxa_by_target: dict[str, list[str]] = {}
        for target_taxon_id in unique_taxon_ids:
            seen: set[str] = set()
            resolved_taxa: list[str] = []
            for hint in hints_by_canonical_taxon_id.get(target_taxon_id, []):
                source_name = str(hint.get("source_name") or "")
                if source_name != "inaturalist":
                    continue
                external_taxon_id = str(hint.get("external_taxon_id") or "").strip()
                if not external_taxon_id:
                    continue
                mapped_taxon_id = inat_external_id_to_canonical_taxon_id.get(external_taxon_id)
                if (
                    mapped_taxon_id is None
                    or mapped_taxon_id == target_taxon_id
                    or mapped_taxon_id in seen
                ):
                    continue
                seen.add(mapped_taxon_id)
                resolved_taxa.append(mapped_taxon_id)
            similar_taxa_by_target[target_taxon_id] = sorted(resolved_taxa)

        return similar_taxa_by_target

    def _parse_json_list_of_dicts(self, raw_value: object) -> list[dict[str, object]]:
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                return []
        elif isinstance(raw_value, list):
            parsed = raw_value
        else:
            return []

        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    def _normalize_playable_pack_row(self, row: dict[str, object]) -> dict[str, object]:
        row["similar_taxon_ids"] = self._normalize_similar_taxon_ids(row)
        return row

    def _normalize_similar_taxon_ids(self, row: dict[str, object]) -> list[str]:
        raw_value = row.get("similar_taxon_ids")
        if raw_value is None:
            raw_value = row.get("similar_taxon_ids_json")

        parsed: list[object]
        if isinstance(raw_value, str):
            try:
                decoded = json.loads(raw_value)
            except json.JSONDecodeError:
                decoded = []
            parsed = decoded if isinstance(decoded, list) else []
        elif isinstance(raw_value, list):
            parsed = raw_value
        else:
            parsed = []

        normalized: list[str] = []
        for value in parsed:
            text = str(value).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _distractor_item_sort_key(
        self,
        *,
        difficulty_policy: str,
        row: dict[str, object],
    ) -> tuple[int, int, int, str, str]:
        media_role = str(row.get("media_role") or "")
        media_role_priority = {
            "primary_id": 0,
            "context": 1,
            "non_diagnostic": 2,
            "distractor_risk": 3,
        }
        confusion_relevance = str(row.get("confusion_relevance") or "")
        confusion_relevance_priority = {
            "high": 0,
            "medium": 1,
            "low": 2,
            "none": 3,
        }
        pack_sort_key = self._pack_item_sort_key(
            difficulty_policy=difficulty_policy,
            canonical_taxon_id=str(row["canonical_taxon_id"]),
            playable_item_id=str(row["playable_item_id"]),
            difficulty_level=str(row["difficulty_level"]),
        )
        return (
            media_role_priority.get(media_role, 99),
            confusion_relevance_priority.get(confusion_relevance, 99),
            pack_sort_key[0],
            pack_sort_key[1],
            pack_sort_key[2],
        )

    def _pack_item_sort_key(
        self,
        *,
        difficulty_policy: str,
        canonical_taxon_id: str,
        playable_item_id: str,
        difficulty_level: str,
    ) -> tuple[int, str, str]:
        if difficulty_policy == "easy":
            difficulty_priority = {"easy": 0, "medium": 1, "hard": 2, "unknown": 3}
            return (
                difficulty_priority.get(difficulty_level, 99),
                canonical_taxon_id,
                playable_item_id,
            )
        if difficulty_policy == "balanced":
            difficulty_priority = {"medium": 0, "easy": 1, "hard": 2, "unknown": 3}
            return (
                difficulty_priority.get(difficulty_level, 99),
                canonical_taxon_id,
                playable_item_id,
            )
        if difficulty_policy == "hard":
            difficulty_priority = {"hard": 0, "medium": 1, "easy": 2, "unknown": 3}
            return (
                difficulty_priority.get(difficulty_level, 99),
                canonical_taxon_id,
                playable_item_id,
            )
        return (0, canonical_taxon_id, playable_item_id)

    def fetch_qualification_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
        with self.connect() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM qualified_resources_history
                    WHERE run_id = %s
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
                    WHERE run_id = %s
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
