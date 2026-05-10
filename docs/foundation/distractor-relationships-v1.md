---
owner: vicodertoten
status: stable
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/distractor-relationships-v1.md
scope: foundation
---

# Distractor Relationships V1 — Foundation

## Purpose

This document defines the domain model and governance rules for pedagogical
distractor relationships in the Vicodertoten biodiversity learning platform.

A **DistractorRelationship** is a governed relation between a **target taxon** and a
**candidate distractor taxon**. It represents the upstream knowledge that a given taxon is a
plausible pedagogical distractor for a given target — before any question is compiled
or any pack is materialized.

---

## Relationship vs Question Option

A `DistractorRelationship` is **not** a question option and **not** a runtime object.

| Concept | What it is | Owner |
|---|---|---|
| `DistractorRelationship` | A governed pedagogical relation between taxa | `database` |
| `QuestionOption` / Golden Pack option | A compiled or materialized option in a question | `database` (compile-time / artifact materialization) |
| Runtime option display | Presentation order among already-provided options | `runtime` |

The relationship layer is upstream of compile-time. It feeds the compiler, which then
produces `QuestionOption` entries. The compiler consumes relationships; it does not own them.

For the current runtime stack, runtime may display options that are already
present in `session_snapshot.v2` or in the `golden_pack.v1` fallback artifact.
Runtime must not select, replace, add, score, or remap distractor taxa.

---

## Source Hierarchy

Distractor candidates are sourced in strict priority order:

1. **`inaturalist_similar_species`** — iNaturalist "similar species" hints from canonical
   taxon enrichment. First-priority because they are community-validated visual lookalikes.
2. **`taxonomic_neighbor_same_genus`** — Same genus, not explicitly similar. Second priority.
3. **`taxonomic_neighbor_same_family`** — Same family, not same genus. Third priority.
4. **`taxonomic_neighbor_same_order`** — Same order, not same family. Fourth priority.
5. **`ai_pedagogical_proposal`** — AI-proposed distractors based on pedagogical plausibility.
   AI is sovereign for pedagogical plausibility but not for taxonomic truth.
6. **`manual_expert`** — Human expert override. Always takes precedence when present.
7. **`emergency_diversity_fallback`** — Last-resort fallback for corpus coverage. See below.

The `source_rank` field captures the priority position within a given source tier.
Lower `source_rank` = higher priority.

---

## Taxon Shell / Referenced Taxon Strategy

Not all candidate distractors will be resolved to a canonical taxon in this repository.
Three resolution levels exist:

### `canonical_taxon`
The candidate is a fully resolved canonical taxon in this repo.
- `candidate_taxon_ref_id` must be set to the `canonical_taxon_id`.
- Full playable corpus availability can be checked at compile time.

### `referenced_taxon`
The candidate is known from an external source (e.g. iNaturalist) but not yet canonicalized.
A `ReferencedTaxon` shell exists, providing scientific name and source mapping.
- `candidate_taxon_ref_id` must be set to the `referenced_taxon_id`.
- May lack localized names or media; compile-time availability check required.

### `unresolved_taxon`
The candidate is known by scientific name only. No resolved reference exists yet.
- `candidate_taxon_ref_id` must be `null`.
- `candidate_scientific_name` is required.
- Status must be `needs_review` or `unavailable_missing_taxon`.
- Cannot be `validated`.

---

## `candidate_taxon_ref_type` Design Rationale

A single opaque `candidate_taxon_id` field was explicitly rejected.

Using a typed `candidate_taxon_ref_type` + `candidate_taxon_ref_id` pair allows:
- Strict validation rules per resolution level.
- Clear audit trail for unresolved candidates.
- Compile-time availability checks that know which lookup table to consult.
- Future promotion path: unresolved → referenced → canonical.

---

## AI Role

AI (e.g. Gemini) may propose distractor candidates via `ai_pedagogical_proposal`.

AI is **sovereign for pedagogical plausibility** — it can judge whether two species are
visually or behaviorally confusable for a learner at a given level.

AI is **not sovereign for taxonomic truth** — it cannot define canonical identity,
create canonical taxa, or redefine scientific names.

AI proposals enter at `status=candidate` and require human or automated validation
before reaching `status=validated`.

AI proposals are Sprint 11 Phase 3+ scope. They are not implemented in Phase 1.

---

## Diversity Fallback Policy

`emergency_diversity_fallback` exists solely as an emergency / audit / debug source.

**Hard constraints:**
- `emergency_diversity_fallback` relationships **cannot** have `status=validated`.
- `emergency_diversity_fallback` relationships **must not** be used for the first corpus
  candidate.
- They exist only to identify coverage gaps during audit and as last-resort placeholders.

Using diversity fallback distractors in a real learning session would produce random,
pedagogically unmotivated confusion — which is harmful to learning outcomes.

---

## Regional Scope Decision

Distractor relationships are **not hard-blocked by geographic region** at the relationship
layer.

Rationale:
- A distractor can be pedagogically valuable even if the species does not occur in the
  learner's region (e.g. learning to distinguish closely related species globally).
- Regional filtering, if needed, belongs at compile time or artifact
  materialization, not in the upstream relationship definition.
- Hard-blocking by region at the relationship layer would silently discard useful candidates
  for cross-regional or global learning contexts.

---

## Future Layer — Differential Feedback

`DistractorRelationship` does not generate learner feedback in this phase.

However, its fields are explicitly designed to support future post-answer differential
explanations. When a learner selects a distractor, database-authored feedback or
a future audited feedback contract could use:

- The **target image PMP profile** (visible field marks, limitations).
- The **correct taxon** (target).
- The **selected distractor taxon** (candidate).
- The **`confusion_types`** and **`reason`** fields from the relationship.
- The **visible image features** from the media qualification profile.

This design allows future "why is this not X?" feedback without requiring the relationship
layer to encode full explanatory text now.

---

## Non-Goals

The following are explicitly **not** in scope for this foundation:

- Runtime session logic, scoring, or progression.
- Golden Pack materialization or compile-time distractor selection.
- `QuestionOption` generation (downstream concern).
- Supabase/Postgres schema migrations (not required at this stage).
- AI proposal implementation (Phase 3+).
- OCR / screenshot detection.
- Localized name resolution at the relationship layer.
- Default behavior changes in existing pipelines.

---

## Schema

`schemas/distractor_relationship_v1.schema.json`

## Domain model

`src/database_core/domain/models.py` — `DistractorRelationship`

## Enums

`src/database_core/domain/enums.py`:
- `DistractorRelationshipSource`
- `DistractorRelationshipStatus`
- `CandidateTaxonRefType`
- `DistractorConfusionType`
- `DistractorLearnerLevel`
- `DistractorPedagogicalValue`
- `DistractorDifficultyLevel`
