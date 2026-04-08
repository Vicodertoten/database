# Open Questions

Last update: `2026-04-08`

Questions closed by canonical charter v1:

- canonical identity is no longer slug-based; it is now governed by immutable concept IDs (`taxon:<group>:<padded_integer>`)
- `key_identification_features` is now explicitly non-identitary enrichment with required provenance
- canonical similarity taxonomy is now defined (`taxonomic_neighbor`, `visual_lookalike`, `educational_confusion`)
- canonical authority is now explicit for phase 1 birds (`iNaturalist`)
- AI canonical governance scope is now explicit (AI enriches, AI does not govern)
- canonical ID migration hard cutover is complete (mapping in `docs/07_canonical_id_migration_v1.md`)
- no transitional legacy-read window is maintained in v1

Active open questions:

- Operator thresholds for promoting `provisional` taxa to `active` or `deprecated` after manual review.
- Signal extraction depth from raw iNaturalist deltas: current implementation is explicit and deterministic, but still centered on pilot signals (future extension needed for richer taxon-change patterns).
- Canonical governance operator policy after `manual_reviewed`: SLA and escalation path are still open; closure workflow is now implemented in CLI with mandatory note.
- Downstream migration completion plan for ending `v3` sidecar after the two-release transition window.
- Future pedagogical ontology expansion beyond V1 fields (`diagnostic_feature_visibility`, learning sequencing, distractor planning).
- Multi-group rollout guardrails (after birds): sequence, acceptance criteria, and required updates to prompt supplements and canonical mappings.
