from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from database_core.domain.enums import QualificationStage, QualificationStatus, ReviewPriority
from database_core.domain.models import QualifiedResource, ReviewItem
from database_core.qualification.policy import (
    REVIEW_PRIORITY_BY_REASON,
    REVIEW_STAGE_BY_REASON,
    primary_review_reason_code,
)
from database_core.review.queue import build_review_item


def build_review_items(
    resources: Iterable[QualifiedResource],
    *,
    created_at: datetime,
) -> list[ReviewItem]:
    review_items: list[ReviewItem] = []
    for resource in resources:
        if resource.qualification_status != QualificationStatus.REVIEW_REQUIRED:
            continue
        review_reason_code = primary_review_reason_code(resource.qualification_flags)
        review_note = resource.qualification_notes or None
        review_reason = (
            f"{review_reason_code}: {review_note}" if review_note else review_reason_code
        )
        review_items.append(
            build_review_item(
                media_asset_id=resource.media_asset_id,
                canonical_taxon_id=resource.canonical_taxon_id,
                review_reason=review_reason,
                review_reason_code=review_reason_code,
                review_note=review_note,
                stage_name=REVIEW_STAGE_BY_REASON.get(
                    review_reason_code,
                    QualificationStage.REVIEW_QUEUE_ASSEMBLY,
                ),
                priority=REVIEW_PRIORITY_BY_REASON.get(review_reason_code, ReviewPriority.MEDIUM),
                created_at=created_at,
            )
        )
    return review_items
