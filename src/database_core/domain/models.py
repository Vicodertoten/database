from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database_core.domain.canonical_ids import CANONICAL_TAXON_ID_PATTERN
from database_core.domain.enums import (
    CanonicalChangeRelationType,
    CanonicalEventType,
    CanonicalGovernanceDecisionStatus,
    CanonicalRank,
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DifficultyLevel,
    EnrichmentExecutionStatus,
    EnrichmentRequestReasonCode,
    EnrichmentRequestStatus,
    EnrichmentStatus,
    EnrichmentTargetResourceType,
    LearningSuitability,
    LicenseSafetyResult,
    MediaRole,
    MediaType,
    PackCompilationReasonCode,
    PackDifficultyPolicy,
    PackMaterializationPurpose,
    PackVisibility,
    PedagogicalQuality,
    QualificationStage,
    QualificationStatus,
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
    key_identification_features: list[str] = Field(default_factory=list)
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
