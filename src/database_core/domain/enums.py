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


class PedagogicalProfileStatus(StrEnum):
    PENDING_AI = "pending_ai"
    PROFILED = "profiled"
    PROFILED_WITH_WARNINGS = "profiled_with_warnings"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    REJECTED_FOR_PLAYABLE_USE = "rejected_for_playable_use"


class PedagogicalScoreBand(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class PedagogicalUsage(StrEnum):
    PRIMARY_QUESTION_BEGINNER = "primary_question_beginner"
    PRIMARY_QUESTION_INTERMEDIATE = "primary_question_intermediate"
    PRIMARY_QUESTION_EXPERT = "primary_question_expert"
    CONTEXT_LEARNING = "context_learning"
    CONFUSION_TRAINING = "confusion_training"
    FEEDBACK_EXPLANATION = "feedback_explanation"


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


# --- Distractor relationships ---


class DistractorRelationshipSource(StrEnum):
    INATURALIST_SIMILAR_SPECIES = "inaturalist_similar_species"
    TAXONOMIC_NEIGHBOR_SAME_GENUS = "taxonomic_neighbor_same_genus"
    TAXONOMIC_NEIGHBOR_SAME_FAMILY = "taxonomic_neighbor_same_family"
    TAXONOMIC_NEIGHBOR_SAME_ORDER = "taxonomic_neighbor_same_order"
    AI_PEDAGOGICAL_PROPOSAL = "ai_pedagogical_proposal"
    MANUAL_EXPERT = "manual_expert"
    EMERGENCY_DIVERSITY_FALLBACK = "emergency_diversity_fallback"


class DistractorRelationshipStatus(StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    UNAVAILABLE_MISSING_TAXON = "unavailable_missing_taxon"
    UNAVAILABLE_MISSING_LOCALIZED_NAME = "unavailable_missing_localized_name"
    UNAVAILABLE_MISSING_MEDIA = "unavailable_missing_media"


class CandidateTaxonRefType(StrEnum):
    CANONICAL_TAXON = "canonical_taxon"
    REFERENCED_TAXON = "referenced_taxon"
    UNRESOLVED_TAXON = "unresolved_taxon"


class DistractorConfusionType(StrEnum):
    VISUAL_SIMILARITY = "visual_similarity"
    SAME_GENUS = "same_genus"
    SAME_FAMILY = "same_family"
    SAME_ORDER = "same_order"
    SAME_SIZE = "same_size"
    SAME_SHAPE = "same_shape"
    SAME_COLOR_PATTERN = "same_color_pattern"
    SAME_HABITAT = "same_habitat"
    SAME_BEHAVIOR = "same_behavior"
    SAME_SEASON = "same_season"
    SAME_LIFE_STAGE = "same_life_stage"
    BEGINNER_COMMON_CONFUSION = "beginner_common_confusion"
    EXPERT_FINE_CONFUSION = "expert_fine_confusion"
    LOCAL_SPECIES_CONFUSION = "local_species_confusion"
    NAME_SIMILARITY = "name_similarity"
    ECOLOGICAL_ASSOCIATION = "ecological_association"


class DistractorLearnerLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MIXED = "mixed"


class DistractorPedagogicalValue(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DistractorDifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"
