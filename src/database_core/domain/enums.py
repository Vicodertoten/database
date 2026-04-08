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
