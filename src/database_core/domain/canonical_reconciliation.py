from __future__ import annotations

from collections.abc import Sequence

from database_core.domain.models import CanonicalTaxon


def reconcile_canonical_taxa_with_previous_state(
    *,
    current_taxa: Sequence[CanonicalTaxon],
    previous_taxa: Sequence[CanonicalTaxon],
) -> list[CanonicalTaxon]:
    previous_by_id = {item.canonical_taxon_id: item for item in previous_taxa}
    reconciled: list[CanonicalTaxon] = []

    for taxon in current_taxa:
        previous = previous_by_id.get(taxon.canonical_taxon_id)
        if previous is None:
            reconciled.append(taxon)
            continue

        synonyms = _merge_synonyms(
            current_synonyms=taxon.synonyms,
            previous_synonyms=previous.synonyms,
            previous_accepted_name=(
                previous.accepted_scientific_name
                if previous.accepted_scientific_name != taxon.accepted_scientific_name
                else None
            ),
        )
        if synonyms == taxon.synonyms:
            reconciled.append(taxon)
            continue
        reconciled.append(taxon.model_copy(update={"synonyms": synonyms}))

    return sorted(reconciled, key=lambda item: item.canonical_taxon_id)


def _merge_synonyms(
    *,
    current_synonyms: Sequence[str],
    previous_synonyms: Sequence[str],
    previous_accepted_name: str | None,
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in list(current_synonyms) + list(previous_synonyms):
        text = str(value).strip()
        if not text or text in seen:
            continue
        merged.append(text)
        seen.add(text)

    if previous_accepted_name:
        candidate = previous_accepted_name.strip()
        if candidate and candidate not in seen:
            merged.append(candidate)
    return merged
