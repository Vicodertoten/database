from __future__ import annotations

from collections.abc import Mapping, Sequence

from database_core.domain.enums import EnrichmentStatus, SimilarityRelationType, SourceName
from database_core.domain.models import CanonicalTaxon, ExternalSimilarityHint, SimilarTaxon

MALFORMED_ENRICHMENT_PAYLOAD_ERRORS = (
    KeyError,
    TypeError,
    ValueError,
)


def enrich_canonical_taxa(
    canonical_taxa: Sequence[CanonicalTaxon],
    *,
    taxon_payloads_by_canonical_taxon_id: Mapping[str, Mapping[str, object]] | None = None,
) -> list[CanonicalTaxon]:
    payloads = dict(taxon_payloads_by_canonical_taxon_id or {})
    by_external_id = {
        (mapping.source_name, mapping.external_id): taxon.canonical_taxon_id
        for taxon in canonical_taxa
        for mapping in taxon.external_source_mappings
    }
    enriched: list[CanonicalTaxon] = []
    for taxon in canonical_taxa:
        payload = payloads.get(taxon.canonical_taxon_id)
        if payload is None:
            enriched.append(taxon)
            continue
        enriched.append(_enrich_single_taxon(taxon, payload=payload, by_external_id=by_external_id))
    return sorted(enriched, key=lambda item: item.canonical_taxon_id)


def _enrich_single_taxon(
    taxon: CanonicalTaxon,
    *,
    payload: Mapping[str, object],
    by_external_id: Mapping[tuple[SourceName, str], str],
) -> CanonicalTaxon:
    try:
        record = _extract_taxon_record(payload)
        merged_common_names = _merge_strings(
            taxon.common_names,
            _extract_common_names(record),
        )
        key_identification_features = _merge_strings(
            taxon.key_identification_features,
            _extract_key_identification_features(record),
        )
        external_similarity_hints = _merge_similarity_hints(
            taxon.external_similarity_hints,
            _extract_similarity_hints(record),
        )
        resolved, unresolved_count = _resolve_similarity_hints(
            taxon,
            external_similarity_hints=external_similarity_hints,
            by_external_id=by_external_id,
        )
        source_enrichment_status = (
            EnrichmentStatus.PARTIAL if unresolved_count > 0 else EnrichmentStatus.COMPLETE
        )
        return CanonicalTaxon.model_validate(
            {
                **taxon.model_dump(mode="python"),
                "common_names": merged_common_names,
                "key_identification_features": key_identification_features,
                "external_similarity_hints": external_similarity_hints,
                "similar_taxa": _merge_similar_taxa(taxon.similar_taxa, resolved),
                "source_enrichment_status": source_enrichment_status,
            }
        )
    except MALFORMED_ENRICHMENT_PAYLOAD_ERRORS:
        return CanonicalTaxon.model_validate(
            {
                **taxon.model_dump(mode="python"),
                "source_enrichment_status": EnrichmentStatus.FAILED,
            }
        )


def _extract_taxon_record(payload: Mapping[str, object]) -> Mapping[str, object]:
    results = payload.get("results")
    if isinstance(results, Sequence) and results:
        first = results[0]
        if isinstance(first, Mapping):
            return first
    return payload


