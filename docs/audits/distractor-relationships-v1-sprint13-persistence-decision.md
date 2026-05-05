---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-sprint13-persistence-decision.md
scope: audit
---

# Distractor Relationships V1 Sprint 13 Persistence Decision

## Decision Labels

- PERSIST_DISTRACTOR_RELATIONSHIPS_V1
- READY_FOR_AI_RANKING_AND_PROPOSALS
- READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE
- DEFER_PERSISTENCE_NEEDS_REFERENCED_TAXON_REVIEW
- DEFER_PERSISTENCE_NEEDS_NAME_COMPLETION
- DEFER_PERSISTENCE_USE_ARTIFACTS_ONLY_FOR_NOW

## Purpose

Decide whether Sprint 13 DistractorRelationship candidates are ready to persist.
This decision is based on Sprint 13 evidence from phases A to D and the Sprint 12
vs Sprint 13 readiness comparison. No writes are applied in this phase.

## Sprint 12 Blocker Recap

Sprint 12 deferred persistence (DEFER_PERSISTENCE_USE_ARTIFACTS_ONLY_FOR_NOW) due
to four unresolved blockers:

1. Candidate records failed strict schema validation against distractor_relationship_v1
   (407/407 rejected due to additionalProperties).
2. Referenced taxon shell storage and apply path was not reviewed or implemented.
3. Missing French name rate remained high in the expanded candidate pool (156 candidates).
4. Persistence would lock unstable relationships before dependency normalization.

Sprint 13 phases A through D were designed to clear these blockers.

## Phase A — Schema-Compliant Projection

Source evidence:
- docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json
- docs/audits/distractor-relationships-v1-projection-sprint13.md

Key metrics:
- Input records: 407
- Projected records: 407
- Rejected records: 0
- Schema validation errors: 0
- Decision: READY_FOR_REFERENCED_TAXON_SHELL_APPLY_PATH

Outcome: Sprint 12 blocker 1 cleared. All 407 candidates project cleanly
against distractor_relationship_v1 schema with zero rejections. Projection
strips audit-only fields and assigns stable relationship IDs.

## Phase B — Localized Names Foundation

Source evidence:
- docs/audits/evidence/taxon_localized_names_sprint13_apply.json
- docs/audits/evidence/taxon_localized_names_sprint13_audit.json
- docs/audits/taxon-localized-names-sprint13-apply.md
- docs/audits/taxon-localized-names-sprint13-audit.md
- docs/foundation/taxon-localized-names-enrichment-v1.md

Key metrics:
- Patches applied: 44
- Conflicts: 0
- Invalid patches: 0
- Unresolved: 0
- Skipped (same-value EN): 44
- Confidence distribution: low (44/44, provisional seeds)
- Source: manual_override (44/44)

Outcome: Localized names system is in place for both canonical and referenced
taxa. Sprint 13D applied 44 provisional French-name seeds using scientific names
as placeholders. All seeds are confidence=low and require human review replacement
before production use. The system architecture is sound; quality completion is
deferred.

## Phase C — Referenced Taxon Shell Apply Plan

Source evidence:
- docs/audits/evidence/referenced_taxon_shell_apply_plan_sprint13.json
- docs/audits/referenced-taxon-shell-apply-plan-sprint13.md

Key metrics:
- Input candidates assessed: 198
- Mapped to canonical taxa: 42
- Existing referenced records: 0
- New shell plan count: 156
- Ambiguous: 0
- Ignored: 0
- Shells with FR name: 0
- Shells missing FR name: 156
- Mode: dry_run
- Decision: NEEDS_NAME_COMPLETION_FOR_SHELLS

Outcome: Sprint 12 blocker 2 partially cleared. A reviewed, auditable dry-run
apply plan exists for all 156 referenced shell candidates. Rollback notes are
present per record. The plan has not been executed; shell creation remains pending
human approval of FR name seeds for those records.

## Phase D — Priority FR Name Completion and Readiness Rerun

Source evidence:
- docs/audits/evidence/distractor_readiness_v1_sprint13.json
- docs/audits/evidence/distractor_readiness_sprint12_vs_sprint13.json
- docs/audits/distractor-readiness-sprint12-vs-sprint13.md
- data/manual/taxon_localized_name_patches_sprint13.csv

Key metrics (Sprint 13 readiness):
- Targets ready: 47
- Targets blocked: 3
- Targets missing localized names: 2
- Targets insufficient distractors: 1
- Targets needing iNat enrichment: 0
- Targets needing referenced taxon shells: 0
- Candidates missing FR name: 112
- Decision (readiness engine): INSUFFICIENT_DISTRACTOR_COVERAGE

Sprint 12 vs Sprint 13 deltas:
- Targets ready: 39 -> 47 (delta +8)
- Targets blocked: 11 -> 3 (delta -8)
- Targets with >=3 FR-usable candidates: 39 -> 47 (delta +8)
- Missing French names: 156 -> 112 (delta -44)
- Shell candidates with FR seed: 0 -> 44 (delta +44)
- Emergency fallback count: 0 -> 0 (delta 0)
- Taxonomic-only dependency: 1 -> 1 (delta 0)
- iNat usable candidate count: 119 -> 201 (delta +82)
- Comparison decision: READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE

