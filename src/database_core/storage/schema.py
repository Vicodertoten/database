SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS canonical_taxa (
    canonical_taxon_id TEXT PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    canonical_rank TEXT NOT NULL,
    common_names_json TEXT NOT NULL,
    bird_scope_compatible INTEGER NOT NULL,
    external_source_mappings_json TEXT NOT NULL,
    similar_taxon_ids_json TEXT NOT NULL
);

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
    qualification_notes TEXT,
    qualification_flags_json TEXT NOT NULL,
    provenance_summary_json TEXT NOT NULL,
    license_safety_result TEXT NOT NULL,
    export_eligible INTEGER NOT NULL,
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id),
    FOREIGN KEY (source_observation_uid) REFERENCES source_observations (observation_uid),
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id)
);

CREATE TABLE IF NOT EXISTS review_queue (
    review_item_id TEXT PRIMARY KEY,
    media_asset_id TEXT NOT NULL,
    canonical_taxon_id TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (media_asset_id) REFERENCES media_assets (media_id),
    FOREIGN KEY (canonical_taxon_id) REFERENCES canonical_taxa (canonical_taxon_id)
);
"""

