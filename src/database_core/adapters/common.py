from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from database_core.domain.enums import SourceName
from database_core.domain.models import (
    AIQualification,
    CanonicalTaxon,
    MediaAsset,
    SourceObservation,
)
from database_core.qualification.ai import AIQualificationOutcome

SourceExternalKey = tuple[SourceName, str]


def source_external_key(*, source_name: SourceName, external_id: str) -> SourceExternalKey:
    return (source_name, external_id.strip())


@dataclass(frozen=True)
class SourceDataset:
    dataset_id: str
    captured_at: datetime
    canonical_taxa: list[CanonicalTaxon]
    observations: list[SourceObservation]
    media_assets: list[MediaAsset]
    ai_qualifications: dict[SourceExternalKey, AIQualification]
    cached_image_paths_by_source_media_key: dict[SourceExternalKey, Path]
    ai_qualification_outcomes: dict[SourceExternalKey, AIQualificationOutcome] = field(
        default_factory=dict
    )
    taxon_payloads_by_canonical_taxon_id: dict[str, dict[str, object]] = field(default_factory=dict)
