---
owner: database
status: stable
last_reviewed: 2026-04-27
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
- Archive index: `docs/archive/`

## Governance rules

- One topic, one source of truth.
- Closed chantiers must leave active runbooks and be archived.
- Active docs must include required front-matter.
- `.DS_Store` files are forbidden under `docs/`.
