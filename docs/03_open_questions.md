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

- Exact operational signals used to classify iNaturalist taxonomic changes as "clear" versus "ambiguous" for automatic `deprecated` vs `provisional`.
- Operator thresholds for promoting `provisional` taxa to `active` or `deprecated` after manual review.
- Multi-group rollout guardrails (after birds): sequence, acceptance criteria, and required updates to prompt supplements and canonical mappings.
