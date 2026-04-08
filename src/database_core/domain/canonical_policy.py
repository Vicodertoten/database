from __future__ import annotations

from database_core.domain.canonical_ids import CANONICAL_TAXON_ID_PATTERN

UNRESOLVED_CANONICAL_TAXON_IDS = {"unresolved", "unknown", "pending", "none"}


def is_resolved_canonical_taxon_id(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized or normalized in UNRESOLVED_CANONICAL_TAXON_IDS:
        return False
    return CANONICAL_TAXON_ID_PATTERN.fullmatch(normalized) is not None
