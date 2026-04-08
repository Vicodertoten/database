from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def main() -> None:
    _bootstrap_src_path()
    from database_core.cli import main as cli_main

    sys.argv.insert(1, "inspect")
    cli_main()


if __name__ == "__main__":
    main()
