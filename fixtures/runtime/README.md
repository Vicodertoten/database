# Runtime Sample Fixtures (INT-003)

## Role

These three files are the official owner-side reference fixtures for runtime v1 local consumption in `runtime-app`:

- `playable_corpus.sample.json`
- `pack_compiled.sample.json`
- `pack_materialization.sample.json`

They are locked by chantier `INT-003` in `database`.

## Fixture policy

- These fixtures are **payloads minimaux valides** (not exhaustive payloads).
- `playable_corpus.sample.json` is a reduced subset of a real `playable_corpus.v1` output.
- `pack_compiled.sample.json` is a real `pack.compiled.v1` output with `question_count=1`.
- `pack_materialization.sample.json` is a real `pack.materialization.v1` output with `question_count=1` and `purpose="daily_challenge"`.
- Scope target is local runtime integration, not product-wide dataset coverage.

## Local assumptions

- `.env` contains a valid `DATABASE_URL`.
- Database schema is migrated to the current version.
- Runtime surfaces already exist or can be produced via the repo CLI.
- `jq` is available locally.

## Regeneration (owner-side, step-by-step)

1. Ensure schema is up to date:

```bash
python scripts/migrate_database.py --database-url "$DATABASE_URL"
```

2. Inspect available playable data:

```bash
python scripts/inspect_database.py playable-corpus --limit 20
```

3. Create or revise a reference pack with real taxa (compilable set):

```bash
python scripts/manage_packs.py create \
  --pack-id pack:int003:runtime-fixtures:v1 \
  --canonical-taxon-id taxon:birds:000019 \
  --canonical-taxon-id taxon:birds:000013 \
  --canonical-taxon-id taxon:birds:000010 \
  --canonical-taxon-id taxon:birds:000009 \
  --canonical-taxon-id taxon:birds:000017 \
  --canonical-taxon-id taxon:birds:000016 \
  --canonical-taxon-id taxon:birds:000020 \
  --canonical-taxon-id taxon:birds:000008 \
  --canonical-taxon-id taxon:birds:000018 \
  --canonical-taxon-id taxon:birds:000015 \
  --difficulty-policy balanced \
  --visibility private \
  --intended-use quiz
```

4. Compile with one question:

```bash
python scripts/manage_packs.py compile \
  --pack-id pack:int003:runtime-fixtures:v1 \
  --revision 2 \
  --question-count 1 \
  > /tmp/int003-pack-compiled.json
```

5. Materialize as `daily_challenge`:

```bash
python scripts/manage_packs.py materialize \
  --pack-id pack:int003:runtime-fixtures:v1 \
  --revision 2 \
  --question-count 1 \
  --purpose daily_challenge \
  --ttl-hours 24 \
  > /tmp/int003-pack-materialization.json
```

6. Build the reduced playable subset (4 required items only):

```bash
python scripts/inspect_database.py playable-corpus > /tmp/int003-playable-full.json
jq --slurpfile compiled /tmp/int003-pack-compiled.json \
  '{schema_version, playable_corpus_version, generated_at, run_id, items: [.items[] | select(.playable_item_id as $id | (([$compiled[0].questions[0].target_playable_item_id] + $compiled[0].questions[0].distractor_playable_item_ids) | index($id)))]}' \
  /tmp/int003-playable-full.json \
  > fixtures/runtime/playable_corpus.sample.json
cp /tmp/int003-pack-compiled.json fixtures/runtime/pack_compiled.sample.json
cp /tmp/int003-pack-materialization.json fixtures/runtime/pack_materialization.sample.json
```

## Validation checklist

```bash
python -m jsonschema -i fixtures/runtime/playable_corpus.sample.json schemas/playable_corpus_v1.schema.json
python -m jsonschema -i fixtures/runtime/pack_compiled.sample.json schemas/pack_compiled_v1.schema.json
python -m jsonschema -i fixtures/runtime/pack_materialization.sample.json schemas/pack_materialization_v1.schema.json
```

Cross-ID coherence:

```bash
comm -3 \
  <(jq -r '[.questions[0].target_playable_item_id] + .questions[0].distractor_playable_item_ids | .[]' fixtures/runtime/pack_compiled.sample.json | sort) \
  <(jq -r '.items[].playable_item_id' fixtures/runtime/playable_corpus.sample.json | sort)
```

Expected output: empty.

## What can be regenerated

- All three sample files can be regenerated from real owner runtime surfaces using the commands above.

## What must not be edited manually

- Do not rename, simplify, or translate any schema field names.
- Do not invent IDs (`playable_item_id`, `canonical_taxon_id`, `build_id`, `materialization_id`, etc.).
- Do not rewrite semantics consumer-side.
- Do not use `export.bundle.v4` as runtime fixture source.
