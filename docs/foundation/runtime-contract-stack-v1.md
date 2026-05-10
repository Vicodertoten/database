---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/foundation/runtime-contract-stack-v1.md
scope: durable_artifact_inventory
---

# Durable Artifact Inventory V1

This document is a broad inventory of durable artifact versions across
`database` and `runtime-app`. It is not the runtime contract-status source of
truth. Current contract status, runtime role, and archive/deprecation decisions
are canonical in `docs/architecture/contract-map.md`.

Scope here is limited to schema-backed artifacts and stable version constants
used as handoff, storage, runtime, or owner/operator boundaries. One-off
audit/report/evidence outputs are intentionally out of scope.

`session_snapshot.v2` is an exported product contract. It is not the internal
dynamic session compiler domain model. Internal compiler concepts and the
allowed product-constant boundary are documented in
`docs/foundation/dynamic-session-compiler-internals-v1.md`.

## Current Runtime Stack

Canonical status: `docs/architecture/contract-map.md`.

`runtime-app` starts quiz sessions from owner-produced local artifacts. The
active playable runtime contract is `session_snapshot.v2`, generated from a
validated local `serving_bundle.v1` or loaded from frozen regression fixtures.
`golden_pack.v1` remains available only as the fallback runtime contract when
Dynamic Pack mode is disabled or unavailable.

Runtime never reads owner raw data, owner Postgres, live external providers, or
audit evidence as quiz input. Runtime may select among already provided
bundle/snapshot data, persist session state, score answers by `selectedOptionId`,
and export answer signals back to `database`.

## Artifact Inventory

