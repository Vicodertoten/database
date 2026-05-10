from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database_core.domain.canonical_ids import CANONICAL_TAXON_ID_PATTERN
from database_core.domain.enums import (
    CandidateTaxonRefType,
    CanonicalChangeRelationType,
    CanonicalEventType,
    CanonicalGovernanceDecisionStatus,
    CanonicalRank,
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DiagnosticStrength,
    DifficultyBand,
    DifficultyLevel,
    DistractorConfusionType,
    DistractorDifficultyLevel,
    DistractorLearnerLevel,
    DistractorPedagogicalValue,
    DistractorRelationshipSource,
    DistractorRelationshipStatus,
    EnrichmentExecutionStatus,
    EnrichmentRequestReasonCode,
    EnrichmentRequestStatus,
    EnrichmentStatus,
    EnrichmentTargetResourceType,
    LearningSuitability,
    LicenseSafetyResult,
    MediaRole,
    MediaType,
    ObservationKind,
    PackCompilationReasonCode,
    PackDifficultyPolicy,
    PackMaterializationPurpose,
    PackVisibility,
    PedagogicalProfileStatus,
    PedagogicalQuality,
    PedagogicalRole,
    PedagogicalScoreBand,
    PedagogicalUsage,
    QualificationStage,
    QualificationStatus,
    ReferencedTaxonMappingStatus,
    ReviewPriority,
    ReviewStatus,
    Sex,
    SimilarityRelationType,
    SourceName,
    TaxonGroup,
    TaxonStatus,
    TechnicalQuality,
    UncertaintyReason,
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


class GeoPoint(DomainModel):
    longitude: float
    latitude: float


class GeoBBox(DomainModel):
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float

    @model_validator(mode="after")
    def validate_bbox_order(self) -> Self:
        if self.min_longitude > self.max_longitude:
            raise ValueError("min_longitude must be <= max_longitude")
        if self.min_latitude > self.max_latitude:
            raise ValueError("min_latitude must be <= max_latitude")
        return self


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
    difficulty_level: DifficultyLevel = DifficultyLevel.UNKNOWN
    media_role: MediaRole = MediaRole.CONTEXT
    confusion_relevance: ConfusionRelevance = ConfusionRelevance.NONE
    diagnostic_feature_visibility: DiagnosticFeatureVisibility = (
        DiagnosticFeatureVisibility.UNKNOWN
    )
    learning_suitability: LearningSuitability = LearningSuitability.UNKNOWN
    uncertainty_reason: UncertaintyReason = UncertaintyReason.NONE
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
    relation_type: SimilarityRelationType = SimilarityRelationType.VISUAL_LOOKALIKE
    accepted_scientific_name: str | None = None
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
    relation_type: SimilarityRelationType = SimilarityRelationType.VISUAL_LOOKALIKE
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
    accepted_scientific_name: str
    canonical_rank: CanonicalRank
    taxon_group: TaxonGroup = TaxonGroup.BIRDS
    taxon_status: TaxonStatus = TaxonStatus.ACTIVE
    authority_source: SourceName = SourceName.INATURALIST
    display_slug: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    common_names: list[str] = Field(default_factory=list)
    common_names_by_language: dict[str, list[str]] | None = None
    key_identification_features: list[str] = Field(default_factory=list)
    key_identification_features_by_language: dict[str, list[str]] | None = None
    source_enrichment_status: EnrichmentStatus = EnrichmentStatus.SEEDED
    bird_scope_compatible: bool = True
    external_source_mappings: list[ExternalMapping] = Field(default_factory=list)
    external_similarity_hints: list[ExternalSimilarityHint] = Field(default_factory=list)
    similar_taxa: list[SimilarTaxon] = Field(default_factory=list)
    similar_taxon_ids: list[str] = Field(default_factory=list)
    split_into: list[str] = Field(default_factory=list)
    merged_into: str | None = None
    replaced_by: str | None = None
    derived_from: str | None = None
    authority_taxonomy_profile: dict[str, object] = Field(default_factory=dict)

    @field_validator("canonical_taxon_id")
    @classmethod
    def validate_canonical_taxon_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("canonical_taxon_id must not be blank")
        match = CANONICAL_TAXON_ID_PATTERN.fullmatch(normalized)
        if match is None:
            raise ValueError(
                "canonical_taxon_id must match 'taxon:<group>:<6-digit integer>'"
            )
        return normalized

    @field_validator("accepted_scientific_name")
    @classmethod
    def validate_accepted_scientific_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("accepted_scientific_name must not be blank")
        return value

    @field_validator("common_names_by_language")
    @classmethod
    def validate_common_names_by_language(
        cls, value: dict[str, list[str]] | None
    ) -> dict[str, list[str]] | None:
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("common_names_by_language must be a dict or None")
        normalized: dict[str, list[str]] = {}
        for language, names in value.items():
            if not isinstance(names, list):
                raise ValueError(f"common_names_by_language['{language}'] must be a list")
            normalized[language] = [str(name).strip() for name in names if str(name).strip()]
        return normalized if normalized else None

    @field_validator("key_identification_features_by_language")
    @classmethod
    def validate_key_identification_features_by_language(
        cls, value: dict[str, list[str]] | None
    ) -> dict[str, list[str]] | None:
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("key_identification_features_by_language must be a dict or None")
        normalized: dict[str, list[str]] = {}
        for language, features in value.items():
            if not isinstance(features, list):
                raise ValueError(
                    "key_identification_features_by_language"
                    f"['{language}'] must be a list"
                )
            normalized[language] = [
                str(feature).strip()
                for feature in features
                if str(feature).strip()
            ]
        return normalized if normalized else None

    @model_validator(mode="after")
    def normalize_canonical_fields(self) -> Self:
        match = CANONICAL_TAXON_ID_PATTERN.fullmatch(self.canonical_taxon_id)
        if match is not None and match.group("group") != self.taxon_group:
            raise ValueError(
                "canonical_taxon_id group segment must match taxon_group"
            )
        if not self.display_slug or not self.display_slug.strip():
            object.__setattr__(
                self,
                "display_slug",
                _slugify_scientific_name(self.accepted_scientific_name),
            )

        derived_ids = sorted(
            {
                item.target_canonical_taxon_id
                for item in self.similar_taxa
                if item.target_canonical_taxon_id != self.canonical_taxon_id
            }
        )
        if derived_ids != self.similar_taxon_ids:
            object.__setattr__(self, "similar_taxon_ids", derived_ids)

        split_targets = sorted(
            {item for item in self.split_into if item != self.canonical_taxon_id}
        )
        if split_targets != self.split_into:
            object.__setattr__(self, "split_into", split_targets)

        if self.merged_into == self.canonical_taxon_id:
            object.__setattr__(self, "merged_into", None)
        if self.replaced_by == self.canonical_taxon_id:
            object.__setattr__(self, "replaced_by", None)
        if self.derived_from == self.canonical_taxon_id:
            object.__setattr__(self, "derived_from", None)
        if (
            self.taxon_status == TaxonStatus.ACTIVE
            and (self.split_into or self.merged_into or self.replaced_by)
        ):
            object.__setattr__(self, "taxon_status", TaxonStatus.DEPRECATED)

        # Ensure fallback for multilingual fields (backward compatibility)
        if (
            self.common_names_by_language is None
            and self.common_names
        ):
            object.__setattr__(
                self,
                "common_names_by_language",
                {"en": self.common_names},
            )

        if (
            self.key_identification_features_by_language is None
            and self.key_identification_features
        ):
            object.__setattr__(
                self,
                "key_identification_features_by_language",
                {"en": self.key_identification_features},
            )

        return self


class CanonicalTaxonRelationship(DomainModel):
    source_canonical_taxon_id: str
    relationship_type: CanonicalChangeRelationType
    target_canonical_taxon_id: str
    source_name: SourceName
    created_at: datetime


class CanonicalTaxonEvent(DomainModel):
    event_id: str
    event_type: CanonicalEventType
    canonical_taxon_id: str
    source_name: SourceName
    effective_at: datetime
    payload: dict[str, object] = Field(default_factory=dict)


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
    source_observation_key: str
    source_media_key: str
    source_observation_id: str
    source_media_id: str
    raw_payload_ref: str
    run_id: str
    observation_license: str | None = None
    media_license: str | None = None
    qualification_method: str
    ai_model: str | None = None
    ai_prompt_version: str | None = None
    ai_task_name: str | None = None
    ai_status: str | None = None


class DerivedClassification(DomainModel):
    observation_kind: ObservationKind = ObservationKind.UNKNOWN
    diagnostic_strength: DiagnosticStrength = DiagnosticStrength.UNKNOWN
    pedagogical_role: PedagogicalRole = PedagogicalRole.EXCLUDED
    difficulty_band: DifficultyBand = DifficultyBand.UNKNOWN


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
    difficulty_level: DifficultyLevel = DifficultyLevel.UNKNOWN
    media_role: MediaRole = MediaRole.CONTEXT
    confusion_relevance: ConfusionRelevance = ConfusionRelevance.NONE
    diagnostic_feature_visibility: DiagnosticFeatureVisibility = (
        DiagnosticFeatureVisibility.UNKNOWN
    )
    learning_suitability: LearningSuitability = LearningSuitability.UNKNOWN
    uncertainty_reason: UncertaintyReason = UncertaintyReason.NONE
    qualification_notes: str | None = None
    qualification_flags: list[str] = Field(default_factory=list)
    provenance_summary: ProvenanceSummary
    license_safety_result: LicenseSafetyResult
    export_eligible: bool
    ai_confidence: float | None = None
    derived_classification: DerivedClassification | None = None

    @field_validator("qualified_resource_id", "canonical_taxon_id", "media_asset_id")
    @classmethod
    def validate_resource_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("ai_confidence")
    @classmethod
    def validate_ai_confidence(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not 0.0 <= value <= 1.0:
            raise ValueError("ai_confidence must be between 0.0 and 1.0")
        return value

    @model_validator(mode="after")
    def validate_exportability(self) -> Self:
        if self.export_eligible:
            if self.qualification_status != QualificationStatus.ACCEPTED:
                raise ValueError("exportable resources must be accepted")
            if self.license_safety_result != LicenseSafetyResult.SAFE:
                raise ValueError("exportable resources must have a safe license result")
        return self


class PedagogicalImageSubscores(DomainModel):
    technical_quality: int = Field(ge=0, le=100)
    subject_visibility: int = Field(ge=0, le=100)
    diagnostic_value: int = Field(ge=0, le=100)
    pedagogical_clarity: int = Field(ge=0, le=100)
    representativeness: int = Field(ge=0, le=100)
    difficulty_fit: int = Field(ge=0, le=100)
    feedback_potential: int = Field(ge=0, le=100)
    confusion_potential: int = Field(ge=0, le=100)
    context_value: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)


class PedagogicalUsageScores(DomainModel):
    primary_question_beginner: int = Field(ge=0, le=100)
    primary_question_intermediate: int = Field(ge=0, le=100)
    primary_question_expert: int = Field(ge=0, le=100)
    context_learning: int = Field(ge=0, le=100)
    confusion_training: int = Field(ge=0, le=100)
    feedback_explanation: int = Field(ge=0, le=100)


class PostAnswerFeedbackVariant(DomainModel):
    short: str | None = None
    long: str | None = None


class PostAnswerFeedback(DomainModel):
    correct: PostAnswerFeedbackVariant = Field(default_factory=PostAnswerFeedbackVariant)
    incorrect: PostAnswerFeedbackVariant = Field(default_factory=PostAnswerFeedbackVariant)
    identification_tips: list[str] = Field(default_factory=list)
    confidence: int = Field(default=0, ge=0, le=100)


class PedagogicalFeedbackProfile(DomainModel):
    feedback_short: str | None = None
    feedback_long: str | None = None
    what_to_look_at: list[str] = Field(default_factory=list)
    why_good_example: list[str] = Field(default_factory=list)
    why_not_ideal: list[str] = Field(default_factory=list)
    beginner_hint: str | None = None
    expert_hint: str | None = None
    confusion_hint: str | None = None
    post_answer_feedback: PostAnswerFeedback | None = None
    feedback_confidence: int = Field(default=0, ge=0, le=100)


class BirdImagePedagogicalFeatures(DomainModel):
    visible_bird_parts: list[str] = Field(default_factory=list)
    pose: str | None = None
    plumage_visibility: str | None = None
    field_marks_visible: list[str] = Field(default_factory=list)
    sex_or_life_stage_relevance: str | None = None
    habitat_visible: str | None = None


class PedagogicalImageProfile(DomainModel):
    profile_version: str = "pedagogical_image_profile.v1"
    profile_status: PedagogicalProfileStatus
    qualified_resource_id: str
    media_asset_id: str
    canonical_taxon_id: str
    taxon_group: TaxonGroup
    media_type: MediaType
    overall_score: int = Field(ge=0, le=100)
    score_band: PedagogicalScoreBand
    confidence: int = Field(ge=0, le=100)
    subscores: PedagogicalImageSubscores
    usage_scores: PedagogicalUsageScores
    recommended_usages: list[PedagogicalUsage] = Field(default_factory=list)
    avoid_usages: list[PedagogicalUsage] = Field(default_factory=list)
    feedback: PedagogicalFeedbackProfile
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    bird_image: BirdImagePedagogicalFeatures | None = None
    ai_required: bool = True
    ai_profile_source: str | None = None
    ai_prompt_version: str | None = None
    model_name: str | None = None

    @field_validator("recommended_usages", "avoid_usages")
    @classmethod
    def validate_unique_usages(
        cls, value: list[PedagogicalUsage]
    ) -> list[PedagogicalUsage]:
        return list(dict.fromkeys(value))

    @field_validator("reason_codes", "warnings")
    @classmethod
    def validate_non_blank_unique_strings(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item and item.strip()]
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_profile_consistency(self) -> Self:
        recommended = set(self.recommended_usages)
        avoid = set(self.avoid_usages)
        overlap = recommended.intersection(avoid)
        if overlap:
            raise ValueError(
                "recommended_usages and avoid_usages must not overlap "
                f"(overlap={sorted(item.value for item in overlap)})"
            )

        if self.profile_status == PedagogicalProfileStatus.PROFILED:
            if self.confidence < 50:
                raise ValueError("profiled profiles must have confidence >= 50")
            if not self.recommended_usages:
                raise ValueError("profiled profiles must recommend at least one usage")

        if self.profile_status == PedagogicalProfileStatus.PENDING_AI:
            if self.overall_score != 0:
                raise ValueError("pending_ai profiles must keep overall_score at 0")
            if self.recommended_usages:
                raise ValueError("pending_ai profiles cannot have recommended usages")

        if self.profile_status == PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE:
            if self.recommended_usages:
                raise ValueError(
                    "rejected_for_playable_use profiles cannot have recommended usages"
                )

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


class PlayableItem(DomainModel):
    playable_item_id: str
    run_id: str
    qualified_resource_id: str
    canonical_taxon_id: str
    media_asset_id: str
    source_observation_uid: str
    source_name: SourceName
    source_observation_id: str
    source_media_id: str
    scientific_name: str
    common_names_i18n: dict[str, list[str]] = Field(default_factory=dict)
    difficulty_level: DifficultyLevel
    media_role: MediaRole
    learning_suitability: LearningSuitability
    confusion_relevance: ConfusionRelevance
    diagnostic_feature_visibility: DiagnosticFeatureVisibility
    similar_taxon_ids: list[str] = Field(default_factory=list)
    what_to_look_at_specific: list[str] = Field(default_factory=list)
    what_to_look_at_general: list[str] = Field(default_factory=list)
    confusion_hint: str | None = None
    country_code: str | None = None
    observed_at: datetime | None = None
    location_point: GeoPoint | None = None
    location_bbox: GeoBBox | None = None
    location_radius_meters: float | None = None

    @field_validator(
        "playable_item_id",
        "run_id",
        "qualified_resource_id",
        "canonical_taxon_id",
        "media_asset_id",
        "source_observation_uid",
        "source_observation_id",
        "source_media_id",
        "scientific_name",
    )
    @classmethod
    def validate_non_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("common_names_i18n")
    @classmethod
    def validate_common_names_i18n(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        required_languages = ("fr", "en", "nl")
        missing = [language for language in required_languages if language not in value]
        if missing:
            raise ValueError(
                "common_names_i18n must include keys: fr, en, nl "
                f"(missing={','.join(missing)})"
            )
        normalized: dict[str, list[str]] = {}
        for language, names in value.items():
            normalized[language] = [str(name).strip() for name in names if str(name).strip()]
        return normalized


class PackRevisionParameters(DomainModel):
    canonical_taxon_ids: list[str]
    difficulty_policy: PackDifficultyPolicy
    country_code: str | None = None
    location_bbox: GeoBBox | None = None
    location_point: GeoPoint | None = None
    location_radius_meters: float | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    owner_id: str | None = None
    org_id: str | None = None
    visibility: PackVisibility = PackVisibility.PRIVATE
    intended_use: str = "training"

    @field_validator("canonical_taxon_ids")
    @classmethod
    def validate_canonical_taxon_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("canonical_taxon_ids must contain at least one taxon")
        unique_ids = list(dict.fromkeys(normalized))
        return unique_ids

    @field_validator("country_code", "owner_id", "org_id")
    @classmethod
    def validate_optional_non_blank_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be blank when provided")
        return normalized

    @field_validator("intended_use")
    @classmethod
    def validate_intended_use(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("intended_use must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_geo_and_time_filters(self) -> Self:
        if self.observed_from and self.observed_to and self.observed_from > self.observed_to:
            raise ValueError("observed_from must be <= observed_to")

        geo_modes = 0
        if self.country_code:
            geo_modes += 1
        if self.location_bbox is not None:
            geo_modes += 1
        if self.location_point is not None or self.location_radius_meters is not None:
            geo_modes += 1
        if geo_modes > 1:
            raise ValueError("at most one geo filter form can be active")

        if self.location_point is None and self.location_radius_meters is not None:
            raise ValueError("location_radius_meters requires location_point")
        if self.location_point is not None and self.location_radius_meters is None:
            raise ValueError("location_point requires location_radius_meters")
        if self.location_radius_meters is not None and self.location_radius_meters <= 0:
            raise ValueError("location_radius_meters must be > 0")
        return self


class PackSpec(DomainModel):
    pack_id: str
    latest_revision: int
    created_at: datetime
    updated_at: datetime

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pack_id must not be blank")
        return value

    @field_validator("latest_revision")
    @classmethod
    def validate_latest_revision(cls, value: int) -> int:
        if value < 1:
            raise ValueError("latest_revision must be >= 1")
        return value


class PackRevision(DomainModel):
    pack_id: str
    revision: int
    parameters: PackRevisionParameters
    created_at: datetime

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pack_id must not be blank")
        return value

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: int) -> int:
        if value < 1:
            raise ValueError("revision must be >= 1")
        return value


class PackCompilationDeficit(DomainModel):
    code: str
    current: int
    required: int
    missing: int


class PackTaxonDeficit(DomainModel):
    canonical_taxon_id: str
    media_count: int
    missing_media_count: int


class PackCompilationAttempt(DomainModel):
    attempt_id: str
    pack_id: str
    revision: int
    attempted_at: datetime
    compilable: bool
    reason_code: PackCompilationReasonCode
    thresholds: dict[str, int]
    measured: dict[str, int]
    deficits: list[PackCompilationDeficit] = Field(default_factory=list)
    blocking_taxa: list[PackTaxonDeficit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reason_consistency(self) -> Self:
        if self.compilable and self.reason_code != PackCompilationReasonCode.COMPILABLE:
            raise ValueError("compilable attempts must use reason_code=compilable")
        if not self.compilable and self.reason_code == PackCompilationReasonCode.COMPILABLE:
            raise ValueError("non compilable attempts cannot use reason_code=compilable")
        return self


class EnrichmentRequest(DomainModel):
    enrichment_request_id: str
    pack_id: str
    revision: int = Field(ge=1)
    reason_code: EnrichmentRequestReasonCode
    request_status: EnrichmentRequestStatus = EnrichmentRequestStatus.PENDING
    created_at: datetime
    completed_at: datetime | None = None
    execution_attempt_count: int = Field(default=0, ge=0)

    @field_validator("enrichment_request_id", "pack_id")
    @classmethod
    def validate_request_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_completion_fields(self) -> Self:
        if self.request_status == EnrichmentRequestStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed_at is required when request_status=completed")
        return self


class EnrichmentRequestTarget(DomainModel):
    enrichment_request_target_id: str
    enrichment_request_id: str
    resource_type: EnrichmentTargetResourceType
    resource_id: str
    target_attribute: str
    created_at: datetime

    @field_validator(
        "enrichment_request_target_id",
        "enrichment_request_id",
        "resource_id",
        "target_attribute",
    )
    @classmethod
    def validate_target_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class EnrichmentExecution(DomainModel):
    enrichment_execution_id: str
    enrichment_request_id: str
    execution_status: EnrichmentExecutionStatus
    executed_at: datetime
    execution_context: dict[str, object] = Field(default_factory=dict)
    error_info: str | None = None

    @field_validator("enrichment_execution_id", "enrichment_request_id")
    @classmethod
    def validate_execution_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_error_info(self) -> Self:
        if self.execution_status == EnrichmentExecutionStatus.FAILED:
            if self.error_info is None or not self.error_info.strip():
                raise ValueError("error_info is required when execution_status=failed")
        return self


class ConfusionBatch(DomainModel):
    batch_id: str
    created_at: datetime
    event_count: int = Field(ge=0)
    source_schema_version: str | None = None
    source_export_id: str | None = None
    source_app: str | None = None
    source_table: str | None = None
    source_filters_json: str | None = None
    skipped_correct_count: int = Field(default=0, ge=0)

    @field_validator("batch_id")
    @classmethod
    def validate_batch_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("batch_id must not be blank")
        return value


class ConfusionEventInput(DomainModel):
    taxon_confused_for_id: str
    taxon_correct_id: str
    occurred_at: datetime
    source_signal_id: str | None = None
    runtime_session_id: str | None = None
    question_position: int | None = Field(default=None, ge=1)
    session_snapshot_id: str | None = None
    pool_id: str | None = None
    locale: str | None = None
    seed: str | None = None
    selected_option_id: str | None = None
    distractor_source: str | None = None
    option_sources_json: str | None = None

    @field_validator("taxon_confused_for_id", "taxon_correct_id")
    @classmethod
    def validate_taxon_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("taxon ids must not be blank")
        return value

    @model_validator(mode="after")
    def validate_distinct_taxa(self) -> Self:
        if self.taxon_confused_for_id == self.taxon_correct_id:
            raise ValueError("taxon_confused_for_id and taxon_correct_id must differ")
        return self


class ConfusionEvent(DomainModel):
    confusion_event_id: str
    batch_id: str
    taxon_confused_for_id: str
    taxon_correct_id: str
    occurred_at: datetime
    created_at: datetime
    source_signal_id: str | None = None
    runtime_session_id: str | None = None
    question_position: int | None = Field(default=None, ge=1)
    session_snapshot_id: str | None = None
    pool_id: str | None = None
    locale: str | None = None
    seed: str | None = None
    selected_option_id: str | None = None
    distractor_source: str | None = None
    option_sources_json: str | None = None

    @field_validator(
        "confusion_event_id",
        "batch_id",
        "taxon_confused_for_id",
        "taxon_correct_id",
    )
    @classmethod
    def validate_event_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_distinct_taxa(self) -> Self:
        if self.taxon_confused_for_id == self.taxon_correct_id:
            raise ValueError("taxon_confused_for_id and taxon_correct_id must differ")
        return self


class ConfusionAggregateGlobal(DomainModel):
    taxon_confused_for_id: str
    taxon_correct_id: str
    locale: str = "unknown"
    distractor_source: str = "unknown"
    event_count: int = Field(ge=0)
    latest_occurred_at: datetime
    aggregated_at: datetime

    @field_validator("taxon_confused_for_id", "taxon_correct_id")
    @classmethod
    def validate_aggregate_taxon_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("taxon ids must not be blank")
        return value

    @model_validator(mode="after")
    def validate_distinct_taxa(self) -> Self:
        if self.taxon_confused_for_id == self.taxon_correct_id:
            raise ValueError("taxon_confused_for_id and taxon_correct_id must differ")
        return self


class CompiledPackQuestion(DomainModel):
    position: int = Field(ge=1)
    target_playable_item_id: str
    target_canonical_taxon_id: str
    distractor_playable_item_ids: list[str] = Field(default_factory=list)
    distractor_canonical_taxon_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "target_playable_item_id",
        "target_canonical_taxon_id",
    )
    @classmethod
    def validate_non_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_distractors(self) -> Self:
        if len(self.distractor_playable_item_ids) != 3:
            raise ValueError("compiled question must include exactly 3 distractor playable items")
        if len(self.distractor_canonical_taxon_ids) != 3:
            raise ValueError("compiled question must include exactly 3 distractor taxa")
        if len(set(self.distractor_playable_item_ids)) != 3:
            raise ValueError("distractor_playable_item_ids must be unique")
        if len(set(self.distractor_canonical_taxon_ids)) != 3:
            raise ValueError("distractor_canonical_taxon_ids must be unique")
        if self.target_canonical_taxon_id in self.distractor_canonical_taxon_ids:
            raise ValueError("distractor taxa must not include the target taxon")
        return self


class CompiledPackBuild(DomainModel):
    build_id: str
    pack_id: str
    revision: int = Field(ge=1)
    built_at: datetime
    question_count_requested: int = Field(ge=1)
    question_count_built: int = Field(ge=0)
    distractor_count: int = Field(default=3, ge=3, le=3)
    source_run_id: str | None = None
    questions: list[CompiledPackQuestion] = Field(default_factory=list)

    @field_validator("build_id", "pack_id")
    @classmethod
    def validate_build_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_question_counts(self) -> Self:
        if self.question_count_built != len(self.questions):
            raise ValueError("question_count_built must equal the number of questions")
        if self.question_count_built > self.question_count_requested:
            raise ValueError("question_count_built cannot exceed question_count_requested")
        return self


class MaterializedPack(DomainModel):
    materialization_id: str
    pack_id: str
    revision: int = Field(ge=1)
    source_build_id: str
    created_at: datetime
    purpose: PackMaterializationPurpose
    ttl_hours: int | None = None
    expires_at: datetime | None = None
    question_count: int = Field(ge=0)
    questions: list[CompiledPackQuestion] = Field(default_factory=list)

    @field_validator("materialization_id", "pack_id", "source_build_id")
    @classmethod
    def validate_materialization_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_materialization_shape(self) -> Self:
        if self.question_count != len(self.questions):
            raise ValueError("question_count must equal the number of questions")
        if self.purpose == PackMaterializationPurpose.ASSIGNMENT:
            if self.ttl_hours is not None or self.expires_at is not None:
                raise ValueError("assignment materializations cannot define ttl/expires_at")
        if self.purpose == PackMaterializationPurpose.DAILY_CHALLENGE:
            if self.ttl_hours is None or self.ttl_hours <= 0:
                raise ValueError("daily_challenge materializations require ttl_hours > 0")
            if self.expires_at is None:
                raise ValueError("daily_challenge materializations require expires_at")
        return self


class QuestionOption(DomainModel):
    option_id: str
    canonical_taxon_id: str
    taxon_label: str
    is_correct: bool
    playable_item_id: str | None = None
    source: str
    score: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    referenced_only: bool = False

    @field_validator("option_id", "canonical_taxon_id", "taxon_label", "source")
    @classmethod
    def validate_non_blank_option_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("playable_item_id")
    @classmethod
    def validate_optional_playable_item_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("playable_item_id must not be blank when provided")
        return value

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("reason_codes must be unique")
        return normalized

    @field_validator("score")
    @classmethod
    def validate_optional_score(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("score must be >= 0")
        return value

    @model_validator(mode="after")
    def validate_distractor_trace(self) -> Self:
        if not self.is_correct and not self.reason_codes:
            raise ValueError("distractor options require reason_codes")
        return self


class CompiledPackQuestionV2(DomainModel):
    position: int = Field(ge=1)
    target_playable_item_id: str
    target_canonical_taxon_id: str
    options: list[QuestionOption] = Field(default_factory=list)

    @field_validator("target_playable_item_id", "target_canonical_taxon_id")
    @classmethod
    def validate_non_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        if len(self.options) != 4:
            raise ValueError("compiled v2 question must include exactly 4 options")
        correct_options = [option for option in self.options if option.is_correct]
        if len(correct_options) != 1:
            raise ValueError("compiled v2 question must include exactly 1 correct option")
        option_taxa = [option.canonical_taxon_id for option in self.options]
        if len(set(option_taxa)) != len(option_taxa):
            raise ValueError("option canonical_taxon_id values must be unique")
        if self.target_canonical_taxon_id not in option_taxa:
            raise ValueError("target_canonical_taxon_id must be present in options")
        for option in self.options:
            if option.is_correct:
                if option.canonical_taxon_id != self.target_canonical_taxon_id:
                    raise ValueError("correct option must match target_canonical_taxon_id")
                if option.playable_item_id != self.target_playable_item_id:
                    raise ValueError("correct option must carry target_playable_item_id")
            elif option.canonical_taxon_id == self.target_canonical_taxon_id:
                raise ValueError("distractor options must not use target taxon")
        return self


class CompiledPackBuildV2(DomainModel):
    build_id: str
    pack_id: str
    revision: int = Field(ge=1)
    built_at: datetime
    question_count_requested: int = Field(ge=1)
    question_count_built: int = Field(ge=0)
    distractor_count: int = Field(default=3, ge=3, le=3)
    source_run_id: str | None = None
    questions: list[CompiledPackQuestionV2] = Field(default_factory=list)

    @field_validator("build_id", "pack_id")
    @classmethod
    def validate_build_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_question_counts(self) -> Self:
        if self.question_count_built != len(self.questions):
            raise ValueError("question_count_built must equal the number of questions")
        if self.question_count_built > self.question_count_requested:
            raise ValueError("question_count_built cannot exceed question_count_requested")
        return self


class MaterializedPackV2(DomainModel):
    materialization_id: str
    pack_id: str
    revision: int = Field(ge=1)
    source_build_id: str
    created_at: datetime
    purpose: PackMaterializationPurpose
    ttl_hours: int | None = None
    expires_at: datetime | None = None
    question_count: int = Field(ge=0)
    questions: list[CompiledPackQuestionV2] = Field(default_factory=list)

    @field_validator("materialization_id", "pack_id", "source_build_id")
    @classmethod
    def validate_materialization_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_materialization_shape(self) -> Self:
        if self.question_count != len(self.questions):
            raise ValueError("question_count must equal the number of questions")
        if self.purpose == PackMaterializationPurpose.ASSIGNMENT:
            if self.ttl_hours is not None or self.expires_at is not None:
                raise ValueError("assignment materializations cannot define ttl/expires_at")
        if self.purpose == PackMaterializationPurpose.DAILY_CHALLENGE:
            if self.ttl_hours is None or self.ttl_hours <= 0:
                raise ValueError("daily_challenge materializations require ttl_hours > 0")
            if self.expires_at is None:
                raise ValueError("daily_challenge materializations require expires_at")
        return self


class ReferencedTaxon(DomainModel):
    referenced_taxon_id: str
    source: SourceName
    source_taxon_id: str
    scientific_name: str
    preferred_common_name: str | None = None
    common_names_i18n: dict[str, list[str]] = Field(default_factory=dict)
    rank: str | None = None
    taxon_group: TaxonGroup = TaxonGroup.BIRDS
    mapping_status: ReferencedTaxonMappingStatus
    mapped_canonical_taxon_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_validator("referenced_taxon_id", "source_taxon_id", "scientific_name")
    @classmethod
    def validate_referenced_taxon_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("reason_codes")
    @classmethod
    def validate_reference_reason_codes(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("referenced taxa require reason_codes")
        if len(normalized) != len(set(normalized)):
            raise ValueError("reason_codes must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_mapping_status(self) -> Self:
        if (
            self.mapping_status == ReferencedTaxonMappingStatus.MAPPED
            and not self.mapped_canonical_taxon_id
        ):
            raise ValueError("mapped referenced taxa require mapped_canonical_taxon_id")
        if (
            self.mapping_status != ReferencedTaxonMappingStatus.MAPPED
            and self.mapped_canonical_taxon_id is not None
        ):
            raise ValueError("only mapped referenced taxa may carry mapped_canonical_taxon_id")
        return self


class DistractorPolicy(DomainModel):
    allow_out_of_pack_distractors: bool = True
    allow_referenced_only_distractors: bool = True
    prefer_inat_similar_species: bool = True
    max_referenced_only_distractors_per_question: int = Field(default=1, ge=0, le=3)


class CanonicalGovernanceReviewItem(DomainModel):
    governance_review_item_id: str
    run_id: str
    governance_event_id: str
    canonical_taxon_id: str
    decision_status: CanonicalGovernanceDecisionStatus
    reason_code: str
    review_note: str
    review_status: ReviewStatus = ReviewStatus.OPEN
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_note: str | None = None
    resolved_by: str | None = None

    @field_validator(
        "governance_review_item_id",
        "run_id",
        "governance_event_id",
        "canonical_taxon_id",
        "reason_code",
        "review_note",
    )
    @classmethod
    def validate_required_non_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def validate_resolution_payload(self) -> Self:
        if self.review_status == ReviewStatus.CLOSED:
            if self.resolved_at is None:
                raise ValueError("resolved_at is required when review_status=closed")
            if not self.resolved_note or not self.resolved_note.strip():
                raise ValueError("resolved_note is required when review_status=closed")
            if not self.resolved_by or not self.resolved_by.strip():
                raise ValueError("resolved_by is required when review_status=closed")
        return self


def _slugify_scientific_name(value: str) -> str:
    return "-".join(part.strip().lower() for part in value.split() if part.strip())


class DistractorRelationship(DomainModel):
    relationship_id: str
    target_canonical_taxon_id: str
    target_scientific_name: str
    candidate_taxon_ref_type: CandidateTaxonRefType
    candidate_taxon_ref_id: str | None = None
    candidate_scientific_name: str
    source: DistractorRelationshipSource
    source_rank: int = Field(ge=1)
    confusion_types: list[DistractorConfusionType] = Field(default_factory=list)
    pedagogical_value: DistractorPedagogicalValue = DistractorPedagogicalValue.UNKNOWN
    difficulty_level: DistractorDifficultyLevel = DistractorDifficultyLevel.MEDIUM
    learner_level: DistractorLearnerLevel = DistractorLearnerLevel.MIXED
    reason: str | None = None
    status: DistractorRelationshipStatus = DistractorRelationshipStatus.CANDIDATE
    constraints: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None

    @field_validator("relationship_id", "target_canonical_taxon_id", "target_scientific_name")
    @classmethod
    def validate_required_string_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @field_validator("candidate_scientific_name")
    @classmethod
    def validate_candidate_scientific_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("candidate_scientific_name must not be blank")
        return value

    @model_validator(mode="after")
    def validate_distractor_relationship(self) -> Self:
        # candidate_taxon_ref_id rules
        if self.candidate_taxon_ref_type in (
            CandidateTaxonRefType.CANONICAL_TAXON,
            CandidateTaxonRefType.REFERENCED_TAXON,
        ):
            if not self.candidate_taxon_ref_id or not self.candidate_taxon_ref_id.strip():
                raise ValueError(
                    f"candidate_taxon_ref_id is required when "
                    f"candidate_taxon_ref_type={self.candidate_taxon_ref_type}"
                )
        if self.candidate_taxon_ref_type == CandidateTaxonRefType.UNRESOLVED_TAXON:
            if self.candidate_taxon_ref_id is not None:
                raise ValueError(
                    "candidate_taxon_ref_id must be null for unresolved_taxon"
                )

        # unresolved_taxon cannot be validated
        if (
            self.candidate_taxon_ref_type == CandidateTaxonRefType.UNRESOLVED_TAXON
            and self.status == DistractorRelationshipStatus.VALIDATED
        ):
            raise ValueError("unresolved_taxon cannot have status=validated")

        # unresolved_taxon must be needs_review or unavailable_missing_taxon
        if self.candidate_taxon_ref_type == CandidateTaxonRefType.UNRESOLVED_TAXON and (
            self.status
            not in (
                DistractorRelationshipStatus.NEEDS_REVIEW,
                DistractorRelationshipStatus.UNAVAILABLE_MISSING_TAXON,
            )
        ):
            raise ValueError(
                "unresolved_taxon status must be needs_review or unavailable_missing_taxon"
            )

        # emergency_diversity_fallback cannot be validated
        if (
            self.source == DistractorRelationshipSource.EMERGENCY_DIVERSITY_FALLBACK
            and self.status == DistractorRelationshipStatus.VALIDATED
        ):
            raise ValueError(
                "emergency_diversity_fallback relationships cannot be status=validated"
            )

        # target must not equal candidate (by scientific name)
        if self.target_scientific_name.strip() == self.candidate_scientific_name.strip():
            raise ValueError(
                "target_scientific_name must not equal candidate_scientific_name"
            )

        # validated relationships should have at least one confusion type
        if (
            self.status == DistractorRelationshipStatus.VALIDATED
            and not self.confusion_types
        ):
            raise ValueError(
                "validated relationships must have at least one confusion_type"
            )

        return self
