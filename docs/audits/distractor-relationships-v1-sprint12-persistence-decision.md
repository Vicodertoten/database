---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-sprint12-persistence-decision.md
scope: audit
---

# Distractor Relationships V1 Sprint 12 Persistence Decision

## Decision Labels

- PERSIST_DISTRACTOR_RELATIONSHIPS_V1
- DEFER_PERSISTENCE_NEEDS_MORE_ENRICHMENT
- DEFER_PERSISTENCE_NEEDS_NAME_COMPLETION
- DEFER_PERSISTENCE_NEEDS_REFERENCED_TAXON_REVIEW
- DEFER_PERSISTENCE_USE_ARTIFACTS_ONLY_FOR_NOW

## Purpose

Decide whether Sprint 12 DistractorRelationship candidates are ready to persist.
This decision is based on Sprint 12 evidence from phases A to E and does not
apply writes in this phase.

## Sprint 11 Blocker Recap

- 0 iNaturalist similar-species candidates in generation outputs.
- 43 candidates missing French names.
- 0/50 targets with >=3 FR-usable candidates.
- Readiness outcome remained blocked for first corpus distractor gate.

## Phase A Root Cause

Source evidence:
- docs/audits/evidence/inat_similarity_enrichment_gap_audit.json

Findings:
- Root cause: SIMILAR_HINTS_REQUIRE_API_REFRESH
- Decision: READY_FOR_INAT_TAXON_REFRESH
- Wrong endpoint in baseline snapshots caused similar hints to be absent.

## Phase B Enrichment Results

Source evidence:
- docs/audits/evidence/inat_similarity_enrichment_sprint12.json

Key metrics:
- Total similarity hints extracted: 323
- Hints mapped to existing canonical taxa: 119
- Hints unmapped: 204
- Decision: NEEDS_REFERENCED_TAXON_SHELL_PREP

## Phase C Localized Names Results

Source evidence:
- docs/audits/evidence/taxon_localized_names_enrichment_sprint12.json

Key metrics:
- FR names added: 50
- NL names added: 50
- Conflicts: 0
- Candidates still missing FR (in canonical pool): 0
- Decision: READY_FOR_DISTRACTOR_READINESS_RERUN

## Phase D Referenced Shell Results

Source evidence:
- docs/audits/evidence/referenced_taxon_shell_needs_sprint12.json
- docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json

Key metrics:
- Total iNat candidate taxa assessed: 198
- Mapped to canonical taxa: 42
- New referenced shells needed: 156
- Ambiguous: 0
- Ignored: 0
- Shell creation mode: dry_run
- Decision: NEEDS_REFERENCED_TAXON_STORAGE_WORK

## Phase E Readiness Comparison

Source evidence:
- docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json
- docs/audits/evidence/distractor_readiness_v1_sprint12.json
- docs/audits/evidence/distractor_readiness_sprint11_vs_sprint12.json
- docs/audits/distractor-readiness-sprint11-vs-sprint12.md

Sprint 11 -> Sprint 12 deltas:
- iNat similar count: 0 -> 323 (delta +323)
- Total candidates: 244 -> 407 (delta +163)
- Targets ready: 0 -> 39 (delta +39)
- Targets blocked: 50 -> 11 (delta -39)
- Targets with >=3 candidates: 26 -> 49 (delta +23)
- Targets with >=3 FR-usable candidates: 0 -> 39 (delta +39)
- Missing French names: 43 -> 156 (delta +113)
- Taxonomic-only dependency: 26 -> 1 (delta -25)
- Same-order dependency: 17 -> 1 (delta -16)
- Emergency fallback generated: no

Comparison decision:
- NEEDS_MORE_TAXON_NAME_ENRICHMENT

## Current Candidate Relationship Quality

Strengths:
- Strong iNat contribution now present (323 iNat-sourced candidates).
- Major readiness improvement over Sprint 11.
- No unresolved candidate references in Sprint 12 artifact.
- No emergency diversity fallback generated.

Limitations:
- Candidate records currently include audit-only fields that fail strict schema validation.
  - Against schemas/distractor_relationship_v1.schema.json:
    - 407/407 records fail due additionalProperties false and extra audit fields.
- 156 relationships reference virtual referenced taxon IDs requiring reviewed storage strategy.
- French label coverage remains a blocking quality signal at candidate-level scale.

## Persistence Criteria Assessment

- Meaningful iNaturalist or taxonomic coverage: PASS
  - 323 iNaturalist-sourced candidates and 407 total generated candidates.
- Enough candidates have FR names: PARTIAL
  - 39 targets with >=3 FR-usable candidates, but 156 candidates still miss FR names.
- Unresolved candidates are low or clearly marked: PASS
  - unresolved_candidate_count = 0, targets_not_ready explicitly listed.
- Referenced shell strategy is clear: PARTIAL
  - Need count is 0 for this snapshot, but 156 referenced shell candidates require reviewed storage/apply strategy before persistence.
- No emergency fallback needed: PASS
  - no_emergency_diversity_fallback_generated = true.
- Candidate JSON validates against distractor_relationship_v1 schema: FAIL
  - 407/407 fail strict schema due additionalProperties.
- Readiness materially improved over Sprint 11: PASS
  - targets_ready: 0 -> 39, iNat similar: 0 -> 323, blocked: 50 -> 11.

## Persistence Risks

1. Schema compliance risk:
- Current Sprint 12 candidate records are not directly persistable against
  distractor_relationship_v1 schema without projection/normalization.

2. Referenced dependency risk:
- 156 referenced taxon dependencies are represented as shell candidates,
  but standalone reviewed creation/apply pathway is not yet in place.

3. Label quality risk:
- Missing French names remain high in expanded candidate set (156),
  reducing first-corpus confidence for persisted outputs.

4. Governance risk:
- Persisting before dependency and schema normalization would lock unstable
  relationships and increase rollback complexity.

## Recommended Decision

Decision label:
- DEFER_PERSISTENCE_USE_ARTIFACTS_ONLY_FOR_NOW

Rationale:
- Evidence shows meaningful progress and better coverage, but persistence
  criteria are not fully satisfied yet due schema non-compliance, outstanding
  referenced-taxon storage workflow, and label-quality blockers at scale.

Action for next sprint:
- Keep Sprint 12 generated JSON artifacts as source of truth for analysis.
- Do not persist DistractorRelationship rows in this phase.
- Resolve blockers before any write approval.

## Exact Blockers To Clear Before Persist

1. Create a schema-compliant projection for relationship persistence records.
2. Implement and review referenced taxon shell apply path (dry-run/apply, audit trail).
3. Reduce missing FR names in the expanded candidate pool.
4. Re-run Phase E comparison and confirm decision upgrade.
