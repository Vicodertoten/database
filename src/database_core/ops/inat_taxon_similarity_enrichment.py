"""
inat_taxon_similarity_enrichment.py

Sprint 12 Phase B — iNaturalist similar-species enrichment.

Calls GET /v1/identifications/similar_species for each target canonical taxon,
extracts source-side ExternalSimilarityHint records, and writes:
  - data/enriched/{snapshot_id}.similar_species_v1.json  (per-taxon raw cache)
  - data/enriched/{snapshot_id}.normalized_enriched_v1.json  (enriched normalized taxa)
  - docs/audits/evidence/inat_similarity_enrichment_sprint12.json  (audit evidence)

Doctrine:
  - iNat similar species are source-side hints only.
  - They do NOT create CanonicalTaxon records.
  - Unresolved hints remain separate from canonical identity.
  - Canonical identity fields are never mutated.
  - Live API calls are rate-limited to 1 req/s and cached; dry-run skips writes.
"""
from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ENRICHMENT_VERSION = "inat.similarity.v1"
INAT_SIMILAR_API = (
    "https://api.inaturalist.org/v1/identifications/similar_species"
)
INAT_PLACE_ID_BELGIUM = "7008"
USER_AGENT = "BioLearnDatabaseBot/1.0"
REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 1.1  # polite rate: slightly above 1/s

DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_ENRICHED_DIR = Path("data/enriched")
DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimilarSpeciesHint:
    """Source-side hint from iNat similar_species endpoint."""

    inat_id: str
    scientific_name: str
    preferred_common_name: str | None
    rank: str | None
    count: int  # co-identification count from iNat
    source_rank_order: int  # position in iNat result list (0-based)

    def to_external_similarity_hint_dict(self) -> dict[str, Any]:
        """Serialize as ExternalSimilarityHint-compatible dict."""
        return {
            "source_name": "inaturalist",
            "external_taxon_id": self.inat_id,
            "relation_type": "visual_lookalike",
            "accepted_scientific_name": self.scientific_name,
            "common_name": self.preferred_common_name,
            "confidence": None,
            "note": f"iNat co-identification count: {self.count}; rank: {self.source_rank_order}",
        }


@dataclass
class TaxonEnrichmentResult:
    """Result for a single target taxon."""

    canonical_taxon_id: str
    scientific_name: str
    inat_id: str
    hints: list[SimilarSpeciesHint] = field(default_factory=list)
    fetch_status: str = "pending"  # ok | empty | error | skipped | cached
    fetched_at: str | None = None
    error: str | None = None
    cache_path: str | None = None

    @property
    def hint_count(self) -> int:
        return len(self.hints)


# ---------------------------------------------------------------------------
# iNat API helpers
# ---------------------------------------------------------------------------


