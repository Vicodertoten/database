"""
run_inat_taxon_similarity_enrichment.py

CLI script for Sprint 12 Phase B: iNaturalist similar-species enrichment.

Usage:
  python scripts/run_inat_taxon_similarity_enrichment.py [options]

Options:
  --snapshot-id          Snapshot identifier (default: palier1-be-birds-50taxa-run003-v11-baseline)
  --normalized-path      Path to normalized JSON (resolved from snapshot-id if not given)
  --enriched-dir         Root dir for enriched cache output (default: data/enriched)
  --output-json          Path for audit evidence JSON
  --output-md            Path for audit markdown report
  --dry-run              Do not write cache files or mutate artifacts
  --refresh-live         Fetch from iNat API (default: False — use cache only)
  --max-taxa             Maximum number of taxa to process (default: 50)
  --place-id             iNat place_id filter (default: 7008 = Belgium)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from database_core.ops.inat_taxon_similarity_enrichment import (  # noqa: E402
    DEFAULT_ENRICHED_DIR,
    DEFAULT_NORMALIZED_ROOT,
    DEFAULT_SNAPSHOT_ID,
    INAT_PLACE_ID_BELGIUM,
    run_enrichment,
    write_markdown_report,
)

DEFAULT_OUTPUT_JSON = Path("docs/audits/evidence/inat_similarity_enrichment_sprint12.json")
DEFAULT_OUTPUT_MD = Path("docs/audits/inat-similarity-enrichment-sprint12.md")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sprint 12 Phase B — iNat similar-species enrichment"
    )
    p.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    p.add_argument(
        "--normalized-path",
        type=Path,
        default=None,
        help="Explicit path to normalized JSON. Auto-resolved from --snapshot-id if omitted.",
    )
    p.add_argument(
        "--enriched-dir",
        type=Path,
        default=DEFAULT_ENRICHED_DIR,
    )
    p.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    p.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip all writes; produce audit output only.",
    )
    p.add_argument(
        "--refresh-live",
        action="store_true",
        default=False,
        help="Fetch from iNat API. Without this flag, only cached results are used.",
    )
    p.add_argument("--max-taxa", type=int, default=50)
    p.add_argument("--place-id", default=INAT_PLACE_ID_BELGIUM)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    snapshot_id: str = args.snapshot_id

    if args.normalized_path is not None:
        normalized_path = args.normalized_path
    else:
        safe_id = snapshot_id.replace("-", "_")
        normalized_path = DEFAULT_NORMALIZED_ROOT / f"{safe_id}.normalized.json"

    if not normalized_path.exists():
        print(f"ERROR: normalized path not found: {normalized_path}", file=sys.stderr)
        return 1

    enriched_dir: Path = args.enriched_dir
    output_json: Path = args.output_json
    output_md: Path = args.output_md
    dry_run: bool = args.dry_run
    refresh_live: bool = args.refresh_live
    max_taxa: int = args.max_taxa
    place_id: str = args.place_id

    print("Sprint 12 Phase B — iNat similar-species enrichment")
    print(f"  snapshot_id     : {snapshot_id}")
    print(f"  normalized_path : {normalized_path}")
    print(f"  enriched_dir    : {enriched_dir}")
    print(f"  dry_run         : {dry_run}")
    print(f"  refresh_live    : {refresh_live}")
    print(f"  max_taxa        : {max_taxa}")
    print(f"  place_id        : {place_id}")
    print()

    evidence = run_enrichment(
        snapshot_id=snapshot_id,
        normalized_path=normalized_path,
        enriched_dir=enriched_dir,
        dry_run=dry_run,
        refresh_live=refresh_live,
        max_taxa=max_taxa,
        place_id=place_id,
    )

    # Write audit JSON (always — except dry-run still writes audit, just not cache)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    # Strip heavy enriched_taxa from JSON if too large
    evidence_for_json = {k: v for k, v in evidence.items() if k != "normalized_enriched_taxa"}
    output_json.write_text(json.dumps(evidence_for_json, indent=2), encoding="utf-8")
    print(f"Audit evidence written: {output_json}")

    # Write markdown
    write_markdown_report(evidence, output_md)
    print(f"Markdown report written: {output_md}")

    # Summary
    print()
    print("=== Summary ===")
    print(f"  Targets attempted : {evidence['targets_attempted']}")
    print(f"  Targets enriched  : {evidence['targets_enriched']}")
    print(f"  Total hints       : {evidence['total_similarity_hints']}")
    print(f"  Unmapped hints    : {evidence['hints_unmapped']}")
    print(f"  Errors            : {len(evidence['errors'])}")
    print(f"  Decision          : {evidence['decision']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
