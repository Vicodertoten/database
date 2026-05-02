from __future__ import annotations

from enum import StrEnum


class SourceName(StrEnum):
    INATURALIST = "inaturalist"
    GBIF = "gbif"
    WIKIMEDIA_COMMONS = "wikimedia_commons"


class CanonicalRank(StrEnum):
    SPECIES = "species"
    GENUS = "genus"
    FAMILY = "family"


class TaxonGroup(StrEnum):
    BIRDS = "birds"


class TaxonStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    PROVISIONAL = "provisional"


class CanonicalChangeRelationType(StrEnum):
    SPLIT_INTO = "split_into"
    MERGED_INTO = "merged_into"
    REPLACED_BY = "replaced_by"
    DERIVED_FROM = "derived_from"


class CanonicalEventType(StrEnum):
    CREATE = "create"
    NAME_UPDATE = "name_update"
    STATUS_CHANGE = "status_change"
    SPLIT = "split"
    MERGE = "merge"
    REPLACE = "replace"
    MAPPING_CONFLICT = "mapping_conflict"


class CanonicalGovernanceDecisionStatus(StrEnum):
    AUTO_CLEAR = "auto_clear"
    MANUAL_REVIEWED = "manual_reviewed"


class EnrichmentStatus(StrEnum):
    SEEDED = "seeded"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


class SimilarityRelationType(StrEnum):
    TAXONOMIC_NEIGHBOR = "taxonomic_neighbor"
    VISUAL_LOOKALIKE = "visual_lookalike"
    EDUCATIONAL_CONFUSION = "educational_confusion"


class MediaType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class QualificationStatus(StrEnum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class TechnicalQuality(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PedagogicalQuality(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DifficultyLevel(StrEnum):
    UNKNOWN = "unknown"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MediaRole(StrEnum):
    PRIMARY_ID = "primary_id"
    CONTEXT = "context"
    DISTRACTOR_RISK = "distractor_risk"
    NON_DIAGNOSTIC = "non_diagnostic"


class ConfusionRelevance(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DiagnosticFeatureVisibility(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LearningSuitability(StrEnum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ObservationKind(StrEnum):
    FULL_BIRD = "full_bird"
    IN_FLIGHT = "in_flight"
    PARTIAL = "partial"
    NEST_OR_EGGS = "nest_or_eggs"
    TRACE_OR_FEATHER = "trace_or_feather"
    CARCASS = "carcass"
    HABITAT_CONTEXT = "habitat_context"
    UNKNOWN = "unknown"


class DiagnosticStrength(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class PedagogicalRole(StrEnum):
    CORE_ID = "core_id"
    ADVANCED_ID = "advanced_id"
    CONTEXT = "context"
    FORENSICS = "forensics"
    EXCLUDED = "excluded"


class DifficultyBand(StrEnum):
    STARTER = "starter"
    INTERMEDIATE = "intermediate"
    EXPERT = "expert"
    UNKNOWN = "unknown"


class UncertaintyReason(StrEnum):
    NONE = "none"
    OCCLUSION = "occlusion"
    ANGLE = "angle"
    DISTANCE = "distance"
    MOTION = "motion"
    MULTIPLE_SUBJECTS = "multiple_subjects"
    MODEL_UNCERTAIN = "model_uncertain"
    TAXONOMY_AMBIGUOUS = "taxonomy_ambiguous"


class Sex(StrEnum):
    UNKNOWN = "unknown"
    MALE = "male"
    FEMALE = "female"
    MIXED = "mixed"


class ViewAngle(StrEnum):
    UNKNOWN = "unknown"
    LATERAL = "lateral"
    FRONTAL = "frontal"
    DORSAL = "dorsal"
    VENTRAL = "ventral"
    OBLIQUE = "oblique"
    CLOSE_UP = "close_up"


class LicenseSafetyResult(StrEnum):
    SAFE = "safe"
    REVIEW_REQUIRED = "review_required"
    UNSAFE = "unsafe"


class QualificationStage(StrEnum):
    COMPLIANCE_SCREENING = "compliance_screening"
    FAST_SEMANTIC_SCREENING = "fast_semantic_screening"
    EXPERT_QUALIFICATION = "expert_qualification"
    REVIEW_QUEUE_ASSEMBLY = "review_queue_assembly"


class ReviewStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class ReviewPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InvalidationReason(StrEnum):
    QUALIFICATION_NOT_EXPORTABLE = "qualification_not_exportable"
    CANONICAL_TAXON_NOT_ACTIVE = "canonical_taxon_not_active"
    SOURCE_RECORD_REMOVED = "source_record_removed"
    POLICY_FILTERED = "policy_filtered"


class PackDifficultyPolicy(StrEnum):
    EASY = "easy"
    BALANCED = "balanced"
    HARD = "hard"
    MIXED = "mixed"


class PackProfile(StrEnum):
    CORE = "core"
    MIXED = "mixed"


class PackVisibility(StrEnum):
    PRIVATE = "private"
    ORG = "org"
    PUBLIC = "public"


class PackMaterializationPurpose(StrEnum):
    ASSIGNMENT = "assignment"
    DAILY_CHALLENGE = "daily_challenge"


class ReferencedTaxonMappingStatus(StrEnum):
    MAPPED = "mapped"
    AUTO_REFERENCED_HIGH_CONFIDENCE = "auto_referenced_high_confidence"
    AUTO_REFERENCED_LOW_CONFIDENCE = "auto_referenced_low_confidence"
    AMBIGUOUS = "ambiguous"
    IGNORED = "ignored"


class PackCompilationReasonCode(StrEnum):
    COMPILABLE = "compilable"
    NO_PLAYABLE_ITEMS = "no_playable_items"
    INSUFFICIENT_TAXA_SERVED = "insufficient_taxa_served"
    INSUFFICIENT_MEDIA_PER_TAXON = "insufficient_media_per_taxon"
    INSUFFICIENT_TOTAL_QUESTIONS = "insufficient_total_questions"


class EnrichmentRequestStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class EnrichmentExecutionStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class EnrichmentTargetResourceType(StrEnum):
    PACK = "pack"
    CANONICAL_TAXON = "canonical_taxon"
    PLAYABLE_ITEM = "playable_item"
    QUALIFIED_RESOURCE = "qualified_resource"


class EnrichmentRequestReasonCode(StrEnum):
    NO_PLAYABLE_ITEMS = "no_playable_items"
    INSUFFICIENT_TAXA_SERVED = "insufficient_taxa_served"
    INSUFFICIENT_MEDIA_PER_TAXON = "insufficient_media_per_taxon"
    INSUFFICIENT_TOTAL_QUESTIONS = "insufficient_total_questions"
