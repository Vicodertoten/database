---
owner: vicodertoten
status: stable
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/distractor-ai-proposals-v1.md
scope: foundation
---

# Distractor AI Proposals V1

## Purpose

This document defines the contract, role, and constraints for AI-generated
distractor proposals in the Vicodertoten biodiversity learning platform.

AI proposals are the **third priority source** for `DistractorRelationship` candidates,
after iNaturalist similar species and taxonomic neighbors.

---

## Role of AI

The AI acts as a **pedagogical ranker and gap filler**, not as a taxonomic authority.

Its two jobs are:

1. **Rank existing candidates** (from iNat or taxonomy) by pedagogical plausibility.
2. **Propose additional candidates** when the existing candidate set is too small
   or misses obvious confusion species.

The AI **must not**:

- Override canonical taxonomy.
- Assert that a taxon exists if it is not in the provided pool or registry.
- Invent identifiers, taxon IDs, or canonical names.
- Act as the primary source when iNat and taxonomic neighbors are sufficient.

---

## Source Priority

| Priority | Source | Trigger |
|---|---|---|
| 1 | iNaturalist similar species | Always preferred when populated |
| 2 | Taxonomic neighbors (genus → family → order) | Used when iNat hints absent or insufficient |
| 3 | AI pedagogical proposal (this doc) | Used when sources 1+2 yield too few candidates |

The AI may also be used to **re-rank** candidates from sources 1 and 2 before
question compilation — this is a future ranking pass, not modeled here.

---

## AI Input Context

The following context must be provided to the AI prompt:

| Field | Description |
|---|---|
| `target_scientific_name` | Accepted scientific name of the target taxon |
| `target_common_names` | Common names by language (e.g., `{"en": [...], "fr": [...]}`) |
| `organism_group` | e.g. `birds` |
| `region_hint` | Optional — e.g. `Belgium` — provided as context, **not as a hard filter** |
| `inat_similar_candidates` | List of names from iNat similar_taxa (may be empty) |
| `taxonomic_neighbor_candidates` | List of names from same-genus/family/order neighbors |
| `canonical_taxon_pool` | List of all canonical taxon names available in the dataset |
| `referenced_taxon_pool` | List of referenced taxon names available (may be empty) |
| `learner_level` | Target learner level: `beginner` / `intermediate` / `advanced` / `expert` / `mixed` |
| `desired_difficulty` | Target difficulty: `easy` / `medium` / `hard` / `expert` |

Region is informational only. Distractors outside the target region are allowed
if pedagogically useful.

---

## AI Output Schema

The AI must return a strict JSON object matching
`schemas/distractor_ai_proposal_v1.schema.json`.

Top-level fields:

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Always `"distractor_ai_proposal_v1"` |
| `prompt_version` | string | Version of the prompt used (e.g. `"v1.0"`) |
| `target_scientific_name` | string | Echo of the target name |
| `ranked_existing_candidates` | array | Candidates from sources 1+2, ranked by AI |
| `proposed_additional_candidates` | array | New candidates not in existing lists |
| `overall_notes` | string or null | Free-text notes from the AI |
| `confidence` | number | Overall confidence `[0.0, 1.0]` |

Each candidate object (both arrays):

| Field | Type | Required | Description |
|---|---|---|---|
| `scientific_name` | string | yes | Accepted scientific name |
| `source_reference` | string or null | no | e.g. `"inaturalist_similar_species"` or `"ai_proposal"` |
| `rank` | integer | yes | Rank within this proposal (1 = most pedagogically useful) |
| `confusion_types` | array | yes | From controlled enum (see below) |
| `pedagogical_value` | string | yes | `high` / `medium` / `low` / `unknown` |
| `difficulty_level` | string | yes | `easy` / `medium` / `hard` / `expert` |
| `learner_level` | string | yes | `beginner` / `intermediate` / `advanced` / `expert` / `mixed` |
| `reason` | string | yes | Pedagogical justification |
| `confidence` | number | yes | Per-candidate confidence `[0.0, 1.0]` |

### Controlled confusion_type values

```
visual_similarity, same_genus, same_family, same_order, same_size, same_shape,
same_color_pattern, same_habitat, same_behavior, same_season, same_life_stage,
beginner_common_confusion, expert_fine_confusion, local_species_confusion,
name_similarity, ecological_association
```

---

## Validation Gate

Before any AI proposal is used:

1. **Schema validation** — output must parse against `distractor_ai_proposal_v1.schema.json`.
2. **Scientific name check** — each `scientific_name` must be resolved against:
   - canonical taxon pool (→ `candidate_taxon_ref_type = canonical_taxon`)
   - referenced taxon pool (→ `candidate_taxon_ref_type = referenced_taxon`)
   - if neither: `candidate_taxon_ref_type = unresolved_taxon`