def _extract_common_names(record: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    preferred_common_name = record.get("preferred_common_name")
    if preferred_common_name:
        names.append(str(preferred_common_name))
    english_common_name = record.get("english_common_name")
    if isinstance(english_common_name, Mapping):
        name = english_common_name.get("name")
        if name:
            names.append(str(name))
    return _dedupe_preserve_order(names)


def _extract_key_identification_features(record: Mapping[str, object]) -> list[str]:
    raw_value = record.get("key_identification_features")
    if raw_value is None:
        return []
    if isinstance(raw_value, Sequence) and not isinstance(raw_value, str):
        return _dedupe_preserve_order(str(item).strip() for item in raw_value if str(item).strip())
    return _dedupe_preserve_order(
        item.strip() for item in str(raw_value).split("|") if item.strip()
    )


def _extract_similarity_hints(record: Mapping[str, object]) -> list[ExternalSimilarityHint]:
    raw_hints = record.get("similar_taxa") or []
    if not isinstance(raw_hints, Sequence) or isinstance(raw_hints, str):
        return []

    hints: list[ExternalSimilarityHint] = []
    for item in raw_hints:
        if not isinstance(item, Mapping):
            continue
        external_taxon_id = item.get("id") or item.get("taxon_id")
        if external_taxon_id is None:
            continue
        confidence = item.get("confidence")
        confidence_value = float(confidence) if confidence is not None else None
        hints.append(
            ExternalSimilarityHint(
                source_name=SourceName.INATURALIST,
                external_taxon_id=str(external_taxon_id),
                relation_type=_coerce_similarity_relation_type(item.get("relation_type")),
                accepted_scientific_name=(
                    str(item.get("name"))
                    if item.get("name") is not None
                    else str(item.get("accepted_scientific_name"))
                    if item.get("accepted_scientific_name") is not None
                    else None
                ),
                common_name=(
                    str(item.get("preferred_common_name"))
                    if item.get("preferred_common_name") is not None
                    else str(item.get("common_name"))
                    if item.get("common_name") is not None
                    else None
                ),
                confidence=confidence_value,
                note=str(item.get("note")) if item.get("note") is not None else None,
            )
        )
    return _merge_similarity_hints([], hints)


def _resolve_similarity_hints(
    taxon: CanonicalTaxon,
    *,
    external_similarity_hints: Sequence[ExternalSimilarityHint],
    by_external_id: Mapping[tuple[SourceName, str], str],
) -> tuple[list[SimilarTaxon], int]:
    resolved: list[SimilarTaxon] = []
    unresolved = 0
    for hint in external_similarity_hints:
        target_canonical_taxon_id = by_external_id.get((hint.source_name, hint.external_taxon_id))
        if (
            target_canonical_taxon_id is None
            or target_canonical_taxon_id == taxon.canonical_taxon_id
        ):
            unresolved += 1
            continue
        resolved.append(
            SimilarTaxon(
                target_canonical_taxon_id=target_canonical_taxon_id,
                source_name=hint.source_name,
                relation_type=hint.relation_type,
                confidence=hint.confidence,
                note=hint.note or hint.accepted_scientific_name or hint.common_name,
            )
        )
    return _merge_similar_taxa([], resolved), unresolved


def _merge_strings(*collections: Sequence[str]) -> list[str]:
    merged: list[str] = []
    for values in collections:
        merged.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe_preserve_order(merged)


def _merge_similarity_hints(
    left: Sequence[ExternalSimilarityHint],
    right: Sequence[ExternalSimilarityHint],
) -> list[ExternalSimilarityHint]:
    merged: dict[tuple[str, str, str], ExternalSimilarityHint] = {}
    for item in list(left) + list(right):
        key = (item.source_name, item.external_taxon_id, item.relation_type)
        merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: (item.source_name, item.external_taxon_id, item.relation_type),
    )


def _merge_similar_taxa(
    left: Sequence[SimilarTaxon], right: Sequence[SimilarTaxon]
) -> list[SimilarTaxon]:
    merged: dict[tuple[str, str, str], SimilarTaxon] = {}
    for item in list(left) + list(right):
        key = (item.target_canonical_taxon_id, item.source_name, item.relation_type)
        merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: (item.target_canonical_taxon_id, item.source_name, item.relation_type),
    )


def _dedupe_preserve_order(values: Sequence[str] | object) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _coerce_similarity_relation_type(raw_value: object) -> SimilarityRelationType:
    if raw_value is None:
        return SimilarityRelationType.VISUAL_LOOKALIKE
    try:
        return SimilarityRelationType(str(raw_value))
    except ValueError:
        return SimilarityRelationType.VISUAL_LOOKALIKE
