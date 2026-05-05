---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/AUDIT_INDEX.md
scope: audit_index
---

# Audit Index

This index classifies audit documents and evidence artifacts that support the
current Golden Pack and runtime handoff direction.

It is not an audit report and not a runtime specification. Current operational
direction is defined in `docs/architecture/MASTER_REFERENCE.md`. Audit documents
remain preserved as evidence, decision history, and traceability.

## Classification Vocabulary

| Class | Meaning |
|---|---|
| `active_evidence` | Still directly supports the current Golden Pack/runtime decision state. |
| `historical_active` | Historical audit retained because a current decision depends on it. |
| `superseded` | Preserved for history, but later evidence or canonical docs now narrow or replace its conclusion. |
| `evidence_json` | Machine-readable evidence supporting one or more audit decisions. |
| `canonical_replacement` | Current canonical document that governs future work instead of the audit narrative. |

## Current Canonical Documents

| Document | Class | Governs |
|---|---|---|
| `docs/architecture/MASTER_REFERENCE.md` | `canonical_replacement` | Golden Pack MVP direction, artifact-only runtime handoff, closure criteria |
| `docs/foundation/localized-name-source-policy-v1.md` | `canonical_replacement` | MVP localized-name display policy |
| `docs/foundation/taxon-localized-names-enrichment-v1.md` | `canonical_replacement` | Localized-name enrichment and apply-plan workflow |
| `docs/foundation/distractor-relationships-v1.md` | `canonical_replacement` | DistractorRelationship domain model and persistence guardrails |
| `docs/foundation/pedagogical-media-profile-v1.md` | `canonical_replacement` | PMP descriptive media profile contract |
| `docs/foundation/pmp-qualification-policy-v1.md` | `canonical_replacement` | PMP usage policy interpretation |

## Current Decision State

| Decision | Current value | Primary support |
|---|---:|---|
| `READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE` | true | Sprint 13 distractor audits |
| `READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS` | true | Sprint 14B runtime handoff audits |
| `PERSIST_DISTRACTOR_RELATIONSHIPS_V1` | false | Sprint 13 persistence decision |
| `DATABASE_PHASE_CLOSED` | false | Sprint 14A closure inventory and Master Reference |

## Active Evidence Audits

| Audit | Class | Proves / Supports | Notes |
|---|---|---|---|
| `docs/audits/distractor-relationships-v1-sprint13.md` | `historical_active` | Sprint 13 closure, 407 projected records, first corpus distractor gate readiness | Preserved as historical active evidence, not a Golden Pack spec. |
| `docs/audits/distractor-relationships-v1-sprint13-persistence-decision.md` | `active_evidence` | Persistence remains deferred; first corpus gate may proceed artifact-only | Current source for `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=false`. |
| `docs/audits/database-phase-closure-inventory.md` | `active_evidence` | Corpus gate, persistence, closure, and runtime handoff are separate decisions | Current source for `DATABASE_PHASE_CLOSED=false` before Golden Pack/UI proof. |
| `docs/audits/database-integrity-runtime-handoff-audit.md` | `active_evidence` | Runtime contracts can proceed with warnings; names policy is source-attested and artifact-driven | Current source for Sprint 14B integrity posture. |
| `docs/audits/sprint14b-final-runtime-handoff-readiness.md` | `active_evidence` | 32 safe targets observed, minimum 30 met, emergency fallback zero | Current compact readiness summary. |
| `docs/audits/localized-name-projection-vs-14b-audit-reconciliation.md` | `active_evidence` | Dry-run/apply/audit plan hashes match | Supports apply-plan-based readiness. |

## Superseded Or Narrowed Audits

| Audit | Class | Superseded / Narrowed By | Keep Because |
|---|---|---|---|
| `docs/audits/distractor-relationships-v1-sprint12-persistence-decision.md` | `superseded` | Sprint 13 persistence decision | Shows why persistence was originally deferred. |
| `docs/audits/distractor-readiness-v1-sprint12.md` | `superseded` | Sprint 13 readiness and comparison | Baseline for readiness delta. |
| `docs/audits/distractor-readiness-sprint12-vs-sprint13.md` | `historical_active` | Master Reference narrows MVP use to Golden Pack artifact | Still supports the first corpus gate decision. |
| `docs/audits/taxon-localized-names-sprint13-audit.md` | `superseded` | Sprint 14 localized-name apply plan and source policy | Documents provisional seed state and earlier blockers. |
| `docs/audits/taxon-localized-names-sprint13-apply.md` | `superseded` | Sprint 14 source-attested apply plan | Documents earlier patch mechanics and low-confidence seed risk. |
| `docs/audits/taxon-localized-names-multisource-sprint14-dry-run.md` | `historical_active` | `localized_name_apply_plan_v1.json` and runtime handoff audit | Shows transition to single decision engine. |

## Evidence JSON Index

| Evidence artifact | Class | Supports |
|---|---|---|
| `docs/audits/evidence/database_integrity_runtime_handoff_audit.json` | `evidence_json` | Sprint 14B runtime contract readiness with warnings |
| `docs/audits/evidence/localized_name_apply_plan_v1.json` | `evidence_json` | Source-attested localized-name decisions, safe-ready target derivation |
| `docs/audits/evidence/localized_name_projection_vs_14b_audit_reconciliation.json` | `evidence_json` | Plan hash reconciliation and dry-run/apply consistency |
| `docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json` | `evidence_json` | Schema-compliant projected distractor records |
| `docs/audits/evidence/distractor_readiness_v1_sprint13.json` | `evidence_json` | First corpus distractor readiness |
| `docs/audits/evidence/distractor_readiness_sprint12_vs_sprint13.json` | `evidence_json` | Readiness delta from Sprint 12 to Sprint 13 |
| `docs/audits/evidence/referenced_taxon_shell_apply_plan_sprint13.json` | `evidence_json` | Referenced shell dry-run plan and non-creation state |
| `docs/audits/evidence/sprint14b_final_runtime_handoff_readiness.json` | `evidence_json` | Final Sprint 14B readiness synthesis |
| `docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json` | `evidence_json` | PMP policy warning categories and media-policy calibration risks |

## Documents Not To Use As Runtime Specifications

The following documents remain useful, but must not be treated as the MVP runtime
artifact contract:

- `docs/foundation/runtime-consumption-v1.md`
- `docs/foundation/domain-model.md` pack v1/v2 sections
- `docs/foundation/pipeline.md` Gate 8-10 playable/pack/materialization sections
- Sprint 12/13 distractor audit narratives
- Sprint 13 localized-name seed audits

For MVP runtime work, use:

1. `docs/architecture/MASTER_REFERENCE.md`
2. future `golden_pack.v1` schemas/specifications
3. `data/exports/golden_packs/belgian_birds_mvp_v1/manifest.json`
4. `data/exports/golden_packs/belgian_birds_mvp_v1/pack.json`
5. `data/exports/golden_packs/belgian_birds_mvp_v1/validation_report.json`

## Non-Actions

- Do not delete historical audits.
- Do not move evidence JSON during the Golden Pack documentation pass.
- Do not infer persistence approval from corpus gate readiness.
- Do not infer database closure from runtime contract readiness.
- Do not use archived or superseded audits as direct runtime implementation
  specs.
