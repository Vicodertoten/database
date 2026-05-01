---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/foundation/adr/0006-taxon-based-question-options.md
scope: foundation
---

# ADR-0006 — Taxon-Based Question Options and Pack Contracts v2

Statut: `implemented`  
Date: `2026-04-29`  
Portee: `pack.compiled.v2`, `pack.materialization.v2`, distracteurs taxon-based, frontiere `database` / `runtime-app`

## Contexte

`pack.compiled.v1` et `pack.materialization.v1` representent les distracteurs avec:

- `distractor_playable_item_ids`
- `distractor_canonical_taxon_ids`

Ce modele impose que chaque distracteur corresponde a un `PlayableItem`. Il limite la qualite pedagogique, car un bon distracteur peut etre un taxon plausible sans media qualifie ni item jouable dans le pack courant.

La cible Phase 3 est de conserver la question comme une image cible issue d'un item jouable, mais de representer les options de reponse comme des options taxonomiques snapshottees dans la materialization.

## Decision

Le projet adopte un contrat v2 pour les questions a options taxonomiques:

- `pack.compiled.v2`
- `pack.materialization.v2`

`pack.compiled.v1` et `pack.materialization.v1` restent supportes pendant une periode de transition.

La numerotation de cet ADR est `0006`, car `0004` et `0005` existent deja dans ce repo.

## Decisions verrouillees

1. La cible de question reste toujours un `PlayableItem`.
2. Un distracteur est une option taxonomique, pas obligatoirement un item jouable.
3. Les options de reponse sont produites par `database`.
4. Les labels d'options sont snapshottes dans la materialization.
5. `runtime-app` ne resout pas les labels de taxon pour les options v2.
6. `runtime-app` ne score pas et ne selectionne pas les distracteurs.
7. `selectedOptionId` devient la soumission standard pour v2.
8. `selectedPlayableItemId` reste legacy temporaire pour v1.
9. Les materializations figent les options affichees.
10. Aucun taxon reference-only ne devient automatiquement `active`, `playable` ou `fully_qualified`.

## Contrat logique v2

```ts
type PackMaterializationV2 = {
  schema_version: string;
  pack_materialization_version: "pack.materialization.v2";
  materialization_id: string;
  pack_id: string;
  revision: number;
  source_build_id: string;
  created_at: string;
  purpose: "assignment" | "daily_challenge";
  question_count: number;
  questions: MaterializedQuestionV2[];
};

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

The compiled v2 contract uses the same question shape for `questions`, with `pack_compiled_version: "pack.compiled.v2"` and build metadata equivalent to v1.

## Invariants v2

For every materialized question:

- exactly 4 options are present
- exactly 1 option has `is_correct = true`
- exactly 3 options are distractors
- `canonical_taxon_id` is unique across options
- `target_canonical_taxon_id` is present in options
- no distractor has `canonical_taxon_id = target_canonical_taxon_id`
- every `taxon_label` is non-empty
- every distractor has non-empty `reason_codes`
- every distractor has traceable `source`
- options are immutable once materialized
- `target_playable_item_id` must belong to the compiled pack target set
- distractor options may be outside the pack
- distractor options may have `playable_item_id = null`
- distractor options do not require media

JSON Schema can enforce the structural subset of these invariants. Cross-field invariants, such as target inclusion and canonical ID uniqueness by field, must be enforced by model validators and tests.

## Database responsibilities

`database` owns:

- candidate pool construction
- iNaturalist similar species mapping
- referenced taxon classification
- distractor scoring
- top-3 distractor selection
- option ordering policy
- label snapshotting
- v2 contract schemas
- materialization immutability
- audit traces (`source`, `score`, `reason_codes`, `referenced_only`)

`database` must not introduce runtime session, scoring, answer, progression, or UX state.

## Runtime responsibilities

`runtime-app` owns:

- session lifecycle
- question serving as runtime API
- displaying the target media from `target_playable_item_id`
- displaying the snapshot `options`
- validating that a submitted `selectedOptionId` belongs to the displayed question
- deriving `selectedTaxonId` from the selected option
- recording answer and learning events

`runtime-app` must not:

- recompute distractors
- remap iNaturalist similar species
- create referenced taxa
- resolve option labels from canonical storage
- infer a playable item for taxon-only distractors
- use `export.bundle.v4` as a live question surface

## Referenced taxon policy

Phase 3 may introduce a cautious referenced taxon layer for external similar species that are useful as distractors but are not yet playable.

Preferred model:

```ts
type ReferencedTaxon = {
  referenced_taxon_id: string;
  source: "inaturalist";
  source_taxon_id: string;
  scientific_name: string;
  preferred_common_name?: string | null;
  common_names_i18n?: Record<string, string[]>;
  rank?: string;
  taxon_group: string;
  mapping_status:
    | "mapped"
    | "auto_referenced_high_confidence"
    | "auto_referenced_low_confidence"
    | "ambiguous"
    | "ignored";
  mapped_canonical_taxon_id?: string | null;
  reason_codes: string[];
  created_at: string;
};
```

Usage rules:

- `mapped`: usable as distractor
- `auto_referenced_high_confidence`: usable as distractor with trace
- `auto_referenced_low_confidence`: diagnostic only, not displayed
- `ambiguous`: excluded
- `ignored`: excluded

If the implementation chooses to store these as canonical rows instead, it must use a strict status such as `referenced_only` and preserve these invariants:

- `referenced_only != active`
- `referenced_only != playable`
- `referenced_only != fully_qualified`
- `referenced_only` is usable only as a distractor option when its label is reliable and policy allows it

## Distractor policy

Phase 3 introduces a policy object for pack/materialization contexts:

```ts
type DistractorPolicy = {
  allow_out_of_pack_distractors: boolean;
  allow_referenced_only_distractors: boolean;
  prefer_inat_similar_species: boolean;
  max_referenced_only_distractors_per_question: number;
};
```

Recommended defaults:

- free quiz: out-of-pack allowed, referenced-only allowed
- assignment: out-of-pack configurable, referenced-only false by default
- daily challenge: out-of-pack allowed, frozen in materialization

## Migration strategy

The transition is additive by contract family, not a patch to v1:

1. keep `pack.compiled.v1` and `pack.materialization.v1` unchanged
2. add schemas for `pack.compiled.v2` and `pack.materialization.v2`
3. implement v2 generation in `database`
4. publish fixture/materialization examples for runtime contract regeneration
5. update `runtime-app` to consume both v1 and v2
6. make `selectedOptionId` the standard submit field for v2
7. retire v1 only after consumers no longer depend on `distractor_playable_item_ids`

## Consequences

Positive consequences:

- good distractors no longer require media or pack membership
- materialized questions become the single source of displayed option truth
- runtime answer validation becomes stronger through `selectedOptionId`
- label drift is prevented by snapshotting labels in materializations

Tradeoffs:

- runtime must handle two contract families during migration
- database validators must enforce cross-field invariants beyond JSON Schema
- referenced taxon governance must be explicit to avoid canonical pollution
- assignment policy must be conservative enough to avoid perceived unfairness

## Non-scope

This ADR does not implement:

- runtime session storage changes
- runtime submit route changes
- scoring UI changes
- canonical taxon auto-activation
- live iNaturalist calls during compilation or runtime serving
- retirement of v1 contracts

## References

- `docs/foundation/canonical-charter-v1.md`
- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`
- `docs/foundation/runtime-consumption-v1.md`
- `docs/runbooks/phase3-distractor-strategy.md`
- `schemas/pack_compiled_v2.schema.json`
- `schemas/pack_materialization_v2.schema.json`
