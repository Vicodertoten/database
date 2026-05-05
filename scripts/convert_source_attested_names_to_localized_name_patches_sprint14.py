from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_source_attested_patches_sprint14.csv"
OUTPUT_JSON = REPO_ROOT / "data" / "manual" / "taxon_localized_name_patches_sprint14_source_attested.json"


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _patch_from_row(row: dict[str, str], index: int) -> dict[str, Any] | None:
    if str(row.get("apply_status", "")).strip().lower() != "ready":
        return None
    lang = str(row.get("language", "")).strip().lower()
    if lang not in {"fr", "en", "nl"}:
        return None

    common_name = str(row.get("common_name", "")).strip()
    if not common_name:
        return None

    taxon_kind = str(row.get("taxon_kind", "")).strip()
    taxon_id = str(row.get("taxon_id", "")).strip()
    if taxon_kind not in {"canonical_taxon", "referenced_taxon"} or not taxon_id:
        return None

    confidence_src = str(row.get("confidence", "")).strip().lower()
    confidence = "medium" if confidence_src == "source_attested" else "high"

    patch: dict[str, Any] = {
        "schema_version": "1.0",
        "patch_id": f"s14-source-attested-{index:04d}",
        "taxon_ref_type": taxon_kind,
        "scientific_name": str(row.get("scientific_name", "")).strip() or None,
        "source": "manual_override",
        "confidence": confidence,
        "reviewer": "system/source_policy",
        "notes": str(row.get("notes", "")).strip() or "source-attested by localized-name-source-policy-v1",
        f"common_name_{lang}": common_name,
    }

    if taxon_kind == "canonical_taxon":
        patch["canonical_taxon_id"] = taxon_id
    else:
        patch["referenced_taxon_id"] = taxon_id
        if taxon_id.startswith("reftaxon:inaturalist:"):
            patch["source_taxon_id"] = taxon_id.split(":")[-1]

    return patch


def convert(input_csv: Path = INPUT_CSV, output_json: Path = OUTPUT_JSON) -> dict[str, Any]:
    rows = _load_rows(input_csv)
    patches: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        patch = _patch_from_row(row, idx)
        if patch is not None:
            patches.append(patch)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps({"patches": patches}, indent=2), encoding="utf-8")
    return {"input_rows": len(rows), "patches": len(patches), "output": str(output_json)}


def main() -> None:
    out = convert()
    print(f"Converted rows: {out['input_rows']}")
    print(f"Generated patches: {out['patches']}")
    print(f"Output: {out['output']}")


if __name__ == "__main__":
    main()
