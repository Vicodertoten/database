---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-sprint8-audit.md
scope: audit
---

# Sprint 8 audit - broader profiled corpus audit preparation + human review preparation

## Purpose

Close the remaining post-Sprint-7 gaps, improve policy evidence quality, and
prepare PMP policy calibration through a high-quality human review sample.

## Scope

In scope:
- pre-Sprint-8 policy/export/doc fixes,
- policy audit metadata/taxon joins,
- taxon-level policy summaries,
- human review CSV/JSONL export,
- broader corpus run preparation,
- Sprint 6 real-output re-audit with improved tooling.

Out of scope:
- runtime changes,
- materialization,
- pack generation,
- production rollout,
- feedback or distractor implementation,
- default behavior change.

## Pre-Sprint-8 fixes completed

- exported PMP policy public API from `database_core.qualification`,
- clarified `confusion_learning` as image/profile-level suitability only,
- added threshold calibration warnings,
- documented open calibration questions,
- improved policy audit with scientific-name and taxon joins,
- added taxon-level summary outputs,
- created deterministic human review export,
- created deterministic subset builder for a future broader controlled snapshot.

## Policy audit improvements

Sprint 8 policy audit now includes:
- `metadata_join_status`,
- `scientific_name`, `canonical_taxon_id`, `source_taxon_id`,
- taxon label examples in audit samples,
- `count_by_taxon`,
- `profile_valid_count_by_taxon`,
- `profile_failed_count_by_taxon`,
- `pre_ai_rejected_count_by_taxon`,
- `policy_status_distribution_by_taxon`,
- `eligible_database_uses_by_taxon`,
- `usage_eligibility_by_taxon`,
- `evidence_type_distribution_by_taxon`,
- bounded taxon summaries for review.

## Taxon / scientific-name join status

For Sprint 8 audit on the Sprint 6 controlled snapshot:
- `metadata_join_status = joined_from_manifest`
- examples now include scientific name and taxon labels.

## Broader corpus status

Status: **prepared, deferred**

- No broader PMP `ai_outputs.json` snapshot was identified in the current
  workspace.
- A deterministic subset builder and exact broader-run command are now ready.
- No broader live Gemini run was executed in this Sprint 8 pass.

See:
- `docs/audits/pmp-policy-v1-sprint8-plan.md`
- `scripts/build_controlled_inat_snapshot_subset.py`

## Snapshot audited in Sprint 8

Audited snapshot:
- `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`

Evidence output:
- `docs/audits/evidence/pmp_policy_v1_sprint8_snapshot_audit.json`

## Policy distribution summary

From Sprint 8 policy audit evidence:
- processed media: 120
- profile_valid: 106
- profile_failed: 10
- pre_ai_rejected: 4
- doctrine pollution: 0
- high-global-score guardrail violations: 0
- indirect evidence eligible cases present: yes

Usage eligibility distribution:
- basic_identification: eligible 52, borderline 14, not_recommended 40, not_applicable 14
- field_observation: eligible 78, borderline 28, not_applicable 14
- confusion_learning: eligible 41, borderline 51, not_recommended 14, not_applicable 14
- morphology_learning: eligible 46, borderline 36, not_recommended 24, not_applicable 14
- species_card: eligible 52, borderline 18, not_recommended 36, not_applicable 14
- indirect_evidence_learning: eligible 7, borderline 7, not_applicable 106

## Taxon coverage summary

- taxon_count: 36
- top taxa by media count:
  - `taxon:birds:000009` -> 9
  - `taxon:birds:000008` -> 7
  - `taxon:birds:000017` -> 7
  - `taxon:birds:000033` -> 6
  - `taxon:birds:000022` -> 6

Examples of taxa without eligible `basic_identification`:
- `taxon:birds:000013` (5)
- `taxon:birds:000011` (4)
- `taxon:birds:000005` (3)

Examples of taxa with high failure rate:
- `taxon:birds:000026` -> 0.50 (2 / 4)
- `taxon:birds:000020` -> 0.50 (1 / 2)
- `taxon:birds:000021` -> 0.50 (1 / 2)

## Evidence-type coverage summary

Observed in audited snapshot:
- whole_organism: 92
- multiple_organisms: 7
- nest: 3
- feather: 2
- habitat: 1
- dead_organism: 1
- unknown: 14 (failed + pre-AI/non-profile-evaluated rows)

## Known threshold concerns

Sprint 8 keeps thresholds unchanged but documents the main concerns:
- `field_observation` may be too permissive,
- `species_card` may be too permissive,
- `confusion_learning` remains image-level only and must not be interpreted as
  distractor readiness,
- broader corpus plus human review is needed before any threshold promotion.

## Human review sample summary

Outputs:
- `docs/audits/human_review/pmp_policy_v1_human_review_sample.csv`
- `docs/audits/human_review/pmp_policy_v1_human_review_sample.jsonl`
- `docs/audits/human_review/pmp_policy_v1_human_review_readme.md`

Generated sample:
- deterministic seed: 42
- review items: 40
- metadata_join_status: `joined_from_manifest`
- distinct taxa represented: 23
- policy status mix:
  - profile_valid: 35
  - profile_failed: 4
  - pre_ai_rejected: 1
- evidence-type mix:
  - whole_organism: 26
  - multiple_organisms: 3
  - nest: 3
  - feather: 1
  - habitat: 1
  - dead_organism: 1
  - blank/unknown: 5
- sample includes:
  - high-confidence eligible basic-identification examples,
  - borderline basic-identification examples,
  - not-recommended basic but eligible field-observation examples,
  - species-card eligible and questionable examples,
  - confusion-learning eligible examples,
  - indirect-evidence-learning eligible examples,
  - failed PMP examples,
  - pre-AI example,
  - multiple taxa with real image URLs and local image paths.

## What remains out of scope

- broader live PMP run execution,
- runtime or materialization integration,
- distractor generation,
- policy threshold changes without calibration evidence,
- policy promotion to default behavior.

## Open questions

Tracked in:
- `docs/audits/pmp-policy-v1-open-questions.md`

## Final decision

**`READY_FOR_HUMAN_REVIEW_CALIBRATION`**

Rationale:
- human review CSV and JSONL were generated,
- policy audit now includes scientific-name/taxon joins,
- threshold limitations are documented,
- no doctrine regression detected,
- tests and checks pass,
- broader corpus execution is prepared but intentionally deferred.
