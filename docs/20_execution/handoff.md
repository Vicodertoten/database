# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-008
- Title: Pack and enrichment operations V1 owner documentation
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: database owner documentation -> runtime-app consumer mirror docs

## Last validated state

- Last validated commit or tag: 1e42da7 (INT-008 owner closure)
- Validation date: 2026-04-17
- What is already validated:
  - owner reference doc added: `docs/pack_enrichment_operations_v1.md`
  - operation inventory is aligned with real commands in `src/database_core/cli.py`
  - canonical outputs are explicit where versioned artifacts already exist (`pack.spec.v1`, `pack.diagnostic.v1`, `pack.compiled.v1`, `pack.materialization.v1`)
  - enrichment status/request flows are explicitly documented as owner-side operational flows (non public schema-versioned contract at this stage)
  - runtime-app INT-008 consumer mirror is closed (`4f87665`)
  - no schema, pipeline, or runtime-surface change introduced by INT-008
- What is not validated yet:
  - none for INT-008 scope

## Decisions already locked

- `database` remains owner of pack/enrichment truth:
  - valid parameters
  - compilability criteria
  - diagnostics semantics
  - produced artifacts
  - enrichment status semantics
- `runtime-app` may pilot these operations later but must not redefine owner truth
- versioned artifacts are canonical outputs when they already exist
- non-versioned enrichment/status zones remain documented as operational owner flows only

## Important constraints

- Do not touch existing schemas.
- Do not modify pipeline logic.
- Do not create a new network/API surface in INT-008.
- Do not transfer semantic ownership of pack/enrichment logic to runtime-app.

## Next exact step

- runtime-app: open INT-009 and implement consumer editorial facades over database-owned operations

## Files to read first in this repo

- README.md
- docs/README.md
- docs/runtime_consumption_v1.md
- docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md
- docs/adr/0004-runtime-consumption-transport-v1.md
- docs/pack_enrichment_operations_v1.md
- docs/20_execution/chantiers/INT-008.md
- docs/20_execution/integration_log.md

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-008.md
- runtime-app/docs/20_execution/handoff.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python scripts/check_doc_code_coherence.py` (optional doc coherence check)

## Notes for next IA session

- INT-008 owner-side is docs/contractual only.
- Keep enrichment described as operational owner flow until a public versioned contract is explicitly introduced.
- Keep `apps/api` and future consumer facades as orchestration surfaces, never as truth ownership surfaces.
