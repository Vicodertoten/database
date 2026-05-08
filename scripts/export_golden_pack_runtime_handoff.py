from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_golden_pack_runtime_handoff import verify_runtime_handoff


def export_runtime_handoff(
    *,
    pack_dir: Path,
    output_dir: Path,
    include_audit: bool = False,
) -> Path:
    verify_runtime_handoff(pack_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"{output_dir.name}_staging_",
        dir=str(output_dir.parent),
    ) as tmp:
        staging = Path(tmp)
        shutil.copy2(pack_dir / "pack.json", staging / "pack.json")
        shutil.copytree(pack_dir / "media", staging / "media")
        if include_audit:
            audit_dir = staging / "audit"
            audit_dir.mkdir()
            shutil.copy2(pack_dir / "manifest.json", audit_dir / "manifest.json")
            shutil.copy2(
                pack_dir / "validation_report.json",
                audit_dir / "validation_report.json",
            )
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.move(str(staging), str(output_dir))
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pack-dir",
        type=Path,
        default=Path("data/exports/golden_packs/belgian_birds_mvp_v1"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--include-audit", action="store_true")
    args = parser.parse_args()
    exported = export_runtime_handoff(
        pack_dir=args.pack_dir,
        output_dir=args.output_dir,
        include_audit=args.include_audit,
    )
    print(f"Runtime handoff exported: {exported}")


if __name__ == "__main__":
    main()
