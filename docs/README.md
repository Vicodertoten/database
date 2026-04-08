# Documentation Index

This index is the canonical entrypoint for repository documentation.
Before adding a new document, update an existing one whenever possible.

## Start Here

- `README.md`: quickstart, operational commands, output contracts.
- `docs/05_audit_reference.md`: living execution baseline and delivery priorities.

## Domain And Architecture

- `docs/00_scope.md`: pilot scope and non-goals.
- `docs/01_domain_model.md`: domain entities and contracts.
- `docs/02_pipeline.md`: pipeline stages and invariants.
- `docs/06_charte_canonique_v1.md`: canonical governance policy (normative).
- `docs/07_canonical_id_migration_v1.md`: canonical ID migration mapping and cutover policy.
- `docs/adr/0001-charte-canonique-v1.md`: implementation ADR for canonical governance v1.

## Operations

- `docs/04_smoke_runbook.md`: weekly live smoke process and reporting template.
- `docs/08_goldset_v1.md`: AI gold set build, verification, and live E2E usage.

## Audit And Execution Tracking

- `docs/05_audit_reference.md`: single source of truth for current status and roadmap.
- `docs/09_remediation_execution.md`: active remediation directive linked to the audit baseline.

## Documentation Hygiene Rules

- Keep one source of truth per topic: update existing documents before creating new ones.
- Any change to canonical IDs, schema versions, export contract, or CI must update `README.md` and `docs/05_audit_reference.md`.
- Keep document names stable; use ADRs for irreversible architecture decisions.
