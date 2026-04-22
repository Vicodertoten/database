# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-028
- Title: Protocole preflight v2 (preuve binaire operabilite Phase 3.1)
- Status: closed_no_go

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: baseline diagnose -> targeted remediation passes -> diagnose/compile delta -> runtime compatibility check

## Last validated state

- Last validated context: INT-028 executed end-to-end with published verdict.
- What is already validated:
  - preflight deficit source now follows `pack diagnose` (`min_media_per_taxon` missing), not smoke reason_count
  - bounded protocol orchestrator implemented (`scripts/phase3_1_preflight_v2_protocol.py`)
  - strict status mapping maintained (`CONTINUE_SCALE->GO`, `GO_WITH_GAPS->GO_WITH_GAPS`, others->NO_GO)
  - real run executed and verdict artifact published: `phase3_1_preflight_v2_verdict.v1.json`
  - final verdict: `NO_GO` (`cause=no_compile_signal_under_capped_probe`)
- What is not validated yet:
  - no pending validation in INT-028 scope (chantier closed)

## Decisions already locked

- source of truth for targeting: pack diagnose output
- idempotence logic lives in remediation script + snapshot filtering (not enrichment_store core)
- no runtime contract change
- no Phase 4/5 work in this chantier

## Important constraints

- no schema/contract break
- additive-only data surface changes
- no refactor outside pre-filtering scope
- keep owner/consumer boundary explicit

## Next exact step

- open next owner-only retargeting step to improve compile-impact per Gemini call before re-attempting any Phase 3.1 full campaign.

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-028.md
- docs/20_execution/integration_log.md
- scripts/phase3_1_preflight_v2_protocol.py
- scripts/phase3_1_complete_measurement.py
- src/database_core/ops/phase3_taxon_remediation.py
- scripts/phase3_taxon_remediation.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-026.md
- runtime-app/docs/20_execution/handoff.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q -p no:capture tests/test_phase3_taxon_remediation.py`
- `python -m pytest -q -p no:capture tests/test_inat_snapshot.py`
- `python -m pytest -q -p no:capture tests/test_storage.py`
- `python scripts/verify_goldset_v1.py`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`

## Notes for next IA session

- INT-026 is closed with final decision `NO_GO`.
- INT-027 is closed `NO_GO`; it introduced the hard gate before full 3.1 campaign.
- INT-028 is now closed `NO_GO` after real supervised execution.
- `verify_repo.py` currently fails on a pre-existing doctrine marker check (`Politique distracteurs v2`) unrelated to this chantier.
- Full 3.1 run is now controlled by `phase3_1_preflight_v2_protocol.py` and should not be launched outside that flow.
