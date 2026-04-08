from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database_core.domain.enums import (
    CanonicalRank,
    EnrichmentStatus,
    LicenseSafetyResult,
    MediaType,
    PedagogicalQuality,
    QualificationStage,
    QualificationStatus,
    ReviewPriority,
    ReviewStatus,
    Sex,
    SimilarityRelationType,
    SourceName,
    TaxonGroup,
    TechnicalQuality,
    ViewAngle,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class ExternalMapping(DomainModel):
    source_name: SourceName
    external_id: str

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("external_id must not be blank")
        return value


class LocationMetadata(DomainModel):
    place_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    country_code: str | None = None


class SourceQualityMetadata(DomainModel):
    quality_grade: str
    research_grade: bool
    observation_license: str | None = None
    captive: bool | None = None


class AIQualification(DomainModel):
    technical_quality: TechnicalQuality
    pedagogical_quality: PedagogicalQuality
    life_stage: str = "unknown"
    sex: Sex = Sex.UNKNOWN
    visible_parts: list[str] = Field(default_factory=list)
    view_angle: ViewAngle = ViewAngle.UNKNOWN
    confidence: float = 0.0
    model_name: str = "fixture-ai"
    notes: str | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class ExternalSimilarityHint(DomainModel):
    source_name: SourceName
    external_taxon_id: str
    relation_type: SimilarityRelationType = SimilarityRelationType.SIMILAR_SPECIES
    scientific_name: str | None = None
    common_name: str | None = None
    confidence: float | None = None
    note: str | None = None

    @field_validator("external_taxon_id")
    @classmethod
    def validate_external_taxon_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("external_taxon_id must not be blank")
        return value

    @field_validator("confidence")
    @classmethod
    def validate_optional_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class SimilarTaxon(DomainModel):
    target_canonical_taxon_id: str
    source_name: SourceName
    relation_type: SimilarityRelationType = SimilarityRelationType.SIMILAR_SPECIES
    confidence: float | None = None
    note: str | None = None

    @field_validator("target_canonical_taxon_id")
    @classmethod
    def validate_target_canonical_taxon_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("target_canonical_taxon_id must not be blank")
        return normalized

    @field_validator("confidence")
    @classmethod
    def validate_similarity_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return value


class CanonicalTaxon(DomainModel):
    canonical_taxon_id: str
    scientific_name: str
    canonical_rank: CanonicalRank
    common_names: list[str] = Field(default_factory=list)
    taxon_group: TaxonGroup = TaxonGroup.BIRDS
    key_identification_features: list[str] = Field(default_factory=list)
    source_enrichment_status: EnrichmentStatus = EnrichmentStatus.SEEDED
    bird_scope_compatible: bool = True
    external_source_mappings: list[ExternalMapping] = Field(default_factory=list)
    external_similarity_hints: list[ExternalSimilarityHint] = Field(default_factory=list)
    similar_taxa: list[SimilarTaxon] = Field(default_factory=list)
    similar_taxon_ids: list[str] = Field(default_factory=list)

    @field_validator("canonical_taxon_id")
    @classmethod
    def validate_canonical_taxon_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("canonical_taxon_id must not be blank")
        if normalized != normalized.lower():
            raise ValueError("canonical_taxon_id must be lowercase for stability")
        return normalized

    @field_validator("scientific_name")
    @classmethod
    def validate_scientific_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scientific_name must not be blank")
        return value

    @model_validator(mode="after")
    def derive_similar_taxon_ids(self) -> Self:
        derived_ids = sorted(
            {
                item.target_canonical_taxon_id
                for item in self.similar_taxa
                if item.target_canonical_taxon_id != self.canonical_taxon_id
            }
        )
        if derived_ids != self.similar_taxon_ids:
            object.__setattr__(self, "similar_taxon_ids", derived_ids)
        return self


class SourceObservation(DomainModel):
    observation_uid: str
    source_name: SourceName
    source_observation_id: str
    source_taxon_id: str
    observed_at: datetime | None = None
    location: LocationMetadata = Field(default_factory=LocationMetadata)
    source_quality: SourceQualityMetadata
    raw_payload_ref: str
    canonical_taxon_id: str | None = None

    @field_validator(
        "observation_uid", "source_observation_id", "source_taxon_id", "raw_payload_ref"
    )
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class MediaAsset(DomainModel):
    media_id: str
    source_name: SourceName
    source_media_id: str
    media_type: MediaType
    source_url: str
    attribution: str
    author: str | None = None
    license: str | None = None
    mime_type: str | None = None
    file_extension: str | None = None
    width: int | None = None
    height: int | None = None
    checksum: str | None = None
    source_observation_uid: str
    canonical_taxon_id: str | None = None
    raw_payload_ref: str

    @field_validator(
        "media_id", "source_media_id", "source_url", "source_observation_uid", "raw_payload_ref"
    )
    @classmethod
    def validate_media_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ProvenanceSummary(DomainModel):
    source_name: SourceName
    source_observation_id: str
    source_media_id: str
    raw_payload_ref: str
    observation_license: str | None = None
    media_license: str | None = None
    qualification_method: str
    ai_model: str | None = None


class QualifiedResource(DomainModel):
    qualified_resource_id: str
    canonical_taxon_id: str
    source_observation_uid: str
    source_observation_id: str
    media_asset_id: str
    qualification_status: QualificationStatus
    qualification_version: str
    technical_quality: TechnicalQuality
    pedagogical_quality: PedagogicalQuality
    life_stage: str = "unknown"
    sex: Sex = Sex.UNKNOWN
    visible_parts: list[str] = Field(default_factory=list)
    view_angle: ViewAngle = ViewAngle.UNKNOWN
    qualification_notes: str | None = None
    qualification_flags: list[str] = Field(default_factory=list)
    provenance_summary: ProvenanceSummary
    license_safety_result: LicenseSafetyResult
    export_eligible: bool

    @field_validator("qualified_resource_id", "canonical_taxon_id", "media_asset_id")
    @classmethod
    def validate_resource_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_exportability(self) -> Self:
        if self.export_eligible:
            if self.qualification_status != QualificationStatus.ACCEPTED:
                raise ValueError("exportable resources must be accepted")
            if self.license_safety_result != LicenseSafetyResult.SAFE:
                raise ValueError("exportable resources must have a safe license result")
        return self


class ReviewItem(DomainModel):
    review_item_id: str
    media_asset_id: str
    canonical_taxon_id: str
    review_reason: str
    review_reason_code: str
    review_note: str | None = None
    stage_name: QualificationStage
    priority: ReviewPriority = ReviewPriority.MEDIUM
    review_status: ReviewStatus = ReviewStatus.OPEN
    created_at: datetime