Outcome: Sprint 12 blocker 3 substantially reduced. Missing FR rate dropped from
50.1% to 29.9%, below the 30% threshold. 47 targets now have >=3 FR-usable
candidates, sufficient for a 30-target first corpus gate. The 44 applied FR seeds
remain provisional and require human review.

## Criteria Assessment

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Projected records validate against distractor_relationship_v1 with 0 errors | PASS | 0 errors, 0 rejected (Phase A) |
| 2 | Referenced shell apply path exists and is audited | PARTIAL | Dry-run plan exists; shells not yet created (Phase C) |
| 3 | Ambiguous referenced taxa are blocked or reviewed | PASS | ambiguous_count=0 (Phase C) |
| 4 | Localized names system exists for canonical + referenced taxa | PASS | System in place; 44 seeds applied (Phase B) |
| 5 | >=30 targets have >=3 FR-usable candidates | PASS | 47 targets qualify (Phase D) |
| 6 | Emergency diversity fallback remains 0 | PASS | emergency_fallback_count=0 (Phase D) |
| 7 | Unresolved records are not marked usable | PASS | unresolved status=needs_review in projection (Phase A) |
| 8 | Rollback/dry-run/apply behavior is documented | PARTIAL | Shell apply is dry_run; apply script + rollback notes present but not executed |
| 9 | Persistence risk is low enough | PARTIAL | 44 FR seeds are provisional; referenced shells unwritten |

Summary: 6 PASS, 3 PARTIAL, 0 FAIL.

All hard blockers from Sprint 12 are cleared. Remaining partials concern the
execution of the shell apply step and the quality of provisional FR seeds. These
are acceptable for a first corpus gate but not yet sufficient for permanent
DistractorRelationship persistence.

## Decision

**READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE**

Rationale:
- All schema compliance blockers are cleared (criterion 1: PASS).
- Ambiguity is zero and unresolved records are correctly flagged (criteria 3, 7: PASS).
- Localized names system is operational (criterion 4: PASS).
- 47 targets qualify for the gate, exceeding the 30-target minimum (criterion 5: PASS).
- No emergency fallback was generated (criterion 6: PASS).
- The referenced shell apply plan is documented and auditable but not yet applied.
  Actual shell creation is blocked on FR name quality review (criterion 2: PARTIAL).
- 44 provisional FR seeds use scientific names as placeholders with confidence=low.
  These must be replaced with correct common names before production label usage
  (criteria 8, 9: PARTIAL).

The comparison decision (READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE) is confirmed.
Full persistence (PERSIST_DISTRACTOR_RELATIONSHIPS_V1) is not yet warranted because
the shell apply path has not been executed and provisional FR seeds are unreviewed.

## Persistence Risks

1. Provisional FR seed risk:
   44 applied FR name seeds use the scientific name as a placeholder French label
   with confidence=low. These would surface as incorrect French labels if used
   directly in a corpus without human review replacement.

2. Referenced shell creation risk:
   156 shell records are planned but not created. Distractor relationships that
   reference these shells will remain in needs_review status until shells exist
   and FR names are assigned.

3. Missing FR label risk:
   112 candidates still lack a French name. At 29.9% missing-FR ratio, enough
   targets qualify for the first corpus gate, but the long-tail gap reduces the
   candidate pool depth for less-covered targets.

4. Governance risk:
   Persisting DistractorRelationship rows before referenced shells are applied would
   require either accepting needs_review rows in the corpus or post-hoc updates
   when shells are created, increasing rollback complexity.

## Recommended Decision

Decision label: **READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE**

Action:
- Do not persist DistractorRelationship rows in this phase.
- Proceed to first corpus distractor gate using Sprint 13 artifacts as source of truth.
- Assign human reviewers to validate and replace the 44 provisional FR seeds.
- Execute the referenced shell apply plan (dry_run -> apply) after FR seed review.
- After shell apply completes, re-evaluate criteria 2, 8, 9 for full persistence.

## Exact Next Actions

1. Human review: Replace 44 provisional FR name seeds in
   data/manual/taxon_localized_name_patches_sprint13.csv with correct French
   common names. Confidence must be upgraded to high before corpus use.
2. Shell apply: After FR seed review, re-run
   scripts/prepare_referenced_taxon_shell_apply_plan_v1.py in apply mode (dry_run=false)
   to materialize 156 referenced taxon shells.
3. First corpus gate: Select >=30 targets from the 47 ready targets and execute
   the distractor gate pipeline using distractor_readiness_v1_sprint13.json.
4. Re-evaluate persistence: After steps 1–2, re-run criteria assessment.
   If criteria 2, 8, 9 pass, issue PERSIST_DISTRACTOR_RELATIONSHIPS_V1.
