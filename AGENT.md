# AGENT.md

This file defines the operating rules for automated agents and contributors working in this repository.

## 1. Repository identity

`database` is **not** the final product backend.
It is the **knowledge core** of a future biodiversity learning platform.

Its job is to:
- maintain an internal canonical taxon reference,
- ingest and normalize traceable naturalist data,
- qualify media for pedagogical reuse,
- derive playable learning surfaces,
- define versioned learning packs,
- compile deterministic builds and frozen materializations,
- preserve governance, provenance, and auditability.

Its job is **not** to implement:
- runtime sessions,
- answer submission,
- scoring,
- progression,
- user state,
- UX-facing runtime orchestration.

## 2. Absolute architectural boundaries

These rules are mandatory.

1. **Do not turn this repo into the runtime backend.**
2. `runtime` concerns must stay outside this repository.
3. `database` owns data surfaces, not live gameplay execution.
4. The runtime must **never** read `export.bundle.v4` directly.
5. Do not twist export contracts to satisfy runtime shortcuts.
6. Compilation must remain deterministic on already-ingested data.
7. Enrichment must remain asynchronous and traceable.
8. External sources may feed the system, but must not freely define internal identity.

## 3. Current scope

Current implementation is intentionally narrow:
- birds only,
- iNaturalist-first,
- image-first qualification,
- pilot-scale but structurally serious.

Do not implicitly broaden scope in code or docs.
If you extend scope (new taxa, new sources, new media families), make the change explicit in:
- domain model,
- validation contracts,
- docs,
- tests,
- migration strategy.

## 4. Canonical invariants

The internal canonical layer is the strategic core of the repository.
Protect it.

Mandatory rules:
- `canonical_taxon_id` represents a stable internal concept, not a name.
- Accepted scientific names may change; canonical identity must not silently drift.
- Taxonomic transitions must remain explicit and auditable.
- `provisional` taxa must not silently leak into pedagogical export surfaces.
- AI may enrich, but must not arbitrarily mutate identity-level fields.
- Automatic canonical creation remains governed by the canonical charter.

Before touching canonical behavior, read:
- `docs/06_charte_canonique_v1.md`
- `docs/adr/0001-charte-canonique-v1.md`
- `docs/07_canonical_id_migration_v1.md`

## 5. Playable / pack / compilation boundaries

The repository already includes downstream learning-data surfaces.
Do not confuse them.

- `playable_items` = reusable learning-ready corpus entries.
- `pack` = durable, versioned editorial specification.
- `compiled build` = deterministic question set derived from a pack revision.
- `materialization` = frozen derivative snapshot for a concrete use.
- `runtime session` = out of scope here.

Important current reality:
- the **target** playable model is cumulative and incremental,
- the **current** implementation still rebuilds a latest materialized playable surface on each pipeline run.

Do not hide this gap.
Do not write docs that pretend it is already solved.
Do not build new product logic on top of this gap without making it explicit.

## 6. Known strategic debt

The following debt is real and must not be obscured:

1. `PostgresRepository` currently concentrates too many responsibilities.
2. The playable persistence model is not yet in its final target shape.
3. The repo is richer than a simple pipeline, but still not a general product backend.
4. Sidecar transition surfaces must not be prolonged indefinitely without explicit decision.

If you modify code around these areas:
- state the debt explicitly,
- avoid abstract refactors without a concrete boundary goal,
- prefer incremental extraction over redesign theater.

## 7. Read-before-change order

Before changing anything structural, read at minimum:

- `README.md`
- `docs/README.md`
- `docs/00_scope.md`
- `docs/01_domain_model.md`
- `docs/02_pipeline.md`
- `docs/05_audit_reference.md`
- `docs/06_charte_canonique_v1.md`
- `docs/10_program_kpis.md`
- `docs/codex_execution_plan.md`
- `src/database_core/domain/models.py`
- `src/database_core/domain/enums.py`
- `src/database_core/pipeline/runner.py`
- `src/database_core/export/json_exporter.py`
- `src/database_core/storage/postgres.py`
- `src/database_core/storage/postgres_schema.py`
- `src/database_core/qualification/policy.py`
- `src/database_core/qualification/engine.py`

If your change touches packs, also read pack-related tests and storage methods.
If your change touches governance, also read governance/review tests.

## 8. Change discipline

Every structural change must keep these five dimensions aligned:
- code,
- schema/migrations,
- tests,
- documentation,
- contracts/version markers.

Do not merge or commit a structural change that updates only one of these dimensions.

When you add or change:
- a persistent surface,
- a version token,
- a CLI command,
- a schema contract,
- a governance rule,
- a KPI or inspect surface,

you must update all affected docs and checks.

## 9. Contracts and versioning

This repository uses explicit version markers.
Respect them.

When a contract changes:
- update the relevant version token,
- update the relevant schema if applicable,
- update docs,
- update tests,
- describe whether the change is additive, breaking, or transitional.

Do not silently change the semantics of a versioned surface.
Do not leave docs implying backward compatibility if there is none.

## 10. Migrations and storage

Storage is PostgreSQL/PostGIS-backed and schema-versioned.

Rules:
- no ad hoc schema drift,
- no hidden persistence contract changes,
- no manual table edits without migration logic,
- no weakening of audit/history surfaces without explicit rationale.

If you introduce a persistent concept, decide clearly whether it is:
- latest state,
- append-only history,
- immutable derived artifact,
- operator queue,
- aggregate surface.

Do not blur those categories.

## 11. Testing expectations

At minimum, meaningful changes should preserve or extend:
- unit coverage of domain invariants,
- integration coverage of storage behavior,
- contract validation where relevant,
- doc/code coherence where relevant.

Use the repository verification path:

```bash
python scripts/verify_repo.py
```

If your change affects migrations or database behavior, also validate migration flow explicitly.

## 12. Documentation expectations

Do not use documentation as aspiration-only marketing.
Documentation must distinguish clearly between:
- what exists now,
- what is target,
- what is debt,
- what is intentionally out of scope.

`docs/05_audit_reference.md` and `README.md` must stay aligned with reality.
If the implementation is partial, say so explicitly.

## 13. What to avoid

Do not:
- add session or scoring logic,
- add user-progress state,
- introduce runtime-only shortcuts,
- let external data redefine internal identity,
- hide strategic debt,
- refactor broadly without operational gain,
- overstate maturity in docs,
- conflate exported data with playable/runtime-ready data.

## 14. What good changes look like

Good changes in this repo usually:
- strengthen canonical governance,
- improve provenance and auditability,
- improve qualification rigor,
- improve playable/packs/build/materialization consistency,
- reduce ambiguity between layers,
- improve deterministic reproducibility,
- improve institutional credibility without pulling runtime concerns inside.

## 15. Definition of done for structural work

A structural change is done only if:
- code is coherent,
- storage/migration story is explicit,
- tests cover the intended behavior,
- docs reflect reality,
- versioned contracts are handled correctly,
- repository boundaries remain intact.

If any of those is missing, the change is incomplete.
