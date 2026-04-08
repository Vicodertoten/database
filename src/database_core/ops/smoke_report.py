from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from database_core.storage.sqlite import SQLiteRepository

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


def generate_smoke_report(
    repository: SQLiteRepository,
    *,
    snapshot_id: str | None,
    db_path: Path,
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
                WHERE resource.export_eligible = 1
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
        "target": "== 0",
        "actual": unresolved_or_provisional_exportable_count,
        "pass": unresolved_or_provisional_exportable_count == 0,
    }
    kpi_governance_reason_signal = {
        "target": "== 1.0",
        "actual": governance_reason_signal["coverage_ratio"],
        "pass": governance_reason_signal["coverage_ratio"] == 1.0,
        "stats": governance_reason_signal,
    }
    kpi_export_trace_flags_uncertainty = {
        "target": "== 1.0",
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

    return {
        "report_version": _REPORT_VERSION,
        "generated_at": timestamp.isoformat(),
        "snapshot_id": snapshot_id,
        "db_path": str(db_path),
        "latest_run": (
            {
                "run_id": latest_run["run_id"],
                "started_at": latest_run["started_at"],
                "completed_at": latest_run["completed_at"],
                "run_status": latest_run["run_status"],
            }
            if latest_run
            else None
        ),
        "run_metrics": run_metrics,
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
        }

    covered = 0
    missing_reason = 0
    missing_signal_breakdown = 0
    for row in rows:
        reason = str(row["decision_reason"] or "").strip()
        payload = _safe_load_json(row["payload_json"])
        signal_breakdown = payload.get("signal_breakdown") if isinstance(payload, dict) else None
        has_reason = bool(reason)
        has_signal_breakdown = _valid_signal_breakdown(signal_breakdown)
        if has_reason and has_signal_breakdown:
            covered += 1
            continue
        if not has_reason:
            missing_reason += 1
        if not has_signal_breakdown:
            missing_signal_breakdown += 1

    total = len(rows)
    return {
        "total": total,
        "covered": covered,
        "coverage_ratio": round(covered / total, 6),
        "missing_reason": missing_reason,
        "missing_signal_breakdown": missing_signal_breakdown,
    }


def _export_trace_flags_uncertainty_coverage(*, connection) -> dict[str, object]:
    rows = connection.execute(
        """
        SELECT provenance_summary_json, qualification_flags_json, uncertainty_reason
        FROM qualified_resources
        WHERE export_eligible = 1
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

