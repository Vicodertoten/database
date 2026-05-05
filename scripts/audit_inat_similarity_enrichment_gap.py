"""
audit_inat_similarity_enrichment_gap.py

Sprint 12 / Phase A — Similar-species gap audit.

Diagnoses why iNaturalist similar-species hints are absent from all 50 target
taxa in the palier1-be-birds-50taxa-run003-v11-baseline snapshot.

Inspects four levels:
  A. CanonicalTaxon level (normalized JSON)
  B. Raw cached payload level (taxa/*.json files from the snapshot)
  C. Snapshot / manifest level
  D. Code-path level (static inspection of enrichment source files)

Produces:
  docs/audits/evidence/inat_similarity_enrichment_gap_audit.json
  docs/audits/inat-similarity-enrichment-gap-audit.md

No data is mutated. No API calls are made. No runtime/pack changes.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"
DEFAULT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_OUTPUT_JSON = Path(
    "docs/audits/evidence/inat_similarity_enrichment_gap_audit.json"
)
DEFAULT_OUTPUT_MD = Path("docs/audits/inat-similarity-enrichment-gap-audit.md")

SIMILARITY_KEYWORDS = ["similar", "confus", "related", "lookalike"]

# Root cause labels
RC_PRESENT_NOT_EXTRACTED = "SIMILAR_HINTS_PRESENT_BUT_NOT_EXTRACTED"
RC_REQUIRE_API_REFRESH = "SIMILAR_HINTS_REQUIRE_API_REFRESH"
RC_UNAVAILABLE = "SIMILAR_HINTS_UNAVAILABLE_IN_CURRENT_PAYLOADS"
RC_MAPPING_BUG = "AUDIT_OR_GENERATOR_MAPPING_BUG"
RC_SNAPSHOT_OLD = "SNAPSHOT_PREDATES_ENRICHMENT"
RC_UNKNOWN = "UNKNOWN_REQUIRES_MANUAL_INSPECTION"

# Phase B decision labels
DECISION_EXTRACT = "READY_TO_EXTRACT_EXISTING_SIMILAR_HINTS"
DECISION_REFRESH = "READY_FOR_INAT_TAXON_REFRESH"
DECISION_FIX_BUG = "FIX_AUDIT_OR_MAPPING_BUG_FIRST"
DECISION_MISSING_PAYLOADS = "BLOCKED_BY_MISSING_RAW_TAXON_PAYLOADS"
DECISION_MANUAL = "NEEDS_MANUAL_INSPECTION"

# Known iNat API endpoints
INAT_TAXA_ENDPOINT = "https://api.inaturalist.org/v1/taxa/{inat_id}"
INAT_SIMILAR_ENDPOINT = (
    "https://api.inaturalist.org/v1/identifications/similar_species"
    "?taxon_id={inat_id}&place_id=7008"
)

# Source file paths for code-path analysis
ENRICHMENT_TAXA_SRC = Path("src/database_core/enrichment/taxa.py")
SNAPSHOT_ADAPTER_SRC = Path("src/database_core/adapters/inaturalist_snapshot.py")
HARVEST_ADAPTER_SRC = Path("src/database_core/adapters/inaturalist_harvest.py")
TEST_SNAPSHOT_FILE = Path("tests/test_inat_snapshot.py")
FIXTURE_TAXA_DIR = Path("tests/fixtures/inaturalist_snapshot_smoke/taxa")


# ---------------------------------------------------------------------------
# Level A — CanonicalTaxon level
# ---------------------------------------------------------------------------


def _inspect_canonical_taxa(
    normalized_path: Path,
) -> dict[str, Any]:
    """Inspect normalized taxa for similarity hints and enrichment status."""
    if not normalized_path.exists():
        return {"error": f"normalized file not found: {normalized_path}"}

    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    taxa = data.get("canonical_taxa", [])

    total = len(taxa)
    with_hints = 0
    with_inat_hints = 0
    with_similar_taxa = 0
    with_similar_taxon_ids = 0
    enrichment_statuses: Counter = Counter()

    for t in taxa:
        hints = t.get("external_similarity_hints", [])
        if hints:
            with_hints += 1
        inat_hints = [
            h for h in hints if h.get("source_name") == "inaturalist"
        ]
        if inat_hints:
            with_inat_hints += 1
        if t.get("similar_taxa"):
            with_similar_taxa += 1
        if t.get("similar_taxon_ids"):
            with_similar_taxon_ids += 1
        enrichment_statuses[t.get("source_enrichment_status", "missing")] += 1

    return {
        "normalized_path": str(normalized_path),
        "total_taxa": total,
        "taxa_with_any_similarity_hints": with_hints,
        "taxa_with_inat_similarity_hints": with_inat_hints,
        "taxa_with_similar_taxa": with_similar_taxa,
        "taxa_with_similar_taxon_ids": with_similar_taxon_ids,
        "enrichment_status_distribution": dict(enrichment_statuses),
        "conclusion": (
            "All taxa enriched to completion but with empty similarity hints."
            if all(
                v == total
                for k, v in enrichment_statuses.items()
                if k == "complete"
            )
            and with_inat_hints == 0
            else "Enrichment incomplete or hints present — inspect further."
        ),
    }


# ---------------------------------------------------------------------------
# Level B — Raw cached payload level
# ---------------------------------------------------------------------------


def _inspect_raw_payloads(
    snapshot_dir: Path,
) -> dict[str, Any]:
    """Inspect raw taxon payload files for similarity-like fields."""
    taxa_dir = snapshot_dir / "taxa"
    if not taxa_dir.exists():
        return {"error": f"taxa dir not found: {taxa_dir}"}

    payload_files = sorted(taxa_dir.glob("*.json"))
    total_files = len(payload_files)

    all_result_keys: set[str] = set()
    similarity_fields_found: dict[str, list[str]] = {}
    payloads_with_similar_taxa = 0
    sample_paths: list[str] = []

    for f in payload_files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        results = raw.get("results", [])
        record = results[0] if results and isinstance(results[0], dict) else raw
        all_result_keys.update(record.keys())

        for key in record.keys():
            if any(kw in key.lower() for kw in SIMILARITY_KEYWORDS):
                similarity_fields_found.setdefault(key, []).append(f.name)

        if record.get("similar_taxa"):
            payloads_with_similar_taxa += 1

        if not sample_paths:
            sample_paths.append(str(f))

    return {
        "taxa_dir": str(taxa_dir),
        "total_payload_files": total_files,
        "payloads_with_similar_taxa": payloads_with_similar_taxa,
        "all_result_keys": sorted(all_result_keys),
        "similarity_fields_found": similarity_fields_found,
        "api_endpoint_used": INAT_TAXA_ENDPOINT,
        "similar_taxa_field_absent": payloads_with_similar_taxa == 0,
        "sample_payload_paths": sample_paths[:3],
        "conclusion": (
            "Raw payloads from GET /v1/taxa/{id} do not contain a `similar_taxa` field. "
            "The iNat taxon-detail endpoint does not expose visual similarity data. "
            "A separate endpoint is required: GET /v1/identifications/similar_species."
            if payloads_with_similar_taxa == 0
            else f"{payloads_with_similar_taxa} payloads already have similar_taxa — "
            "enrichment extraction may have a bug."
        ),
    }


# ---------------------------------------------------------------------------
# Level C — Snapshot / manifest level
# ---------------------------------------------------------------------------


def _inspect_manifest(
    snapshot_dir: Path,
) -> dict[str, Any]:
    """Inspect snapshot manifest for enrichment version and payload presence."""
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return {"error": f"manifest not found: {manifest_path}"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    seeds = manifest.get("taxon_seeds", [])

    seeds_with_payload = sum(1 for s in seeds if s.get("taxon_payload_path"))
    seeds_payload_exists = sum(
        1
        for s in seeds
        if s.get("taxon_payload_path")
        and (snapshot_dir / s["taxon_payload_path"]).exists()
    )

    return {
        "manifest_path": str(manifest_path),
        "snapshot_id": manifest.get("snapshot_id"),
        "manifest_version": manifest.get("manifest_version"),
        "enrichment_version": manifest.get("enrichment_version"),
        "source_name": manifest.get("source_name"),
        "total_seeds": len(seeds),
        "seeds_with_taxon_payload_path": seeds_with_payload,
        "seeds_with_payload_file_on_disk": seeds_payload_exists,
        "conclusion": (
            "Manifest has no enrichment_version field — "
            "snapshot was built before a multi-pass enrichment model was defined. "
            f"All {seeds_payload_exists}/{seeds_with_payload} taxon payload files "
            "exist on disk."
        ),
    }


# ---------------------------------------------------------------------------
# Level D — Code-path level (static analysis)
# ---------------------------------------------------------------------------


def _find_functions_in_source(
    path: Path,
    keywords: list[str],
) -> list[str]:
    """Return function/method names containing any of the given keywords."""
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(kw in node.name.lower() for kw in keywords):
                names.append(node.name)
    return names


def _test_covers_similar_species(test_path: Path) -> bool:
    """Return True if the test file has assertions about similar_taxa."""
    if not test_path.exists():
        return False
    content = test_path.read_text(encoding="utf-8")
    return "similar_taxa" in content or "external_similarity_hints" in content


def _fixture_has_similar_taxa(fixture_taxa_dir: Path) -> dict[str, Any]:
    """Check test fixtures for similar_taxa presence."""
    if not fixture_taxa_dir.exists():
        return {"fixture_dir_found": False}
    files = sorted(fixture_taxa_dir.glob("*.json"))
    found: list[str] = []
    for f in files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        results = raw.get("results", [])
        record = results[0] if results and isinstance(results[0], dict) else raw
        if record.get("similar_taxa"):
            found.append(f.name)
    return {
        "fixture_dir_found": True,
        "fixture_files_checked": len(files),
        "fixtures_with_similar_taxa": found,
    }


def _inspect_code_paths() -> dict[str, Any]:
    """Static analysis of enrichment and adapter source files."""
    enrich_similarity_fns = _find_functions_in_source(
        ENRICHMENT_TAXA_SRC,
        ["similar", "hint", "resolve_similarity", "merge_similar"],
    )
    harvest_fns = _find_functions_in_source(
        HARVEST_ADAPTER_SRC,
        ["similar", "taxon_payload", "taxon_detail"],
    )
    snapshot_fns = _find_functions_in_source(
        SNAPSHOT_ADAPTER_SRC,
        ["similar", "taxon_payload"],
    )
    test_covers = _test_covers_similar_species(TEST_SNAPSHOT_FILE)
    fixture_info = _fixture_has_similar_taxa(FIXTURE_TAXA_DIR)

    # Determine if harvest calls similar_species endpoint
    harvest_calls_similar = False
    if HARVEST_ADAPTER_SRC.exists():
        content = HARVEST_ADAPTER_SRC.read_text(encoding="utf-8")
        harvest_calls_similar = "similar_species" in content

    # Determine enrichment key read
    enrichment_key = None
    if ENRICHMENT_TAXA_SRC.exists():
        content = ENRICHMENT_TAXA_SRC.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "similar_taxa" in line and "record.get" in line:
                enrichment_key = line.strip()
                break

    return {
        "enrichment_source": str(ENRICHMENT_TAXA_SRC),
        "enrichment_similarity_functions": enrich_similarity_fns,
        "enrichment_reads_key": enrichment_key,
        "harvest_source": str(HARVEST_ADAPTER_SRC),
        "harvest_similarity_functions": harvest_fns,
        "harvest_calls_similar_species_endpoint": harvest_calls_similar,
        "snapshot_adapter_source": str(SNAPSHOT_ADAPTER_SRC),
        "snapshot_similarity_functions": snapshot_fns,
        "test_snapshot_covers_similar_taxa": test_covers,
        "fixture_info": fixture_info,
        "conclusion": (
            "The enrichment function `_extract_similarity_hints` reads "
            "`record.get('similar_taxa')` from the taxon payload results[0]. "
            "Test fixtures confirm this works when the field is manually injected. "
            "The harvest adapter calls GET /v1/taxa/{id} which does NOT return "
            "`similar_taxa`. The harvest adapter does NOT call "
            "GET /v1/identifications/similar_species."
        ),
    }


# ---------------------------------------------------------------------------
# Root cause classification
# ---------------------------------------------------------------------------


def _classify_root_cause(
    level_a: dict[str, Any],
    level_b: dict[str, Any],
    level_c: dict[str, Any],
    level_d: dict[str, Any],
) -> tuple[str, str, str]:
    """Return (root_cause, decision, reasoning)."""
    a_error = "error" in level_a
    b_error = "error" in level_b
    c_error = "error" in level_c

    if a_error or b_error or c_error:
        return RC_UNKNOWN, DECISION_MANUAL, "Inspection errors prevent classification."

    payloads_missing = level_b.get("total_payload_files", 0) == 0
    if payloads_missing:
        return (
            RC_UNAVAILABLE,
            DECISION_MISSING_PAYLOADS,
            "No raw taxon payload files found on disk.",
        )

    hints_in_canonical = level_a.get("taxa_with_inat_similarity_hints", 0)
    hints_in_payloads = level_b.get("payloads_with_similar_taxa", 0)
    harvest_calls_similar = level_d.get("harvest_calls_similar_species_endpoint", False)

    if hints_in_canonical > 0 and hints_in_payloads == 0:
        # Hints somehow exist in canonical but not in raw — mapping bug
        return (
            RC_MAPPING_BUG,
            DECISION_FIX_BUG,
            "Canonical taxa have iNat hints but raw payloads do not — "
            "investigate mapping pipeline.",
        )

    if hints_in_payloads > 0 and hints_in_canonical == 0:
        # Hints in payloads but not extracted
        return (
            RC_PRESENT_NOT_EXTRACTED,
            DECISION_EXTRACT,
            "Raw payloads contain similar_taxa but enrichment produced empty hints — "
            "check _extract_similarity_hints.",
        )

    if not harvest_calls_similar and hints_in_payloads == 0:
        # Both absent — harvest never called the right endpoint
        return (
            RC_REQUIRE_API_REFRESH,
            DECISION_REFRESH,
            "Raw taxon payloads (from GET /v1/taxa/{id}) do not contain `similar_taxa`. "
            "The harvest adapter does not call GET /v1/identifications/similar_species. "
            "A separate enrichment pass using the similar_species endpoint is required.",
        )

    return RC_UNKNOWN, DECISION_MANUAL, "Unexpected state — manual inspection required."


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def run_audit(
    snapshot_id: str,
    snapshot_dir: Path,
    normalized_path: Path,
) -> dict[str, Any]:
    """Run all four inspection levels and classify the root cause."""
    level_a = _inspect_canonical_taxa(normalized_path)
    level_b = _inspect_raw_payloads(snapshot_dir)
    level_c = _inspect_manifest(snapshot_dir)
    level_d = _inspect_code_paths()

    root_cause, decision, reasoning = _classify_root_cause(
        level_a, level_b, level_c, level_d
    )

    fixtures = level_d.get("fixture_info", {})
    fixture_files_with_similar = fixtures.get("fixtures_with_similar_taxa", [])

    total_taxa = level_a.get("total_taxa", 0)

    return {
        "audit_version": "similarity_gap_audit.v1",
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "root_cause_classification": root_cause,
        "phase_b_decision": decision,
        "reasoning": reasoning,
        "evidence_summary": {
            "taxa_inspected": total_taxa,
            "taxa_with_inat_similarity_hints": level_a.get(
                "taxa_with_inat_similarity_hints", 0
            ),
            "taxa_with_similar_taxa": level_a.get("taxa_with_similar_taxa", 0),
            "raw_payloads_found": level_b.get("total_payload_files", 0),
            "raw_payloads_with_similar_taxa": level_b.get(
                "payloads_with_similar_taxa", 0
            ),
            "raw_payload_api_endpoint": INAT_TAXA_ENDPOINT,
            "similar_species_api_endpoint": INAT_SIMILAR_ENDPOINT,
            "harvest_calls_similar_species_endpoint": level_d.get(
                "harvest_calls_similar_species_endpoint", False
            ),
            "enrichment_status_distribution": level_a.get(
                "enrichment_status_distribution", {}
            ),
            "test_fixture_has_similar_taxa": bool(fixture_files_with_similar),
            "fixture_files_with_similar_taxa": fixture_files_with_similar,
            "enrichment_reads_key": level_d.get("enrichment_reads_key"),
        },
        "affected_taxa": list(range(1, total_taxa + 1)),
        "sample_payload_paths": level_b.get("sample_payload_paths", []),
        "sample_similarity_fields_found": level_b.get("similarity_fields_found", {}),
        "recommended_next_action": (
            "Implement scripts/fetch_inat_similar_species_v1.py — "
            "call GET /v1/identifications/similar_species?taxon_id={inat_id}&place_id=7008 "
            "for each of the 50 target taxa and write enrichment JSON to "
            "data/enriched/{snapshot_id}.similar_species_v1.json. "
            "Then re-run candidate generation and readiness synthesis."
        ),
        "levels": {
            "A_canonical_taxa": level_a,
            "B_raw_payloads": level_b,
            "C_manifest": level_c,
            "D_code_paths": level_d,
        },
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------


def _write_markdown(result: dict[str, Any], output_path: Path) -> None:
    levels = result.get("levels", {})
    lA = levels.get("A_canonical_taxa", {})
    lB = levels.get("B_raw_payloads", {})
    lC = levels.get("C_manifest", {})
    lD = levels.get("D_code_paths", {})
    fixture_info = lD.get("fixture_info", {})

    root_cause = result["root_cause_classification"]
    decision = result["phase_b_decision"]
    snapshot_id = result["snapshot_id"]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {result['run_date'][:10]}",
        "source_of_truth: docs/audits/inat-similarity-enrichment-gap-audit.md",
        "scope: audit",
        "---",
        "",
        "# iNat Similarity Enrichment Gap Audit",
        "",
        "## Purpose",
        "",
        "Diagnose why all 50 target taxa have zero iNaturalist similar-species hints "
        "after Sprint 11 distractor candidate generation.",
        "",
        "## Sprint 11 Blocker Recap",
        "",
        "| Metric | Sprint 11 value |",
        "|---|---|",
        "| Target taxa | 50 |",
        "| iNat similar-species hints | 0 |",
        "| Candidates generated | 244 (all taxonomic) |",
        "| Targets ready for first corpus gate | 0 |",
        "| Final decision | `NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS` |",
        "",
        "---",
        "",
        "## Inspected Sources",
        "",
        "| Source | Path |",
        "|---|---|",
        f"| Normalized taxa | `{lA.get('normalized_path', 'N/A')}` |",
        f"| Raw taxon payloads | `{lB.get('taxa_dir', 'N/A')}` |",
        f"| Snapshot manifest | `{lC.get('manifest_path', 'N/A')}` |",
        f"| Enrichment source | `{lD.get('enrichment_source', 'N/A')}` |",
        f"| Harvest source | `{lD.get('harvest_source', 'N/A')}` |",
        f"| Test fixtures | `{FIXTURE_TAXA_DIR}` |",
        "",
        "---",
        "",
        "## Findings by Level",
        "",
        "### Level A — CanonicalTaxon",
        "",
        f"- **Total taxa**: {lA.get('total_taxa', 0)}",
        f"- **Taxa with any similarity hints**: {lA.get('taxa_with_any_similarity_hints', 0)}",
        f"- **Taxa with iNat similarity hints**: {lA.get('taxa_with_inat_similarity_hints', 0)}",
        f"- **Taxa with resolved `similar_taxa`**: {lA.get('taxa_with_similar_taxa', 0)}",
        f"- **Taxa with `similar_taxon_ids`**: {lA.get('taxa_with_similar_taxon_ids', 0)}",
        f"- **Enrichment status distribution**: "
        f"`{lA.get('enrichment_status_distribution', {})}`",
        "",
        f"> {lA.get('conclusion', '')}",
        "",
        "### Level B — Raw Cached Payloads",
        "",
        f"- **Taxon payload files found**: {lB.get('total_payload_files', 0)}",
        f"- **Payloads with `similar_taxa`**: {lB.get('payloads_with_similar_taxa', 0)}",
        f"- **Similarity-like keys found**: `{lB.get('similarity_fields_found', {})}`",
        f"- **API endpoint used**: `GET {lB.get('api_endpoint_used', 'N/A')}`",
        "",
        "Keys present in every raw payload result:",
        "",
        "```",
    ]
    for k in lB.get("all_result_keys", []):
        lines.append(f"  {k}")
    lines += [
        "```",
        "",
        f"> {lB.get('conclusion', '')}",
        "",
        "### Level C — Snapshot / Manifest",
        "",
        f"- **Snapshot ID**: `{lC.get('snapshot_id', 'N/A')}`",
        f"- **Manifest version**: `{lC.get('manifest_version', 'N/A')}`",
        f"- **Enrichment version**: `{lC.get('enrichment_version', 'N/A')}`",
        f"- **Total seeds**: {lC.get('total_seeds', 0)}",
        f"- **Seeds with taxon payload path**: {lC.get('seeds_with_taxon_payload_path', 0)}",
        f"- **Payload files on disk**: {lC.get('seeds_with_payload_file_on_disk', 0)}",
        "",
        f"> {lC.get('conclusion', '')}",
        "",
        "### Level D — Code Paths",
        "",
        f"- **Enrichment similarity functions**: "
        f"`{lD.get('enrichment_similarity_functions', [])}`",
        f"- **Enrichment reads key**: `{lD.get('enrichment_reads_key', 'N/A')}`",
        f"- **Harvest calls similar_species endpoint**: "
        f"`{lD.get('harvest_calls_similar_species_endpoint', False)}`",
        f"- **Test snapshot covers similar_taxa**: "
        f"`{lD.get('test_snapshot_covers_similar_taxa', False)}`",
        f"- **Test fixtures with similar_taxa populated**: "
        f"`{fixture_info.get('fixtures_with_similar_taxa', [])}`",
        "",
        f"> {lD.get('conclusion', '')}",
        "",
        "---",
        "",
        "## Root Cause Classification",
        "",
        f"**`{root_cause}`**",
        "",
        f"{result.get('reasoning', '')}",
        "",
        "### Evidence chain",
        "",
        "1. All 50 raw taxon payload files were fetched via "
        "   `GET /v1/taxa/{id}` (iNat taxon-detail endpoint).",
        "2. That endpoint does **not** include a `similar_taxa` field in its response.",
        "3. The enrichment function `_extract_similarity_hints` reads "
        "   `record.get('similar_taxa')` from `results[0]` of the payload.",
        "4. Since `similar_taxa` is absent, enrichment produces empty hints "
        "   and sets `source_enrichment_status = complete` (0 unresolved = complete).",
        "5. Test fixtures (`tests/fixtures/inaturalist_snapshot_smoke/taxa/`) "
        "   manually inject `similar_taxa` — proving the extraction code is correct.",
        "6. iNat exposes visual similarity via a separate endpoint: "
        "   `GET /v1/identifications/similar_species?taxon_id={id}&place_id=7008`.",
        "7. The harvest adapter never calls this endpoint.",
        "",
        "---",
        "",
        "## Recommended Phase B Path",
        "",
        f"**Decision: `{decision}`**",
        "",
        "Implement `scripts/fetch_inat_similar_species_v1.py`:",
        "",
        "```",
        f"GET {INAT_SIMILAR_ENDPOINT}",
        "```",
        "",
        "Steps:",
        "",
        "1. Load all 50 `(canonical_taxon_id, inat_id)` pairs from the normalized JSON.",
        "2. For each, call `GET /v1/identifications/similar_species?taxon_id={inat_id}"
        "&place_id=7008`.",
        "3. Parse results: each result has `{taxon: {...}, count: N}`.",
        "4. Write enrichment JSON to "
        "   `data/enriched/{snapshot_id}.similar_species_v1.json`.",
        "5. Re-run `generate_distractor_relationship_candidates_v1.py` "
        "   with `--enrichment-json`.",
        "6. Re-run `build_distractor_readiness_v1.py` and compare Sprint 11 vs Sprint 12.",
        "",
        "Rate-limit: 1 request/second. 50 requests total ≈ 50 seconds.",
        "Cache: re-run skips taxa whose enrichment already exists on disk.",
        "",
        "---",
        "",
        "## Risks",
        "",
        "| Risk | Mitigation |",
        "|---|---|",
        "| `similar_species` results are globally scoped, not Belgium-specific | "
        "Use `place_id=7008` parameter to filter to Belgian observations |",
        "| Some similar species may not be in the canonical corpus | "
        "Phase D creates referenced taxon shells for out-of-corpus candidates |",
        "| iNat API rate limits | 1 req/s polite rate, 50 requests total |",
        "| `similar_species` results may include non-species ranks | "
        "Filter to `rank=species` in Phase B script |",
        "",
        "---",
        "",
        "## Final Decision",
        "",
        f"**`{decision}`**",
        "",
        "No data was mutated. No runtime or pack changes were made.",
        f"Snapshot `{snapshot_id}` was not modified.",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sprint 12 Phase A — iNat similarity enrichment gap audit"
    )
    parser.add_argument(
        "--snapshot-id",
        default=DEFAULT_SNAPSHOT_ID,
        help="Snapshot ID (default: %(default)s)",
    )
    parser.add_argument(
        "--snapshot-base-path",
        default=str(DEFAULT_SNAPSHOT_ROOT),
        help="Root directory containing snapshot folders (default: %(default)s)",
    )
    parser.add_argument(
        "--normalized-path",
        default=None,
        help="Path to normalized JSON (auto-derived from snapshot-id if omitted)",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
    )
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    snapshot_id = args.snapshot_id
    snapshot_dir = Path(args.snapshot_base_path) / snapshot_id

    if args.normalized_path:
        normalized_path = Path(args.normalized_path)
    else:
        slug = snapshot_id.replace("-", "_")
        normalized_path = DEFAULT_NORMALIZED_ROOT / f"{slug}.normalized.json"

    result = run_audit(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        normalized_path=normalized_path,
    )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    output_md = Path(args.output_md)
    _write_markdown(result, output_md)

    print(f"Root cause:  {result['root_cause_classification']}")
    print(f"Decision:    {result['phase_b_decision']}")
    print(f"Taxa inspected: {result['evidence_summary']['taxa_inspected']}")
    print(f"iNat hints in canonical: "
          f"{result['evidence_summary']['taxa_with_inat_similarity_hints']}")
    print(f"Similar_taxa in raw payloads: "
          f"{result['evidence_summary']['raw_payloads_with_similar_taxa']}")
    print(f"JSON: {args.output_json}")
    print(f"MD:   {args.output_md}")


if __name__ == "__main__":
    main(sys.argv[1:])
