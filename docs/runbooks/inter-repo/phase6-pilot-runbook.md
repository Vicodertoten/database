---
owner: database
status: in_progress
last_reviewed: 2026-04-27
source_of_truth: docs/runbooks/inter-repo/phase6-pilot-runbook.md
scope: runbook_inter_repo
---

# Phase 6 Pilot Runbook (database + runtime-app)

## Purpose

Owner-side operational companion for phase 6 pilot-prep:

- verify owner service readiness (`runtime_read`, `editorial_write`)
- provide cross-repo incident triage path with `runtime-app`
- capture dry-run evidence required for Go/No-Go dossier

## Owner services baseline

- runtime-read owner service:
  - `database-runtime-read-owner`
  - health: `GET /health`
- editorial-write owner service:
  - `database-editorial-write-owner`
  - health: `GET /health`

Both services remain bounded:

- read: `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`
- write: pack/enrichment orchestration only

## Dry-run owner checks

1. Verify owner health endpoints before runtime dry-run start.
2. Run owner-side verification tests:
   - `tests/test_runtime_read_owner_service.py`
   - `tests/test_editorial_write_owner_service.py`
3. Confirm request logs emit:
   - `status`
   - `error_category`
   - `latency_ms`
4. During simulated incident:
   - force/read timeout or owner unavailability scenario
   - confirm runtime error classification remains explicit
5. Confirm recovery:
   - health back to `ready=true`
   - runtime flows resume without contract drift

## Incident triage handoff (owner perspective)

1. Determine affected owner service (`runtime_read` vs `editorial_write`).
2. Confirm if error class is `client_error` or `server_error` in owner logs.
3. Inspect runtime-side propagated class (`owner_timeout`, `owner_unavailable`, `owner_http_error`).
4. Coordinate mitigation with runtime operator:
   - restart owner service if needed
   - rollback recent owner env/config drift
5. Record incident evidence for Go/No-Go dossier.

## Go/No-Go evidence contribution

Required owner-side evidence block:

- health snapshots before/after each dry-run
- incident timeline and root-cause note (if any)
- recovery confirmation timestamp
- confirmation of unchanged owner boundaries/contracts
