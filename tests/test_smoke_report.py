from pathlib import Path

from database_core.ops import generate_smoke_report
from database_core.pipeline.runner import run_pipeline
from database_core.storage.sqlite import SQLiteRepository


def test_generate_smoke_report_includes_locked_kpis(tmp_path: Path) -> None:
    db_path = tmp_path / "smoke.sqlite"
    run_pipeline(
        db_path=db_path,
        normalized_snapshot_path=tmp_path / "normalized.json",
        qualification_snapshot_path=tmp_path / "qualified.json",
        export_path=tmp_path / "export.json",
    )
    repository = SQLiteRepository(db_path)
    report = generate_smoke_report(
        repository,
        snapshot_id=None,
        db_path=db_path,
    )

    assert report["report_version"] == "smoke.report.v1"
    assert report["overall_pass"] is True
    kpis = report["kpis"]
    assert set(kpis.keys()) == {
        "exportable_unresolved_or_provisional",
        "governance_reason_and_signal_coverage",
        "export_trace_flags_uncertainty_coverage",
    }
    assert kpis["exportable_unresolved_or_provisional"]["actual"] == 0
    assert kpis["governance_reason_and_signal_coverage"]["actual"] == 1.0
    assert kpis["export_trace_flags_uncertainty_coverage"]["actual"] == 1.0

