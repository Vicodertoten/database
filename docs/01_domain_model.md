# Domain Model

## CanonicalTaxon

Internal taxon identity. Upstream identifiers are mappings, not product identity.
Normative reference: `docs/06_charte_canonique_v1.md`.

Canonical v1 target structure:

Identity core (stable):

- `canonical_taxon_id` (immutable concept ID, target format `taxon:<group>:<padded_integer>`)
- `taxon_group`
- `canonical_rank`
- `taxon_status` (`active`, `deprecated`, `provisional`)

Current taxonomy layer:

- `accepted_scientific_name`
- `synonyms[]`
- `common_names[]`
- `authority_source`
- `external_source_mappings[]`

Derived enrichment layer (non-identitary):

- `display_slug`
- `key_identification_features`
- `external_similarity_hints`
- `similar_taxa`
- `similar_taxon_ids` (derived index for consumers)

Implementation note (2026-04-08):

- canonical v1 hard cutover is implemented
- legacy slug-style IDs and legacy `scientific_name` canonical field are removed from the active contract
- ID migration mapping is documented in `docs/07_canonical_id_migration_v1.md`
- governance implementation tracking is maintained in `docs/05_audit_reference.md` tasks `CAN-01` to `CAN-12`

## SourceObservation

Traceable upstream observation record.

Fields:

- source name
- source observation ID
- source taxon ID
- observed timestamp when known
- minimal location metadata
- source quality metadata
- raw payload reference
- resolved canonical taxon link when available

## MediaAsset

Source media attached to an observation.

Fields:

- stable internal media ID
- source name
- source media ID
- media type
- source URL
- attribution
- author
- license
- MIME type and extension when known
- basic dimensions when known
- checksum placeholder
- linked observation
- linked canonical taxon when resolved

## QualifiedResource

Derived resource that is explicitly judged usable or not usable for pedagogical reuse.

Fields:

- stable qualified resource ID
- canonical taxon ID
- source observation reference
- media asset ID
- qualification status
- qualification version
- technical quality
- pedagogical quality
- life stage
- sex
- visible parts
- view angle
- notes and flags
- provenance summary
- license safety result
- export eligibility

Qualification stays explicit. Unknown and review-required are first-class outcomes.

## PlayableItem (Gate 2)

Derived, queryable runtime-facing item persisted in database (without runtime session logic).

Fields:

- stable `playable_item_id` (derived from qualified resource)
- run lineage (`run_id`, `qualified_resource_id`)
- canonical and media links (`canonical_taxon_id`, `media_asset_id`, source refs)
- taxon display (`scientific_name`, `common_names_i18n` with mandatory `fr`/`en`/`nl` keys)
- pedagogical signals (`difficulty_level`, `media_role`, `learning_suitability`, `confusion_relevance`, `diagnostic_feature_visibility`)
- canonical similarity projection (`similar_taxon_ids`)
- feedback blocks (`what_to_look_at_specific`, `what_to_look_at_general`, `confusion_hint`)
- geo/date facets (`country_code`, `observed_at`, `location_point`, `location_bbox`, `location_radius_meters`)

Rules:

- playable v1 is fed only from exportable qualified resources (`export_eligible=true`)
- `common_names_i18n` is extensible; current bootstrap maps existing names to `en` and initializes `fr`/`nl` as empty arrays
- playable is additive and does not replace `CanonicalTaxon`, `QualifiedResource`, or `export.bundle.v4`

## PackSpec / PackRevision / PackCompilationAttempt (Gate 3)

Pack layer is durable and versioned, without runtime session logic.

PackSpec:

- stable `pack_id`
- pointer to `latest_revision`

PackRevision (immutable):

- `(pack_id, revision)` is unique and append-only
- parameters include:
  - `canonical_taxon_ids`
  - `difficulty_policy` (`easy|balanced|hard|mixed`)
  - one optional geo form (`country_code` or `bbox` or `point+radius`)
  - `observed_from` / `observed_to` (UTC inclusive bounds)
  - `owner_id`, `org_id`, `visibility`, `intended_use`
- every change creates `revision +1`

PackCompilationAttempt (deterministic diagnosis):

- persisted trace of one diagnostic execution for a pack revision
- includes `compilable`, `reason_code`, measured metrics, deficits, and blocking taxa
- no external calls and no runtime/session/scoring/progression side effects
