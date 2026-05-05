from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from database_core.enrichment.localized_names.models import NameEvidence, RuntimeTaxon
from database_core.enrichment.localized_names.normalization import (
    ALL_LOCALES,
    normalize_compare_text,
    normalize_whitespace,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        raw = payload.get("response", payload)
        if isinstance(raw, dict):
            results = raw.get("results")
            if isinstance(results, list):
                return [item for item in results if isinstance(item, dict)]
            return [raw]
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _taxon_lookup_keys(taxon: RuntimeTaxon) -> set[str]:
    keys = {normalize_compare_text(taxon.scientific_name)}
    if taxon.source_taxon_id:
        keys.add(str(taxon.source_taxon_id))
    if taxon.taxon_id.startswith("reftaxon:inaturalist:"):
        keys.add(taxon.taxon_id.split(":")[-1])
    return {key for key in keys if key}


def collect_inaturalist_all_names_evidence(
    taxa: list[RuntimeTaxon],
    all_names_dir: Path,
) -> list[NameEvidence]:
    if not all_names_dir.exists():
        return []

    taxa_by_source_or_name: dict[str, list[RuntimeTaxon]] = {}
    for taxon in taxa:
        for key in _taxon_lookup_keys(taxon):
            taxa_by_source_or_name.setdefault(key, []).append(taxon)

    evidences: list[NameEvidence] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for path in sorted(all_names_dir.glob("*.json")):
        payload = load_json(path)
        for result in _results(payload):
            source_id = str(result.get("id", "")).strip()
            scientific_key = normalize_compare_text(str(result.get("name", "")))
            matched_taxa = taxa_by_source_or_name.get(source_id, []) + taxa_by_source_or_name.get(
                scientific_key, []
            )
            if not matched_taxa:
                continue
            raw_names = result.get("names", [])
            if not isinstance(raw_names, list):
                continue
            for name_item in raw_names:
                if not isinstance(name_item, dict):
                    continue
                locale = str(name_item.get("locale", "")).strip().lower()
                value = normalize_whitespace(str(name_item.get("name", "")))
                if locale not in ALL_LOCALES or not value:
                    continue
                for taxon in matched_taxa:
                    key = (taxon.taxon_id, locale, value, "inaturalist", "all_names")
                    if key in seen:
                        continue
                    seen.add(key)
                    evidences.append(
                        NameEvidence(
                            taxon_kind=taxon.taxon_kind,
                            taxon_id=taxon.taxon_id,
                            scientific_name=taxon.scientific_name,
                            locale=locale,
                            value=value,
                            source="inaturalist",
                            method="all_names",
                            confidence="medium_high",
                            source_url=f"https://www.inaturalist.org/taxa/{source_id}"
                            if source_id
                            else None,
                            raw_ref={
                                "artifact": str(path.name),
                                "source_taxon_id": source_id,
                                "locale": locale,
                                "position": name_item.get("position"),
                                "lexicon": name_item.get("lexicon"),
                            },
                        )
                    )
    return evidences


def collect_inaturalist_locale_cache_evidence(
    taxa: list[RuntimeTaxon],
    fetch_cache_dir: Path,
) -> list[NameEvidence]:
    if not fetch_cache_dir.exists():
        return []
    evidences: list[NameEvidence] = []
    taxa_by_source_id: dict[str, list[RuntimeTaxon]] = {}
    for taxon in taxa:
        if taxon.source_taxon_id:
            taxa_by_source_id.setdefault(str(taxon.source_taxon_id), []).append(taxon)
        if taxon.taxon_id.startswith("reftaxon:inaturalist:"):
            taxa_by_source_id.setdefault(taxon.taxon_id.split(":")[-1], []).append(taxon)

    for path in sorted(fetch_cache_dir.glob("inaturalist_taxa_*_*.json")):
        stem = path.stem.removeprefix("inaturalist_taxa_")
        try:
            source_taxon_id, locale = stem.rsplit("_", 1)
        except ValueError:
            continue
        if locale not in ALL_LOCALES:
            continue
        payload = load_json(path)
        for result in _results(payload):
            value = normalize_whitespace(str(result.get("preferred_common_name", "")))
            if not value:
                continue
            matched_taxa = taxa_by_source_id.get(source_taxon_id, [])
            if not matched_taxa:
                scientific = normalize_compare_text(str(result.get("name", "")))
                matched_taxa = [
                    taxon
                    for taxon in taxa
                    if normalize_compare_text(taxon.scientific_name) == scientific
                ]
            for taxon in matched_taxa:
                evidences.append(
                    NameEvidence(
                        taxon_kind=taxon.taxon_kind,
                        taxon_id=taxon.taxon_id,
                        scientific_name=taxon.scientific_name,
                        locale=locale,
                        value=value,
                        source="inaturalist",
                        method="taxa_locale",
                        confidence="high",
                        source_url=f"https://www.inaturalist.org/taxa/{source_taxon_id}",
                        raw_ref={
                            "artifact": str(path.name),
                            "source_taxon_id": source_taxon_id,
                            "locale": locale,
                        },
                    )
                )
    return evidences


def collect_wikimedia_cache_evidence(
    taxa: list[RuntimeTaxon],
    fetch_cache_dir: Path,
) -> list[NameEvidence]:
    if not fetch_cache_dir.exists():
        return []
    evidences: list[NameEvidence] = []
    taxa_by_id = {taxon.taxon_id: taxon for taxon in taxa}
    for path in sorted(fetch_cache_dir.glob("wikimedia_*.json")):
        payload = load_json(path)
        rows = payload.get("evidence", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            taxon = taxa_by_id.get(str(row.get("taxon_id", "")).strip())
            if taxon is None:
                continue
            locale = str(row.get("locale", "")).strip().lower()
            value = normalize_whitespace(str(row.get("value", "")))
            if locale not in ALL_LOCALES or not value:
                continue
            source = str(row.get("source", "wikidata")).strip() or "wikidata"
            method = str(row.get("method", "label")).strip() or "label"
            confidence = "low" if method == "alias" else "medium"
            evidences.append(
                NameEvidence(
                    taxon_kind=taxon.taxon_kind,
                    taxon_id=taxon.taxon_id,
                    scientific_name=taxon.scientific_name,
                    locale=locale,
                    value=value,
                    source=source,
                    method=method,
                    confidence=confidence,  # type: ignore[arg-type]
                    source_url=row.get("source_url"),
                    raw_ref={"artifact": str(path.name), **row},
                )
            )
    return evidences


def collect_name_evidence(
    taxa: list[RuntimeTaxon],
    *,
    all_names_dir: Path,
    fetch_cache_dir: Path,
) -> list[NameEvidence]:
    evidences: list[NameEvidence] = []
    evidences.extend(collect_inaturalist_locale_cache_evidence(taxa, fetch_cache_dir))
    evidences.extend(collect_inaturalist_all_names_evidence(taxa, all_names_dir))
    evidences.extend(collect_wikimedia_cache_evidence(taxa, fetch_cache_dir))
    return evidences
