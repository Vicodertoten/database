---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/foundation/pipeline.md
scope: foundation
---

# Pipeline

The pipeline is deliberately small, versioned, and reproducible.

Post-Gate 9 note:

Gate 0 to Gate 9 are implemented and operational. Playable persistence now uses a cumulative incremental lifecycle with explicit invalidation while preserving `playable_corpus.v1` as a stable serving contract.

Corrective strategic alignment (Gate 4.5): contracts stayed stable while the sequencing was tightened before opening new structural workstreams.

Runtime contract boundary (2026-05-10):

- `session_snapshot.v2` is the active playable runtime contract.
- `serving_bundle.v1` is the active local input used to generate sessions.
- `golden_pack.v1` remains the runtime fallback contract.
- The Gate 8-10 playable/pack/compiled/materialization pipeline remains valid
  database infrastructure and historical context, but it is not the active
  runtime contract.
- `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`, and the
  planned `pack.compiled.v2`/`pack.materialization.v2` family are legacy /
  historical / strategic-later for runtime handoff.
- Runtime consumes local `serving_bundle.v1` / `session_snapshot.v2` artifacts,
  with local Golden Pack `pack.json` as fallback; it does not fetch owner-side
  HTTP surfaces, choose distractors, resolve labels, or map taxa.

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

Controlled promotion rule:

- source-side similar species hints may be promoted to internal similarity indexes when canonical target taxa already exist.
- any future automatic canonical creation path remains constrained by canonical governance rules.
- external sources feed the system but do not define internal identity freely.

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

## Canonical governance guardrails

- `canonical_taxon_id` is immutable and concept-based, not name-based
- accepted scientific names and synonyms can evolve without ID changes
- split/merge/replacement transitions are explicit and never silently rewrite history
- ambiguous canonical transitions are routed into a dedicated operator queue
- deprecated taxa are preserved for traceability and reject new asset attachment
- canonical policy reference: `docs/foundation/canonical-charter-v1.md`

## 7. Inspect

- provide summary counts
- list exportable resources
- list review queue items with filters
- report snapshot health for cached iNaturalist snapshots
- expose playable corpus payload (`playable_corpus.v1`) with canonical/pedagogy/geo/date filters

## 8. Build playable corpus (Gate 2)

MVP status: non-MVP / legacy context for the Golden Pack handoff. This gate can
remain a database input and operational serving surface, but `playable_corpus.v1`
is not the first UI/UX smoke-test payload.

- derive `PlayableItem` rows from current run outputs (`canonical_taxa`, `observations`, `media_assets`, `qualified_resources`)
- include only exportable resources (`export_eligible = true`)
- materialize feedback blocks for runtime-facing consumption:
  - `what_to_look_at_specific` from qualified visible parts
  - `what_to_look_at_general` from canonical key identification features
  - `confusion_hint` from resolved similar canonical taxa when available
- current persistence: durable serving payload in `playable_items`, lifecycle state in `playable_item_lifecycle`, plus immutable snapshots in `playable_items_history`
- current contract behavior: `playable_corpus_v1` serves only lifecycle-active rows
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

Status: legacy / historical / strategic-later for runtime handoff.
`golden_pack.v1` is a separate artifact-only export contract and must not be
treated as a rename of `pack.materialization.v1`.

- compile a pack revision deterministically from `playable_items`
- enforce question validity:
  - one target playable item
  - exactly three distractors
  - distractor taxa all distinct and different from the target taxon
- persist each compiled build in `compiled_pack_builds` (`pack.compiled.v1`)
- keep historical compiled builds for traceability and reproducibility
- create optional frozen snapshots in `pack_materializations` (`pack.materialization.v1`)
- materializations are immutable snapshots by design
- keep strict boundaries:
  - no queue d’enrichissement (Gate 6+) in this stage
  - no runtime/session/scoring/progression logic
  - no change to `export.bundle.v4`

Historical Phase 3 v2 extension:

Status: historical / strategic-later context. `pack.compiled.v2` and
`pack.materialization.v2` remain useful surfaces, but they are not the active
runtime handoff.

- `pack.compiled.v2` and `pack.materialization.v2` replace playable-item distractor slots with `QuestionOption[]`
- the target remains a playable item from the pack
- distractors become taxon options selected from a governed pool and may be out-of-pack
- distractors may be referenced-only high-confidence taxa without media or playable item
- materialization v2 freezes option labels, sources, scores, and reason codes
- compilation remains deterministic and does not call live external sources
- runtime continues to own sessions, submissions, scoring, progression, and UX only

## 11. Manage asynchronous enrichment

- persist non-compilable pack remediation requests in `enrichment_requests`
- persist resource-level remediation targets in `enrichment_request_targets`
- persist execution attempts and outcomes in `enrichment_executions`
- keep enrichment asynchronous and traceable rather than inlining external work into compilation

## 12. Ingest confusion batches and recompute aggregates

- ingest runtime-originated confusion batches without importing runtime session state
- persist one directed event per confusion pair observation
- recompute global directed aggregates in an operator-driven manner
- keep confusion data as a strategic signal layer, not a real-time scoring engine

## 13. Standing strategic corrections

- maintain explicit invalidation reason precision and lifecycle explainability for operators (inspect includes playable invalidations by run/cause)
- reduce `PostgresRepository` responsibility concentration without breaking existing contracts
- extend multilingual naming and editorial quality before broad public use

See `docs/runbooks/audit-reference.md` for priority, order of execution, and expected acceptance criteria for these corrections.

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
