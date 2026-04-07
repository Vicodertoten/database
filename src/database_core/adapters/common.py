from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from database_core.domain.models import AIQualification, CanonicalTaxon, MediaAsset, SourceObservation
from database_core.qualification.ai import AIQualificationOutcome


@dataclass(frozen=True)
class SourceDataset:
    dataset_id: str
    captured_at: datetime
    canonical_taxa: list[CanonicalTaxon]
    observations: list[SourceObservation]
    media_assets: list[MediaAsset]
    ai_qualifications: dict[str, AIQualification]
    cached_image_paths_by_source_media_id: dict[str, Path]
    ai_qualification_outcomes: dict[str, AIQualificationOutcome] = field(default_factory=dict)
