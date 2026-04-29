---
owner: database
status: implemented
last_reviewed: 2026-04-29
source_of_truth: docs/runbooks/phase3-distractor-strategy.md
scope: runbook
---

# Phase 3 Distractor Strategy

## Objective

Phase 3 makes distractors taxon-based while preserving the strict `database` / `runtime-app` boundary.

The target remains a playable item. Distractors become governed question options that may come from outside the pack and may not have media.

## Success criteria

Phase 3A/3B are complete when:

- `QuestionOption` is defined
- v2 contract invariants are written
- v1/v2 transition strategy is explicit
- repo responsibilities are unambiguous
- no runtime code anticipates truth not yet produced by `database`
- v1 contracts remain compatible during transition

## Execution order

1. Phase 3A - Doctrine and invariants -> verify: ADR accepted, runbook published, boundaries unchanged.
2. Phase 3B - Contract v2 -> verify: `pack.compiled.v2` and `pack.materialization.v2` schemas exist and are documented.
3. Phase 3C - Referenced taxa -> verify: referenced-only or external referenced taxon model has tests and governance rules.
4. Phase 3D - iNaturalist similar species mapping -> verify: mapped/high/low/ambiguous/ignored cases covered.
5. Phase 3E - Distractor scoring -> verify: deterministic score and reason codes covered by tests.
6. Phase 3F - Top-3 out-of-pack selection -> verify: exactly 3 valid distractors, label/source/score/reason traces present.
7. Phase 3G - Materialization snapshot -> verify: materializations freeze options and labels immutably.
8. Phase 3H - Runtime consumption -> verify: `runtime-app` consumes v2 without recomputing distractors.
9. Phase 3I - Submit migration -> verify: `selectedOptionId` is standard for v2 and legacy v1 still works.
10. Phase 3J - Learning compatibility -> verify: learning events use selected taxon derived from option snapshot.
11. Phase 3K - Technical and pedagogical validation -> verify: contract/session/learning tests and manual plausibility review pass.

## Locked doctrine

- `database` defines and produces distractor truth.
- `database` versions pack contracts.
- `runtime-app` consumes generated contracts after `database` produces them.
- `runtime-app` does not calculate scores.
- `runtime-app` does not map similar species.
- `runtime-app` does not create referenced taxa.
- `runtime-app` displays, validates displayed option selection, records, and logs.
- `export.bundle.v4` remains forbidden as a live runtime surface.

## Contract v2 summary

`pack.compiled.v2` and `pack.materialization.v2` add `QuestionOption[]` to each question.

Core shape:

```ts
type MaterializedQuestionV2 = {
  position: number;
  target_playable_item_id: string;
  target_canonical_taxon_id: string;
  options: QuestionOption[];
};

type QuestionOption = {
  option_id: string;
  canonical_taxon_id: string;
  taxon_label: string;
  is_correct: boolean;
  playable_item_id?: string | null;
  source: string;
  score?: number | null;
  reason_codes: string[];
  referenced_only?: boolean;
};
```

## Invariants

Every v2 question must satisfy:

- 4 options exactly
- 1 correct option exactly
- 3 distractors exactly
- unique `canonical_taxon_id` across options
- target taxon present in options
- no distractor with target taxon
- non-empty label for each option
- non-empty `reason_codes` for distractors
- traceable source for distractors
- immutable option snapshot in materialization

## Referenced taxon strategy

Preferred implementation is a separate `ReferencedTaxon` model/table, not direct creation of active canonical taxa.

Mapping statuses:

- `mapped`: usable as distractor
- `auto_referenced_high_confidence`: usable as distractor with trace
- `auto_referenced_low_confidence`: diagnostic only
- `ambiguous`: excluded
- `ignored`: excluded

If a canonical status is used instead, `referenced_only` must never imply active, playable, or fully qualified.

## iNaturalist similar species mapping

Pipeline:

1. read iNaturalist similar species hints
2. attempt mapping to existing `CanonicalTaxon`
3. if found, classify as `mapped`
4. if absent but clear, classify as `auto_referenced_high_confidence`
5. if incomplete, classify as `auto_referenced_low_confidence`
6. if conflicting, classify as `ambiguous`
7. if unusable, classify as `ignored`

