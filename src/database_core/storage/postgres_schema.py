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
