---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/foundation/runtime-contract-stack-v1.md
scope: runtime_contract_stack
---

# Runtime Contract Stack V1

This document is the canonical source of truth for active, fallback, owner-only,
historical, and forbidden runtime-facing contract surfaces across `database` and
`runtime-app`.

## Current Stack

`runtime-app` starts quiz sessions from owner-produced local artifacts. The
active playable runtime contract is `session_snapshot.v2`, generated from a
validated local `serving_bundle.v1` or loaded from frozen regression fixtures.
`golden_pack.v1` remains available only as the fallback runtime contract when
Dynamic Pack mode is disabled or unavailable.

Runtime never reads owner raw data, owner Postgres, live external providers, or
audit evidence as quiz input. Runtime may select among already provided
bundle/snapshot data, persist session state, score answers by `selectedOptionId`,
and export answer signals back to `database`.

## Contract Truth Table

| Contract or surface | Owner | Consumer | Purpose | Status | Source schema | Runtime eligibility | Deprecation status |
|---|---|---|---|---|---|---|---|
| `session_snapshot.v2` | `database` | `runtime-app` | Frozen playable quiz session with questions, media, option order, labels, correctness, feedback, and distractor metadata. | Active runtime | `database/schemas/session_snapshot_v2.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/session_snapshot_v2.schema.json` | Current playable runtime contract. | Stable for current Dynamic Pack runtime. |
| `serving_bundle.v1` | `database` | `runtime-app` | Local serving-ready bundle used by runtime to generate a fresh `session_snapshot.v2` at session start. | Active runtime input | `database/schemas/serving_bundle_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/serving_bundle_v1.schema.json` | Runtime may consume locally and project into `session_snapshot.v2`; it must not derive missing owner semantics. | Stable active input. |
| `golden_pack.v1` | `database` | `runtime-app` | Promoted artifact-only Golden Pack quiz payload. | Runtime fallback | `database/schemas/golden_pack_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/golden_pack_v1.schema.json` | Fallback only when Dynamic Pack mode is disabled or unavailable. | Retained until Dynamic Pack fallback is no longer needed. |
| `pack_pool.v1` | `database` | `database` | Owner-side dynamic source pool used to build serving bundles and session snapshots. | Owner-only | `database/schemas/pack_pool_v1.schema.json` | Runtime must not consume directly. | Active owner-side surface. |
| `runtime_answer_signals.v1` | `runtime-app` | `database` | Batch export of answered runtime questions for owner confusion ingestion and aggregate learning signals. | Runtime-to-owner handback | `database/schemas/runtime_answer_signals_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/runtime_answer_signals_v1.schema.json` | Runtime writes/exports; not a quiz input. | Active handback surface. |
| `playable_corpus.v1` | `database` | Historical owner-read consumers | Owner-prepared playable item corpus with minimal player-ready metadata. | Historical / strategic-later | `database/schemas/playable_corpus_v1.schema.json` | Not a current runtime target. | Kept for lineage and older owner-read context. |
| `pack.compiled.v1` | `database` | Historical owner-read consumers | Deterministic compiled pack build. | Historical / strategic-later | `database/schemas/pack_compiled_v1.schema.json` | Not a current runtime target. | Kept for lineage and older owner-read context. |
| `pack.materialization.v1` | `database` | Historical owner-read consumers | Frozen materialization derived from a compiled v1 build. | Historical / strategic-later | `database/schemas/pack_materialization_v1.schema.json` | Not a current runtime target. | Kept for lineage and older owner-read context. |
| `pack.compiled.v2` | `database` | `database` reference docs/tests | Historical `QuestionOption[]` semantics reference. | Historical / strategic-later | `database/schemas/pack_compiled_v2.schema.json` | Not a current runtime target. | Do not use as the Dynamic Pack runtime handoff. |
| `pack.materialization.v2` | `database` | `database` reference docs/tests | Historical `QuestionOption[]` semantics reference and baseline audit artifact family. | Historical / strategic-later | `database/schemas/pack_materialization_v2.schema.json` | Not a current runtime target. | Superseded by `session_snapshot.v2` for playable dynamic runtime handoff. |
| Owner-side runtime-read HTTP surfaces | `database` | Historical owner-read consumers | Private HTTP read endpoints for `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1`. | Historical / strategic-later | Underlying v1 schemas above | Not a current runtime target. | Keep only as bounded historical/operator context unless explicitly reopened. |

## Forbidden Runtime Inputs

`runtime-app` must not use these as quiz input:

- `export.bundle.v4`
- owner Postgres or owner internal tables
- owner raw data, run directories, audit evidence, apply plans, or unresolved candidates
- `manifest.json` and `validation_report.json`
- live iNaturalist, Gemini, or other enrichment providers
- `pack_pool.v1` directly
- owner-side runtime-read HTTP surfaces unless a future decision explicitly reopens them

## Operational Rules

- `database` remains the source of truth for contract schemas and semantics.
- `runtime-app` mirrors schemas needed for local validation and TypeScript types.
- Runtime may assemble sessions, persist state, score submitted option ids, and
  export answer signals.
- Runtime must not invent labels, replace distractors, map taxa, recalculate
  media policy, generate feedback, or repair owner data.
- Historical references to `pack.materialization.v2` or owner-read surfaces are
  allowed only when clearly marked historical, owner-only, or strategic-later.
