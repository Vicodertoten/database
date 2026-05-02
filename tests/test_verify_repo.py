from __future__ import annotations

import importlib.util
import io
import re
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


def test_verify_repo_runs_compile_pytest_and_ruff_in_order(monkeypatch) -> None:
    module = _load_verify_repo_module()
    commands: list[list[str]] = []

    def fake_run(command, *, cwd, check, **kwargs):
        del check, kwargs
        commands.append(command)
        assert cwd == module.ROOT
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert module.main() == 0

    assert commands == [
        [module.sys.executable, "-m", "compileall", "src", "tests"],
        [
            module.sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:capture",
            "-n",
            "auto",
            "--dist",
            "loadscope",
        ],
        [module.sys.executable, "scripts/check_doc_code_coherence.py"],
        [module.sys.executable, "scripts/check_docs_hygiene.py"],
        [module.sys.executable, "scripts/check_palier1_v11_baseline.py"],
        [module.sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
    ]
    assert "Repository verification complete" in buffer.getvalue()


def test_gate_8_docs_keep_playable_gap_and_gate_ordering_visible() -> None:
    root = Path(".")
    readme = (root / "README.md").read_text(encoding="utf-8")
    scope = (root / "docs/foundation/scope.md").read_text(encoding="utf-8")
    model = (root / "docs/foundation/domain-model.md").read_text(encoding="utf-8")
    pipeline = (root / "docs/foundation/pipeline.md").read_text(encoding="utf-8")
    audit = (root / "docs/runbooks/audit-reference.md").read_text(encoding="utf-8")
    plan = (root / "docs/runbooks/execution-plan.md").read_text(encoding="utf-8")

    _assert_gate_markers(readme, ("4.5", "5", "6", "7", "8"))
    _assert_any_contains(readme, ("cumulative incremental", "incremental playable"))
    _assert_any_contains(readme, ("latest materialized surface", "materialized surface"))

    _assert_gate_markers(scope, ("4.5",))
    _assert_any_contains(scope, ("cumulative incremental playable corpus", "playable corpus"))

    _assert_gate_markers(model, ("4.5",))
    _assert_any_contains(model, ("migration framing", "migration"))

    _assert_gate_markers(pipeline, ("4.5", "6"))
    _assert_any_contains(pipeline, ("Corrective strategic alignment", "strategic alignment"))
    _assert_any_contains(pipeline, ("queue d’enrichissement", "queue d'enrichissement"))

    _assert_gate_markers(audit, ("4.5", "5"))
    _assert_any_contains(audit, ("closure checklist", "checklist"))
    _assert_any_contains(audit, ("Politique distracteurs v3", "distracteurs v3"))

    _assert_gate_markers(plan, ("4.5", "5", "6", "7", "8"))
    _assert_any_contains(plan, ("Correctif strategique", "strategique"))
    _assert_any_contains(plan, ("Politique distracteurs v3", "distracteurs v3"))
    _assert_any_contains(plan, ("Queue d'enrichissement", "enrichissement"))
    _assert_any_contains(plan, ("Contrat batch confusions", "confusions"))
    _assert_any_contains(plan, ("Inspection/KPI/smoke/CI", "Inspection"))


def test_gate_9_storage_layers_keep_gate_7_markers_and_retire_sidecar_v3() -> None:
    root = Path(".")
    storage_schema = (root / "src/database_core/storage/postgres_schema.py").read_text(
        encoding="utf-8"
    )
    storage_repo = (root / "src/database_core/storage/postgres.py").read_text(
        encoding="utf-8"
    )

    required_gate_7_markers = (
        "enrichment_requests",
        "enrichment_request_targets",
        "enrichment_executions",
        "confusion_events",
        "confusion_aggregates_global",
    )
    for marker in required_gate_7_markers:
        assert marker in storage_schema or marker in storage_repo

    # Gate 9 sidecar retirement is complete in this cycle.
    versioning = (root / "src/database_core/versioning.py").read_text(encoding="utf-8")
    pipeline_runner = (root / "src/database_core/pipeline/runner.py").read_text(
        encoding="utf-8"
    )
    assert 'LEGACY_EXPORT_VERSION = "export.bundle.v3"' not in versioning
    assert "write_sidecar_export_v3" not in pipeline_runner


def _load_verify_repo_module():
    script_path = Path("scripts/verify_repo.py")
    spec = importlib.util.spec_from_file_location("verify_repo_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_gate_markers(content: str, gates: tuple[str, ...]) -> None:
    for gate in gates:
        assert re.search(rf"Gate\s+{re.escape(gate)}\b", content), f"Missing Gate {gate} marker"


def _assert_any_contains(content: str, candidates: tuple[str, ...]) -> None:
    assert any(candidate in content for candidate in candidates), (
        f"None of the expected markers found: {', '.join(candidates)}"
    )
