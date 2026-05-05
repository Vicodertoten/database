---
owner: database
status: ready_for_validation
generated_at: 2026-05-05
last_reviewed: 2026-05-05
source_of_truth: docs/audits/pmp-policy-v1-broader-400-human-review-analysis.md
scope: audit
---

# PMP policy v1 — Broader-400 human review analysis

## Purpose

Analyze the human review of the broader PMP policy qualification run
(`palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`) to identify
calibration issues, schema false negatives, and policy patch candidates
for Sprint 9 Phase 2.

## Input file

`docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sheet.csv`

## Scope

- 400 media qualified, 60 sampled for human review.
- Human reviewer: one reviewer, manual pass.
- This analysis normalizes judgments, infers issue categories, and surfaces
  calibration candidates.

## What this analysis does and does not decide

- **Does**: surface patch candidates, categorize issues, compute metrics.
- **Does not**: change PMP schema, change policy thresholds, run Gemini,
  touch runtime or materialization.

---

## Review completion summary

| Metric | Value |
|---|---|
| Total rows | 60 |
| Rows with judgment | 58 |
| Rows with notes | 23 |
| Accept rate | 83.3% |

---

## Normalized judgment distribution

| Judgment | Count | % |
|---|---|---|
| accept | 50 | 83.3% |
| too_strict | 5 | 8.3% |
| too_permissive | 1 | 1.7% |
| reject | 0 | 0.0% |
| unclear | 2 | 3.3% |
| blank | 2 | 3.3% |

---

## Issue category distribution

| Issue category | Count |
|---|---|
| policy_accept | 41 |
| same_species_multiple_individuals_ok | 5 |
| schema_false_negative | 4 |
| multiple_species_target_unclear | 4 |
| pre_ai_borderline | 1 |
| field_observation_too_permissive | 1 |
| text_overlay_or_answer_visible | 1 |
| rare_model_subject_miss | 1 |
| species_card_too_permissive | 1 |
| habitat_too_permissive | 1 |

---

## Key findings

1. **Schema false negatives** (4 cases): `profile_failed` images
   that the human reviewer considers good or usable. Root cause is likely
   over-strict schema validation on certain field combinations.

2. **Multiple-species / target-taxon ambiguity** (4 unclear +
   5 same-species-ok): Policy needs a formal rule for
   `multiple_organisms` evidence distinguishing same-species groups (acceptable)
   from mixed-species frames where target identity is ambiguous (higher caution).

3. **Text overlay / answer visible** (1 cases): Screenshots showing
   species name or identification app UI must be detected and rejected or
   heavily penalized. Currently not handled.

4. **Habitat evidence permissiveness** (1 cases): Habitat images
   classified as `field_observation`-eligible when species cannot be inferred
   from image content alone.

5. **Species card and field observation concerns** (1 + 1 cases):
   Some `species_card` assignments appear too permissive for distant/silhouette
   shots; `field_observation` may be broad but is generally appropriate.

6. **Rare model-subject miss** (1 cases): AI assigned
   `evidence_type=unknown` on at least one image where a reviewer can see a
   very distant bird. Low frequency; not a new category priority.

7. **Pre-AI borderline** (1 cases): Image rejected before AI
   qualification; reviewer considers it borderline but prefers not to
   over-complicate the pipeline.

---

## Schema false negative summary

- `pmp-policy-review-0138` | Podiceps cristatus | `` | too_strict | bonne image a a travers des jumelles; compliqué/mpas meilleure qualité mais clai
- `pmp-policy-review-0283` | Podiceps cristatus | `` | too_strict | bonne image de l'espèce dans son nid en boule donc rare de la voir comme ca et p
- `pmp-policy-review-0284` | Larus argentatus | `` | too_strict | image moyenne mais clairement utilisable
- `pmp-policy-review-0213` | Coccothraustes coccothraustes | `` | blank | très bonne image a voir pourquoi elle ne passe pas

**Action:** investigate `profile_failed` root causes per item; candidate schema
patch if validation rules are over-strict on specific field combinations.

---

## Pre-AI borderline summary

- `pmp-policy-review-0335` | Phoenicurus ochruros | `` | blank | probablement une image pas assez large pour passer la pipeline. mais elle est gl

**Action:** consider slight relaxation of image size/resolution thresholds only
if pattern is consistent. Do not introduce new status classes.

---

## Target taxon / multi-species summary

### Multiple species — target unclear

