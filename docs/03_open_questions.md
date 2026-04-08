# Open Questions

- Internal taxon IDs are stable slugs in this MVP. A stricter long-term governance rule is still needed for future taxonomic splits, merges, and synonym management.
- `key_identification_features` now exists in the canonical model, but the long-term source of truth is still open. The next decision is whether these features remain manually curated, source-assisted, or partly AI-assisted with review.
- The review override workflow is now explicit and replayable, but the right operational thresholds are still unknown. A larger live smoke is needed to understand whether the current reject-first policy yields enough accepted resources.
- Canonical similarity is now represented cleanly, but the future relation taxonomy is still open. The next extension may need to distinguish look-alike distractors, educational confusions, and taxonomy-neighbor relations instead of only `similar_species`.
- The repo is still birds-only. The multi-group prompt supplements and canonical field policy for future taxa remain open until the birds pipeline is exercised on a wider live sample.