3. **Unresolved candidates** — allowed at AI output level, but must not be promoted to
   `validated` status until a human expert or future harvest resolves them.
4. **No auto-validate** — AI proposals always land as `candidate` or `needs_review`,
   never `validated` directly.

---

## Hallucination Risks

AI models may confidently name species that:

- Do not exist in the registry.
- Exist in other regions and have no localized name.
- Have been synonymized or split since the training data cutoff.
- Share a common name but differ in scientific name.

Mitigations:

- Always validate scientific names against the canonical + referenced pool.
- Treat any name not in the registry as `unresolved_taxon`.
- Use `confidence` field to surface low-certainty proposals for human review.
- Do not bypass `status = candidate` based on AI confidence alone.

---

## Scientific Name Validation

The AI prompt instructs the model to:

- Use the scientific name exactly as provided in the canonical or referenced pool.
- Never invent a name.
- If proposing a name not in the given pool, mark it clearly as a suggestion
  requiring validation.

Post-processing must re-validate all output names regardless of AI confidence.

---

## Unresolved Candidate Handling

If a proposed `scientific_name` is not in the canonical or referenced pool:

- Set `candidate_taxon_ref_type = unresolved_taxon`.
- Set `status = needs_review`.
- Add to `referenced_taxon_shell_needed` tracking for future harvest.
- Block from any use in compiled question options until resolved.

---

## No Taxonomic Override

The AI must not:

- Reassign a taxon to a different genus, family, or order.
- Assert synonymy or split/merge relationships.
- Override `accepted_scientific_name` of any canonical or referenced taxon.
- Produce taxonomy as a primary source of truth.

All taxonomy truth comes from iNaturalist + the canonical charter.

---

## Future Relation to Differential Feedback

In future phases, user session confusion signals may inform distractor quality:

- Distractor hit rate → can refine `pedagogical_value`.
- Confusion pair co-occurrence → can validate or strengthen `confusion_types`.
- Learner difficulty signal → can calibrate `difficulty_level`.

The AI proposal layer is a **supply-time** step. Differential feedback is a
**demand-time** refinement. They operate on the same `DistractorRelationship`
record and do not overlap functionally.

---

## Prompt Draft V1.0

The following prompt is the first draft for AI pedagogical distractor proposals.
It must be used with structured output mode (JSON mode enforced at the API level).

```
You are a pedagogical expert for a biodiversity learning platform.
Your job is to help rank and propose distractor species for a species identification quiz.

You will be given:
- A target species (the correct answer in a quiz)
- A list of existing candidate distractors from iNaturalist and taxonomy
- The pool of available canonical and referenced taxa
- Learner level and desired difficulty

Your tasks:
1. Rank the existing candidates by pedagogical usefulness (most confusable first).
2. Propose up to 5 additional candidates ONLY if the existing list has fewer than 3
   strong candidates or has obvious omissions.

Rules:
- Return ONLY valid JSON matching the schema. No prose, no markdown fences.
- Do NOT invent taxonomy. Do NOT assert scientific names as correct unless they appear
  in the canonical pool, referenced pool, or existing candidate list.
- If you propose a name not in the given pools, acknowledge uncertainty in the reason
  and set confidence below 0.7.
- Use only these confusion_type values: visual_similarity, same_genus, same_family,
  same_order, same_size, same_shape, same_color_pattern, same_habitat, same_behavior,
  same_season, same_life_stage, beginner_common_confusion, expert_fine_confusion,
  local_species_confusion, name_similarity, ecological_association
- Use only these pedagogical_value values: high, medium, low, unknown
- Use only these difficulty_level values: easy, medium, hard, expert
- Use only these learner_level values: beginner, intermediate, advanced, expert, mixed
- Prefer candidates already in the given lists. Propose additional only when useful.
- If uncertain about a candidate, lower confidence and explain in reason.
- region_hint is context only. Do not exclude species solely because they are
  outside the region if they are pedagogically useful.

Return JSON with this top-level structure:
{
  "schema_version": "distractor_ai_proposal_v1",
  "prompt_version": "v1.0",
  "target_scientific_name": "<echo>",
  "ranked_existing_candidates": [ ... ],
  "proposed_additional_candidates": [ ... ],
  "overall_notes": "<string or null>",
  "confidence": <float 0.0-1.0>
}

Each candidate object:
{
  "scientific_name": "<string>",
  "source_reference": "<string or null>",
  "rank": <integer starting at 1>,
  "confusion_types": ["<enum>", ...],
  "pedagogical_value": "<enum>",
  "difficulty_level": "<enum>",
  "learner_level": "<enum>",
  "reason": "<string>",
  "confidence": <float 0.0-1.0>
}
```
