from __future__ import annotations

from dataclasses import dataclass

from database_core.domain.models import MediaAsset
from database_core.qualification.policy import MIN_ACCEPTED_HEIGHT, MIN_ACCEPTED_WIDTH


@dataclass(frozen=True)
class FastSemanticScreeningResult:
    flags: list[str]


def run_fast_semantic_screening(*, media_asset: MediaAsset) -> FastSemanticScreeningResult:
    flags: list[str] = []
    if (
        media_asset.width is None
        or media_asset.height is None
        or media_asset.width < MIN_ACCEPTED_WIDTH
        or media_asset.height < MIN_ACCEPTED_HEIGHT
    ):
        flags.append("insufficient_resolution")
    return FastSemanticScreeningResult(flags=flags)
