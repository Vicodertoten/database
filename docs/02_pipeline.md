# Pipeline

The pipeline is deliberately small, versioned, and reproducible.

## 1. Ingest

- either read a tiny local bird fixture or a cached iNaturalist snapshot
- for live harvesting, cache raw observation API responses, taxon detail payloads, and one candidate image per observation
- preserve raw payload references as local artifact paths
- write a versioned snapshot manifest
- apply authority scope for phase 1: iNaturalist is the only auto-creation source for canonical taxa

## 2. Normalize

- resolve source taxon mappings to canonical taxa
- create a new canonical taxon only when an unknown iNaturalist taxon enters scope
- do not auto-create canonical taxa from secondary unresolved hints
- assign stable internal media IDs
- persist normalized objects in PostgreSQL/PostGIS
- write a normalized JSON snapshot
- use measured downloaded image dimensions for qualification decisions

## 3. Enrich canonical taxa

- read only cached local taxon payloads from the snapshot
- populate canonical enrichment fields such as `key_identification_features`
- extract source-side similarity hints when available
- resolve similarity into internal `similar_taxa` only when the target taxon already exists in the canonical seed
- keep unresolved source hints separate from canonical relationships
- never let AI or source hints mutate canonical identity fields directly

## 4. Qualify

- run explicit stages:
  - compliance screening
  - fast semantic screening
  - expert qualification
  - review queue assembly
- enforce image-only scope
- evaluate commercial-safe license policy
- run either fixture AI outputs, cached AI outputs, rules-only mode, or Gemini over cached images
- persist Gemini outputs back into the snapshot cache
- reject uncertain snapshot records automatically in the nominal snapshot flow
- write qualified resources and structured review queue entries

## 5. Optional review overrides

- inspect the structured review queue
- create or update snapshot-scoped overrides in `data/review_overrides/<snapshot_id>.json`
- rerun the pipeline with `--apply-review-overrides`
- replay human decisions without mutating raw snapshot artifacts

## 6. Export

- export only `QualifiedResource` records with `export_eligible = true`
- include only canonical taxa needed by downstream consumers
- keep unresolved external hints out of the public export bundle
- fail on unresolved canonical taxon IDs in exportable resources
- exclude `provisional` taxa from pedagogical export by default
- validate the primary export against `schemas/qualified_resources_bundle_v4.schema.json` before writing
- emit transitional sidecar `export.bundle.v3` only when explicitly requested (`--export-v3-sidecar`)

## Canonical governance guardrails

- `canonical_taxon_id` is immutable and concept-based, not name-based
- accepted scientific names and synonyms can evolve without ID changes
- split/merge/replacement transitions are explicit and never silently rewrite history
- ambiguous canonical transitions are routed into a dedicated operator queue
- deprecated taxa are preserved for traceability and reject new asset attachment
- canonical policy reference: `docs/06_charte_canonique_v1.md`

## 7. Inspect

- provide summary counts
- list exportable resources
- list review queue items with filters
- report snapshot health for cached iNaturalist snapshots
- expose playable corpus payload (`playable_corpus.v1`) with canonical/pedagogy/geo/date filters

## 8. Build playable corpus (Gate 2)

- derive `PlayableItem` rows from current run outputs (`canonical_taxa`, `observations`, `media_assets`, `qualified_resources`)
- include only exportable resources (`export_eligible = true`)
- materialize feedback blocks for runtime-facing consumption:
  - `what_to_look_at_specific` from qualified visible parts
  - `what_to_look_at_general` from canonical key identification features
  - `confusion_hint` from resolved similar canonical taxa when available
- persist living surface in Postgres (`playable_items`) and append immutable snapshots in `playable_items_history`
- keep contract isolation:
  - `export.bundle.v4` remains unchanged
  - no runtime/session/scoring/progression logic in this stage

## 9. Manage packs and diagnostics (Gate 3)

- persist durable pack specs with immutable revisions (`pack_id + revision`)
- allow pack creation even when not compilable
- run deterministic diagnostics against current `playable_items` only
- persist each diagnostic attempt with measured deficits and reason code
- keep strict boundaries:
  - no `compiled_pack_builds` and no `pack_materializations` at this gate
  - no enrichment queue or confusions runtime ingestion at this gate
  - no runtime/session/scoring/progression logic

## 10. Compile and materialize packs (Gate 4)

- compile a pack revision deterministically from `playable_items`
- enforce question validity:
  - one target playable item
  - exactly three distractors
  - distractor taxa all distinct and different from the target taxon
- persist each compiled build in `compiled_pack_builds` (`pack.compiled.v1`)
- create optional frozen snapshots in `pack_materializations` (`pack.materialization.v1`)
- keep strict boundaries:
  - no queue d’enrichissement (Gate 5+) in this stage
  - no runtime/session/scoring/progression logic
  - no change to `export.bundle.v4`

## Versioning

Generated artifacts carry explicit stage versions:

- `schema_version`
- `manifest_version`
- `normalized_snapshot_version`
- `enrichment_version`
- `qualification_version`
- `export_version`
- `playable_corpus_version`

The current writers always emit snapshot manifests as `inaturalist.snapshot.v3`.
Legacy manifests without `manifest_version` are rejected.
Unknown manifest versions are rejected explicitly.
