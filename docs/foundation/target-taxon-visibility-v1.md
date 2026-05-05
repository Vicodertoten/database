---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/target-taxon-visibility-v1.md
scope: foundation
---

# Target taxon visibility v1

## Purpose

Define a policy/PMP-side concept for describing whether the expected target taxon
is visibly present and pedagogically usable in the media.

This concept exists to resolve recurring broader_400 review issues around
multiple organisms, mixed-species frames, and target ambiguity.

## Why this is needed

Human review in Sprint 9 Phase 1 showed two distinct cases that should not be
collapsed into one bucket:

- multiple individuals of the same taxon, which are often still pedagogically
  useful;
- multiple species in the same frame, where the target individual can become
  ambiguous.

The goal is not taxonomic correction.
The goal is to describe whether the expected target taxon is visibly usable in
this media.

## Controlled enum

- `clear_primary`
- `clear_secondary`
- `multiple_individuals_same_taxon`
- `multiple_species_target_clear`
- `multiple_species_target_unclear`
- `target_not_visible`
- `unknown`

## Meaning of values

- `clear_primary`: the expected target taxon is the main, clearly visible subject.
- `clear_secondary`: the target is visible and usable, but not the dominant
  subject.
- `multiple_individuals_same_taxon`: several individuals are present, but they
  belong to the same taxon and remain pedagogically useful.
- `multiple_species_target_clear`: several species are present, but the intended
  target is still clearly distinguishable.
- `multiple_species_target_unclear`: several species are present and the intended
  target is ambiguous.
- `target_not_visible`: the expected target taxon is not visibly present as a
  usable subject.
- `unknown`: the visibility relation is not confidently determined.

## Policy interpretation guidance

- same-species multiple individuals are often acceptable;
- mixed-species target-unclear cases require caution for identification and
  species-card uses;
- target visibility can influence policy eligibility,
  but it is not a runtime selection field;
- target visibility does not rename, override, or challenge canonical taxonomy.

## Current v1.1 integration decision

Sprint 9 Phase 2 keeps this as a policy-side optional hint first.

Current implementation approach:
- no PMP schema expansion yet;
- policy can consume optional context such as `target_taxon_visibility`;
- this allows calibration without forcing a contract migration.

## Non-goals

This concept does not:
- override canonical taxon identity,
- create distractor logic,
- create runtime selection behavior,
- introduce `selectedOptionId`,
- redefine iNaturalist taxonomy.
