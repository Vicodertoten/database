from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    _run_step([sys.executable, "-m", "compileall", "src", "tests"])
    _run_pytest_with_xdist_preferred()
    _run_step([sys.executable, "scripts/check_doc_code_coherence.py"])
    _run_step([sys.executable, "scripts/check_docs_hygiene.py"])
    _run_step([sys.executable, "scripts/check_palier1_v11_baseline.py"])
    _run_step([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
    print("Repository verification complete")
    return 0


def _run_pytest_with_xdist_preferred() -> None:
    base = [sys.executable, "-m", "pytest", "-q", "-p", "no:capture"]
    xdist_command = [*base, "-n", "auto", "--dist", "loadscope"]
    print(f"$ {' '.join(xdist_command)}")
    completed = subprocess.run(xdist_command, cwd=ROOT, check=False, capture_output=True, text=True)
    if completed.returncode == 0:
        return
    stderr = completed.stderr or ""
    stdout = completed.stdout or ""
    xdist_unavailable = (
        "unrecognized arguments: -n" in stderr
        or "unrecognized arguments: -n" in stdout
    )
    if xdist_unavailable:
        print("pytest-xdist unavailable; retrying without parallelization")
        _run_step(base)
        return
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    raise SystemExit(completed.returncode)


def _run_step(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
