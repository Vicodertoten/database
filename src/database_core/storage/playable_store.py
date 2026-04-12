from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import psycopg

from database_core.domain.enums import InvalidationReason
from database_core.domain.models import PlayableItem
from database_core.playable import validate_playable_corpus
from database_core.versioning import PLAYABLE_CORPUS_VERSION, SCHEMA_VERSION_LABEL


class PostgresPlayableStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    # ------------------------------------------------------------------
    # Write — playable corpus lifecycle
    # ------------------------------------------------------------------

    def save_playable_items(
        self,
        playable_items: Sequence[PlayableItem],
        *,
        run_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self._connect() as owned_connection:
                self.save_playable_items(
                    playable_items,
                    run_id=run_id,
                    connection=owned_connection,
                )
            return

        current_run_id = _resolve_playable_run_id(playable_items, explicit_run_id=run_id)

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
            ON CONFLICT (playable_item_id)
            DO UPDATE SET
                run_id = EXCLUDED.run_id,
                qualified_resource_id = EXCLUDED.qualified_resource_id,
                canonical_taxon_id = EXCLUDED.canonical_taxon_id,
                media_asset_id = EXCLUDED.media_asset_id,
                source_observation_uid = EXCLUDED.source_observation_uid,
                source_name = EXCLUDED.source_name,
                source_observation_id = EXCLUDED.source_observation_id,
                source_media_id = EXCLUDED.source_media_id,
                scientific_name = EXCLUDED.scientific_name,
                common_names_i18n_json = EXCLUDED.common_names_i18n_json,
                difficulty_level = EXCLUDED.difficulty_level,
                media_role = EXCLUDED.media_role,
                learning_suitability = EXCLUDED.learning_suitability,
                confusion_relevance = EXCLUDED.confusion_relevance,
                diagnostic_feature_visibility = EXCLUDED.diagnostic_feature_visibility,
                similar_taxon_ids_json = EXCLUDED.similar_taxon_ids_json,
                what_to_look_at_specific_json = EXCLUDED.what_to_look_at_specific_json,
                what_to_look_at_general_json = EXCLUDED.what_to_look_at_general_json,
                confusion_hint = EXCLUDED.confusion_hint,
                country_code = EXCLUDED.country_code,
                observed_at = EXCLUDED.observed_at,
                location_point = EXCLUDED.location_point,
                location_bbox = EXCLUDED.location_bbox,
                location_radius_meters = EXCLUDED.location_radius_meters
            """,
            [
                (
                    item.playable_item_id,
                    current_run_id,
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

        _executemany(
            connection,
            """
            INSERT INTO playable_item_lifecycle (
                playable_item_id,
                qualified_resource_id,
                lifecycle_status,
                created_run_id,
                last_seen_run_id,
                invalidated_run_id,
                invalidation_reason,
                created_at,
                updated_at
            ) VALUES (%s, %s, 'active', %s, %s, NULL, NULL, now(), now())
            ON CONFLICT (playable_item_id)
            DO UPDATE SET
                qualified_resource_id = EXCLUDED.qualified_resource_id,
                lifecycle_status = 'active',
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                invalidated_run_id = NULL,
                invalidation_reason = NULL,
                updated_at = now()
            """,
            [
                (
                    item.playable_item_id,
                    item.qualified_resource_id,
                    item.run_id,
                    item.run_id,
                )
                for item in playable_items
            ],
        )

        if current_run_id is None:
            return

        active_ids = [item.playable_item_id for item in playable_items]
        self._invalidate_missing_playable_items(
            connection,
            current_run_id=current_run_id,
            active_ids=active_ids,
        )

    def _invalidate_missing_playable_items(
        self,
        connection: psycopg.Connection,
        *,
        current_run_id: str,
        active_ids: Sequence[str],
    ) -> None:
        reason_params: tuple[object, ...] = (
            current_run_id,
            InvalidationReason.SOURCE_RECORD_REMOVED,
            InvalidationReason.CANONICAL_TAXON_NOT_ACTIVE,
            InvalidationReason.QUALIFICATION_NOT_EXPORTABLE,
            InvalidationReason.POLICY_FILTERED,
        )

        active_filter_sql = ""
        active_filter_params: tuple[object, ...] = ()
        if active_ids:
            active_filter_sql = "AND NOT (l.playable_item_id = ANY(%s::TEXT[]))"
            active_filter_params = (active_ids,)

        connection.execute(
            f"""
            UPDATE playable_item_lifecycle AS l
            SET
                lifecycle_status = 'invalidated',
                invalidated_run_id = %s,
                invalidation_reason = CASE
                    WHEN q.qualified_resource_id IS NULL
                      OR o.observation_uid IS NULL
                      OR m.media_id IS NULL THEN %s
                    WHEN c.canonical_taxon_id IS NULL
                      OR c.taxon_status <> 'active' THEN %s
                    WHEN q.export_eligible IS FALSE THEN %s
                    ELSE %s
                END,
                updated_at = now()
            FROM playable_items AS p
            LEFT JOIN qualified_resources AS q
                ON q.qualified_resource_id = p.qualified_resource_id
            LEFT JOIN source_observations AS o
                ON o.observation_uid = p.source_observation_uid
            LEFT JOIN media_assets AS m
                ON m.media_id = p.media_asset_id
            LEFT JOIN canonical_taxa AS c
                ON c.canonical_taxon_id = p.canonical_taxon_id
            WHERE l.playable_item_id = p.playable_item_id
              AND l.lifecycle_status = 'active'
              {active_filter_sql}
            """,
            (*reason_params, *active_filter_params),
        )

    # ------------------------------------------------------------------
    # Read — playable corpus queries
    # ------------------------------------------------------------------

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
        with self._connect() as connection:
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
        with self._connect() as connection:
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

    def fetch_playable_invalidations(
        self,
        *,
        invalidated_run_id: str | None = None,
        invalidation_reason: str | None = None,
        lifecycle_status: str = "invalidated",
        limit: int = 100,
    ) -> list[dict[str, object]]:
        conditions = ["l.lifecycle_status = %s"]
        params: list[object] = [lifecycle_status]

        if invalidated_run_id is not None:
            conditions.append("l.invalidated_run_id = %s")
            params.append(invalidated_run_id)
        if invalidation_reason is not None:
            conditions.append("l.invalidation_reason = %s")
            params.append(invalidation_reason)

        where_sql = " AND ".join(conditions)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    l.playable_item_id,
                    l.qualified_resource_id,
                    l.lifecycle_status,
                    l.created_run_id,
                    l.last_seen_run_id,
                    l.invalidated_run_id,
                    l.invalidation_reason,
                    l.created_at,
                    l.updated_at,
                    p.canonical_taxon_id,
                    p.media_asset_id,
                    p.scientific_name
                FROM playable_item_lifecycle AS l
                LEFT JOIN playable_items AS p
                    ON p.playable_item_id = l.playable_item_id
                WHERE {where_sql}
                ORDER BY l.updated_at DESC, l.playable_item_id
                LIMIT %s
                """,
                [*params, limit],
            ).fetchall()

        return [
            {
                "playable_item_id": row["playable_item_id"],
                "qualified_resource_id": row["qualified_resource_id"],
                "lifecycle_status": row["lifecycle_status"],
                "created_run_id": row["created_run_id"],
                "last_seen_run_id": row["last_seen_run_id"],
                "invalidated_run_id": row["invalidated_run_id"],
                "invalidation_reason": row["invalidation_reason"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "canonical_taxon_id": row["canonical_taxon_id"],
                "media_asset_id": row["media_asset_id"],
                "scientific_name": row["scientific_name"],
            }
            for row in rows
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


def _resolve_playable_run_id(
    playable_items: Sequence[PlayableItem],
    *,
    explicit_run_id: str | None,
) -> str | None:
    if explicit_run_id is not None:
        mismatched_ids = sorted(
            {item.run_id for item in playable_items if item.run_id != explicit_run_id}
        )
        if mismatched_ids:
            raise ValueError(
                "save_playable_items requires a single run_id. "
                f"explicit run_id={explicit_run_id} mismatches item run_ids={mismatched_ids}"
            )
        return explicit_run_id

    if not playable_items:
        return None

    run_ids = sorted({item.run_id for item in playable_items})
    if len(run_ids) != 1:
        raise ValueError(
            "save_playable_items requires all playable items to share the same run_id "
            f"when no explicit run_id is provided; got run_ids={run_ids}"
        )
    return run_ids[0]
