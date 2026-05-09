---
owner: database
status: stable
last_reviewed: 2026-05-09
source_of_truth: docs/runbooks/dynamic-pack-phase-0-plan.md
scope: dynamic_pack_phase_0_alignment
---

# Dynamic Pack Phase 0 Plan

## Purpose

Phase 0 prepares the post-`golden_pack.v1` transition without implementing
product code, migrations, runtime changes, or new APIs.

The goal is documentation alignment: the current MVP handoff remains
`golden_pack.v1`, while the post-MVP direction is a dynamic pack pool with
session snapshots, fixed daily challenges, fixed institutional assignments, and
runtime signal batches.

Phase 0 exit criteria were met on `2026-05-09`; Phase 1 now owns the corpus
gate baseline and audit-only preparation for dynamic packs.

## Locked Decisions

- Phase 0 is docs-only plus executable checklist.
- `database` remains the inter-repo source of truth.
- `runtime-app` is not modified in Phase 0.
- Future contract names remain candidates until Phase 2 implementation:
  - `pack_pool.v1`
  - `session_snapshot.v1`
  - `fixed_challenge.v1`
  - `assignment_materialization.v1`
  - `runtime_signal_batch.v1`
- `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1` are
  legacy / strategic-later surfaces, not the current runtime target.
- Daily challenge uses the same questions, images, and options for all users,
  with runtime display localized to the fixed session locale (`fr`, `en`, `nl`).

## Checklist

### Documentation Alignment

- `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md` points to this Phase 0
  runbook.
- `docs/architecture/MASTER_REFERENCE.md` stays MVP-focused and points to the
  dynamic roadmap for the post-MVP direction.
- `docs/foundation/runtime-consumption-v1.md` documents the post-MVP direction
  without redefining contracts.
- `docs/runbooks/v0.1-scope.md` marks old owner-side serving surfaces as
  historical / strategic-later, not current runtime target.
- `docs/runbooks/execution-plan.md` states that the next target is dynamic pack
  pool + session snapshot, not a direct revival of older surfaces.
- `README.md` and `docs/README.md` point to the dynamic roadmap and this runbook.

### Hygiene

- Forbidden `.DS_Store` files are removed from `docs/`.
- `docs/runbooks/golden-pack-v1-runtime-handoff.md` has required front matter.
- Documentation hygiene passes.

### Exit Criteria

- `python scripts/check_docs_hygiene.py` passes.
- `git diff --check` passes.
- No source code, migration, schema, runtime, API, or generated contract files are
  changed.
- Active docs no longer present `playable_corpus.v1`, `pack.compiled.v1`, or
  `pack.materialization.v1` as the current runtime target.
- `golden_pack.v1` remains clearly documented as the current MVP runtime handoff.
- The dynamic roadmap remains vision; this runbook is the execution checklist.

## Phase 1 / Phase 2 Open Questions

- Which future contract names become stable during Phase 2?
- Should dynamic pack pools be exported as artifacts, served from Postgres, or both?
- What are the minimum FR/EN/NL readiness thresholds for dynamic serving?
- When is `DistractorRelationship` persistence safe enough to enable?
- Should `referenced_only` be disabled by default for institutional assignments?
- Which account/auth provider should be used before durable personalization?