| Contract | Owner | Consumer | Purpose | Status | Source-of-truth schema | Stability class | Deprecation path |
|---|---|---|---|---|---|---|---|
| `database.schema.v20` | `database` | `database` storage/services | Current Postgres schema version and migration boundary. | Active storage boundary | Version constant in `src/database_core/versioning.py`; migrations in `src/database_core/storage/postgres_migrations.py` | Internal stable | Superseded only by the next explicit schema migration version. |
| `inaturalist.snapshot.v3` | `database` | `database` ingestion/normalization | Raw iNaturalist snapshot manifest version. | Active owner input | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future snapshot manifest version. |
| `normalized.snapshot.v3` | `database` | `database` pipeline/storage | Normalized snapshot artifact version after source ingestion. | Active owner intermediate | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future normalized snapshot version. |
| `canonical.enrichment.v2` | `database` | `database` pipeline/export | Canonical enrichment payload version. | Active owner intermediate | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future enrichment version. |
| `qualification.staged.v1` | `database` | `database` pipeline/export | Staged qualification result version. | Active owner intermediate | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future qualification version. |
| `export.bundle.v4` | `database` | Owner export/inspection only | Qualified resources bundle export; forbidden as live runtime input. | Active owner export / runtime-forbidden | `schemas/qualified_resources_bundle_v4.schema.json` | Stable owner export | Replaces legacy bundle; future export versions must be explicit. |
| `qualified_resources_bundle.legacy` | `database` | Historical owner export/inspection | Legacy qualified resources bundle schema without a locked export version. | Historical | `schemas/qualified_resources_bundle.schema.json` | Legacy | Retain for old fixtures only; do not use for new runtime or owner handoff work. |
| `review.override.v1` | `database` | `database` pipeline/operator | Snapshot-scoped manual review override file version. | Active owner/operator | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future review override version. |
| `pedagogical_media_profile.v1` | `database` | `database` qualification/policy | Generic descriptive media profile contract. | Active qualification contract | `schemas/pedagogical_media_profile_v1.schema.json` | Stable owner contract | Replaces bird-specific AI review as the preferred qualification profile. |
| `pmp_qualification_policy.v1` | `database` | `database` qualification/export | Policy interpretation layer for PMP profile usability and downstream eligibility. | Active qualification policy | `docs/foundation/pmp-qualification-policy-v1.md`; version constant in `src/database_core/qualification/pmp_policy_v1.py` | Stable owner policy | Superseded only by a future PMP policy version. |
| `pedagogical_image_profile.v1` | `database` | `database` qualification/export | Derived image-focused pedagogical profile used by current pipeline logic. | Active internal profile | Version constant in `src/database_core/qualification/pedagogical_image_profile.py` | Internal stable | May be narrowed or retired after PMP fully replaces image-specific logic. |
| `bird_image_pedagogical_review.v1.2` | `database` | `database` AI qualification adapter | Bird-image AI review payload contract. | Legacy / transitional | `schemas/bird_image_pedagogical_review_v1_2.schema.json` | Legacy stable | Retain for compatibility; prefer `pedagogical_media_profile.v1` for new qualification work. |
| `distractor_ai_proposal_v1` | `database` | `database` distractor review tooling | AI proposal payload for candidate distractor relationships. | Active owner/operator | `schemas/distractor_ai_proposal_v1.schema.json` | Experimental owner contract | Can be replaced when distractor proposal workflow is revised. |
| `distractor_relationship.v1` | `database` | `database` pack/session compilers | Governed distractor relationship between target and candidate taxon. | Active owner domain contract | `schemas/distractor_relationship_v1.schema.json` | Stable owner contract | Future versions must preserve compiled option lineage or provide migration. |
| `taxon_localized_name_patch.v1` | `database` | `database` localized-name enrichment | Manual/localized name patch entries for canonical and referenced taxa. | Active owner/operator | `schemas/taxon_localized_name_patch_v1.schema.json` | Internal stable | Superseded by a normalized multilingual names subsystem. |
| `playable_corpus.v1` | `database` | Owner/operator tools; historical owner-read consumers | Owner-prepared playable item corpus with minimal player-ready metadata. | Internal / historical owner-read | `schemas/playable_corpus_v1.schema.json` | Legacy/internal stable | Keep for lineage and old owner-read context; not a current runtime target. |
| `pack.spec.v1` | `database` | `database` pack tooling | Pack specification/revision contract. | Active owner contract | `schemas/pack_spec_v1.schema.json` | Stable owner contract | Superseded only by a future pack spec version. |
| `pack.diagnostic.v1` | `database` | `database` pack tooling/operator | Deterministic pack compilability diagnostic. | Active owner/operator | `schemas/pack_diagnostic_v1.schema.json` | Stable owner contract | Superseded only by a future diagnostic version. |
| `pack.create.v1` | `database` | `database` CLI/operator | Pack creation operation payload. | Active owner operation | `schemas/pack_create_v1.schema.json` | Internal stable | Superseded by a future operation contract. |
| `pack.diagnose.v1` | `database` | `database` CLI/operator | Pack diagnosis operation payload. | Active owner operation | `schemas/pack_diagnose_operation_v1.schema.json` | Internal stable | Superseded by a future operation contract. |
| `pack.compile.v1` | `database` | `database` CLI/operator | Pack compile operation payload. | Active owner operation | `schemas/pack_compile_operation_v1.schema.json` | Internal stable | Superseded by a future operation contract. |
| `pack.materialize.v1` | `database` | `database` CLI/operator | Pack materialization operation payload. | Active owner operation | `schemas/pack_materialize_operation_v1.schema.json` | Internal stable | Superseded by a future operation contract. |
| `pack.compiled.v1` | `database` | Historical owner-read consumers | Deterministic compiled pack build. | Historical / strategic-later | `schemas/pack_compiled_v1.schema.json` | Legacy stable | Keep for lineage and old owner-read context; not a current runtime target. |
| `pack.materialization.v1` | `database` | Historical owner-read consumers | Frozen materialization derived from a compiled v1 build. | Historical / strategic-later | `schemas/pack_materialization_v1.schema.json` | Legacy stable | Keep for lineage and old owner-read context; not a current runtime target. |
| `pack.compiled.v2` | `database` | `database` reference docs/tests | `QuestionOption[]` compiled-pack semantics reference. | Transitional semantic reference | `schemas/pack_compiled_v2.schema.json` | Legacy semantic reference | Do not use as the Dynamic Pack runtime handoff. |
| `pack.materialization.v2` | `database` | `database` reference docs/tests | `QuestionOption[]` materialization semantics reference. | Transitional semantic reference | `schemas/pack_materialization_v2.schema.json` | Legacy semantic reference | Superseded by `session_snapshot.v2` for playable dynamic runtime handoff. |
| `pack_pool.v1` | `database` | `database` dynamic compiler/export | Owner-side dynamic source pool used to build serving bundles and session snapshots. | Active owner-only | `schemas/pack_pool_v1.schema.json` | Stable owner contract | Runtime must not consume directly; future pool versions must be explicit. |
| `session_snapshot.v1` | `database` | `database`/historical runtime fixtures | Phase 2A target-only dynamic session proof surface. | Historical proof surface | `schemas/session_snapshot_v1.schema.json` | Legacy stable | Superseded by `session_snapshot.v2` for playable runtime use. |
| `session_snapshot.v2` | `database` | `runtime-app` | Frozen playable quiz session with questions, media, option order, labels, correctness, feedback, and distractor metadata. | Active runtime | `schemas/session_snapshot_v2.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/session_snapshot_v2.schema.json` | Product runtime contract | Stable for current Dynamic Pack runtime; future product changes require a new session snapshot version. |
| `serving_bundle.v1` | `database` | `runtime-app` | Local serving-ready bundle runtime can project into a fresh `session_snapshot.v2` at session start. | Active runtime input | `schemas/serving_bundle_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/serving_bundle_v1.schema.json` | Product runtime input | Stable active input; future bundle changes require a new serving bundle version. |
| `golden_pack.v1` | `database` | `runtime-app` | Promoted artifact-only Golden Pack quiz payload. | Runtime fallback | `schemas/golden_pack_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/golden_pack_v1.schema.json` | Product fallback contract | Retain until Dynamic Pack fallback is no longer needed. |
| `golden_pack_manifest.v1` | `database` | `database` operator/audit | Golden Pack artifact identity, gates, warnings, checksums, and evidence links. | Active fallback operator file | `schemas/golden_pack_manifest_v1.schema.json` | Stable operator contract | Retain while Golden Pack fallback is retained. |
| `golden_pack_validation_report.v1` | `database` | `database` operator/audit | Golden Pack validation report with warnings, blockers, and diagnostics. | Active fallback operator file | `schemas/golden_pack_validation_report_v1.schema.json` | Stable operator contract | Retain while Golden Pack fallback is retained. |
| `enrichment.enqueue.v1` | `database` | `database` CLI/operator | Enrichment enqueue operation payload. | Active owner operation | `schemas/enrichment_enqueue_v1.schema.json` | Internal stable | Superseded by a future enrichment operation contract. |
| `enrichment.execute.v1` | `database` | `database` CLI/operator | Enrichment execution operation payload. | Active owner operation | `schemas/enrichment_execute_v1.schema.json` | Internal stable | Superseded by a future enrichment operation contract. |
| `enrichment.request.status.v1` | `database` | `database` CLI/operator | Enrichment request status operation payload. | Active owner operation | `schemas/enrichment_request_status_v1.schema.json` | Internal stable | Superseded by a future enrichment operation contract. |
| `confusion.event.v1` | `database` | `database` confusion ingestion/storage | Directed confusion event version. | Active owner learning signal | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future confusion event version. |
| `confusion.aggregate.v1` | `database` | `database` metrics/storage | Directed confusion aggregate version. | Active owner aggregate | Version constant in `src/database_core/versioning.py` | Internal stable | Superseded by a future confusion aggregate version. |
| `runtime_answer_signals.v1` | `runtime-app` | `database` | Batch export of answered runtime questions for owner confusion ingestion. | Active runtime-to-owner handback | `schemas/runtime_answer_signals_v1.schema.json`; mirrored in `runtime-app/packages/contracts/schemas-owner/runtime_answer_signals_v1.schema.json` | Product handback contract | Stable active handback; future telemetry shape changes require a new version. |
| `fixed_challenge.v1` | `database` | Planned runtime/product consumers | Planned fixed quiz experience generated from the same compiler boundary. | Planned / no schema | No schema yet | Planned product contract | Must receive a schema before implementation or runtime consumption. |
| `assignment_materialization.v1` | `database` | Planned institutional/runtime consumers | Planned fixed assignment artifact generated from the same compiler boundary. | Planned / no schema | No schema yet | Planned product contract | Must receive a schema before implementation or runtime consumption. |

## Forbidden Runtime Inputs

`runtime-app` must not use these as quiz input:

- `export.bundle.v4`
- owner Postgres or owner internal tables
- owner raw data, run directories, audit evidence, apply plans, or unresolved candidates
- `golden_pack_manifest.v1` and `golden_pack_validation_report.v1`
- live iNaturalist, Gemini, or other enrichment providers
- `pack_pool.v1` directly
- owner-side runtime-read HTTP surfaces unless a future decision explicitly reopens them

## Operational Rules

- `database` remains the source of truth for contract schemas and semantics.
- `runtime-app` mirrors only schemas needed for local validation and TypeScript types.
- Runtime may assemble sessions, persist state, score submitted option ids, and
  export answer signals.
- Runtime must not invent labels, replace distractors, map taxa, recalculate
  media policy, generate feedback, or repair owner data.
- Historical references to `pack.materialization.v2` or owner-read surfaces are
  allowed only when clearly marked historical, owner-only, or strategic-later.
- Product constants for `session_snapshot.v2` belong at materialization,
  export, validation, or runtime-consumption boundaries, not in generic domain
  or canonical model code.
