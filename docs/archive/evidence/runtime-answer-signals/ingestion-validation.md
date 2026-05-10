# Runtime Answer Signals Ingestion Validation

Date: 2026-05-09

Scope:

- input contract: `runtime_answer_signals.v1`
- database schema: `database.schema.v20`
- command: `database-core confusion ingest-runtime-signals`

Implemented flow:

```text
runtime_answer_signals.v1
  -> confusion_batches metadata
  -> incorrect answers only as confusion_events
  -> confusion_aggregates_global by selected/correct/locale/source
```

Validation status:

- owner schema mirrors `runtime_answer_signals.v1`;
- CLI validates the batch against the JSON Schema before ingestion;
- correct answers are counted in `skipped_correct_count`;
- incorrect answers preserve runtime session, question position, snapshot,
  pool, locale, seed, selected option, selected option source, and option source
  JSON;
- duplicate `batch_id` ingestion returns a no-op result;
- aggregate recompute groups by `taxon_confused_for_id`,
  `taxon_correct_id`, `locale`, and `distractor_source`.

Real Postgres validation:

- blocked locally because the configured runtime Supabase hostname did not
  resolve: `getaddrinfo ENOTFOUND db.xswpeuxipdhowyfyqzum.supabase.co`.
