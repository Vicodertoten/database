---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/architecture/contract-map.md
scope: contract_status_map
---

# Contract Map

This is the canonical source of truth for the current contract story across
`database` and `runtime-app`.

Read this before older runbooks, ADRs, roadmap sections, schema inventories, or
archive evidence. Older documents may preserve historical implementation details,
but they do not override this map.

## Boundary Summary

- `database` owns truth, lineage, qualification, selection policies, pack pools,
  snapshots, audits, schemas, and exports.
- `database` is not the product backend.
- `runtime-app` consumes owner-produced artifacts.
- Runtime must not derive labels, correctness, distractor semantics, taxonomic
  relationships, feedback, or live content semantics locally.
- `session_snapshot.v2` is a product/runtime contract, not the internal canonical
  domain model.
- `pack_pool.v1` is owner-side, auditable, and not a runtime input.
- `golden_pack.v1` is fallback and regression harness, not the primary dynamic
  runtime path.

## Current Stack

Active now:

- `session_snapshot.v2`: active playable dynamic runtime contract.
- `serving_bundle.v1`: active local runtime input for generated sessions.
- `pack_pool.v1`: active owner-side dynamic source pool.
- `golden_pack.v1`: fallback runtime contract and regression harness.
- `runtime_answer_signals.v1`: active runtime-to-owner handback.

Internal / transitional:

- `playable_corpus.v1`: internal/operator-serving surface, not the current
  runtime target.
- `pack.compiled.v2` and `pack.materialization.v2`: semantic references for
  taxon-based `QuestionOption[]`; not the current dynamic runtime handoff.

Historical / deprecated:

- `pack.compiled.v1`
- `pack.materialization.v1`
- owner-side runtime-read as the default product path

## Contract Truth Table

