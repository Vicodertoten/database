# AGENTS.md

## Purpose

This repository is the owner knowledge core for the biodiversity learning platform.

It owns:
- canonical taxonomy truth
- qualification truth
- governed playable/pack artifacts
- enrichment and governance workflows

It does **not** own runtime live session behavior.

---

## Source-of-truth hierarchy

Before making meaningful changes, read in this order:

1. `README.md`
2. `docs/README.md`
3. `docs/foundation/scope.md`
4. `docs/foundation/canonical-charter-v1.md`
5. `docs/foundation/domain-model.md`
6. `docs/foundation/pipeline.md`
7. `docs/foundation/runtime-consumption-v1.md`
8. `docs/runbooks/audit-reference.md`
9. `docs/runbooks/execution-plan.md`
10. `docs/runbooks/inter-repo/`

---

## Core boundaries

- `database` is the source of truth for inter-repo active tracking.
- Runtime consumers read official serving surfaces only.
- Runtime must never consume `export.bundle.v4` as live surface.

---

## Hard boundaries

Never do the following in this repo:

- move runtime session/scoring/progression logic into `database`
- let external sources redefine canonical identity freely
- let AI mutate canonical identity fields directly
- redefine runtime-owned behavior in owner-side transports
- introduce silent contract changes without docs and tests

---

## Working method

- work docs-first on boundary changes
- keep one structural chantier active at a time
- prefer narrow, reversible changes
- update docs, code, tests, and CI together
- keep active inter-repo notes only under `docs/runbooks/inter-repo/`

---

## Minimum local verification

- `python scripts/verify_repo.py`
- `python scripts/check_doc_code_coherence.py`
- `python scripts/check_docs_hygiene.py`
- `python -m ruff check src tests scripts`
