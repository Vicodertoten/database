# Open Questions

- Internal taxon IDs are stable slugs in this MVP. A stricter long-term governance rule is still needed for future taxonomic splits and merges.
- The current live snapshot path is manual and local-first. The next iteration should decide whether harvested snapshots need a stricter naming/versioning convention beyond operator-provided `snapshot_id`.
- Observation and media licenses are tracked separately, but the current export rule is conservative: export requires a commercially safe result at the qualified resource level. If downstream export omits some observation fields, that rule may later be relaxed with explicit legal review.
- The automatic flow now rejects uncertain records instead of requiring human review. If yield is too low on real snapshots, the next choice is whether to relax thresholds slightly or reintroduce a lightweight override path.
- The snapshot cache now stores one AI result per media item. If prompts evolve, a stricter prompt/version migration policy may be needed so old and new caches do not get mixed accidentally.