def _fetch_similar_species(
    inat_id: str,
    *,
    place_id: str = INAT_PLACE_ID_BELGIUM,
    timeout: int = REQUEST_TIMEOUT,
) -> dict[str, Any]:
    """Call GET /v1/identifications/similar_species?taxon_id={id}&place_id={place}."""
    url = f"{INAT_SIMILAR_API}?taxon_id={inat_id}&place_id={place_id}"
    req = Request(
        url=url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_hints(payload: dict[str, Any]) -> list[SimilarSpeciesHint]:
    """Parse iNat similar_species API response into SimilarSpeciesHint list."""
    hints: list[SimilarSpeciesHint] = []
    for i, result in enumerate(payload.get("results", [])):
        taxon = result.get("taxon")
        if not isinstance(taxon, Mapping):
            continue
        inat_id = taxon.get("id")
        name = taxon.get("name")
        if inat_id is None or not name:
            continue
        hints.append(
            SimilarSpeciesHint(
                inat_id=str(inat_id),
                scientific_name=str(name),
                preferred_common_name=(
                    str(taxon["preferred_common_name"])
                    if taxon.get("preferred_common_name")
                    else None
                ),
                rank=str(taxon["rank"]) if taxon.get("rank") else None,
                count=int(result.get("count", 0)),
                source_rank_order=i,
            )
        )
    return hints


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(enriched_dir: Path, snapshot_id: str, canonical_taxon_id: str) -> Path:
    slug = canonical_taxon_id.replace(":", "_")
    return enriched_dir / snapshot_id / "similar_species" / f"{slug}.json"


def _write_cache(
    cache_file: Path,
    inat_id: str,
    scientific_name: str,
    raw_payload: dict[str, Any],
    fetched_at: str,
) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "inat_id": inat_id,
                "scientific_name": scientific_name,
                "fetched_at": fetched_at,
                "raw_payload": raw_payload,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_cache(cache_file: Path) -> dict[str, Any] | None:
    if not cache_file.exists():
        return None
    return json.loads(cache_file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Canonical taxon resolution
# ---------------------------------------------------------------------------


def _build_canonical_index(
    normalized_taxa: list[dict[str, Any]],
) -> dict[str, str]:
    """Return {inat_external_id -> canonical_taxon_id} for all taxa with iNat mappings."""
    index: dict[str, str] = {}
    for t in normalized_taxa:
        for m in t.get("external_source_mappings", []):
            if m.get("source_name") == "inaturalist" and m.get("external_id"):
                index[str(m["external_id"])] = t["canonical_taxon_id"]
    return index


def _extract_inat_pairs(
    normalized_taxa: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Return [(canonical_taxon_id, inat_id, scientific_name)] for all 50 targets."""
    pairs: list[tuple[str, str, str]] = []
    for t in normalized_taxa:
        name = t.get("accepted_scientific_name", "")
        for m in t.get("external_source_mappings", []):
            if m.get("source_name") == "inaturalist" and m.get("external_id"):
                pairs.append((t["canonical_taxon_id"], str(m["external_id"]), name))
                break  # one iNat mapping per taxon
    return sorted(pairs, key=lambda p: p[0])


# ---------------------------------------------------------------------------
# Core enrichment logic
# ---------------------------------------------------------------------------


def enrich_taxa_with_similar_species(
    normalized_taxa: list[dict[str, Any]],
    *,
    enriched_dir: Path,
    snapshot_id: str,
    dry_run: bool = False,
    refresh_live: bool = True,
    max_taxa: int = 50,
    place_id: str = INAT_PLACE_ID_BELGIUM,
) -> list[TaxonEnrichmentResult]:
    """
    For each target taxon, fetch or load cached similar-species hints.

    Returns one TaxonEnrichmentResult per target taxon.
    Does NOT mutate canonical identity. Does NOT create CanonicalTaxon records.
    """
    pairs = _extract_inat_pairs(normalized_taxa)[:max_taxa]
    results: list[TaxonEnrichmentResult] = []

    for canonical_taxon_id, inat_id, scientific_name in pairs:
        cache_file = _cache_path(enriched_dir, snapshot_id, canonical_taxon_id)
        result = TaxonEnrichmentResult(
            canonical_taxon_id=canonical_taxon_id,
            scientific_name=scientific_name,
            inat_id=inat_id,
        )

        cached = _read_cache(cache_file)
        if cached is not None:
            hints = _parse_hints(cached.get("raw_payload", {}))
            result.hints = hints
            result.fetch_status = "cached"
            result.fetched_at = cached.get("fetched_at")
            result.cache_path = str(cache_file)
            results.append(result)
            continue

        if not refresh_live:
            result.fetch_status = "skipped"
            result.error = "live refresh disabled; no cache found"
            results.append(result)
            continue

        if dry_run:
            result.fetch_status = "skipped"
            result.error = "dry_run=True; no live fetch"
            results.append(result)
            continue

        fetched_at = datetime.now(UTC).isoformat()
        try:
            raw_payload = _fetch_similar_species(inat_id, place_id=place_id)
            hints = _parse_hints(raw_payload)
            result.hints = hints
            result.fetch_status = "ok" if hints else "empty"
            result.fetched_at = fetched_at
            result.cache_path = str(cache_file)
            _write_cache(
                cache_file,
                inat_id=inat_id,
                scientific_name=scientific_name,
                raw_payload=raw_payload,
                fetched_at=fetched_at,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            result.fetch_status = "error"
            result.error = str(exc)
        finally:
            time.sleep(RATE_LIMIT_SECONDS)

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Enriched normalized taxa writer
# ---------------------------------------------------------------------------


def apply_hints_to_normalized(
    normalized_taxa: list[dict[str, Any]],
    results: list[TaxonEnrichmentResult],
) -> list[dict[str, Any]]:
    """
    Return a copy of normalized_taxa with external_similarity_hints populated.

    Does NOT modify canonical identity fields (accepted_scientific_name,
    canonical_taxon_id, external_source_mappings, similar_taxa, similar_taxon_ids).
    Only external_similarity_hints is updated.
    """
    results_by_id = {r.canonical_taxon_id: r for r in results}
    enriched: list[dict[str, Any]] = []
    for taxon in normalized_taxa:
        tid = taxon.get("canonical_taxon_id", "")
        result = results_by_id.get(tid)
        if result is None or not result.hints:
            enriched.append(dict(taxon))
            continue
        existing_hints: list[dict[str, Any]] = list(
            taxon.get("external_similarity_hints", [])
        )
        new_hint_ids = {str(h.inat_id) for h in result.hints}
        existing_ids = {
            str(h.get("external_taxon_id", "")) for h in existing_hints
        }
        for hint in result.hints:
            if hint.inat_id not in existing_ids:
                existing_hints.append(hint.to_external_similarity_hint_dict())
                new_hint_ids.discard(hint.inat_id)
        updated = dict(taxon)
        updated["external_similarity_hints"] = existing_hints
        enriched.append(updated)
    return enriched


# ---------------------------------------------------------------------------
# Audit evidence builder
# ---------------------------------------------------------------------------


def build_audit_evidence(
    snapshot_id: str,
    results: list[TaxonEnrichmentResult],
    canonical_index: dict[str, str],
    *,
    dry_run: bool,
    refresh_live: bool,
) -> dict[str, Any]:
    """Build the JSON audit evidence for Phase B."""
    total_hints = sum(r.hint_count for r in results)
    hints_with_name = sum(
        1 for r in results for h in r.hints if h.scientific_name
    )
    hints_with_common = sum(
        1 for r in results for h in r.hints if h.preferred_common_name
    )
    hints_mapped = sum(
        1 for r in results for h in r.hints if h.inat_id in canonical_index
    )
    hints_unmapped = total_hints - hints_mapped

    statuses = [r.fetch_status for r in results]
    from collections import Counter

    status_dist = dict(Counter(statuses))

    enriched_count = sum(1 for r in results if r.hint_count > 0)

    per_target = [
        {
            "canonical_taxon_id": r.canonical_taxon_id,
            "scientific_name": r.scientific_name,
            "inat_id": r.inat_id,
            "hint_count": r.hint_count,
            "fetch_status": r.fetch_status,
            "fetched_at": r.fetched_at,
            "cache_path": r.cache_path,
            "error": r.error,
            "hints": [h.to_external_similarity_hint_dict() for h in r.hints],
        }
        for r in results
    ]

    # Determine decision
    if dry_run:
        decision = "BLOCKED_BY_SOURCE_DATA"
        decision_note = "dry_run=True; no data fetched"
    elif refresh_live is False and all(r.fetch_status == "skipped" for r in results):
        decision = "BLOCKED_BY_SOURCE_DATA"
        decision_note = "live refresh disabled and no cache found"
    elif enriched_count == 0:
        decision = "NEEDS_EXTRACTION_FIXES"
        decision_note = "No hints extracted despite successful API calls"
    elif hints_unmapped > 0:
        decision = "NEEDS_REFERENCED_TAXON_SHELL_PREP"
        decision_note = (
            f"{hints_unmapped} hints reference taxa not in the canonical corpus"
        )
    else:
        decision = "READY_FOR_LOCALIZED_NAMES_ENRICHMENT"
        decision_note = "All hints mapped; proceed to Phase C"

    return {
        "audit_version": ENRICHMENT_VERSION,
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "enrichment_mode": (
            "live_api_fetch_with_cache"
            if refresh_live and not dry_run
            else "cache_only" if not refresh_live else "dry_run"
        ),
        "dry_run": dry_run,
        "decision": decision,
        "decision_note": decision_note,
        "targets_attempted": len(results),
        "targets_enriched": enriched_count,
        "targets_with_inat_similarity_hints": enriched_count,
        "total_similarity_hints": total_hints,
        "hints_with_external_taxon_id": total_hints,  # all have inat_id by construction
        "hints_with_scientific_name": hints_with_name,
        "hints_with_common_name": hints_with_common,
        "hints_mapped_to_existing_canonical_taxon": hints_mapped,
        "hints_unmapped": hints_unmapped,
        "raw_payloads_read": status_dist.get("cached", 0),
        "raw_payloads_fetched_live": status_dist.get("ok", 0)
        + status_dist.get("empty", 0),
        "cache_paths_written": sum(
            1 for r in results if r.cache_path is not None and r.fetch_status == "ok"
        ),
        "errors": [
            {"canonical_taxon_id": r.canonical_taxon_id, "error": r.error}
            for r in results
            if r.error
        ],
        "skipped_taxa": [
            r.canonical_taxon_id for r in results if r.fetch_status == "skipped"
        ],
        "fetch_status_distribution": status_dist,
        "per_target": per_target,
    }


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------


def write_markdown_report(evidence: dict[str, Any], output_path: Path) -> None:
    snapshot_id = evidence["snapshot_id"]
    decision = evidence["decision"]
    mode = evidence["enrichment_mode"]
    run_date = evidence["run_date"][:10]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/inat-similarity-enrichment-sprint12.md",
        "scope: audit",
        "---",
        "",
        "# iNat Similarity Enrichment — Sprint 12",
        "",
        "## Purpose",
        "",
        "Populate `external_similarity_hints` for all 50 target taxa using the "
        "iNaturalist `GET /v1/identifications/similar_species` endpoint (Phase B).",
        "",
        "## Phase A Root Cause",
        "",
        "**`SIMILAR_HINTS_REQUIRE_API_REFRESH`** — The snapshot was built using "
        "`GET /v1/taxa/{id}` which does not include `similar_taxa`. "
        "A dedicated similar-species endpoint is required.",
        "",
        "## Chosen Enrichment Mode",
        "",
        f"**`{mode}`**",
        "",
        "Endpoint: `GET https://api.inaturalist.org/v1/identifications/similar_species"
        "?taxon_id={{inat_id}}&place_id=7008`",
        "",
        "Cache: `data/enriched/{snapshot_id}/similar_species/{canonical_taxon_id}.json`",
        "",
        "Rate-limit: 1 request/second. Cached results re-used on repeat runs.",
        "",
        "---",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Snapshot | `{snapshot_id}` |",
        f"| Targets attempted | {evidence['targets_attempted']} |",
        f"| Targets enriched | {evidence['targets_enriched']} |",
        f"| Total similarity hints | {evidence['total_similarity_hints']} |",
        f"| Hints with scientific name | {evidence['hints_with_scientific_name']} |",
        f"| Hints with common name | {evidence['hints_with_common_name']} |",
        f"| Hints mapped to canonical | {evidence['hints_mapped_to_existing_canonical_taxon']} |",
        f"| Hints unmapped (out-of-corpus) | {evidence['hints_unmapped']} |",
        f"| Payloads fetched live | {evidence['raw_payloads_fetched_live']} |",
        f"| Payloads loaded from cache | {evidence['raw_payloads_read']} |",
        f"| Errors | {len(evidence['errors'])} |",
        f"| Skipped taxa | {len(evidence['skipped_taxa'])} |",
        "",
        "Fetch status distribution:",
        "",
    ]
    for status, count in evidence.get("fetch_status_distribution", {}).items():
        lines.append(f"- `{status}`: {count}")

    errors = evidence.get("errors", [])
    if errors:
        lines += [
            "",
            "### Errors",
            "",
        ]
        for e in errors[:10]:
            lines.append(f"- `{e['canonical_taxon_id']}`: {e['error']}")

    skipped = evidence.get("skipped_taxa", [])
    if skipped:
        lines += [
            "",
            "### Skipped Taxa",
            "",
        ]
        for s in skipped[:5]:
            lines.append(f"- `{s}`")
        if len(skipped) > 5:
            lines.append(f"- … and {len(skipped) - 5} more")

    lines += [
        "",
        "---",
        "",
        "## Cache Behavior",
        "",
        "Each fetched response is written to:",
        "```",
        f"data/enriched/{snapshot_id}/similar_species/<canonical_taxon_id>.json",
        "```",
        "Re-running the script reads from cache and does not re-fetch.",
        "",
        "---",
        "",
        "## Doctrine: No Canonical Identity Mutation",
        "",
        "- `ExternalSimilarityHint` records are source-side only.",
        "- No `CanonicalTaxon` records are created for unresolved hints.",
        "- `similar_taxa` and `similar_taxon_ids` are populated only by "
        "  the governed enrichment pipeline when canonical mapping is resolved.",
        "- `accepted_scientific_name`, `canonical_taxon_id`, and "
        "  `external_source_mappings` are never mutated.",
        "",
        "---",
        "",
        "## Limitations",
        "",
        "- `place_id=7008` (Belgium) scopes co-identification counts to Belgian "
        "  observations. Some globally common confusion species may be absent.",
        "- Out-of-corpus similar species (unmapped hints) require Phase D "
        "  (referenced taxon shell prep) before use in distractor candidate generation.",
        "- `similar_species` endpoint does not return localized names (fr/nl). "
        "  Phase C handles localized name enrichment via `GET /v1/taxa/{id}?all_names=true`.",
        "",
        "---",
        "",
        "## Next Phase Recommendation",
        "",
        f"**Decision: `{decision}`**",
        "",
    ]

    if decision == "NEEDS_REFERENCED_TAXON_SHELL_PREP":
        lines += [
            f"{evidence['hints_unmapped']} out-of-corpus hints found. "
            "Run Phase D (referenced taxon shell prep) before re-running "
            "distractor candidate generation.",
            "",
            "Parallel path: Run Phase C (localized names enrichment) "
            "for the already-mapped canonical candidates.",
        ]
    elif decision == "READY_FOR_LOCALIZED_NAMES_ENRICHMENT":
        lines += [
            "All hints are mapped to existing canonical taxa. "
            "Proceed directly to Phase C: localized names enrichment "
            "(`scripts/fetch_localized_names_v1.py`).",
        ]
    elif decision == "BLOCKED_BY_SOURCE_DATA":
        lines += [
            "No data was fetched (dry_run or live refresh disabled). "
            "Re-run with `--refresh-live` to fetch from iNat API.",
        ]
    else:
        lines.append(evidence.get("decision_note", ""))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level run function
# ---------------------------------------------------------------------------


def run_enrichment(
    snapshot_id: str,
    normalized_path: Path,
    enriched_dir: Path,
    *,
    dry_run: bool = False,
    refresh_live: bool = True,
    max_taxa: int = 50,
    place_id: str = INAT_PLACE_ID_BELGIUM,
) -> dict[str, Any]:
    """
    Main entry point. Loads normalized taxa, enriches with similar-species hints,
    writes per-taxon cache, builds enriched normalized snapshot, returns evidence.
    """
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    normalized_taxa: list[dict[str, Any]] = data.get("canonical_taxa", [])

    canonical_index = _build_canonical_index(normalized_taxa)

    results = enrich_taxa_with_similar_species(
        normalized_taxa,
        enriched_dir=enriched_dir,
        snapshot_id=snapshot_id,
        dry_run=dry_run,
        refresh_live=refresh_live,
        max_taxa=max_taxa,
        place_id=place_id,
    )

    enriched_taxa = apply_hints_to_normalized(normalized_taxa, results)

    evidence = build_audit_evidence(
        snapshot_id=snapshot_id,
        results=results,
        canonical_index=canonical_index,
        dry_run=dry_run,
        refresh_live=refresh_live,
    )

    evidence["enriched_taxa_count"] = len(enriched_taxa)
    evidence["normalized_enriched_taxa"] = enriched_taxa

    return evidence
