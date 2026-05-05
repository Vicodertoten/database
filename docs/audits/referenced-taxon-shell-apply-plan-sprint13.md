---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/referenced-taxon-shell-apply-plan-sprint13.md
scope: audit
---

# Referenced Taxon Shell Apply Plan — Sprint 13C

## Purpose

Create a governed dry-run/apply pathway for ReferencedTaxon shells needed by distractor candidates.

## Inputs

- docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json
- docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json
- Sprint 13B localized name audit/patch artifacts when available
- canonical/referenced stores when available

## Shell Creation Rules

- mapped canonical candidates never create shells
- existing referenced taxa are reused
- source_taxon_id + scientific_name creates shell plan
- missing scientific_name becomes ambiguous or ignored
- ambiguous rows require manual review and are never auto-applied
- no canonical promotion

## Breakdown

- input_candidates_count: 198
- mapped_to_canonical_count: 42
- existing_referenced_count: 0
- new_shell_plan_count: 156
- ambiguous_count: 0
- ignored_count: 0

## Localized Name Status

- shells_with_fr_name_count: 0
- shells_missing_fr_name_count: 156

## Dry-Run/Apply Status

- dry_run: True
- decision: NEEDS_NAME_COMPLETION_FOR_SHELLS
- execution_status: complete

## Risks

- ambiguous taxa require manual adjudication before apply
- missing FR names reduce FR distractor usability
- source_taxon_id conflicts require review before mutation

## Next Phase Recommendation

- complete FR naming pipeline before enabling FR-first distractor readiness

## Rollback Notes

- Before apply, create timestamped backup of referenced snapshot.
- Rollback by restoring the backup file if apply output is rejected in review.
- For targeted rollback, remove rows created by this run_date and source_taxon_id set.
