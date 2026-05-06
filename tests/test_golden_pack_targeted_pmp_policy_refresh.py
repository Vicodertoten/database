from __future__ import annotations

import json
from pathlib import Path

from scripts import refresh_golden_pack_v1_targeted_pmp_policy as refresh


def test_targeted_pmp_policy_refresh_dry_run_and_apply(tmp_path: Path) -> None:
    evidence_path = Path("docs/audits/evidence/database_integrity_runtime_handoff_audit.json")
    evidence_before = evidence_path.read_text(encoding="utf-8")

    dry_dir = refresh.run_refresh(mode="dry-run", max_per_target=3, max_total=30, output_root=tmp_path)
    assert (dry_dir / "dry_run_plan.json").exists()
    assert not (dry_dir / "pack.json").exists()

    dry = json.loads((dry_dir / "dry_run_plan.json").read_text(encoding="utf-8"))
    assert "summary" in dry
    assert dry["summary"]["total_candidates"] >= dry["summary"]["apply_ready_candidates"]

    batch = dry["apply_ready_batch"]
    if len(batch) >= 2:
        assert batch[0]["priority_rank"] <= batch[-1]["priority_rank"]

    skipped = json.loads((dry_dir / "rejected_or_skipped_media.json").read_text(encoding="utf-8"))
    for row in skipped["skipped"]:
        if "borderline_inspection_only" in row.get("skip_reasons", []):
            assert row["policy_eval"]["eligible"] is False

    apply_dir = refresh.run_refresh(mode="apply", max_per_target=2, max_total=20, output_root=tmp_path)
    assert (apply_dir / "refresh_results.json").exists()
    assert (apply_dir / "pmp_evaluation_queue.json").exists()
    assert not (apply_dir / "pack.json").exists()

    res = json.loads((apply_dir / "refresh_results.json").read_text(encoding="utf-8"))
    assert "summary" in res
    assert "results" in res
    for row in res["results"]:
        if row["borderline"] is True:
            assert row["eligible"] is False

    manifest = json.loads((apply_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["flags"]["DATABASE_PHASE_CLOSED"] is False
    assert manifest["flags"]["PERSIST_DISTRACTOR_RELATIONSHIPS_V1"] is False

    evidence_after = evidence_path.read_text(encoding="utf-8")
    assert evidence_before == evidence_after

