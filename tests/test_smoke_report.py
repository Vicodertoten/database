import json
from pathlib import Path
from urllib.parse import urlsplit

from database_core.ops import generate_smoke_report
from database_core.pipeline.runner import run_pipeline
from database_core.storage.services import build_storage_services


def _build_repository(database_url: str):
    return build_storage_services(database_url).pipeline_store


def test_generate_smoke_report_includes_locked_kpis(tmp_path: Path, database_url: str) -> None:
    run_pipeline(
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "normalized.json",
        qualification_snapshot_path=tmp_path / "qualified.json",
        export_path=tmp_path / "export.json",
    )
    repository = _build_repository(database_url)
    report = generate_smoke_report(
        repository,
        snapshot_id=None,
        database_url=database_url,
    )

    assert report["report_version"] == "smoke.report.v1"
    redacted_database_url = str(report["database_url"])
    assert redacted_database_url != database_url
    parsed_redacted = urlsplit(redacted_database_url)
    parsed_raw = urlsplit(database_url)
    assert parsed_redacted.scheme == parsed_raw.scheme
    assert parsed_redacted.hostname == parsed_raw.hostname
    assert parsed_redacted.port == parsed_raw.port
    assert parsed_redacted.username == parsed_raw.username
    assert parsed_redacted.password == "***"
    assert parsed_redacted.path == parsed_raw.path
    assert parsed_redacted.query == parsed_raw.query
    assert "db_path" not in report
    assert report["overall_pass"] is True
    kpis = report["kpis"]
    assert set(kpis.keys()) == {
        "exportable_unresolved_or_provisional",
        "governance_reason_and_signal_coverage",
        "export_trace_flags_uncertainty_coverage",
    }
    assert kpis["exportable_unresolved_or_provisional"]["actual"] == 0
    assert kpis["governance_reason_and_signal_coverage"]["actual"] == 1.0
    assert (
        kpis["governance_reason_and_signal_coverage"]["stats"]["missing_source_delta"] == 0
    )
    assert kpis["export_trace_flags_uncertainty_coverage"]["actual"] == 1.0
    extended_kpis = report["extended_kpis"]
    assert set(extended_kpis.keys()) == {
        "taxon_playable_coverage_ratio",
        "taxon_with_min2_media_ratio",
        "country_code_completeness_ratio",
        "distractor_diversity_index",
    }
    for key in extended_kpis:
        assert extended_kpis[key]["target"] == "baseline_observe"
        assert extended_kpis[key]["pass"] is None
        assert isinstance(extended_kpis[key]["actual"], float)
        assert isinstance(extended_kpis[key]["stats"], dict)
    compile_deficits_summary = report["compile_deficits_summary"]
    assert set(compile_deficits_summary.keys()) == {
        "attempts_total",
        "non_compilable_attempts",
        "reason_counts",
        "top_blocking_taxa",
    }
    assert isinstance(compile_deficits_summary["attempts_total"], int)
    assert isinstance(compile_deficits_summary["non_compilable_attempts"], int)
    assert isinstance(compile_deficits_summary["reason_counts"], dict)
    assert isinstance(compile_deficits_summary["top_blocking_taxa"], list)
    assert set(report["governance_review_alerts"].keys()) == {
        "open_backlog",
        "avg_open_age_hours",
        "thresholds",
        "open_backlog_alert",
        "avg_open_age_alert",
    }
    latest_run = report["latest_run"]
    assert isinstance(latest_run, dict)
    assert isinstance(latest_run["started_at"], str)
    assert isinstance(latest_run["completed_at"], str)
    json.dumps(report)


def test_generate_smoke_report_uses_locked_kpi_registry(tmp_path: Path, database_url: str) -> None:
    run_pipeline(
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "normalized_registry.json",
        qualification_snapshot_path=tmp_path / "qualified_registry.json",
        export_path=tmp_path / "export_registry.json",
    )
    repository = _build_repository(database_url)
    report = generate_smoke_report(
        repository,
        snapshot_id=None,
        database_url=database_url,
    )

    # Keep smoke report KPI names stable and sourced from the locked registry.
    from database_core.ops.smoke_report import _LOCKED_KPIS

    assert set(report["kpis"].keys()) == set(_LOCKED_KPIS.keys())
    for name, expected_target in _LOCKED_KPIS.items():
        assert report["kpis"][name]["target"] == expected_target


def test_generate_smoke_report_phase1_additive_contract(tmp_path: Path, database_url: str) -> None:
    run_pipeline(
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "normalized_phase1.json",
        qualification_snapshot_path=tmp_path / "qualified_phase1.json",
        export_path=tmp_path / "export_phase1.json",
    )
    repository = _build_repository(database_url)
    report = generate_smoke_report(
        repository,
        snapshot_id=None,
        database_url=database_url,
    )

    assert report["report_version"] == "smoke.report.v1"
    assert "kpis" in report
    assert "overall_pass" in report
    assert "extended_kpis" in report
    assert "compile_deficits_summary" in report