- `pmp-policy-review-0148` | Cygnus olor | `multiple_organisms` | accept | trop de bordel dans la photo pour qu'elle soit bonne. multi espèces, mauvaise qu
- `pmp-policy-review-0044` | Anser anser | `multiple_organisms` | accept | plusieurs espèces différentes présentes, qualité bof, on est pas surs de quel in
- `pmp-policy-review-0176` | Cygnus olor | `multiple_organisms` | accept | plusieurs espèces sur la meme photo mais ok de définir celle qu'on doit identifi
- `pmp-policy-review-0097` | Cyanistes caeruleus | `multiple_organisms` | unclear | on doit préciser le comportement lorsqu'il y a plusieurs individus d'espèces DIF


### Same species — multiple individuals OK

- `pmp-policy-review-0157` | Falco peregrinus | `multiple_organisms` | too_strict | très bonne photo avec deux individus, un seul usage recommandé alors que bonne p
- `pmp-policy-review-0123` | Anas platyrhynchos | `multiple_organisms` | accept | —
- `pmp-policy-review-0376` | Riparia riparia | `multiple_organisms` | accept | —
- `pmp-policy-review-0242` | Sturnus vulgaris | `multiple_organisms` | accept | —
- `pmp-policy-review-0195` | Larus michahellis | `multiple_organisms` | accept | bon exemple de plusieurs individus mais pas un problème car meme espèce. c'est m

**Action:** define `target_taxon_visibility` policy rule distinguishing
same-species multi-individual (acceptable, possibly rich) from mixed-species
frame where target is ambiguous (policy downgrade or flag).

---

## Text overlay summary

- `pmp-policy-review-0398` | Strix aluco | `whole_organism` | too_permissive | screenshot d'un écran d'identification par le son avec le nom de l'espèce en cla

**Action:** add detection criterion for visible species name / app screenshot.
Candidate: reject or heavy penalty at pre-AI or PMP schema validation stage.

---

## Habitat evidence summary

- `pmp-policy-review-0072` | Sturnus vulgaris | `habitat` | accept | mais score horrible car globalement impossible de savoir de quelle espèce on par

**Action:** tighten habitat evidence scoring; consider requiring minimum
ecological specificity to qualify for `field_observation`.

---

## Species card and field observation concerns

### Species card possibly too permissive

- `pmp-policy-review-0340` | Coloeus monedula | `whole_organism` | accept | quand meme bizzare de dire oui a species card


### Field observation possibly too permissive / strict

- `pmp-policy-review-0188` | Phalacrocorax carbo | `whole_organism` | too_strict | un peu trop strict a mon gout

**Action:** review `species_card` threshold conditions; `field_observation` is
intentionally broad but should not be assigned to screenshots.

---

## Rare model-subject miss note

- `pmp-policy-review-0253` | Falco peregrinus | `unknown` | unclear | very distant shot of a peregrine falcon. extremly hard but challenging ans possi

**Action:** mark for second review. Do not create a major new policy category
unless this pattern recurs at scale.

---

## Recommended Sprint 9 Phase 2 patches

1. **Schema fix**: investigate 4 `schema_false_negative` items for
   over-strict validation rules.
2. **Target taxon visibility**: define and document
   `target_taxon_visibility_v1` policy distinguishing same-species vs
   mixed-species `multiple_organisms`.
3. **Text overlay rejection**: add detection rule for visible species name /
   app screenshot at pre-AI or PMP stage.
4. **Habitat scoring**: tighten `habitat` evidence score thresholds.
5. **Pre-AI threshold**: evaluate whether image size/resolution limits can
   be slightly lowered without pipeline complexity.
6. **Species card conditions**: add minimum clarity condition for
   `species_card` eligibility.

---

## Open questions

- How should same-species multiple individuals be formally treated in PMP?
- How should mixed-species frames with unclear target be penalized?
- Should `target_taxon_visibility` be a new PMP field or a policy rule?
- How should visible answer text / app screenshots be detected?
- Should habitat evidence require ecological specificity for `field_observation`?
- Should `species_card` require stricter conditions (distance, clarity)?
- Is `field_observation` intentionally broad? Current behavior seems correct.
- Should pre-AI resolution thresholds be slightly lowered?
- How should rare model-subject-miss cases be tracked without over-complexifying?

---

## Final decision

**READY_FOR_PMP_POLICY_V1_1_PATCHES**

Rationale: accept rate is 83.3% (50/60),
judgments are normalized, issue categories populated, high-priority patch
candidates identified. Proceeding to Sprint 9 Phase 2 patches is appropriate.
