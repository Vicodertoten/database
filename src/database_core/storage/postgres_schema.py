from __future__ import annotations

POSTGRES_SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    source_mode TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    snapshot_id TEXT,
    schema_version TEXT NOT NULL,
    qualification_version TEXT NOT NULL,
    enrichment_version TEXT NOT NULL,
    export_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    run_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at
    ON pipeline_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS canonical_taxa (
    canonical_taxon_id TEXT PRIMARY KEY,
    accepted_scientific_name TEXT NOT NULL,
    canonical_rank TEXT NOT NULL,
    taxon_group TEXT NOT NULL,
    taxon_status TEXT NOT NULL,
    authority_source TEXT NOT NULL,
    display_slug TEXT NOT NULL,
    synonyms_json TEXT NOT NULL,
    common_names_json TEXT NOT NULL,
    key_identification_features_json TEXT NOT NULL,
    source_enrichment_status TEXT NOT NULL,
    bird_scope_compatible BOOLEAN NOT NULL,
    external_source_mappings_json TEXT NOT NULL,
    external_similarity_hints_json TEXT NOT NULL,
    similar_taxa_json TEXT NOT NULL,
    similar_taxon_ids_json TEXT NOT NULL,
    split_into_json TEXT NOT NULL,
    merged_into TEXT,
    replaced_by TEXT,
    derived_from TEXT,
    authority_taxonomy_profile_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_taxon_relationships (
    source_canonical_taxon_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    target_canonical_taxon_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_canonical_taxon_id, relationship_type, target_canonical_taxon_id),
    FOREIGN KEY (source_canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id),
    FOREIGN KEY (target_canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

CREATE TABLE IF NOT EXISTS canonical_state_events (
    state_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_state_events_run
    ON canonical_state_events (run_id, canonical_taxon_id, event_type);

CREATE TABLE IF NOT EXISTS canonical_change_events (
    change_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_change_events_run
    ON canonical_change_events (run_id, canonical_taxon_id, event_type);

CREATE INDEX IF NOT EXISTS idx_canonical_change_events_created_at
    ON canonical_change_events (created_at DESC);

CREATE TABLE IF NOT EXISTS canonical_taxa_history (
    run_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, canonical_taxon_id),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS source_observations_history (
    run_id TEXT NOT NULL,
    observation_uid TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, observation_uid),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS media_assets_history (
    run_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_media_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, media_id),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS qualified_resources_history (
    run_id TEXT NOT NULL,
    qualified_resource_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, qualified_resource_id),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS review_queue_history (
    run_id TEXT NOT NULL,
    review_item_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, review_item_id),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS canonical_governance_events (
    governance_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    decision_status TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_governance_events_run
    ON canonical_governance_events (run_id, decision_status, decision_reason);

CREATE TABLE IF NOT EXISTS canonical_governance_review_queue (
    governance_review_item_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    governance_event_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    review_note TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    resolved_note TEXT,
    resolved_by TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id),
    FOREIGN KEY (governance_event_id) REFERENCES canonical_governance_events (governance_event_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_governance_review_queue_status
    ON canonical_governance_review_queue (review_status, created_at);

CREATE INDEX IF NOT EXISTS idx_canonical_governance_review_queue_reason
    ON canonical_governance_review_queue (reason_code, review_status, created_at);

CREATE TABLE IF NOT EXISTS source_observations (
    observation_uid TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    source_taxon_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ,
    location_json TEXT NOT NULL,
    source_quality_json TEXT NOT NULL,
    raw_payload_ref TEXT NOT NULL,
    canonical_taxon_id TEXT,
    country_code TEXT,
    location_point geometry(Point, 4326),
    location_bbox geometry(Polygon, 4326),
    location_radius_meters DOUBLE PRECISION,
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_observations_source_external
    ON source_observations (source_name, source_observation_id);

CREATE INDEX IF NOT EXISTS idx_source_observations_country_code
    ON source_observations (country_code);

CREATE INDEX IF NOT EXISTS idx_source_observations_point_gist
    ON source_observations USING GIST (location_point);

CREATE INDEX IF NOT EXISTS idx_source_observations_bbox_gist
    ON source_observations USING GIST (location_bbox);

CREATE TABLE IF NOT EXISTS media_assets (
    media_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_media_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    source_url TEXT NOT NULL,
    attribution TEXT NOT NULL,
    author TEXT,
    license TEXT,
    mime_type TEXT,
    file_extension TEXT,
    width INTEGER,
    height INTEGER,
    checksum TEXT,
    source_observation_uid TEXT NOT NULL,
    canonical_taxon_id TEXT,
    raw_payload_ref TEXT NOT NULL,
    FOREIGN KEY (source_observation_uid) REFERENCES source_observations (observation_uid),
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_media_assets_source_external
    ON media_assets (source_name, source_media_id);

CREATE TABLE IF NOT EXISTS qualified_resources (
    qualified_resource_id TEXT PRIMARY KEY,
    canonical_taxon_id TEXT NOT NULL,
    source_observation_uid TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    media_asset_id TEXT NOT NULL,
    qualification_status TEXT NOT NULL,
    qualification_version TEXT NOT NULL,
    technical_quality TEXT NOT NULL,
    pedagogical_quality TEXT NOT NULL,
    life_stage TEXT NOT NULL,
    sex TEXT NOT NULL,
    visible_parts_json TEXT NOT NULL,
    view_angle TEXT NOT NULL,
    difficulty_level TEXT NOT NULL,
    media_role TEXT NOT NULL,
    confusion_relevance TEXT NOT NULL,
    diagnostic_feature_visibility TEXT NOT NULL,
    learning_suitability TEXT NOT NULL,
    uncertainty_reason TEXT NOT NULL,
    qualification_notes TEXT,
    qualification_flags_json TEXT NOT NULL,
    provenance_summary_json TEXT NOT NULL,
    license_safety_result TEXT NOT NULL,
    export_eligible BOOLEAN NOT NULL,
    ai_confidence DOUBLE PRECISION,
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id),
    FOREIGN KEY (source_observation_uid) REFERENCES source_observations (observation_uid),
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id)
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_item_id TEXT PRIMARY KEY,
    media_asset_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    review_reason_code TEXT NOT NULL,
    review_note TEXT,
    stage_name TEXT NOT NULL,
    priority TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id),
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);
"""

POSTGRES_PLAYABLE_V9_SQL = """
CREATE TABLE IF NOT EXISTS playable_items (
    playable_item_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    qualified_resource_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    media_asset_id TEXT NOT NULL,
    source_observation_uid TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    source_media_id TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    common_names_i18n_json TEXT NOT NULL,
    difficulty_level TEXT NOT NULL,
    media_role TEXT NOT NULL,
    learning_suitability TEXT NOT NULL,
    confusion_relevance TEXT NOT NULL,
    diagnostic_feature_visibility TEXT NOT NULL,
    similar_taxon_ids_json TEXT NOT NULL,
    what_to_look_at_specific_json TEXT NOT NULL,
    what_to_look_at_general_json TEXT NOT NULL,
    confusion_hint TEXT,
    country_code TEXT,
    observed_at TIMESTAMPTZ,
    location_point geometry(Point, 4326),
    location_bbox geometry(Polygon, 4326),
    location_radius_meters DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id),
    FOREIGN KEY (qualified_resource_id) REFERENCES qualified_resources (qualified_resource_id),
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id),
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id),
    FOREIGN KEY (source_observation_uid) REFERENCES source_observations (observation_uid)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_playable_items_qualified_resource
    ON playable_items (qualified_resource_id);

CREATE INDEX IF NOT EXISTS idx_playable_items_canonical_taxon_id
    ON playable_items (canonical_taxon_id);

CREATE INDEX IF NOT EXISTS idx_playable_items_country_code
    ON playable_items (country_code);

CREATE INDEX IF NOT EXISTS idx_playable_items_observed_at
    ON playable_items (observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_playable_items_difficulty
    ON playable_items (difficulty_level);

CREATE INDEX IF NOT EXISTS idx_playable_items_media_role
    ON playable_items (media_role);

CREATE INDEX IF NOT EXISTS idx_playable_items_learning_suitability
    ON playable_items (learning_suitability);

CREATE INDEX IF NOT EXISTS idx_playable_items_confusion_relevance
    ON playable_items (confusion_relevance);

CREATE INDEX IF NOT EXISTS idx_playable_items_point_gist
    ON playable_items USING GIST (location_point);

CREATE INDEX IF NOT EXISTS idx_playable_items_bbox_gist
    ON playable_items USING GIST (location_bbox);

CREATE TABLE IF NOT EXISTS playable_items_history (
    run_id TEXT NOT NULL,
    playable_item_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, playable_item_id),
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE OR REPLACE VIEW playable_corpus_v1 AS
SELECT
    playable_item_id,
    run_id,
    qualified_resource_id,
    canonical_taxon_id,
    media_asset_id,
    source_observation_uid,
    source_name,
    source_observation_id,
    source_media_id,
    scientific_name,
    common_names_i18n_json,
    difficulty_level,
    media_role,
    learning_suitability,
    confusion_relevance,
    diagnostic_feature_visibility,
    similar_taxon_ids_json,
    what_to_look_at_specific_json,
    what_to_look_at_general_json,
    confusion_hint,
    country_code,
    observed_at,
    location_point,
    location_bbox,
    location_radius_meters,
    created_at
FROM playable_items;
"""

POSTGRES_PACK_V10_SQL = """
CREATE TABLE IF NOT EXISTS pack_specs (
    pack_id TEXT PRIMARY KEY,
    latest_revision INTEGER NOT NULL CHECK (latest_revision >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pack_revisions (
    pack_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    canonical_taxon_ids_json TEXT NOT NULL,
    difficulty_policy TEXT NOT NULL CHECK (
        difficulty_policy IN ('easy', 'balanced', 'hard', 'mixed')
    ),
    country_code TEXT,
    location_bbox geometry(Polygon, 4326),
    location_point geometry(Point, 4326),
    location_radius_meters DOUBLE PRECISION,
    observed_from TIMESTAMPTZ,
    observed_to TIMESTAMPTZ,
    owner_id TEXT,
    org_id TEXT,
    visibility TEXT NOT NULL CHECK (visibility IN ('private', 'org', 'public')),
    intended_use TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pack_id, revision),
    FOREIGN KEY (pack_id) REFERENCES pack_specs (pack_id) ON DELETE CASCADE,
    CONSTRAINT pack_revisions_observed_order
        CHECK (observed_from IS NULL OR observed_to IS NULL OR observed_from <= observed_to),
    CONSTRAINT pack_revisions_geo_exclusive
        CHECK (
            (
                CASE WHEN country_code IS NOT NULL THEN 1 ELSE 0 END
                + CASE WHEN location_bbox IS NOT NULL THEN 1 ELSE 0 END
                + CASE
                    WHEN location_point IS NOT NULL OR location_radius_meters IS NOT NULL
                    THEN 1
                    ELSE 0
                  END
            ) <= 1
        ),
    CONSTRAINT pack_revisions_point_radius_consistency
        CHECK (
            (location_point IS NULL AND location_radius_meters IS NULL)
            OR (
                location_point IS NOT NULL
                AND location_radius_meters IS NOT NULL
                AND location_radius_meters > 0
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_pack
    ON pack_revisions (pack_id, revision DESC);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_country_code
    ON pack_revisions (country_code);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_observed_from
    ON pack_revisions (observed_from);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_observed_to
    ON pack_revisions (observed_to);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_bbox_gist
    ON pack_revisions USING GIST (location_bbox);

CREATE INDEX IF NOT EXISTS idx_pack_revisions_point_gist
    ON pack_revisions USING GIST (location_point);

CREATE TABLE IF NOT EXISTS pack_compilation_attempts (
    attempt_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_version TEXT NOT NULL,
    pack_diagnostic_version TEXT NOT NULL,
    compilable BOOLEAN NOT NULL,
    reason_code TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    deficits_json TEXT NOT NULL,
    blocking_taxa_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (pack_id, revision) REFERENCES pack_revisions (pack_id, revision) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pack_compilation_attempts_pack
    ON pack_compilation_attempts (pack_id, revision, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_pack_compilation_attempts_reason
    ON pack_compilation_attempts (reason_code, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_pack_specs_updated_at
    ON pack_specs (updated_at DESC);
"""

POSTGRES_PACK_COMPILATION_V11_SQL = """
CREATE TABLE IF NOT EXISTS compiled_pack_builds (
    build_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    built_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_version TEXT NOT NULL,
    pack_compiled_version TEXT NOT NULL,
    question_count_requested INTEGER NOT NULL CHECK (question_count_requested >= 1),
    question_count_built INTEGER NOT NULL CHECK (question_count_built >= 0),
    distractor_count INTEGER NOT NULL CHECK (distractor_count = 3),
    source_run_id TEXT,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (pack_id, revision) REFERENCES pack_revisions (pack_id, revision) ON DELETE CASCADE,
    FOREIGN KEY (source_run_id) REFERENCES pipeline_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_compiled_pack_builds_pack_revision
    ON compiled_pack_builds (pack_id, revision, built_at DESC);

CREATE TABLE IF NOT EXISTS pack_materializations (
    materialization_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    source_build_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    purpose TEXT NOT NULL CHECK (purpose IN ('assignment', 'daily_challenge')),
    ttl_hours INTEGER,
    expires_at TIMESTAMPTZ,
    schema_version TEXT NOT NULL,
    pack_materialization_version TEXT NOT NULL,
    question_count INTEGER NOT NULL CHECK (question_count >= 0),
    payload_json TEXT NOT NULL,
    FOREIGN KEY (pack_id, revision) REFERENCES pack_revisions (pack_id, revision) ON DELETE CASCADE,
    FOREIGN KEY (source_build_id) REFERENCES compiled_pack_builds (build_id) ON DELETE CASCADE,
    CONSTRAINT pack_materializations_assignment_ttl
        CHECK (
            (purpose = 'assignment' AND ttl_hours IS NULL AND expires_at IS NULL)
            OR
            (
                purpose = 'daily_challenge'
                AND ttl_hours IS NOT NULL
                AND ttl_hours > 0
                AND expires_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_pack_materializations_pack_revision
    ON pack_materializations (pack_id, revision, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pack_materializations_purpose_expires_at
    ON pack_materializations (purpose, expires_at);
"""

POSTGRES_ENRICHMENT_QUEUE_V12_SQL = """
CREATE TABLE IF NOT EXISTS enrichment_requests (
    enrichment_request_id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    request_status TEXT NOT NULL CHECK (
        request_status IN ('pending', 'in_progress', 'completed', 'failed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    execution_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (execution_attempt_count >= 0),
    FOREIGN KEY (pack_id, revision) REFERENCES pack_revisions (pack_id, revision) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrichment_requests_status_created
    ON enrichment_requests (request_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_enrichment_requests_pack_revision
    ON enrichment_requests (pack_id, revision, created_at DESC);

CREATE TABLE IF NOT EXISTS enrichment_request_targets (
    enrichment_request_target_id TEXT PRIMARY KEY,
    enrichment_request_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    target_attribute TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (enrichment_request_id) REFERENCES enrichment_requests (enrichment_request_id)
        ON DELETE CASCADE,
    CONSTRAINT enrichment_request_targets_unique
        UNIQUE (enrichment_request_id, resource_type, resource_id, target_attribute)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_request_targets_request_id
    ON enrichment_request_targets (enrichment_request_id);

CREATE TABLE IF NOT EXISTS enrichment_executions (
    enrichment_execution_id TEXT PRIMARY KEY,
    enrichment_request_id TEXT NOT NULL,
    execution_status TEXT NOT NULL CHECK (
        execution_status IN ('success', 'partial', 'failed')
    ),
    executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    execution_context_json TEXT NOT NULL,
    error_info TEXT,
    FOREIGN KEY (enrichment_request_id) REFERENCES enrichment_requests (enrichment_request_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrichment_executions_request_id
    ON enrichment_executions (enrichment_request_id, executed_at DESC);
"""

POSTGRES_CONFUSION_V13_SQL = """
CREATE TABLE IF NOT EXISTS confusion_batches (
    batch_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_count INTEGER NOT NULL CHECK (event_count >= 0)
);

CREATE TABLE IF NOT EXISTS confusion_events (
    confusion_event_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    taxon_confused_for_id TEXT NOT NULL,
    taxon_correct_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (batch_id) REFERENCES confusion_batches (batch_id) ON DELETE CASCADE,
    CONSTRAINT confusion_events_distinct_taxa
        CHECK (taxon_confused_for_id <> taxon_correct_id)
);

CREATE INDEX IF NOT EXISTS idx_confusion_events_batch_id
    ON confusion_events (batch_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_confusion_events_pair
    ON confusion_events (taxon_confused_for_id, taxon_correct_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS confusion_aggregates_global (
    taxon_confused_for_id TEXT NOT NULL,
    taxon_correct_id TEXT NOT NULL,
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    latest_occurred_at TIMESTAMPTZ NOT NULL,
    aggregated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxon_confused_for_id, taxon_correct_id),
    CONSTRAINT confusion_aggregates_global_distinct_taxa
        CHECK (taxon_confused_for_id <> taxon_correct_id)
);

CREATE INDEX IF NOT EXISTS idx_confusion_aggregates_global_event_count
    ON confusion_aggregates_global (event_count DESC, taxon_confused_for_id, taxon_correct_id);
"""

POSTGRES_PLAYABLE_INCREMENTAL_V14_SQL = """
ALTER TABLE playable_items
    DROP CONSTRAINT IF EXISTS playable_items_qualified_resource_id_fkey;

ALTER TABLE playable_items
    DROP CONSTRAINT IF EXISTS playable_items_canonical_taxon_id_fkey;

ALTER TABLE playable_items
    DROP CONSTRAINT IF EXISTS playable_items_media_asset_id_fkey;

ALTER TABLE playable_items
    DROP CONSTRAINT IF EXISTS playable_items_source_observation_uid_fkey;

CREATE TABLE IF NOT EXISTS playable_item_lifecycle (
    playable_item_id TEXT PRIMARY KEY,
    qualified_resource_id TEXT NOT NULL UNIQUE,
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN ('active', 'invalidated')),
    created_run_id TEXT NOT NULL,
    last_seen_run_id TEXT NOT NULL,
    invalidated_run_id TEXT,
    invalidation_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_playable_item_lifecycle_status
    ON playable_item_lifecycle (lifecycle_status);

CREATE INDEX IF NOT EXISTS idx_playable_item_lifecycle_last_seen
    ON playable_item_lifecycle (last_seen_run_id);

CREATE INDEX IF NOT EXISTS idx_playable_item_lifecycle_invalidated_run
    ON playable_item_lifecycle (invalidated_run_id);

CREATE INDEX IF NOT EXISTS idx_playable_item_lifecycle_reason
    ON playable_item_lifecycle (invalidation_reason);

INSERT INTO playable_item_lifecycle (
    playable_item_id,
    qualified_resource_id,
    lifecycle_status,
    created_run_id,
    last_seen_run_id,
    invalidated_run_id,
    invalidation_reason,
    created_at,
    updated_at
)
SELECT
    playable_item_id,
    qualified_resource_id,
    'active',
    run_id,
    run_id,
    NULL,
    NULL,
    created_at,
    now()
FROM playable_items
ON CONFLICT (playable_item_id) DO NOTHING;

CREATE OR REPLACE VIEW playable_corpus_v1 AS
SELECT
    p.playable_item_id,
    p.run_id,
    p.qualified_resource_id,
    p.canonical_taxon_id,
    p.media_asset_id,
    p.source_observation_uid,
    p.source_name,
    p.source_observation_id,
    p.source_media_id,
    p.scientific_name,
    p.common_names_i18n_json,
    p.difficulty_level,
    p.media_role,
    p.learning_suitability,
    p.confusion_relevance,
    p.diagnostic_feature_visibility,
    p.similar_taxon_ids_json,
    p.what_to_look_at_specific_json,
    p.what_to_look_at_general_json,
    p.confusion_hint,
    p.country_code,
    p.observed_at,
    p.location_point,
    p.location_bbox,
    p.location_radius_meters,
    p.created_at
FROM playable_items AS p
JOIN playable_item_lifecycle AS l
    ON l.playable_item_id = p.playable_item_id
WHERE l.lifecycle_status = 'active';
"""

POSTGRES_PLAYABLE_INVALIDATION_REASONS_V15_SQL = """
UPDATE playable_item_lifecycle
SET invalidation_reason = 'qualification_not_exportable'
WHERE lifecycle_status = 'invalidated' AND invalidation_reason IS NULL;

ALTER TABLE playable_item_lifecycle
    DROP CONSTRAINT IF EXISTS playable_item_lifecycle_invalidation_consistency;

ALTER TABLE playable_item_lifecycle
    ADD CONSTRAINT playable_item_lifecycle_invalidation_consistency
    CHECK (
        (
            lifecycle_status = 'active'
            AND invalidated_run_id IS NULL
            AND invalidation_reason IS NULL
        )
        OR
        (
            lifecycle_status = 'invalidated'
            AND invalidated_run_id IS NOT NULL
            AND invalidation_reason IN (
                'qualification_not_exportable',
                'canonical_taxon_not_active',
                'source_record_removed',
                'policy_filtered'
            )
        )
    );

CREATE INDEX IF NOT EXISTS idx_playable_item_lifecycle_status_reason_run
    ON playable_item_lifecycle (lifecycle_status, invalidation_reason, invalidated_run_id);
"""

POSTGRES_REFERENCED_TAXA_V16_SQL = """
CREATE TABLE IF NOT EXISTS referenced_taxa (
    referenced_taxon_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_taxon_id TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    preferred_common_name TEXT,
    common_names_i18n_json TEXT NOT NULL,
    rank TEXT,
    taxon_group TEXT NOT NULL,
    mapping_status TEXT NOT NULL CHECK (
        mapping_status IN (
            'mapped',
            'auto_referenced_high_confidence',
            'auto_referenced_low_confidence',
            'ambiguous',
            'ignored'
        )
    ),
    mapped_canonical_taxon_id TEXT,
    reason_codes_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_json TEXT NOT NULL,
    UNIQUE (source, source_taxon_id),
    FOREIGN KEY (mapped_canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id),
    CONSTRAINT referenced_taxa_mapped_canonical_consistency
        CHECK (
            (mapping_status = 'mapped' AND mapped_canonical_taxon_id IS NOT NULL)
            OR
            (mapping_status <> 'mapped' AND mapped_canonical_taxon_id IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_referenced_taxa_mapping_status
    ON referenced_taxa (mapping_status, source, source_taxon_id);

CREATE TABLE IF NOT EXISTS referenced_taxon_events (
    referenced_taxon_event_id TEXT PRIMARY KEY,
    referenced_taxon_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_taxon_id TEXT NOT NULL,
    mapping_status TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (referenced_taxon_id) REFERENCES referenced_taxa (referenced_taxon_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_referenced_taxon_events_reference
    ON referenced_taxon_events (referenced_taxon_id, created_at DESC);
"""
