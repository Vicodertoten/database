---
owner: database
status: in_progress
last_reviewed: 2026-04-27
source_of_truth: docs/runbooks/inter-repo/handoff.md
scope: inter_repo_handoff
---

# Handoff State

This document tracks the real operational handoff state for the active inter-repo chantier.

## Current active chantier

- ID: `INT-022`
- Title: `Phase 6 pilot-prep hardening alignment`
- Status: `blocked`

## Current validated baseline

- Inter-repo ownership boundaries are stable.
- Owner-side read/write transport remains bounded to governed surfaces.
- Runtime-side observability and operator-route controls are in place.

## Verified commands

- `python scripts/verify_repo.py` must be rerun and green on the current HEAD before promotion.
- Use targeted test commands from the chantier page before promotion.
- For schema/fixture updates, merge order is strict: `runtime-app` sync PR first, then `database`.

## Last verify_repo validation

- Commit: `4079a30`
- Date (UTC): `2026-04-27T20:27:30Z`
- Command: `./.venv/bin/python scripts/verify_repo.py`
- Result: `PASS` (`166 passed`; doc/code coherence, docs hygiene, and Ruff checks passed)

## Next step

Unblock `INT-022` with explicit closure criteria and then archive it after closure.
