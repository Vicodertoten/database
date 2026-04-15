from __future__ import annotations

import json
from datetime import UTC, datetime

from database_core.security import redact_database_url
from database_core.storage.services import PostgresPipelineStore

_REPORT_VERSION = "smoke.report.v1"
_SIGNAL_KEYS = {
    "target_exists_and_active",
    "target_not_provisional",
    "lineage_consistent",
    "source_authority_consistent",
    "mapping_conflict_uniquely_resolved",
    "score",
}
_TYPED_UNCERTAINTY_VALUES = {
    "none",
    "occlusion",
    "angle",
    "distance",
    "motion",
    "multiple_subjects",
    "model_uncertain",
    "taxonomy_ambiguous",
}
_GOVERNANCE_OPEN_BACKLOG_ALERT_THRESHOLD = 25
_GOVERNANCE_AVG_AGE_HOURS_ALERT_THRESHOLD = 72.0
_LOCKED_KPIS = {
    "exportable_unresolved_or_provisional": "== 0",
    "governance_reason_and_signal_coverage": "== 1.0",
    "export_trace_flags_uncertainty_coverage": "== 1.0",
}


def generate_smoke_report(
    repository: PostgresPipelineStore,
    *,
    snapshot_id: str | None,
    database_url: str,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    timestamp = generated_at or datetime.now(UTC)
    run_metrics = repository.fetch_run_level_metrics()
    with repository.connect() as connection:
        latest_run = connection.execute(
            """
            SELECT run_id, started_at, completed_at, run_status
            FROM pipeline_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        unresolved_or_provisional_exportable_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM qualified_resources AS resource
                LEFT JOIN canonical_taxa AS taxon
                    ON taxon.canonical_taxon_id = resource.canonical_taxon_id
                WHERE resource.export_eligible = TRUE
                  AND (
                        taxon.canonical_taxon_id IS NULL
                        OR taxon.taxon_status = 'provisional'
                        OR resource.qualification_status != 'accepted'
                  )
                """
            ).fetchone()["count"]
        )
        governance_reason_signal = _governance_reason_signal_coverage(connection=connection)
        export_trace_flags_uncertainty = _export_trace_flags_uncertainty_coverage(
            connection=connection
        )

    kpi_exportable_unresolved_provisional = {
        "target": _LOCKED_KPIS["exportable_unresolved_or_provisional"],
        "actual": unresolved_or_provisional_exportable_count,
        "pass": unresolved_or_provisional_exportable_count == 0,
    }
    kpi_governance_reason_signal = {
        "target": _LOCKED_KPIS["governance_reason_and_signal_coverage"],
        "actual": governance_reason_signal["coverage_ratio"],
        "pass": governance_reason_signal["coverage_ratio"] == 1.0,
        "stats": governance_reason_signal,
    }
    kpi_export_trace_flags_uncertainty = {
        "target": _LOCKED_KPIS["export_trace_flags_uncertainty_coverage"],
        "actual": export_trace_flags_uncertainty["coverage_ratio"],
        "pass": export_trace_flags_uncertainty["coverage_ratio"] == 1.0,
        "stats": export_trace_flags_uncertainty,
    }
    kpis = {
        "exportable_unresolved_or_provisional": kpi_exportable_unresolved_provisional,
        "governance_reason_and_signal_coverage": kpi_governance_reason_signal,
        "export_trace_flags_uncertainty_coverage": kpi_export_trace_flags_uncertainty,
    }
    overall_pass = all(bool(item["pass"]) for item in kpis.values())
    governance_metrics = run_metrics.get("governance", {})
    governance_open_backlog = int(governance_metrics.get("open_governance_review_items", 0))
    governance_avg_age = float(
        governance_metrics.get("avg_open_governance_review_age_hours", 0.0)
    )
    governance_review_alerts = {
        "open_backlog": governance_open_backlog,
        "avg_open_age_hours": governance_avg_age,
        "thresholds": {
            "open_backlog": _GOVERNANCE_OPEN_BACKLOG_ALERT_THRESHOLD,
            "avg_open_age_hours": _GOVERNANCE_AVG_AGE_HOURS_ALERT_THRESHOLD,
        },
        "open_backlog_alert": governance_open_backlog > _GOVERNANCE_OPEN_BACKLOG_ALERT_THRESHOLD,
        "avg_open_age_alert": governance_avg_age > _GOVERNANCE_AVG_AGE_HOURS_ALERT_THRESHOLD,
    }

    return {
        "report_version": _REPORT_VERSION,
        "generated_at": timestamp.isoformat(),
        "snapshot_id": snapshot_id,
        "database_url": redact_database_url(database_url),
        "latest_run": (
            {
                "run_id": latest_run["run_id"],
                "started_at": _serialize_datetime(latest_run["started_at"]),
                "completed_at": _serialize_datetime(latest_run["completed_at"]),
                "run_status": latest_run["run_status"],
            }
            if latest_run
            else None
        ),
        "run_metrics": run_metrics,
        "governance_review_alerts": governance_review_alerts,
        "kpis": kpis,
        "overall_pass": overall_pass,
    }


