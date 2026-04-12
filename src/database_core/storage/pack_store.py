from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from database_core.domain.enums import PackCompilationReasonCode, PackMaterializationPurpose
from database_core.domain.models import (
    CompiledPackBuild,
    CompiledPackQuestion,
    MaterializedPack,
    PackCompilationAttempt,
    PackCompilationDeficit,
    PackRevision,
    PackRevisionParameters,
    PackSpec,
    PackTaxonDeficit,
)
from database_core.pack import (
    validate_compiled_pack,
    validate_pack_diagnostic,
    validate_pack_materialization,
    validate_pack_spec,
)
from database_core.versioning import (
    COMPILED_PACK_VERSION,
    PACK_DIAGNOSTIC_VERSION,
    PACK_MATERIALIZATION_VERSION,
    PACK_SPEC_VERSION,
    SCHEMA_VERSION_LABEL,
)

MIN_PACK_TAXA_SERVED = 10
MIN_PACK_MEDIA_PER_TAXON = 2
MIN_PACK_TOTAL_QUESTIONS = 20


class PostgresPackStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    def create_pack(
        self,
        *,
        parameters: PackRevisionParameters | dict[str, object],
        pack_id: str | None = None,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
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
            with self._connect() as owned_connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
            with self._connect() as owned_connection:
                return self.diagnose_pack(
                    pack_id=pack_id,
                    revision=revision,
                    connection=owned_connection,
                )

        context = self.compute_pack_compilation_context(
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
            with self._connect() as owned_connection:
                return self.compile_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=question_count,
                    connection=owned_connection,
                )

        context = self.compute_pack_compilation_context(
            connection,
            pack_id=pack_id,
            revision=revision,
            question_count_requested=max(question_count, MIN_PACK_TOTAL_QUESTIONS),
        )
        if not context["compilable"]:
            deficits = ", ".join(
                f"{item.code}:{item.current}/{item.required}" for item in context["deficits"]
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
            with self._connect() as owned_connection:
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
            materialization_id=f"packmat:{pack_id}:{revision_value}:{purpose_value}:{uuid4().hex[:8]}",
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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

    def compute_pack_compilation_context(
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
            len(items_per_taxon[canonical_taxon_id])
            for canonical_taxon_id in requested_taxa
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
            observed_from=row["observed_from"],
            observed_to=row["observed_to"],
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
                selected_distractors.extend(fallback_candidates[: 3 - len(selected_distractors)])
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


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _executemany(
    connection: psycopg.Connection,
    statement: str,
    values: Sequence[Sequence[object]],
) -> None:
    if not values:
        return
    with connection.cursor() as cursor:
        cursor.executemany(statement, values)
