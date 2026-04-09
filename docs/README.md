# Documentation Index

This index is the canonical entrypoint for repository documentation.
Before adding a new document, update an existing one whenever possible.

## Start Here

- `README.md`: quickstart, operational commands, output contracts.
- `docs/05_audit_reference.md`: living execution baseline and delivery priorities.
- `docs/codex_execution_plan.md`: sequential execution plan with the post-Gate 4 corrective gate.

## Domain And Architecture

- `docs/00_scope.md`: pilot scope and non-goals.
- `docs/01_domain_model.md`: domain entities and contracts.
- `docs/02_pipeline.md`: pipeline stages and invariants.
- `schemas/playable_corpus_v1.schema.json`: contract schema for `playable_corpus.v1`.
- `schemas/pack_spec_v1.schema.json`: contract schema for `pack.spec.v1`.
- `schemas/pack_diagnostic_v1.schema.json`: contract schema for `pack.diagnostic.v1`.
- `schemas/pack_compiled_v1.schema.json`: contract schema for `pack.compiled.v1`.
- `schemas/pack_materialization_v1.schema.json`: contract schema for `pack.materialization.v1`.
- `docs/06_charte_canonique_v1.md`: canonical governance policy (normative).
- `docs/07_canonical_id_migration_v1.md`: canonical ID migration mapping and cutover policy.
- `docs/adr/0001-charte-canonique-v1.md`: implementation ADR for canonical governance v1.
- `docs/adr/0002-noyau-canonique-fort-execution-sequentielle.md`: execution ADR locking gates, canonical policy, and export transition.
- `docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`: doctrinal boundaries for playable/pack compilation/enrichment chain.

## Operations

- `docs/04_smoke_runbook.md`: weekly live smoke process and reporting template.
- `docs/08_goldset_v1.md`: AI gold set build, verification, and live E2E usage.
- `docs/10_program_kpis.md`: locked KPI definitions and smoke acceptance thresholds.
- `docs/smoke_reports/`: versioned smoke reports (`smoke.report.v1`).

## Audit And Execution Tracking

- `docs/05_audit_reference.md`: single source of truth for current status and roadmap.
- `docs/codex_execution_plan.md`: actionable gate sequence (one gate at a time).

## Documentation Hygiene Rules

- Keep one source of truth per topic: update existing documents before creating new ones.
- Any change to canonical IDs, schema versions, export contract, or CI must update `README.md` and `docs/05_audit_reference.md`.
- Any strategic gate reordering must update `README.md`, `docs/05_audit_reference.md`, and `docs/codex_execution_plan.md` together.
- Keep document names stable; use ADRs for irreversible architecture decisions.