def _governance_reason_signal_coverage(*, connection) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT decision_reason, payload_json
        FROM canonical_governance_events
        """
    ).fetchall()
    if not rows:
        return {
            "total": 0,
            "covered": 0,
            "coverage_ratio": 1.0,
            "missing_reason": 0,
            "missing_signal_breakdown": 0,
            "missing_source_delta": 0,
        }

    covered = 0
    missing_reason = 0
    missing_signal_breakdown = 0
    missing_source_delta = 0
    for row in rows:
        reason = str(row["decision_reason"] or "").strip()
        payload = _safe_load_json(row["payload_json"])
        signal_breakdown = payload.get("signal_breakdown") if isinstance(payload, dict) else None
        source_delta = payload.get("source_delta") if isinstance(payload, dict) else None
        has_reason = bool(reason)
        has_signal_breakdown = _valid_signal_breakdown(signal_breakdown)
        has_source_delta = _valid_source_delta(source_delta)
        if has_reason and has_signal_breakdown and has_source_delta:
            covered += 1
            continue
        if not has_reason:
            missing_reason += 1
        if not has_signal_breakdown:
            missing_signal_breakdown += 1
        if not has_source_delta:
            missing_source_delta += 1

    total = len(rows)
    return {
        "total": total,
        "covered": covered,
        "coverage_ratio": round(covered / total, 6),
        "missing_reason": missing_reason,
        "missing_signal_breakdown": missing_signal_breakdown,
        "missing_source_delta": missing_source_delta,
    }


def _export_trace_flags_uncertainty_coverage(*, connection) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT provenance_summary_json, qualification_flags_json, uncertainty_reason
        FROM qualified_resources
        WHERE export_eligible = TRUE
        """
    ).fetchall()
    if not rows:
        return {
            "total": 0,
            "covered": 0,
            "coverage_ratio": 1.0,
            "missing_trace": 0,
            "missing_flags": 0,
            "untyped_uncertainty": 0,
        }

    covered = 0
    missing_trace = 0
    missing_flags = 0
    untyped_uncertainty = 0
    for row in rows:
        provenance = _safe_load_json(row["provenance_summary_json"])
        flags = _safe_load_json(row["qualification_flags_json"])
        uncertainty_reason = str(row["uncertainty_reason"] or "")
        has_trace = _has_ai_trace(provenance)
        has_flags = isinstance(flags, list)
        has_typed_uncertainty = uncertainty_reason in _TYPED_UNCERTAINTY_VALUES
        if has_trace and has_flags and has_typed_uncertainty:
            covered += 1
            continue
        if not has_trace:
            missing_trace += 1
        if not has_flags:
            missing_flags += 1
        if not has_typed_uncertainty:
            untyped_uncertainty += 1

    total = len(rows)
    return {
        "total": total,
        "covered": covered,
        "coverage_ratio": round(covered / total, 6),
        "missing_trace": missing_trace,
        "missing_flags": missing_flags,
        "untyped_uncertainty": untyped_uncertainty,
    }


def _has_ai_trace(provenance: object) -> bool:
    if not isinstance(provenance, dict):
        return False
    qualification_method = str(provenance.get("qualification_method") or "").strip()
    ai_status = str(provenance.get("ai_status") or "").strip()
    return bool(qualification_method) and bool(ai_status)


def _valid_signal_breakdown(signal_breakdown: object) -> bool:
    if not isinstance(signal_breakdown, dict):
        return False
    if not _SIGNAL_KEYS.issubset(signal_breakdown.keys()):
        return False
    if not isinstance(signal_breakdown["score"], int):
        return False
    for key in _SIGNAL_KEYS - {"score"}:
        if not isinstance(signal_breakdown[key], bool):
            return False
    return True


def _safe_load_json(raw_value: object) -> object:
    if not isinstance(raw_value, str):
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return None


def _serialize_datetime(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _valid_source_delta(source_delta: object) -> bool:
    if not isinstance(source_delta, dict):
        return False
    required = {
        "source_taxon_id_previous",
        "source_taxon_id_current",
        "name_previous",
        "name_current",
        "is_active_previous",
        "is_active_current",
        "provisional_previous",
        "provisional_current",
        "parent_id_previous",
        "parent_id_current",
        "ancestor_ids_previous",
        "ancestor_ids_current",
        "taxon_changes_count_previous",
        "taxon_changes_count_current",
        "current_synonymous_taxon_ids_previous",
        "current_synonymous_taxon_ids_current",
    }
    if not required.issubset(source_delta.keys()):
        return False
    for list_key in (
        "ancestor_ids_previous",
        "ancestor_ids_current",
        "current_synonymous_taxon_ids_previous",
        "current_synonymous_taxon_ids_current",
    ):
        if not isinstance(source_delta[list_key], list):
            return False
    return True
