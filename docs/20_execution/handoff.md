# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-025
- Title: Phase 2 pre-filtrage image amont (reduction cout IA)
- Status: open_in_progress

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: pre-AI filtering implementation -> owner validation -> consumer nominal smoke -> baseline/candidate decision table

## Last validated state

- Last validated context: INT-025 implementation deployed owner-side.
- What is already validated:
  - pre-AI filters are active before Gemini calls
  - additive manifest/smoke contract preserved
  - pre-AI reasons are traceable (`insufficient_resolution_pre_ai`, `decode_error_pre_ai`, `blur_pre_ai`, `duplicate_pre_ai`)
  - targeted tests are green (`tests/test_inat_snapshot.py`, `tests/test_cli.py`, `tests/test_smoke_report.py`)
  - consumer nominal smoke remains green (`runtime-app`)
- What is not validated yet:
  - final baseline/candidate cost-reduction decision across comparable owner runs

## Decisions already locked

- blur enabled directly (no shadow mode)
- dedup by exact hash only (`sha256`), no `pHash` in Phase 2
- one dimension gate source of truth (existing AI min dimensions)
- no runtime contract change
- no Phase 4/5 remediation work in this chantier

## Important constraints

- no schema/contract break
- additive-only data surface changes
- no refactor outside pre-filtering scope
- keep owner/consumer boundary explicit

## Next exact step

- run baseline/candidate comparable owner measurements and publish the final Phase 2 decision (`GO`/`GO_WITH_GAPS`/`NO_GO`) with cost/exportable evidence.

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-025.md
- docs/20_execution/integration_log.md
- src/database_core/adapters/inaturalist_harvest.py
- src/database_core/adapters/inaturalist_qualification.py
- src/database_core/adapters/inaturalist_snapshot.py
- src/database_core/ops/smoke_report.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-025.md
- runtime-app/docs/20_execution/handoff.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q -p no:capture tests/test_inat_snapshot.py tests/test_cli.py tests/test_smoke_report.py`
- `python scripts/verify_goldset_v1.py`
- `set -a; source .env; set +a; python scripts/generate_smoke_report.py --snapshot-id inaturalist-birds-v2-20260421T210221Z --fail-on-kpi-breach`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`

## Notes for next IA session

- INT-025 implementation is in place and validated by targeted tests.
- `verify_repo.py` currently fails on a pre-existing doctrine marker check (`Politique distracteurs v2`) unrelated to this chantier.
- Final closure requires comparable baseline/candidate owner evidence for cost-reduction impact.
