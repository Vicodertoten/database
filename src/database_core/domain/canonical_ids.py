from __future__ import annotations

import re
from collections.abc import Iterable

from database_core.domain.enums import TaxonGroup

CANONICAL_ID_PADDING = 6
CANONICAL_TAXON_ID_PATTERN = re.compile(r"^taxon:(?P<group>[a-z]+):(?P<index>\d{6})$")


def format_canonical_taxon_id(*, group: TaxonGroup, index: int) -> str:
    if index <= 0:
        raise ValueError("canonical taxon index must be positive")
    return f"taxon:{group}:{index:0{CANONICAL_ID_PADDING}d}"


def canonical_taxon_id_index(canonical_taxon_id: str, *, group: TaxonGroup) -> int | None:
    match = CANONICAL_TAXON_ID_PATTERN.fullmatch(canonical_taxon_id)
    if match is None or match.group("group") != group:
        return None
    return int(match.group("index"))


def next_canonical_taxon_id(
    *,
    existing_ids: Iterable[str],
    group: TaxonGroup,
) -> str:
    max_index = 0
    for canonical_taxon_id in existing_ids:
        index = canonical_taxon_id_index(canonical_taxon_id, group=group)
        if index is None:
            continue
        max_index = max(max_index, index)
    return format_canonical_taxon_id(group=group, index=max_index + 1)


def build_legacy_to_canonical_mapping(
    *,
    legacy_ids: Iterable[str],
    group: TaxonGroup,
) -> dict[str, str]:
    unique_legacy_ids = sorted(set(legacy_ids))
    return {
        legacy_id: format_canonical_taxon_id(group=group, index=index)
        for index, legacy_id in enumerate(unique_legacy_ids, start=1)
    }
