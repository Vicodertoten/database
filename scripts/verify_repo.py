from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    _run_step([sys.executable, "-m", "compileall", "src", "tests"])
    _run_step([sys.executable, "-m", "pytest", "-q", "-p", "no:capture"])
    _run_step([sys.executable, "scripts/check_doc_code_coherence.py"])
    if importlib.util.find_spec("ruff") is None:
        raise SystemExit('ruff is not installed. Run `pip install -e ".[dev]"`.')
    _run_step([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
    print("Repository verification complete")
    return 0


def _run_step(command: list[str]) -> None:
    print(f"$ {' '.join(command)}")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
