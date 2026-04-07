# Open Questions

- Internal taxon IDs are stable slugs in this MVP. A stricter long-term governance rule is still needed for future taxonomic splits and merges.
- The current live snapshot path is manual and local-first. The next iteration should decide whether harvested snapshots need a stricter naming/versioning convention beyond operator-provided `snapshot_id`.
- Qualification can run against cached images with stable Gemini, but live AI outputs are not yet persisted back into the snapshot cache. If reproducible AI review is required, a cached `ai_outputs.json` write-back step should be added deliberately.
- Observation and media licenses are tracked separately, but the current export rule is conservative: export requires a commercially safe result at the qualified resource level. If downstream export omits some observation fields, that rule may later be relaxed with explicit legal review.
- The current inspection commands assume the SQLite database corresponds to the snapshot being inspected. If multiple snapshots need to coexist operationally, snapshot-scoped output locations or a metadata table should be added.
