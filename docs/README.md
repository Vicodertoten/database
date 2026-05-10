---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/README.md
scope: documentation_index
---

# Documentation Index

This repository uses a five-zone documentation lifecycle:

- `docs/architecture/`: active canonical maps and product architecture.
- `docs/foundation/`: stable doctrine, boundaries, and supporting references.
- `docs/runbooks/`: active operational documentation.
- `docs/audits/`: active audits, quality reviews, and retained decisions.
- `docs/archive/`: historical logs, evidence, and retired material.

## Read First

1. Current contract map: `docs/architecture/contract-map.md`.
2. Runtime consumption boundary: `docs/foundation/runtime-consumption-v1.md`.
3. Dynamic Pack runtime session contract: `docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md`.
4. Dynamic Pack owner-side pool runbook: `docs/runbooks/dynamic-pack-phase-2a-pack-pool-session-snapshot.md`.
5. Dynamic Pack product roadmap: `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md`.

## Current Contract Status

Source of truth: `docs/architecture/contract-map.md`.

- Active playable runtime contract: `session_snapshot.v2`.
- Active owner-side dynamic source pool: `pack_pool.v1`.
- Runtime fallback / regression harness: `golden_pack.v1`.
- Owner-only/internal surface: `playable_corpus.v1`.
- Transitional semantic references: `pack.compiled.v2`, `pack.materialization.v2`.
- Historical/deprecated: `pack.compiled.v1`, `pack.materialization.v1`, owner-side runtime-read as default product path.

## Active Canonical Docs

- `docs/architecture/contract-map.md` - canonical contract status and runtime/owner boundary.
- `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md` - current Dynamic Pack product direction.
- `docs/architecture/GOLDEN_PACK_SPEC.md` - fallback Golden Pack contract.
- `docs/architecture/MASTER_REFERENCE.md` - historical Golden Pack fallback reference.
- `docs/foundation/runtime-consumption-v1.md` - runtime consumption boundary and historical transport context.
- `docs/foundation/runtime-contract-stack-v1.md` - broad durable artifact/schema inventory; not the contract-status source.
- `docs/foundation/dynamic-session-compiler-internals-v1.md` - internal compiler versus exported product snapshot boundary.
- `docs/foundation/localized-name-source-policy-v1.md` - owner-side localized name display policy.

## Runbooks

- `docs/runbooks/dynamic-pack-phase-1-corpus-gate.md`
- `docs/runbooks/dynamic-pack-phase-2a-pack-pool-session-snapshot.md`
- `docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md`
- `docs/runbooks/golden-pack-v1-runtime-handoff.md`
- `docs/runbooks/execution-plan.md`
- `docs/runbooks/pre-scale-ingestion-roadmap.md`
- `docs/runbooks/v0.1-scope.md`
- `docs/runbooks/ingestion-quality-gates.md`
- `docs/runbooks/ingestion-code-to-gate-map.md`

## Schemas / Contract References

Schemas live in `schemas/`. Current runtime-facing or fallback schemas are:

- `schemas/session_snapshot_v2.schema.json`
- `schemas/pack_pool_v1.schema.json`
- `schemas/serving_bundle_v1.schema.json`
- `schemas/golden_pack_v1.schema.json`
- `schemas/runtime_answer_signals_v1.schema.json`

Legacy or transitional schemas remain for validation and reference only; see
`docs/architecture/contract-map.md` before using them.

## Internal / Transitional References

- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`
- `docs/foundation/qualification-contracts-status.md`
- `docs/foundation/pmp-qualification-policy-v1.md`
- `docs/runbooks/audit-reference.md`

These documents may mention historical serving surfaces, but they must frame them
as owner-only, transitional, historical, or strategic-later.

## Archived / Superseded Docs

- `docs/archive/superseded-contracts/`: superseded runtime-read and materialization contract plans.
- `docs/archive/runbooks/`: closed execution runbooks.
- `docs/archive/evidence/`: dated evidence and generated artifacts.
- `docs/archive/audits/`: historical audit snapshots.

Archive docs are preserved for context only and must not be used as current
implementation guidance.

## Audit Location Rules

- Active audits stay in `docs/audits/`.
- Closed audits that remain referenced by an active baseline may stay in `docs/audits/` as retained evidence.
- Superseded or purely historical audits must move to `docs/archive/audits/`.

## Inter-Repo Rule

`database` is the only active source of truth for inter-repo execution tracking.

- Active tracking: `docs/runbooks/inter-repo/`
- Compatibility pointer only: `docs/20_execution/README.md`
- `runtime-app` keeps pointer docs only for inter-repo tracking.

## Governance Rules

- One topic, one source of truth.
- Contract status belongs in `docs/architecture/contract-map.md`.
- Closed chantiers and superseded plans must leave active runbooks and be archived.
- Active docs must include required front matter.
- `.DS_Store` files are forbidden under `docs/`.
