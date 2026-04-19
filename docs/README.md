# Documentation Index

This index is the canonical entrypoint for repository documentation.
Before adding a new document, update an existing one whenever possible.

## Start Here

- `README.md`: quickstart, operational commands, output contracts.
- `docs/05_audit_reference.md`: living execution baseline, current structural gaps, and strategic priorities.
- `docs/codex_execution_plan.md`: operating reference for future work after the Gate 9 baseline.

Reading discipline:

- use `docs/00_scope.md`, `docs/01_domain_model.md`, and `docs/02_pipeline.md` for stable scope, contracts, and pipeline behavior
- use `docs/05_audit_reference.md` for current-state synthesis, explicit debt, and strategic posture
- use `docs/codex_execution_plan.md` only for execution order and approved next workstreams

## Domain And Architecture

- `docs/00_scope.md`: pilot scope and non-goals.
- `docs/01_domain_model.md`: domain entities and contracts.
- `docs/02_pipeline.md`: pipeline stages and invariants.
- `schemas/playable_corpus_v1.schema.json`: contract schema for `playable_corpus.v1`.
- `schemas/pack_spec_v1.schema.json`: contract schema for `pack.spec.v1`.
- `schemas/pack_diagnostic_v1.schema.json`: contract schema for `pack.diagnostic.v1`.
- `schemas/pack_compiled_v1.schema.json`: contract schema for `pack.compiled.v1`.
- `schemas/pack_materialization_v1.schema.json`: contract schema for `pack.materialization.v1`.
- `schemas/pack_create_v1.schema.json`: operation envelope schema for `pack.create.v1`.
- `schemas/pack_diagnose_operation_v1.schema.json`: operation envelope schema for `pack.diagnose.v1`.
- `schemas/pack_compile_operation_v1.schema.json`: operation envelope schema for `pack.compile.v1`.
- `schemas/pack_materialize_operation_v1.schema.json`: operation envelope schema for `pack.materialize.v1`.
- `schemas/enrichment_request_status_v1.schema.json`: operation envelope schema for `enrichment.request.status.v1`.
- `schemas/enrichment_enqueue_v1.schema.json`: operation envelope schema for `enrichment.enqueue.v1`.
- `schemas/enrichment_execute_v1.schema.json`: operation envelope schema for `enrichment.execute.v1`.
- `docs/06_charte_canonique_v1.md`: canonical governance policy (normative).
- `docs/07_canonical_id_migration_v1.md`: canonical ID migration mapping and cutover policy.
- `docs/adr/0001-charte-canonique-v1.md`: implementation ADR for canonical governance v1.
- `docs/adr/0002-noyau-canonique-fort-execution-sequentielle.md`: execution ADR locking gates, canonical policy, and export transition.
- `docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`: doctrinal boundaries for playable/pack compilation/enrichment chain.
- `docs/adr/0005-editorial-write-transport-v1.md`: owner-side write transport doctrine for editorial operations.

## Operations

- `docs/04_smoke_runbook.md`: weekly live smoke process and reporting template.
- `docs/pack_enrichment_operations_v1.md`: owner-side reference for real pack/enrichment operations, canonical outputs, and owner/consumer boundaries.
- `docs/security_incident_runbook.md`: mandatory response for leaked credentials and repository remediation.
- `docs/08_goldset_v1.md`: AI gold set build, verification, and live E2E usage.
- `docs/10_program_kpis.md`: locked KPI definitions and smoke acceptance thresholds.
- `docs/smoke_reports/`: versioned smoke reports (`smoke.report.v1`).

## Audit And Execution Tracking

- `docs/05_audit_reference.md`: current state, target posture, explicit debt, and decision baseline.
- `docs/codex_execution_plan.md`: execution discipline and next approved workstreams.
- `docs/20_execution/integration_log.md`: active inter-repo entries (real entries only).
- `docs/20_execution/archive/`: archived or pedagogical execution material (not current-state source of truth).

## Documentation Hygiene Rules

- Keep one source of truth per topic: update existing documents before creating new ones.
- Keep stable contracts separate from evolving posture: avoid restating the same current-vs-target gap in every page.
- Any change to canonical IDs, schema versions, export contract, or CI must update `README.md` and `docs/05_audit_reference.md`.
- Any strategic gate reordering must update `README.md`, `docs/05_audit_reference.md`, and `docs/codex_execution_plan.md` together.
- Do not keep obsolete gate-transition material once a gate is fully closed and absorbed into the baseline.
- Keep document names stable; use ADRs for irreversible architecture decisions.
- Versioned reports must never contain raw secrets or non-redacted `database_url` values.
