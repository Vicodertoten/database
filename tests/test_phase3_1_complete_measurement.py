from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_phase31(output_dir: Path, preflight_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/phase3_1_complete_measurement.py",
            "--output-dir",
            str(output_dir),
            "--preflight-artifact-path",
            str(preflight_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_phase3_1_stops_when_preflight_missing(tmp_path: Path) -> None:
    output_dir = tmp_path / "phase3_1"
    preflight_path = tmp_path / "missing_preflight.json"

    payload = _run_phase31(output_dir, preflight_path)

    assert payload["scale_decision"] == "STOP_RETARGET_PRECHECK"
    summary = json.loads((output_dir / "phase3_1_summary.v1.json").read_text(encoding="utf-8"))
    assert summary["decision"]["status"] == "STOP_RETARGET_PRECHECK"
    assert summary["decision"]["rules_evaluation"]["reason"] == "preflight_artifact_missing"


def test_phase3_1_stops_when_preflight_no_go(tmp_path: Path) -> None:
    output_dir = tmp_path / "phase3_1"
    preflight_path = tmp_path / "preflight.json"
    preflight_payload = {
        "preflight_go": False,
        "preflight_reason": "signal_absent_on_blocking_taxa",
        "candidate_pack_id": "pack:test",
    }
    preflight_path.write_text(json.dumps(preflight_payload), encoding="utf-8")

    payload = _run_phase31(output_dir, preflight_path)

    assert payload["scale_decision"] == "STOP_RETARGET_PRECHECK"
    summary = json.loads((output_dir / "phase3_1_summary.v1.json").read_text(encoding="utf-8"))
    assert summary["decision"]["status"] == "STOP_RETARGET_PRECHECK"
    assert summary["decision"]["rules_evaluation"]["reason"] == "signal_absent_on_blocking_taxa"
