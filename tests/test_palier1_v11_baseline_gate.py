from __future__ import annotations

import importlib.util
from pathlib import Path


def test_palier1_v11_baseline_gate_passes_on_repo_artifacts() -> None:
    module = _load_module()
    assert module.main() == 0


def _load_module():
    script_path = Path("scripts/check_palier1_v11_baseline.py")
    spec = importlib.util.spec_from_file_location("check_palier1_v11_baseline", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
