---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/README.md
scope: documentation_index
---

# Documentation Index

This repository now uses a four-zone documentation architecture:

- `docs/foundation/`: stable doctrine and contracts
- `docs/runbooks/`: active operational documentation
- `docs/audits/`: active audits, policy comparisons, quality reviews, and adoption decisions
- `docs/archive/`: historical logs, evidence, and retired material

## Audit location rules

- Active audits stay in `docs/audits/`.
- Closed audits that remain referenced by an active baseline may stay in `docs/audits/` as retained evidence.
- Superseded or purely historical audits must move to `docs/archive/audits/`.

## Inter-repo rule (single source of truth)

`database` is the only active source of truth for inter-repo execution tracking.

- Active tracking: `docs/runbooks/inter-repo/`
- Compatibility pointer only: `docs/20_execution/README.md`
- `runtime-app` keeps pointer docs only for inter-repo tracking.

## Start here

- Foundation: `docs/foundation/`
  - Pedagogical media qualification contract: `docs/foundation/pedagogical-media-profile-v1.md`
  - Qualification contracts status (v1_1 / v1_2 / PMP v1): `docs/foundation/qualification-contracts-status.md`
- Active runbooks: `docs/runbooks/`
- Active audits: `docs/audits/`
- Locked short-term scope v0.1: `docs/runbooks/v0.1-scope.md`
- Pre-scale ingestion roadmap: `docs/runbooks/pre-scale-ingestion-roadmap.md`
- Ingestion quality gates: `docs/runbooks/ingestion-quality-gates.md`
- Ingestion code-to-gate map: `docs/runbooks/ingestion-code-to-gate-map.md`
- Phase 2 implementation runbook: `docs/runbooks/phase2-playable-corpus-v0.1.md`
- Phase 3 distractor strategy: `docs/runbooks/phase3-distractor-strategy.md`
- Palier 1 v1.1 baseline stabilization: `docs/runbooks/palier-1-v11-baseline.md`
- Palier 1 v1.1 linked audits:
	- `docs/audits/qualification-policy-v1-v11-comparison.md`
	- `docs/audits/palier-1-v11-default-pack-audit.md`
	- `docs/audits/palier-1-v11-manual-review-sheet.md`
	- `docs/audits/palier-1-v12-ai-review-contract.md`
	- `docs/audits/palier-1-v12-live-mini-run-audit.md`
- Archive index: `docs/archive/`

## Governance rules

- One topic, one source of truth.
- Closed chantiers must leave active runbooks and be archived.
- Active docs must include required front-matter.
- `.DS_Store` files are forbidden under `docs/`.
