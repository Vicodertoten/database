from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.convert_source_attested_names_to_localized_name_patches_sprint14 import convert


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "taxon_id",
            "taxon_kind",
            "scientific_name",
            "language",
            "common_name",
            "source",
            "source_priority",
            "confidence",
            "display_status",
            "reviewer",
            "notes",
            "apply_status",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_convert_generates_schema_compatible_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "in.csv"
    output_json = tmp_path / "out.json"
    _write_csv(
        input_csv,
        [
            {
                "taxon_id": "reftaxon:inaturalist:117016",
                "taxon_kind": "referenced_taxon",
                "scientific_name": "Phylloscopus collybita",
                "language": "fr",
                "common_name": "Pouillot véloce",
                "source": "inaturalist",
                "source_priority": "1",
                "confidence": "source_attested",
                "display_status": "displayable_source_attested",
                "reviewer": "",
                "notes": "source-attested by localized-name-source-policy-v1",
                "apply_status": "ready",
            }
        ],
    )

    out = convert(input_csv=input_csv, output_json=output_json)
    assert out["patches"] == 1

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    patch = payload["patches"][0]
    assert patch["taxon_ref_type"] == "referenced_taxon"
    assert patch["referenced_taxon_id"] == "reftaxon:inaturalist:117016"
    assert patch["source_taxon_id"] == "117016"
    assert patch["common_name_fr"] == "Pouillot véloce"
    assert patch["confidence"] == "medium"
    assert patch["reviewer"] == "system/source_policy"


def test_convert_skips_non_ready_rows(tmp_path: Path) -> None:
    input_csv = tmp_path / "in.csv"
    output_json = tmp_path / "out.json"
    _write_csv(
        input_csv,
        [
            {
                "taxon_id": "taxon:birds:000001",
                "taxon_kind": "canonical_taxon",
                "scientific_name": "Columba palumbus",
                "language": "fr",
                "common_name": "Pigeon ramier",
                "source": "manual_or_curated_existing",
                "source_priority": "0",
                "confidence": "high",
                "display_status": "displayable_curated",
                "reviewer": "",
                "notes": "",
                "apply_status": "pending",
            }
        ],
    )

    out = convert(input_csv=input_csv, output_json=output_json)
    assert out["patches"] == 0
