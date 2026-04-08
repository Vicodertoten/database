from __future__ import annotations

from datetime import datetime

from database_core.domain.enums import QualificationStage, ReviewPriority
from database_core.domain.models import ReviewItem


def build_review_item(
    *,
    media_asset_id: str,
    canonical_taxon_id: str,
    review_reason: str,
    review_reason_code: str,
    review_note: str | None,
    stage_name: QualificationStage,
    priority: ReviewPriority,
    created_at: datetime,
) -> ReviewItem:
    return ReviewItem(
        review_item_id=f"review:{media_asset_id}",
        media_asset_id=media_asset_id,
        canonical_taxon_id=canonical_taxon_id,
        review_reason=review_reason,
        review_reason_code=review_reason_code,
        review_note=review_note,
        stage_name=stage_name,
        priority=priority,
        created_at=created_at,
    )