Required traces:

- source name
- source taxon ID
- mapping status
- confidence or reason codes
- mapped canonical taxon ID when present
- created timestamp

## Scoring v1

Without enough global confusion volume:

- 45% iNaturalist similar species
- 25% internal `similar_taxon_ids`
- 20% taxonomic proximity
- 10% diversity / anti-repetition

When global confusion volume is sufficient:

- 35% iNaturalist similar species
- 25% global confusion aggregates
- 20% internal `similar_taxon_ids`
- 10% taxonomic proximity
- 10% diversity / anti-repetition

Global confusion aggregates remain secondary until the volume is sufficient.

## Reason codes

Allowed initial reason codes:

- `inat_similar_species`
- `internal_similarity`
- `same_genus`
- `same_family`
- `same_order`
- `global_confusion`
- `diversity_fallback`
- `referenced_only`
- `out_of_pack`

## Extended pool

Distractors are selected from a governed pool:

- taxa in the pack
- internal `similar_taxon_ids`
- mapped iNaturalist similar species
- high-confidence referenced-only taxa
- taxonomic fallback

Rules:

- target is pack-only and must be a playable item
- distractors may be out-of-pack if policy allows
- referenced-only distractors obey a per-question cap
- label, score, source, and reason codes are mandatory for displayed distractors

## Distractor policy

```ts
type DistractorPolicy = {
  allow_out_of_pack_distractors: boolean;
  allow_referenced_only_distractors: boolean;
  prefer_inat_similar_species: boolean;
  max_referenced_only_distractors_per_question: number;
};
```

Defaults:

- free quiz: allow out-of-pack, allow referenced-only
- assignment: out-of-pack configurable, referenced-only false by default
- daily challenge: allow out-of-pack, freeze options in materialization

## Runtime migration notes

Runtime work must start only after `database` can produce v2 artifacts or fixtures.

Runtime v2 behavior:

- image comes from `target_playable_item_id`
- displayed options come from materialization snapshot
- `selectedOptionId` is the standard submit field
- `selectedTaxonId` is derived from the selected option
- `selectedPlayableItemId` remains legacy for v1
- runtime validates that the selected option belongs to the displayed question

Learning event rule:

- `playableItemId` = target playable item
- `correctTaxonId` = target taxon
- `selectedTaxonId` = selected option taxon
- `shownDistractorTaxonIds` = displayed distractor taxa

## Validation

Technical checks:

- v2 contracts validate
- materializations are immutable
- v1 and v2 can coexist
- runtime submit v1 and v2 work after consumer migration
- learning logs store selected taxon without requiring a distractor playable item
- institutional assignment policy is tested

Pedagogical checks:

- at least 80% distractors are judged plausible in manual review
- at least 85% questions use an iNaturalist signal when available
- intra-pack repetition decreases measurably
- no question has 3 absurd distractors
- no displayed option has an empty label

The iNaturalist threshold is a KPI, not an absolute hard gate, because some taxa will not have useful similar species hints.

## Database files likely affected after this doctrine phase

Priority files:

- `docs/foundation/domain-model.md`
- `docs/foundation/adr/0006-taxon-based-question-options.md`
- `docs/runbooks/execution-plan.md`
- `schemas/pack_compiled_v2.schema.json`
- `schemas/pack_materialization_v2.schema.json`
- `src/database_core/domain/models.py`
- `src/database_core/domain/enums.py`
- `src/database_core/storage/pack_store.py`
- `src/database_core/storage/postgres_schema.py`
- `src/database_core/pipeline/runner.py`
- pack/materialization/distractor tests

Possible later files:

- `src/database_core/enrichment/*`
- `src/database_core/adapters/inaturalist_snapshot.py`
- `src/database_core/storage/canonical_store.py`
- `src/database_core/storage/confusion_store.py`

## Explicit non-scope for this runbook

- no runtime implementation before database v2 output exists
- no live source call during compile/materialization
- no automatic activation of referenced taxa
- no retirement of v1 contracts in Phase 3A/3B
- no movement of session/scoring/progression logic into `database`
