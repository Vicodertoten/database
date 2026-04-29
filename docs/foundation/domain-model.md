---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/foundation/domain-model.md
scope: foundation
---

# Domain Model

Post-Gate 9 note:

Gate 0 to Gate 9 delivered a valid operational backbone for canonical, qualification, playable, packs, compilation, materialization, enrichment queue, and confusion aggregates. The playable lifecycle correction is now implemented: persistence is cumulative incremental with explicit `active`/`invalidated` status.

Gate 4.5 migration framing:

- keep contracts stable while correcting structural drifts
- treat `PostgresRepository` decomposition as a dedicated controlled workstream

## CanonicalTaxon

Internal taxon identity. Upstream identifiers are mappings, not product identity.
Normative reference: `docs/foundation/canonical-charter-v1.md`.

Canonical v1 structure:

Identity core (stable):

- `canonical_taxon_id` (immutable concept ID, target format `taxon:<group>:<padded_integer>`)
- `taxon_group`
- `canonical_rank`
- `taxon_status` (`active`, `deprecated`, `provisional`)

Taxonomy layer:

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
- ID migration mapping is documented in `docs/foundation/canonical-id-migration-v1.md`
- governance implementation tracking is maintained in `docs/runbooks/audit-reference.md` tasks `CAN-01` to `CAN-12`

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

Persistence posture:

- `playable_items` stores durable serving payload rows keyed by `playable_item_id`
- `playable_item_lifecycle` carries `active`/`invalidated` state and invalidation metadata per item
- `playable_items_history` preserves immutable run snapshots for traceability
- `playable_corpus.v1` serves only currently active items

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
- playable does not replace `CanonicalTaxon`, `QualifiedResource`, or `export.bundle.v4`
- invalidation reason taxonomy is explicit in v1 (`qualification_not_exportable`, `canonical_taxon_not_active`, `source_record_removed`, `policy_filtered`) and can be refined without breaking `playable_corpus.v1`

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

## CompiledPackBuild / PackMaterialization (Gate 4)

CompiledPackBuild (`pack.compiled.v1`, current):

- dynamic build computed from current `playable_items` + one pack revision
- deterministic question set:
  - one target playable item
  - exactly 3 distractors
  - distractor taxa distinct from each other and from target taxon
- persisted with build traceability (`build_id`, `pack_id`, `revision`, `built_at`, `source_run_id`)
- historical builds are kept and queryable for audit and operational reproducibility

PackMaterialization (`pack.materialization.v1`, current):

- frozen snapshot derived from one compiled build (`source_build_id`)
- immutable question payload (targets + distractors exacts)
- purpose-constrained:
  - `assignment`: no TTL, no expiration
  - `daily_challenge`: positive TTL and computed `expires_at`
- immutable once written; later compiled builds do not retroactively mutate old materializations
- materialization persistence is still in `database` scope; no runtime/session/scoring/progression object is introduced here

Planned Phase 3 contracts (`pack.compiled.v2`, `pack.materialization.v2`):

- target remains a `PlayableItem` and keeps `target_playable_item_id`
- options become `QuestionOption[]` snapshots
- each `QuestionOption` carries `option_id`, `canonical_taxon_id`, `taxon_label`, `is_correct`, optional `playable_item_id`, `source`, optional `score`, `reason_codes`, and optional `referenced_only`
- distractors are taxon options and may be out-of-pack
- distractors may have no playable item and no media
- materialization v2 freezes displayed option labels, scores, sources, and reason codes
- runtime consumes displayed options and submits `selectedOptionId`; it does not resolve labels, score distractors, or map external similar species
- v1 remains the legacy compatibility family until consumers no longer require `distractor_playable_item_ids`

## EnrichmentRequest / EnrichmentExecution (Gate 6)

Asynchronous remediation layer for non-compilable packs.

EnrichmentRequest:

- durable request keyed by pack revision and reason code
- lifecycle status (`pending`, `in_progress`, `completed`, `failed`)
- target-level traceability through `EnrichmentRequestTarget`

EnrichmentExecution:

- immutable execution trace attached to one request
- execution outcome (`success`, `partial`, `failed`)
- execution context and optional error information

This layer is intentionally persistence-first: it records what must be enriched,
how it was attempted, and whether recompilation should be retried later.

## ConfusionBatch / ConfusionEvent / ConfusionAggregateGlobal (Gate 7)

Batch-only ingestion of runtime confusion signals without introducing runtime state.

ConfusionBatch:

- durable ingestion unit identified by `batch_id`
- event-count metadata for auditability and idempotent operator workflows

ConfusionEvent:

- directed confusion pair (`taxon_confused_for_id` -> `taxon_correct_id`)
- one observed confusion event with occurrence timestamp

ConfusionAggregateGlobal:

- durable global aggregate by directed canonical pair
- event count plus latest occurrence metadata
- operator-driven recomputation, not real-time runtime adaptation

## Similarity and distractor trajectory (post-Gate 9)

Current state:

- canonical taxa already carry `external_similarity_hints`, `similar_taxa`, and derived `similar_taxon_ids`.
- compiled-pack distractor selection already prioritizes internal similarity when available and falls back deterministically otherwise.

Policy notes:

- iNaturalist similar species hints can be promoted to internal similarity only under controlled rules
- if a hinted target taxon already exists internally, promotion to `similar_taxon_ids` is straightforward and traceable
- if target taxon does not exist, Phase 3 prefers a referenced taxon layer or a strict `referenced_only` status rather than creating active canonical taxa
- external sources can inform the system but can never freely define internal identity
- referenced-only taxa are not active, not playable, and not fully qualified; they can be used only as distractor options when mapping confidence and policy allow it

## Architecture debt callout

`PostgresRepository` currently aggregates too many responsibilities
(storage, diagnostics, compile/materialize orchestration, metrics).
This debt is now explicitly tracked as a dedicated strategic workstream,
but no refactor is launched in this documentation-only cycle.
