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


def _load_verify_repo_module():
    script_path = Path("scripts/verify_repo.py")
    spec = importlib.util.spec_from_file_location("verify_repo_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