| Contract / artifact | Status | Owner | Consumer | Purpose | Source-of-truth schema or doc | Runtime role | Stability class | Deprecation / archive path | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `session_snapshot.v1` | Historical | `database` | Historical fixtures / owner tests | Phase 2A target-only session proof surface. | `schemas/session_snapshot_v1.schema.json` | None for current playable runtime. | Legacy stable | Superseded by `session_snapshot.v2`; evidence under `docs/archive/evidence/dynamic-pack-phase-2a/`. | Not playable because options were intentionally deferred. |
| `session_snapshot.v2` | Active | `database` | `runtime-app` | Frozen playable dynamic quiz session with media, labels, options, correctness, feedback, and distractor traces. | `schemas/session_snapshot_v2.schema.json`; runtime mirror in `runtime-app/packages/contracts/schemas-owner/session_snapshot_v2.schema.json`; runbook `docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md` | Primary playable dynamic runtime contract. | Product runtime contract | Future product changes require an explicit new snapshot version. | Runtime scores by snapshotted option id and must not recompute semantics. |
| `serving_bundle.v1` | Active | `database` | `runtime-app` | Serving-ready local bundle containing eligible pool items, labels, media, validated canonical distractor relationships, source scores, and taxonomy fallback profiles. | `schemas/serving_bundle_v1.schema.json`; runtime mirror in `runtime-app/packages/contracts/schemas-owner/serving_bundle_v1.schema.json`; runtime runbook `runtime-app/docs/runbooks/database-integration-v1.md` | Active local runtime input for generated Dynamic Pack sessions. | Product runtime input | Future generated-session input changes require an explicit new serving bundle version. | Runtime may project this bundle into `session_snapshot.v2`; runtime must not consume `pack_pool.v1` directly. |
| `golden_pack.v1` | Fallback | `database` | `runtime-app` | Promoted local Golden Pack quiz payload and regression harness. | `schemas/golden_pack_v1.schema.json`; `docs/architecture/GOLDEN_PACK_SPEC.md`; runtime mirror in `runtime-app/packages/contracts/schemas-owner/golden_pack_v1.schema.json` | Fallback when Dynamic Pack is disabled or unavailable; regression fixture. | Product fallback contract | Retain until fallback is intentionally retired. | Not the main active dynamic runtime path. |
| `pack_pool.v1` | Active | `database` | `database` dynamic compiler/export tooling | Auditable owner-side source pool for dynamic sessions and serving bundles. | `schemas/pack_pool_v1.schema.json`; `docs/runbooks/dynamic-pack-phase-2a-pack-pool-session-snapshot.md` | Runtime-forbidden direct input. | Stable owner contract | Future pool changes require an explicit new pool version. | Owner-side only; runtime consumes derived artifacts, not the pool directly. |
| `runtime_answer_signals.v1` | Active | `runtime-app` | `database` | Batch export of answered runtime questions for owner confusion ingestion and aggregate recomputation. | `schemas/runtime_answer_signals_v1.schema.json`; runtime mirror in `runtime-app/packages/contracts/schemas-owner/runtime_answer_signals_v1.schema.json`; runtime runbook `runtime-app/docs/runbooks/database-integration-v1.md` | No quiz input role; runtime-to-owner handback only. | Product handback contract | Future telemetry shape changes require an explicit new answer signals version. | Correct answers are skipped during owner confusion event ingestion; incorrect answers preserve locale, seed, option source, and snapshot lineage. |
| `playable_corpus.v1` | Internal | `database` | Owner/operator tools; historical owner-read consumers | Prepared playable item corpus and lifecycle-serving surface. | `schemas/playable_corpus_v1.schema.json`; `docs/foundation/pipeline.md` | No current runtime role. | Legacy/internal stable | Historical owner-read context; do not promote as current runtime target. | Useful for lineage, inspection, and owner-side inputs. |
| `pack.compiled.v1` | Deprecated | `database` | Historical owner-read consumers / operator tools | Deterministic compiled pack build from v1 playable items. | `schemas/pack_compiled_v1.schema.json` | No current runtime role. | Legacy stable | Historical context; owner-read path archived in `docs/archive/superseded-contracts/`. | Do not present as active consumer contract. |
| `pack.materialization.v1` | Deprecated | `database` | Historical owner-read consumers / operator tools | Frozen v1 materialization derived from a compiled v1 build. | `schemas/pack_materialization_v1.schema.json` | No current runtime role. | Legacy stable | Historical context; owner-read path archived in `docs/archive/superseded-contracts/`. | Do not present as active consumer contract. |
| `pack.compiled.v2` | Transitional | `database` | `database` reference docs/tests | Taxon-based `QuestionOption[]` compiled-pack semantic reference. | `schemas/pack_compiled_v2.schema.json`; archived ADR/runbook in `docs/archive/superseded-contracts/` | Semantic reference only. | Legacy semantic reference | Not the current Dynamic Pack runtime handoff; archive old live plans. | May inform internal compiler semantics. |
| `pack.materialization.v2` | Transitional | `database` | `database` reference docs/tests | Taxon-based `QuestionOption[]` materialization semantic reference. | `schemas/pack_materialization_v2.schema.json`; archived ADR/runbook in `docs/archive/superseded-contracts/` | Semantic reference only. | Legacy semantic reference | Superseded by `session_snapshot.v2` for playable dynamic runtime handoff. | Must not be called the current runtime handoff. |
| owner-side runtime-read | Historical | `database` | Historical `runtime-app` owner-service clients | Minimal HTTP read path for `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1`. | Archived ADR `docs/archive/superseded-contracts/adr-0004-runtime-consumption-transport-v1.md` | No default product runtime role. | Deprecated transport path | Archived under `docs/archive/superseded-contracts/`; reopen only by explicit future decision. | Owner-side runtime-read is not the default product path. |
| future fixed challenge / assignment snapshots | Transitional | `database` | Planned runtime/product consumers | Future fixed/reproducible quiz variants generated from the same snapshot/materialization boundary. | No active schema yet. | No current runtime role until schema-backed. | Planned product family | Must receive explicit schemas before consumption. | Treat as variants of the internal snapshot/materialization family, not uncontrolled new contract families. |

## Navigation Rules

Use active docs for implementation:

- Active runtime contract: `docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md`
- Owner-side pool: `docs/runbooks/dynamic-pack-phase-2a-pack-pool-session-snapshot.md`
- Dynamic roadmap: `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md`
- Runtime consumption boundary: `docs/foundation/runtime-consumption-v1.md`
- Broad schema inventory: `docs/foundation/runtime-contract-stack-v1.md`

Use archive docs only for historical context:

- Superseded contract/transport plans: `docs/archive/superseded-contracts/`
- Closed execution runbooks: `docs/archive/runbooks/`
- Evidence and fixture records: `docs/archive/evidence/`

## Non-Negotiable Runtime Rules

Runtime must not:

- read owner Postgres, owner raw data, owner audit evidence, unresolved
  candidates, or live enrichment providers during quiz play;
- derive, translate, repair, or replace labels;
- choose, score, replace, or explain distractors locally;
- derive option correctness or taxonomic relationships locally;
- treat `golden_pack.v1`, `playable_corpus.v1`, `pack.compiled.*`, or
  `pack.materialization.*` as the main active Dynamic Pack runtime path.
