from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as materializer


def _fingerprint(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    data = path.read_bytes()
    return True, hashlib.sha256(data).hexdigest()


def test_materializer_writes_only_to_configured_output_dir(tmp_path: Path) -> None:
    canonical_paths = [
        materializer.OUTPUT_PACK_PATH,
        materializer.OUTPUT_MANIFEST_PATH,
        materializer.OUTPUT_VALIDATION_REPORT_PATH,
        materializer.OUTPUT_FAILED_PARTIAL_PACK_PATH,
    ]
    before = {str(path): _fingerprint(path) for path in canonical_paths}

    out_dir = tmp_path / "run_scoped_output"
    config = materializer.MaterializerConfig(
        plan_path=materializer.PLAN_PATH,
        materialization_source_path=materializer.MATERIALIZATION_SOURCE_PATH,
        distractor_path=materializer.DISTRACTOR_PATH,
        qualified_export_path=materializer.QUALIFIED_EXPORT_PATH,
        inat_manifest_path=materializer.INAT_MANIFEST_PATH,
        inat_ai_outputs_path=materializer.INAT_AI_OUTPUTS_PATH,
        schema_pack_path=materializer.SCHEMA_PACK_PATH,
        schema_manifest_path=materializer.SCHEMA_MANIFEST_PATH,
        schema_validation_report_path=materializer.SCHEMA_VALIDATION_REPORT_PATH,
        output_dir=out_dir,
        pack_id="belgian_birds_mvp_v1",
        locale="fr",
        target_count=30,
    )

    with pytest.raises(materializer.ContractError):
        materializer.write_outputs(config=config)

    assert (out_dir / "validation_report.json").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "failed_build" / "partial_pack.json").exists()
    assert not (out_dir / "pack.json").exists()

    after = {str(path): _fingerprint(path) for path in canonical_paths}
    assert before == after
