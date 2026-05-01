---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/README.md
scope: documentation_index
---

# Documentation Index

This repository now uses a three-zone documentation architecture:

- `docs/foundation/`: stable doctrine and contracts
- `docs/runbooks/`: active operational documentation
- `docs/archive/`: historical logs, evidence, and retired material

## Inter-repo rule (single source of truth)

`database` is the only active source of truth for inter-repo execution tracking.

- Active tracking: `docs/runbooks/inter-repo/`
- Compatibility pointer only: `docs/20_execution/README.md`
- `runtime-app` keeps pointer docs only for inter-repo tracking.

## Start here

- Foundation: `docs/foundation/`
- Active runbooks: `docs/runbooks/`
- Locked short-term scope v0.1: `docs/runbooks/v0.1-scope.md`
- Pre-scale ingestion roadmap: `docs/runbooks/pre-scale-ingestion-roadmap.md`
- Ingestion quality gates: `docs/runbooks/ingestion-quality-gates.md`
- Ingestion code-to-gate map: `docs/runbooks/ingestion-code-to-gate-map.md`
- Phase 2 implementation runbook: `docs/runbooks/phase2-playable-corpus-v0.1.md`
- Phase 3 distractor strategy: `docs/runbooks/phase3-distractor-strategy.md`
- Archive index: `docs/archive/`

## Governance rules

- One topic, one source of truth.
- Closed chantiers must leave active runbooks and be archived.
- Active docs must include required front-matter.
- `.DS_Store` files are forbidden under `docs/`.
