---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-qualification-policy-v1-sprint7-audit.md
scope: audit
---

# Sprint 7 audit - pmp_qualification_policy.v1

## Purpose

Audit the first PMP-native qualification policy layer and verify that PMP
outcomes can be converted into database-usable policy statuses without
reintroducing legacy AIQualification coupling or runtime/materialization fields.

## Scope

In scope:
- deterministic policy evaluation for PMP outcomes,
- evidence-type-aware usage policy statuses,
- policy audit over Sprint 6 controlled snapshot outputs,
- doctrine guardrails (no runtime/feedback pollution),
- threshold sanity checks.

Out of scope:
- runtime selection,
- pack materialization,
- selectedOptionId behavior,
- feedback generation,
- distractors,
- production rollout.

## Policy version

- `pmp_qualification_policy.v1`

## Source evidence

- policy foundation: `docs/foundation/pmp-qualification-policy-v1.md`
- policy module: `src/database_core/qualification/pmp_policy_v1.py`
- policy snapshot audit script: `scripts/audit_pmp_policy_v1_snapshot.py`
- evidence JSON:
  `docs/audits/evidence/pmp_policy_v1_sprint7_snapshot_audit.json`
- source snapshot id:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`

## Thresholds used (v1 heuristic)

Base usage thresholds:
- eligible >= 70,
- borderline 50-69,
- not_recommended < 50,
- not_applicable when usage is not meaningful for evidence type or score missing.

Evidence-type overrides:
- indirect evidence: basic identification is generally not recommended,
- species_card is stricter on indirect evidence,
- partial_organism and multiple_organisms apply stricter logic for targeted uses,
- whole_organism treats indirect_evidence_learning as non-primary unless score is high.

## Policy outputs

Policy emits a separate database policy layer with:
- `policy_status` (`profile_valid`, `profile_failed`, `pre_ai_rejected`, ...),
- per-usage `status`, `score`, `reason`,
- `eligible_database_uses`,
- `not_recommended_database_uses`,
- policy notes.

Policy does not emit runtime selection fields.

## Sprint 6 snapshot policy audit result

From `docs/audits/evidence/pmp_policy_v1_sprint7_snapshot_audit.json`:

- processed media: 120
- profile_valid: 106
- profile_failed: 10
- pre_ai_rejected: 4

Policy status distribution:
- profile_valid: 106
- profile_failed: 10
- pre_ai_rejected: 4

Usage eligibility counts:
- basic_identification: eligible 52, borderline 14, not_recommended 40, not_applicable 14
- field_observation: eligible 78, borderline 28, not_applicable 14
- confusion_learning: eligible 41, borderline 51, not_recommended 14, not_applicable 14
- morphology_learning: eligible 46, borderline 36, not_recommended 24, not_applicable 14
- species_card: eligible 52, borderline 18, not_recommended 36, not_applicable 14
- indirect_evidence_learning: eligible 7, borderline 7, not_applicable 106

Guardrail checks:
- runtime/feedback pollution detected: no
- high global score forcing basic_identification: no violations
- indirect evidence eligible for indirect_evidence_learning: yes

Clarification:
- `confusion_learning` here is an image/profile-level suitability signal for
  learning discriminative visual criteria.
- It is not a distractor-readiness signal.
- It does not mean similar species candidates or confusion-set generation are
  already available.

## Examples by evidence type

Observed examples include:
- whole_organism eligible for basic_identification,
- whole_organism non-eligible for basic_identification but eligible for
  field_observation,
- feather eligible for indirect_evidence_learning,
- failed profile,
- pre-AI rejected outcome.

## What this policy enables

- deterministic, inspectable PMP-native qualification statuses,
- usage-specific database recommendations without collapsing into one "playable"
  decision,
- evidence-type-aware interpretation that preserves indirect-evidence usefulness,
- structured handoff for downstream systems to make later selection decisions.

## What remains out of scope

- runtime readiness and runtime-specific fields,
- pack and quiz final selection,
- materialization,
- feedback profile generation,
- cross-taxon routing policy expansion.

## Known limitations

- thresholds are heuristic and need broader-corpus calibration,
- current evidence is bird-focused even though the policy shape is generic,
- no production-scale rollout validation in Sprint 7.

## Threshold calibration warnings

- `field_observation` may be too permissive and needs calibration.
- `species_card` may be too permissive and likely needs stricter review.
- broader corpus audit may reveal bias by taxon and evidence type.
- human review is required before any policy promotion.

Open calibration questions now live in:
`docs/audits/pmp-policy-v1-open-questions.md`

## Decision

**`READY_FOR_BROADER_PROFILED_CORPUS_WITH_POLICY`**

Decision criteria satisfied:
- policy classifies Sprint 6 outcomes,
- no runtime fields emitted,
- indirect evidence handled sensibly,
- high global score alone does not over-select,
- usage distributions are plausible,
- tests and checks pass.

## Next-step recommendation

Sprint 8 should run a broader profiled corpus audit with the same policy layer,
then calibrate thresholds using targeted human review before any default-policy
promotion.
