from database_core.versioning import SCHEMA_VERSION

SCHEMA_SQL = f"""
PRAGMA foreign_keys = ON;

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
    bird_scope_compatible INTEGER NOT NULL,
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
    created_at TEXT NOT NULL,
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
    effective_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
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
    effective_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_change_events_run
    ON canonical_change_events (run_id, canonical_taxon_id, event_type);

CREATE TABLE IF NOT EXISTS canonical_taxon_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    source_mode TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    snapshot_id TEXT,
    schema_version TEXT NOT NULL,
    qualification_version TEXT NOT NULL,
    enrichment_version TEXT NOT NULL,
    export_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    run_status TEXT NOT NULL
);

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
    effective_at TEXT NOT NULL,
    decision_status TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS canonical_governance_review_queue (
    governance_review_item_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    governance_event_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    review_note TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id),
    FOREIGN KEY (governance_event_id) REFERENCES canonical_governance_events (governance_event_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_governance_review_queue_status
    ON canonical_governance_review_queue (review_status, created_at);

CREATE TABLE IF NOT EXISTS source_observations (
    observation_uid TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    source_taxon_id TEXT NOT NULL,
    observed_at TEXT,
    location_json TEXT NOT NULL,
    source_quality_json TEXT NOT NULL,
    raw_payload_ref TEXT NOT NULL,
    canonical_taxon_id TEXT,
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_source_observations_source_external
    ON source_observations (source_name, source_observation_id);

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
    uncertainty_reason TEXT NOT NULL,
    qualification_notes TEXT,
    qualification_flags_json TEXT NOT NULL,
    provenance_summary_json TEXT NOT NULL,
    license_safety_result TEXT NOT NULL,
    export_eligible INTEGER NOT NULL,
    ai_confidence REAL,
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
    created_at TEXT NOT NULL,
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id),
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);

PRAGMA user_version = {SCHEMA_VERSION};
"""
