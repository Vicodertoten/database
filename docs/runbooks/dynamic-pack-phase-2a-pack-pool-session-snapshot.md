---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/runbooks/dynamic-pack-phase-2a-pack-pool-session-snapshot.md
scope: runbook
---

# Dynamic Pack Phase 2A - Pack Pool and Session Snapshot

## Scope

Phase 2A created the first owner-side dynamic source pool from the Phase 1
BE+FR corpus gate. `pack_pool.v1` remains active owner-side input;
`session_snapshot.v1` is now a historical target-only proof surface superseded
for runtime play by `session_snapshot.v2`.

Contract status is tracked in `docs/architecture/contract-map.md`.
Internal dynamic compiler concepts are tracked separately in
`docs/foundation/dynamic-session-compiler-internals-v1.md`; Phase 2A product
constants such as BE+FR, `fr`/`en`/`nl`, and `20` questions are materialization
inputs, not generic domain model constraints.

## Closure Status

Status: done / historical active reference.

Phase 2A is closed as an execution phase. Its durable output, `pack_pool.v1`,
remains the active owner-side dynamic source pool. Its target-only
`session_snapshot.v1` fixtures are historical proof artifacts and are not a
current playable runtime contract. Runtime play uses `session_snapshot.v2`, or
generated `session_snapshot.v2` projected from `serving_bundle.v1`.

Included:

- `pack_pool.v1`
- `session_snapshot.v1`
- Postgres persistence in the isolated Phase 1 schema
- JSON fixtures for runtime handoff tests

Excluded:

- promotion to `public`
- auth or durable personalization
- `fixed_challenge.v1`
- `assignment_materialization.v1`
- advanced distractor generation
- Gemini calls

## Database Safety

Use only `PHASE1_DATABASE_URL` with:

```text
options=-csearch_path=phase1_be_fr_20260509,public
```

Do not use `DATABASE_URL` against `public` for Phase 2A writes.

## Nominal Commands

Migrate the isolated schema to the Phase 2A schema version:

```bash
python scripts/migrate_database.py --database-url "$PHASE1_DATABASE_URL"
```

Build the pack pool:

```bash
python scripts/phase2a_dynamic_pack.py \
  --run-id phase2a-be-fr-20260509-v1 \
  build-pool \
  --pool-id pack-pool:be-fr-birds-50:v1 \
  --source-run-id run:20260509T142438Z:dcbc37c1
```

Build deterministic session fixtures:

```bash
python scripts/phase2a_dynamic_pack.py \
  --run-id phase2a-be-fr-20260509-v1 \
  build-session-fixtures \
  --pool-id pack-pool:be-fr-birds-50:v1 \
  --question-count 20 \
  --seed phase2a-smoke-v1 \
  --locale fr \
  --locale en \
  --locale nl
```

Audit Phase 2A:

```bash
python scripts/phase2a_dynamic_pack.py \
  --run-id phase2a-be-fr-20260509-v1 \
  audit \
  --pool-id pack-pool:be-fr-birds-50:v1
```

## Gate

`GO` requires:

- 50 taxa in the pool
- 50 taxa with at least 20 eligible items
- attribution completeness `1.0`
- media URL completeness `1.0`
- one valid 20-question session for each locale: `fr`, `en`, `nl`

`GO_WITH_WARNINGS` is allowed for internal handoff when labels use the scientific
name fallback. Public release still requires a separate editorial threshold.
