---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/runbooks/open-questions.md
scope: runbook
---

# Open Questions

Last update: `2026-04-12`

Questions closed by canonical charter v1:

- canonical identity is no longer slug-based; it is now governed by immutable concept IDs (`taxon:<group>:<padded_integer>`)
- `key_identification_features` is now explicitly non-identitary enrichment with required provenance
- canonical similarity taxonomy is now defined (`taxonomic_neighbor`, `visual_lookalike`, `educational_confusion`)
- canonical authority is now explicit for phase 1 birds (`iNaturalist`)
- AI canonical governance scope is now explicit (AI enriches, AI does not govern)
- canonical ID migration hard cutover is complete (mapping in `docs/foundation/canonical-id-migration-v1.md`)
- no transitional legacy-read window is maintained in v1
- invalidation reason taxonomy for incremental playable lifecycle is now implemented with explicit v1 codes (`qualification_not_exportable`, `canonical_taxon_not_active`, `source_record_removed`, `policy_filtered`) and a backward-compatible serving contract (`playable_corpus.v1`)

Active open questions:

- Target decomposition plan for `PostgresRepository`: extraction order, compatibility strategy, and minimum acceptable end-state.
- Multilingual naming governance for pedagogical serving (`fr`, `en`, `nl`): extraction path is now implemented, but source-of-truth hierarchy, editorial ownership, and quality thresholds remain open.
- Second-source and future authority strategy beyond phase-1 iNaturalist: sequence, governance rules, and conflict resolution policy.
- How confusion aggregates should influence future pedagogical policies without leaking runtime adaptation logic into `database`.
- Operator thresholds for promoting `provisional` taxa to `active` or `deprecated` after manual review.
- Signal extraction depth from raw iNaturalist deltas: current implementation is explicit and deterministic, but still centered on pilot signals (future extension needed for richer taxon-change patterns).
- Canonical governance operator policy after `manual_reviewed`: SLA and escalation path are still open; closure workflow is now implemented in CLI with mandatory note.
- Future pedagogical ontology expansion beyond V1 fields (`diagnostic_feature_visibility`, learning sequencing, distractor planning).
- Multi-group rollout guardrails (after birds): sequence, acceptance criteria, and required updates to prompt supplements and canonical mappings.
