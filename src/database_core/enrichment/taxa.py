from __future__ import annotations

from collections.abc import Mapping, Sequence

from database_core.domain.enums import EnrichmentStatus, SimilarityRelationType, SourceName
from database_core.domain.models import CanonicalTaxon, ExternalSimilarityHint, SimilarTaxon

MALFORMED_ENRICHMENT_PAYLOAD_ERRORS = (
    KeyError,
    TypeError,
    ValueError,
)

SUPPORTED_COMMON_NAME_LOCALES = ("fr", "en", "nl")


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
        # Extract multilingual names and features
        common_names_by_language = _merge_common_names_by_language(
            taxon.common_names_by_language,
            _extract_common_names_by_language(record),
        )
        key_identification_features_by_language = _merge_key_identification_features_by_language(
            taxon.key_identification_features_by_language,
            _extract_key_identification_features_by_language(record),
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
                "common_names_by_language": common_names_by_language,
                "key_identification_features": key_identification_features,
                "key_identification_features_by_language": key_identification_features_by_language,
                "external_similarity_hints": external_similarity_hints,
                "similar_taxa": _merge_similar_taxa(taxon.similar_taxa, resolved),
                "source_enrichment_status": source_enrichment_status,
                "authority_taxonomy_profile": _extract_authority_taxonomy_profile(record),
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


def _extract_common_names_by_language(record: Mapping[str, object]) -> dict[str, list[str]] | None:
    """Extract common names grouped by language from iNaturalist taxonomy names array.

    iNaturalist provides a 'names' array with structure:
    [
        {"name": "Common Blackbird", "locale": "en", ...},
        {"name": "Merle noir", "locale": "fr", ...},
        {"name": "Merel", "locale": "nl", ...},
    ]
    """
    names_by_language: dict[str, list[str]] = {}
    localized_taxa = record.get("localized_taxa")
    if isinstance(localized_taxa, Mapping):
        for locale in SUPPORTED_COMMON_NAME_LOCALES:
            localized_record = _extract_taxon_record_from_localized_payload(
                localized_taxa.get(locale)
            )
            if localized_record is None:
                continue
            preferred = _non_empty_string(localized_record.get("preferred_common_name"))
            if preferred:
                names_by_language.setdefault(locale, [])
                if preferred not in names_by_language[locale]:
                    names_by_language[locale].append(preferred)
            for name in _extract_names_for_locale(localized_record, locale):
                names_by_language.setdefault(locale, [])
                if name not in names_by_language[locale]:
                    names_by_language[locale].append(name)

    names_array = record.get("names")
    if isinstance(names_array, Sequence) and not isinstance(names_array, str):
        for item in names_array:
            if not isinstance(item, Mapping):
                continue
            language = item.get("locale") or item.get("language")
            name = item.get("name")
            if language and name:
                language_code = str(language).strip().lower()
                name_text = str(name).strip()
                if language_code and name_text:
                    if language_code not in names_by_language:
                        names_by_language[language_code] = []
                    if name_text not in names_by_language[language_code]:
                        names_by_language[language_code].append(name_text)

    return names_by_language if names_by_language else None


def _extract_key_identification_features_by_language(
    record: Mapping[str, object]
) -> dict[str, list[str]] | None:
    """Extract key identification features grouped by language.
    
    Currently iNaturalist doesn't provide multilingual identification features,
    so this reserves the structure for future use. If a 'features_by_language'
    field is added to the API, extract from it; otherwise return None.
    """
    features_by_language: dict[str, list[str]] = {}
    
    # Check for a potential future multilingual features structure
    features_array = record.get("features_by_language")
    if isinstance(features_array, Mapping):
        for language, features in features_array.items():
            if isinstance(features, (list, str)):
                language_code = str(language).strip().lower()
                if isinstance(features, str):
                    feature_list = [f.strip() for f in features.split("|") if f.strip()]
                else:
                    feature_list = [str(f).strip() for f in features if str(f).strip()]
                
                if language_code and feature_list:
                    features_by_language[language_code] = feature_list
    
    return features_by_language if features_by_language else None


def _extract_common_names(record: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    localized_taxa = record.get("localized_taxa")
    if isinstance(localized_taxa, Mapping):
        en_record = _extract_taxon_record_from_localized_payload(localized_taxa.get("en"))
        if en_record is not None:
            preferred = _non_empty_string(en_record.get("preferred_common_name"))
            if preferred:
                names.append(preferred)
    preferred_common_name = record.get("preferred_common_name")
    if preferred_common_name:
        names.append(str(preferred_common_name))
    english_common_name = record.get("english_common_name")
    if isinstance(english_common_name, Mapping):
        name = english_common_name.get("name")
        if name:
            names.append(str(name))
    return _dedupe_preserve_order(names)


def _extract_taxon_record_from_localized_payload(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        results = value.get("results")
        if isinstance(results, Sequence) and not isinstance(results, str) and results:
            first = results[0]
            if isinstance(first, Mapping):
                return first
        return value
    return None


def _extract_names_for_locale(record: Mapping[str, object], locale: str) -> list[str]:
    raw_names = record.get("names")
    if not isinstance(raw_names, Sequence) or isinstance(raw_names, str):
        return []
    names: list[str] = []
    for item in raw_names:
        if not isinstance(item, Mapping):
            continue
        item_locale = str(item.get("locale") or item.get("language") or "").strip().lower()
        name = _non_empty_string(item.get("name"))
        is_valid = item.get("is_valid")
        if item_locale == locale and name and is_valid is not False:
            names.append(name)
    return _dedupe_preserve_order(names)


def _non_empty_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_key_identification_features(record: Mapping[str, object]) -> list[str]:
    raw_value = record.get("key_identification_features")
    if raw_value is None:
        return []
    if isinstance(raw_value, Sequence) and not isinstance(raw_value, str):
        return _dedupe_preserve_order(str(item).strip() for item in raw_value if str(item).strip())
    return _dedupe_preserve_order(
        item.strip() for item in str(raw_value).split("|") if item.strip()
    )


def _extract_authority_taxonomy_profile(record: Mapping[str, object]) -> dict[str, object]:
    source_taxon_id = record.get("id")
    ancestor_ids_raw = record.get("ancestor_ids")
    synonym_ids_raw = record.get("current_synonymous_taxon_ids")
    return {
        "source_taxon_id": str(source_taxon_id) if source_taxon_id is not None else None,
        "accepted_scientific_name": (
            str(record.get("name")) if record.get("name") is not None else None
        ),
        "is_active": bool(record.get("is_active")) if record.get("is_active") is not None else None,
        "provisional": (
            bool(record.get("provisional")) if record.get("provisional") is not None else None
        ),
        "parent_id": str(record.get("parent_id")) if record.get("parent_id") is not None else None,
        "ancestor_ids": (
            [str(item) for item in ancestor_ids_raw if item is not None]
            if isinstance(ancestor_ids_raw, Sequence) and not isinstance(ancestor_ids_raw, str)
            else []
        ),
        "taxon_changes_count": (
            int(record.get("taxon_changes_count"))
            if record.get("taxon_changes_count") is not None
            else None
        ),
        "current_synonymous_taxon_ids": (
            [str(item) for item in synonym_ids_raw if item is not None]
            if isinstance(synonym_ids_raw, Sequence) and not isinstance(synonym_ids_raw, str)
            else []
        ),
    }


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


def _merge_common_names_by_language(
    left: dict[str, list[str]] | None,
    right: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    """Merge two multilingual common name dicts, deduplicating within each language."""
    if left is None and right is None:
        return None
    
    merged: dict[str, list[str]] = {}
    
    # Merge left
    if left:
        for language, names in left.items():
            merged[language] = list(names) if names else []
    
    # Merge right, deduplicating
    if right:
        for language, names in right.items():
            if language not in merged:
                merged[language] = []
            for name in names:
                if name not in merged[language]:
                    merged[language].append(name)
    
    # Clean up empty languages
    merged = {lang: names for lang, names in merged.items() if names}
    
    return merged if merged else None


def _merge_key_identification_features_by_language(
    left: dict[str, list[str]] | None,
    right: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    """Merge two multilingual KIF dicts, deduplicating within each language."""
    if left is None and right is None:
        return None
    
    merged: dict[str, list[str]] = {}
    
    # Merge left
    if left:
        for language, features in left.items():
            merged[language] = list(features) if features else []
    
    # Merge right, deduplicating
    if right:
        for language, features in right.items():
            if language not in merged:
                merged[language] = []
            for feature in features:
                if feature not in merged[language]:
                    merged[language].append(feature)
    
    # Clean up empty languages
    merged = {lang: features for lang, features in merged.items() if features}
    
    return merged if merged else None


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
