from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace


def test_verify_repo_runs_compile_pytest_and_ruff_in_order(monkeypatch) -> None:
    module = _load_verify_repo_module()
    commands: list[list[str]] = []

    def fake_run(command, *, cwd, check):
        del check
        commands.append(command)
        assert cwd == module.ROOT
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module.importlib.util,
        "find_spec",
        lambda name: object() if name == "ruff" else None,
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert module.main() == 0

    assert commands == [
        [module.sys.executable, "-m", "compileall", "src", "tests"],
        [module.sys.executable, "-m", "pytest", "-q", "-p", "no:capture"],
        [module.sys.executable, "scripts/check_doc_code_coherence.py"],
        [module.sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
    ]
    assert "Repository verification complete" in buffer.getvalue()


def test_gate_8_docs_keep_playable_gap_and_gate_ordering_visible() -> None:
    root = Path(".")
    readme = (root / "README.md").read_text(encoding="utf-8")
    scope = (root / "docs/00_scope.md").read_text(encoding="utf-8")
    model = (root / "docs/01_domain_model.md").read_text(encoding="utf-8")
    pipeline = (root / "docs/02_pipeline.md").read_text(encoding="utf-8")
    audit = (root / "docs/05_audit_reference.md").read_text(encoding="utf-8")
    plan = (root / "docs/codex_execution_plan.md").read_text(encoding="utf-8")

    assert "cumulative incremental" in readme
    assert "latest materialized surface" in readme
    assert "Gate 4.5" in readme
    assert "Gate 5" in readme
    assert "Gate 6" in readme
    assert "Gate 7" in readme
    assert "Gate 8" in readme

    assert "during Gate 4.5" in scope
    assert "cumulative incremental playable corpus" in scope

    assert "Gate 4.5 migration framing" in model
    assert "PostgresRepository" in model

    assert "Corrective strategic alignment (Gate 4.5)" in pipeline
    assert "no queue d’enrichissement (Gate 6+)" in pipeline

    assert "Gate 4.5 closure checklist" in audit
    assert "Gate 5 - Politique distracteurs v2" in audit

    assert "Gate 4.5 - Correctif strategique pre-extension" in plan
    assert "Gate 5 - Politique distracteurs v2" in plan
    assert "Gate 6 - Queue d'enrichissement" in plan
    assert "Gate 7 - Contrat batch confusions + agregats globaux" in plan
    assert "Gate 8 - Inspection/KPI/smoke/CI etendus" in plan


def test_gate_8_storage_layers_keep_gate_7_markers_and_gate_9_open() -> None:
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

    # Gate 9 sidecar retirement is still closed in Gate 8.
    versioning = (root / "src/database_core/versioning.py").read_text(encoding="utf-8")
    pipeline_runner = (root / "src/database_core/pipeline/runner.py").read_text(
        encoding="utf-8"
    )
    assert 'LEGACY_EXPORT_VERSION = "export.bundle.v3"' in versioning
    assert "write_sidecar_export_v3" in pipeline_runner


def _load_verify_repo_module():
    script_path = Path("scripts/verify_repo.py")
    spec = importlib.util.spec_from_file_location("verify_repo_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
