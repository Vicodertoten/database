# Inter-Repo Integration Log

Ce journal suit les synchronisations entre `database` et `runtime-app`.
Chaque entree correspond a un chantier identifie, avec un resume des decisions, des validations et de la prochaine etape.

Utilisation:

- ajouter une entree a l'ouverture d'un chantier inter-repos
- completer l'entree a chaque validation importante
- cloturer explicitement l'entree quand le chantier est termine dans les deux repos
- conserver uniquement des entrees reelles dans ce journal actif
- placer les exemples fictifs ou pedagogiques dans `docs/20_execution/archive/`

---

## Entry Template

### Chantier ID

[INT-000]

### Title

[Titre court du chantier]

### Status

[not_started | in_progress | blocked | validated | closed]

### Owner repo

[database]

### Consumer repo

[runtime-app]

### Summary

[Resume court de ce qui est aligne ou en cours d'alignement entre les deux repos]

### Decisions

- [Decision 1]
- [Decision 2]
- [Decision 3]

### Affected files

- [database: docs/...]
- [runtime-app: docs/...]
- [runtime-app: src/...]

### Linked commits

- [database: abc1234]
- [runtime-app: def5678]

### Verification

- [Commande ou preuve de verification cote owner]
- [Commande ou preuve de verification cote consumer]

### Next step

- [Prochaine etape exacte et sequentielle]

### Closed at

[YYYY-MM-DD or open]

---

## Active entries

### Chantier ID

INT-001

### Title

Lock runtime consumption doctrine v1

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

runtime consumption boundary locked owner-side and consumer-side verified as aligned.

### Decisions

- `runtime-app` runtime surfaces are limited to `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1`.
- `export.bundle.v4` remains prohibited as a live runtime surface.
- `database` owns contract and artifact truth; `runtime-app` consumes without redefining ownership.

### Affected files

- database: docs/runtime_consumption_v1.md
- database: docs/20_execution/chantiers/INT-001.md
- database: docs/20_execution/handoff.md

### Linked commits

- database: 20da705
- database: 1f03803
- runtime-app: f9f556a

### Verification

- owner-side doctrinal coherence review completed against README.md and docs/runtime_consumption_v1.md
- consumer-side: `runtime-app/docs/database_integration_v1.md` verified as aligned with locked owner wording; no modification required

### Next step

INT-002

### Closed at

2026-04-15

---

### Chantier ID

INT-002

### Title

Align runtime-app/packages/contracts with official database schemas

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner and consumer steps complete: runtime-app contracts are aligned 1:1 with owner schemas and the cross-repo closure criteria are met.

### Decisions

- `schemas/playable_corpus_v1.schema.json` is the authoritative contract for `playable_corpus.v1`.
- `schemas/pack_compiled_v1.schema.json` is the authoritative contract for `pack.compiled.v1`.
- `schemas/pack_materialization_v1.schema.json` is the authoritative contract for `pack.materialization.v1`.
- No local field renaming is permitted in `runtime-app/packages/contracts`.

### Affected files

- database: docs/runtime_consumption_v1.md
- database: docs/20_execution/chantiers/INT-002.md
- database: docs/20_execution/handoff.md
- runtime-app: packages/contracts/src/index.ts
- runtime-app: packages/contracts/src/guards.ts
- runtime-app: packages/contracts/src/examples.ts
- runtime-app: packages/contracts/README.md
- runtime-app: docs/20_execution/chantiers/INT-002.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: d921a9b
- database: 17f8349
- runtime-app: 1868923

### Verification

- owner-side: schemas verified as stable and complete on 2026-04-15
- consumer-side: field-level alignment verified against owner schemas; no local renaming or semantic transformation
- consumer-side command: `npx -y pnpm run check` passed (exit 0)

### Next step

INT-003

### Closed at

2026-04-15

---

### Chantier ID

INT-003

### Title

Runtime reference fixtures strategy v1 (owner-side)

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side fixture strategy is now explicit and first official minimal fixtures are published from real runtime surfaces (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) for local runtime consumption.

### Decisions

- Only `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1` are eligible as official runtime fixtures.
- `export.bundle.v4` is forbidden as a live runtime fixture source.
- Official fixture publication starts in `database`; `runtime-app` mirrors without semantic transformation.
- Published minimal fixture policy: playable subset of 4 coherent items + compiled(1 question) + materialization daily_challenge(1 question).
- No schema change and no runtime consumer code change in this owner step.

### Affected files

- database: docs/20_execution/chantiers/INT-003.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- database: fixtures/runtime/playable_corpus.sample.json
- database: fixtures/runtime/pack_compiled.sample.json
- database: fixtures/runtime/pack_materialization.sample.json
- runtime-app: docs/20_execution/chantiers/INT-003.md

### Linked commits

- database: 444188a
- runtime-app: open (INT-004 not started)

### Verification

- owner-side doctrinal consistency reviewed against `README.md`, `docs/runtime_consumption_v1.md`, and the three runtime schemas on 2026-04-15
- real DB state reused after schema migration to v15; pack compiled with `question_count=1`; materialized with `purpose=daily_challenge`; playable sample subset count verified at 4 items
- all three fixture files validated against official schemas (`playable_corpus_v1`, `pack_compiled_v1`, `pack_materialization_v1`)
- cross-ID coherence verified (`playable_item_id` and `canonical_taxon_id` references aligned across playable/compiled/materialization)

### Next step

- INT-004 (runtime-app consumer): adopt the published fixture trio in local integration tests, keeping strict field-level mirror semantics

### Closed at

2026-04-15

---

### Chantier ID

INT-004

### Title

Consumer integration closure on owner fixtures

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

`runtime-app` consumed the official fixture trio published by `database` in INT-003 and validated runtime surface ingestion through consumer integration tests, with no new owner-side data surface required.

### Decisions

- INT-004 execution stayed consumer-side in `runtime-app`.
- `database` remained source of truth for runtime fixture payloads and contracts.
- No new runtime surface was introduced.
- No owner-side fixture/schema/pipeline/business logic change was required.

### Affected files

- database: docs/20_execution/chantiers/INT-004.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- runtime-app: apps/api/fixtures/playable_corpus.sample.json
- runtime-app: apps/api/fixtures/pack_compiled.sample.json
- runtime-app: apps/api/fixtures/pack_materialization.sample.json
- runtime-app: apps/api/src/tests/contracts.integration.test.ts
- runtime-app: docs/20_execution/chantiers/INT-004.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: 444188a (owner fixture publication baseline, from INT-003)
- runtime-app: 36a8741

### Verification

- owner-side baseline confirmed: official fixtures from INT-003 remained unchanged
- consumer-side evidence (`runtime-app` 36a8741): fixture import completed, contract integration test added, checks passed
- inter-repo boundary preserved: runtime consumed official surfaces (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) with no owner contract drift

### Next step

- INT-005

### Closed at

2026-04-17

---

### Chantier ID

INT-007

### Title

Runtime consumption transport V1 doctrine

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side ADR now locks the shared transport narrative between repos without redefining existing runtime surfaces.

### Decisions

- Sequence is explicitly locked: V1 artifacts/fixtures, V1.5 minimal read API, later richer editorial operations.
- `apps/api` is the product entry point for runtime reads; web/mobile stay blind to data origin.
- `export.bundle.v4` remains excluded from live runtime surfaces.
- No schema, pipeline, or owner/consumer boundary change is introduced by INT-007.

### Affected files

- database: docs/adr/0004-runtime-consumption-transport-v1.md
- database: docs/20_execution/chantiers/INT-007.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- runtime-app: docs/adr/0001-runtime-database-transport-v1.md
- runtime-app: docs/20_execution/chantiers/INT-007.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: f15d7f9
- runtime-app: 3fb6557

### Verification

- owner-side ADR text reviewed for strict non-regression vs existing runtime surface doctrine
- runtime mirror ADR aligned phrase-by-phrase on sequence and normative reminders
- no code or schema changes introduced

### Next step

- INT-008 or next planned inter-repo chantier from the ADR-0004 baseline

### Closed at

2026-04-17

---

### Chantier ID

INT-008

### Title

Document v1 pack and enrichment operations (owner-side)

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side documentation now formalizes the real pack/enrichment operation loop from current CLI/storage behavior, while preserving strict owner/consumer boundaries and avoiding false public contracts where schemas do not yet exist.

### Decisions

- Canonical versioned outputs are locked where they already exist: `pack.spec.v1`, `pack.diagnostic.v1`, `pack.compiled.v1`, `pack.materialization.v1`.
- Pack listing is documented as a view over `pack.spec.v1` payloads (`pack-specs`, `pack-revisions`).
- Enrichment status and enqueue/execute flows are documented as owner-side operational flows (not yet public schema-versioned contracts).
- `runtime-app` may orchestrate later but does not own semantic truth for pack/enrichment.
- No schema/pipeline/runtime-surface change is introduced in INT-008.

### Affected files

- database: docs/pack_enrichment_operations_v1.md
- database: docs/README.md
- database: docs/20_execution/chantiers/INT-008.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- runtime-app: docs/20_execution/chantiers/INT-008.md (mirror docs-only, closed)

### Linked commits

- database: 1e42da7
- runtime-app: 4f87665

### Verification

- operation inventory checked against `src/database_core/cli.py`, `src/database_core/storage/pack_store.py`, `src/database_core/storage/enrichment_store.py`
- versioned outputs cross-checked against official schemas:
  - `schemas/pack_spec_v1.schema.json`
  - `schemas/pack_diagnostic_v1.schema.json`
  - `schemas/pack_compiled_v1.schema.json`
  - `schemas/pack_materialization_v1.schema.json`
- doctrine consistency preserved with `docs/runtime_consumption_v1.md`, ADR-0003, and ADR-0004

### Next step

- runtime-app opens INT-009 for consumer-side orchestration facades over database-owned operations

### Closed at

2026-04-17

---

### Chantier ID

INT-016

### Title

Runtime-read owner-side proof hardening (Phase 6)

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side runtime-read tests now cover non-trivial series behavior and explicit HTTP error matrix while keeping the same read-only 3-surface boundary.

### Decisions

- No new runtime surface and no contract version bump.
- Latest compiled retrieval (`/packs/{pack_id}/compiled`) must be explicitly proven against revision series.
- HTTP mapping remains strict: `400` parse errors, `404` not found, `500` owner internal errors.

### Affected files

- database: `tests/test_runtime_read_owner_service.py`
- database: `docs/20_execution/chantiers/INT-016.md`
- database: `docs/20_execution/integration_log.md`
- runtime-app: `docs/20_execution/chantiers/INT-016.md`
- runtime-app: `docs/20_execution/integration_log.md`

### Linked commits

- database: edf8e13
- runtime-app: 06c7f5d

### Verification

- `python -m pytest -q tests/test_runtime_read_owner_service.py -p no:capture` passed

### Next step

- INT-017

### Closed at

2026-04-19

---

### Chantier ID

INT-017

### Title

Runtime visible baseline stabilization (wording + archive + cross-repo handoff)

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

This chantier stabilizes the visible runtime baseline narrative across docs/README/UI and isolates historical templates from active execution logs.

### Decisions

- Active integration log keeps real entries only; fictitious examples are archived.
- Current visible baseline wording is explicit: owner-side nominal read, runtime-side persisted sessions, web minimal pedagogical, mobile minimal image-first.
- No owner contract/surface expansion is introduced.

### Affected files

- database: docs/20_execution/integration_log.md
- database: docs/20_execution/archive/integration_log_fictitious_examples.md
- database: docs/20_execution/README.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/chantiers/INT-017-runtime-app-handoff-checklist.md
- database: docs/runtime_consumption_v1.md
- database: README.md
- runtime-app: docs/20_execution/chantiers/INT-017.md
- runtime-app: docs/20_execution/integration_log.md
- runtime-app: README/docs/UI wording and image-first checks

### Linked commits

- database: c847c9b
- runtime-app: eab3bbc


### Verification

- owner-side: doc alignment pass on active runtime wording completed
- owner-side: fictitious examples removed from active integration log
- consumer-side: runtime-app mirror closure recorded (`INT-017` runtime side closed with web wording + mobile image-first evidence)

### Next step

- phase 7 planning

### Closed at

2026-04-19

## Archived examples

Les exemples fictifs ont ete deplaces vers:

- `docs/20_execution/archive/integration_log_fictitious_examples.md`

## Chantier ID: INT-018

- Title: Owner-side runtime-read operational hardening
- Status: closed
- Owner repo: database
- Consumer repo: runtime-app
- Summary: owner-side runtime-read service now exposes richer health diagnostics and request-level JSON observability while staying strictly bounded to the three official read surfaces.
- Source of truth:
  - `docs/20_execution/chantiers/INT-018.md`
  - `docs/runtime_consumption_v1.md`
  - `runtime-app/docs/20_execution/chantiers/INT-018.md`
- Decisions:
  - no contract version change
  - no scope extension beyond read-only runtime transport
  - strict parameter guards (`limit`, `revision`) kept explicit
- Affected files:
  - database: `src/database_core/runtime_read/http_server.py`
  - database: `tests/test_runtime_read_owner_service.py`
  - database: `docs/runtime_consumption_v1.md`
  - database: `docs/20_execution/chantiers/INT-018.md`
  - runtime-app: `apps/api/src/routes/runtime-read.ts`
  - runtime-app: `apps/api/src/routes/sessions.ts`
  - runtime-app: `apps/api/src/integrations/database/owner-http-provider.ts`
- Linked commits:
  - database: pending
  - runtime-app: pending
- Verification:
  - `python -m pytest -q tests/test_runtime_read_owner_service.py -p no:capture` passed
  - `corepack pnpm --filter @runtime-app/api test:runtime-read` passed
- Next step: phase 7 planning
- Closed at: 2026-04-19

## Chantier ID: INT-019

- Title: Formalisation owner-side des operations editoriales critiques (Phase 3)
- Status: closed
- Owner repo: database
- Consumer repo: runtime-app
- Summary: owner-side write transport is now formalized with versioned operation envelopes and a dedicated minimal HTTP service; runtime-app delegates `/editorial/*` to this real transport.
- Source of truth:
  - `docs/adr/0005-editorial-write-transport-v1.md`
  - `docs/20_execution/chantiers/INT-019.md`
  - `runtime-app/docs/20_execution/chantiers/INT-019.md`
- Decisions:
  - keep write transport separated from runtime-read transport
  - formalize operation envelopes per critical editorial operation
  - preserve existing owner artifacts (`pack.spec.v1`, `pack.diagnostic.v1`, `pack.compiled.v1`, `pack.materialization.v1`) as payload truth
  - keep service perimeter strict (pack/enrichment orchestration only)
- Affected files:
  - database: `docs/adr/0005-editorial-write-transport-v1.md`
  - database: `src/database_core/editorial_write/contract.py`
  - database: `src/database_core/editorial_write/service.py`
  - database: `src/database_core/editorial_write/http_server.py`
  - database: `tests/test_editorial_write_owner_service.py`
  - database: `schemas/pack_create_v1.schema.json`
  - database: `schemas/pack_diagnose_operation_v1.schema.json`
  - database: `schemas/pack_compile_operation_v1.schema.json`
  - database: `schemas/pack_materialize_operation_v1.schema.json`
  - database: `schemas/enrichment_request_status_v1.schema.json`
  - database: `schemas/enrichment_enqueue_v1.schema.json`
  - database: `schemas/enrichment_execute_v1.schema.json`
  - runtime-app: `apps/api/src/integrations/database/owner-http-editorial-provider.ts`
  - runtime-app: `apps/api/src/routes/editorial-pack-flows.ts`
  - runtime-app: `apps/api/src/tests/editorial-pack-flows.integration.test.ts`
- Linked commits:
  - database: pending
  - runtime-app: pending
- Verification:
  - `ruff check .` passed
  - `python -m compileall -q src tests/test_editorial_write_owner_service.py` passed
  - manual owner-write smoke passed on isolated schema (Supabase): create/diagnose/materialize/enqueue/status/execute
  - `corepack pnpm --filter @runtime-app/contracts build` passed
  - `corepack pnpm --filter @runtime-app/contracts type-check` passed
  - `corepack pnpm --filter @runtime-app/api type-check` passed
  - `corepack pnpm --filter @runtime-app/api lint` passed
  - `corepack pnpm --filter @runtime-app/api test:editorial` passed
- Next step: institutional minimum planning and bounded write expansion sequencing
- Closed at: 2026-04-19

## Chantier ID: INT-020

- Title: Support owner-side pour surface editoriale legere runtime (Phase 4)
- Status: closed
- Owner repo: database
- Consumer repo: runtime-app
- Summary: owner-side write service remains strict and stable while enabling runtime-app to ship a minimal real editorial operator surface (`/editorial`) through `apps/api`.
- Source of truth:
  - `docs/20_execution/chantiers/INT-020.md`
  - `runtime-app/docs/20_execution/chantiers/INT-020.md`
  - `docs/adr/0005-editorial-write-transport-v1.md`
- Decisions:
  - preserve owner-side scope (pack/enrichment orchestration only)
  - strengthen explicit invalid-input refusals
  - keep contracts/versioning unchanged
- Affected files:
  - database: `src/database_core/editorial_write/http_server.py`
  - database: `tests/test_editorial_write_owner_service.py`
  - database: `docs/20_execution/chantiers/INT-020.md`
  - runtime-app: `apps/web/app/editorial/page.tsx`
  - runtime-app: `packages/shared/src/index.ts`
  - runtime-app: `apps/api/src/routes/editorial-pack-flows.ts`
- Linked commits:
  - database: pending
  - runtime-app: pending
- Verification:
  - `ruff check .` passed
  - `python -m compileall -q src tests/test_editorial_write_owner_service.py` passed
  - `corepack pnpm --filter @runtime-app/api run test:editorial` passed
  - `corepack pnpm --filter @runtime-app/web run test:smoke` passed
- Next step: institutional minimum planning
- Closed at: 2026-04-19

## Chantier ID: INT-021

- Title: Runtime institutional minimum alignment catch-up
- Status: closed
- Owner repo: runtime-app
- Consumer repo: database (owner docs alignment only)
- Summary: owner-side `database` execution trace acknowledges runtime-side INT-021 closure to remove cross-repo baseline drift before phase 6 kickoff.
- Source of truth:
  - `runtime-app/docs/20_execution/chantiers/INT-021.md`
  - `runtime-app/docs/20_execution/integration_log.md`
- Decisions:
  - no owner contract/surface changes
  - institutional ownership remains runtime-side
  - database handoff/log baseline updated to reflect post-INT-021 state
- Affected files:
  - database: `docs/20_execution/handoff.md`
  - database: `docs/20_execution/integration_log.md`
  - runtime-app: `docs/20_execution/chantiers/INT-021.md`
  - runtime-app: `docs/20_execution/integration_log.md`
- Linked commits:
  - database: pending
  - runtime-app: pending
- Verification:
  - docs consistency pass completed across both repos
- Next step: open INT-022 as shared active chantier
- Closed at: 2026-04-20

## Chantier ID: INT-022

- Title: Phase 6 pilot-prep hardening (cross-repo)
- Status: in_progress
- Owner repo: runtime-app + database (split ownership by perimeter)
- Consumer repo: runtime-app + database
- Summary: phase 6 hardening is active with synchronized chantier docs/runbook, runtime-side operator auth + metrics/retry guardrails implemented, and owner-side dry-run evidence path prepared.
- Source of truth:
  - `docs/20_execution/chantiers/INT-022.md`
  - `docs/20_execution/phase6_pilot_runbook.md`
  - `runtime-app/docs/20_execution/chantiers/INT-022.md`
  - `runtime-app/docs/20_execution/phase6_pilot_runbook.md`
- Decisions:
  - acceptance targets locked cross-repo:
    - availability SLO `99.5% / 7d`
    - latency `p95 <= 800ms`
    - load profile `100` concurrent learners
    - `2` complete dry-runs with simulated owner incident
  - owner perimeter remains unchanged (no runtime/institutional semantics moved to database)
  - cross-repo docs sync is mandatory before merge for phase 6 changes
- Affected files:
  - database: `docs/20_execution/chantiers/INT-022.md`
  - database: `docs/20_execution/phase6_pilot_runbook.md`
  - database: `docs/20_execution/handoff.md`
  - database: `docs/20_execution/integration_log.md`
  - runtime-app: `docs/20_execution/chantiers/INT-022.md`
  - runtime-app: `docs/20_execution/phase6_pilot_runbook.md`
  - runtime-app: `docs/20_execution/handoff.md`
  - runtime-app: `docs/20_execution/integration_log.md`
- Linked commits:
  - database: pending
  - runtime-app: pending
- Verification:
  - `ruff check .` pending
  - `python -m compileall -q src tests/test_runtime_read_owner_service.py tests/test_editorial_write_owner_service.py` pending
  - runtime-side phase 6 verification suite pending from synchronized run
- Next step: execute dry-run #1 and publish owner/runtime evidence bundle.
