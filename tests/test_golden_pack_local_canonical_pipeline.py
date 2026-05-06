from __future__ import annotations

import json
from pathlib import Path

from scripts.run_golden_pack_v1_local_canonical_pipeline import run_pipeline


def test_local_canonical_pipeline_outputs_isolated_run(tmp_path: Path) -> None:
    baseline_history = json.loads(
        Path("docs/audits/evidence/database_integrity_runtime_handoff_audit.json").read_text(encoding="utf-8")
    )

    run_dir = run_pipeline(output_root=tmp_path)

    assert run_dir.exists()
    assert (run_dir / "run_manifest.json").exists()
    assert (run_dir / "input_inventory.json").exists()
    assert (run_dir / "lineage_checks.json").exists()
    assert (run_dir / "candidate_readiness.json").exists()

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    inv = json.loads((run_dir / "input_inventory.json").read_text(encoding="utf-8"))
    lineage = json.loads((run_dir / "lineage_checks.json").read_text(encoding="utf-8"))

    assert manifest["flags"]["DATABASE_PHASE_CLOSED"] is False
    assert manifest["flags"]["PERSIST_DISTRACTOR_RELATIONSHIPS_V1"] is False

    assert isinstance(inv["inputs"], list)
    assert len(inv["inputs"]) > 0
    existing_with_hash = [e for e in inv["inputs"] if e.get("exists")]
    assert all("sha256" in e for e in existing_with_hash)

    assert "overlaps" in lineage
    assert "target_level_gaps" in lineage

    # Ensure script does not produce canonical runtime pack as part of this phase
    assert not (run_dir / "pack.json").exists()

    # Ensure historical evidence baseline remains unchanged
    current_history = json.loads(
        Path("docs/audits/evidence/database_integrity_runtime_handoff_audit.json").read_text(encoding="utf-8")
    )
    assert current_history == baseline_history
