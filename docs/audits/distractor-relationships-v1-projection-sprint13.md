---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-projection-sprint13.md
scope: audit
---

# Distractor Relationships V1 Projection — Sprint 13A

## Purpose

Project Sprint 12 candidate artifacts into strict DistractorRelationship V1 records that validate against schema without changing schema permissiveness.

## Input Artifact

- Candidates: docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json
- Schema: schemas/distractor_relationship_v1.schema.json

## Projection Rules

- Remove audit-only fields and keep only schema-defined DistractorRelationship fields.
- Preserve source, source_rank, target taxon, candidate scientific name, status, reason, confusion_types, difficulty_level, learner_level, pedagogical_value.
- Preserve canonical_taxon and unresolved_taxon typing as-is when valid.
- Preserve referenced_taxon only when referenced_taxon_id is stable in referenced storage snapshot.
- Downgrade virtual/unapplied referenced_taxon to unresolved_taxon with status normalized to needs_review when required by model rules.
- Reject invalid records explicitly with reasons; never silently drop.

## Records Projected

- Input records: 407
- Projected records: 407
- Rejected records: 0

## Records Rejected

- Rejection distribution: {}

## Schema Validation Result

- schema_validation_error_count: 0
- Requirement target: 0

## Blockers for Persistence

- Projection now isolates schema-compliant records, but referenced taxon shell apply path remains required before persisting unresolved/referenced edges safely.
- Any rejected records must be triaged before persistence batch planning.

## Recommended Next Phase

- Decision: READY_FOR_REFERENCED_TAXON_SHELL_APPLY_PATH
- Next: Proceed to reviewed referenced taxon shell apply path before persistence writes.
