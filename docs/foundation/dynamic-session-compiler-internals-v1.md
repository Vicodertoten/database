---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/foundation/dynamic-session-compiler-internals-v1.md
scope: dynamic_session_compiler_internals
---

# Dynamic Session Compiler Internals V1

This document separates the internal dynamic session compiler model from the
exported `session_snapshot.v2` product contract.

`session_snapshot.v2` is the frozen runtime payload. Internal compiler code may
prepare, score, select, and order data before projection, but it must not treat
the exported JSON shape as the canonical internal domain model.

## Compiler Boundary

The compiler boundary is:

```text
owner relational state / pack_pool.v1 / serving_bundle.v1
  -> internal compiler inputs and policies
  -> projected product payload
  -> session_snapshot.v2
```

Internal inputs may include product policy values such as locale, question
count, geography, source scores, seed, and policy versions. These values are
inputs to a materialization/export operation; they are not generic domain model
constants.

## Internal Concepts

| Concept | Purpose | Product-agnostic expectation |
|---|---|---|
| Pool item input | Candidate playable item with taxon, media, labels, attribution, country, and feedback fields. | May carry product-filtered fields, but compiler logic should consume it as input data rather than hard-coding a single geography or locale set globally. |
| Label index | Lookup from taxon id to display labels and label sources. | Accepts the requested locale as an input. Locale availability policy belongs at pool/build/export boundaries. |
| Selector policy | Controls question count, media uniqueness, taxon repetition, and seed behavior. | Policy values are injected or attached to the exported product payload; generic domain/storage code must not assume `20` questions. |
| Distractor policy | Controls allowed sources, source scores, fallback source, referenced-only settings, and per-question limits. | Policy is a compiler input and exported trace, not a runtime decision surface. |
| Option candidate | Internal candidate before final projection to an answer option. | May include relationship id, score, source, reason codes, and taxon id; final option shape is owned by `session_snapshot.v2`. |
| Seed policy | Provides reproducibility for generated sessions, fixtures, daily challenges, and assignments. | Seed derivation is mode-specific policy. Runtime stores the consumed seed but does not recompute owner semantics. |
| Projection boundary | Final mapping from internal selected items/options to exported JSON. | All product-specific wire constraints are enforced here or by schema validation. |

## Product Contract Boundary

`session_snapshot.v2` currently carries product constraints for the first Dynamic
Pack runtime:

- locale set: `fr`, `en`, `nl`
- geography in payload items: `BE`, `FR`
- session size: `20` questions
- selector policy: `phase2b.selector.v2`
- distractor policy: `phase2b.distractors.palier_a.v1`

These constraints are allowed in:

- `database` Phase 2B materialization/export tooling
- `database` JSON schemas and contract validators
- `runtime-app` contract guards and local dynamic provider projection
- tests and fixtures that prove the product contract

These constraints must not be introduced into:

- generic canonical taxon models
- generic storage services or repository facades
- qualification contracts
- shared domain models that should support future products

## Boundary Review Notes

This stabilization pass does not change schemas or runtime behavior. It records
the intended boundary for new `session_snapshot.v2` compiler work.

Existing FR/EN/NL constants in localized-name validation, label fallback, and AI
localized-name resolution are older localized-name policy constraints, not the
dynamic session compiler model. Existing `20` question thresholds in pack
diagnostics and historical pack compilation are pack-operation policy
constraints, not the exported `session_snapshot.v2` product contract.

New session compiler logic must keep BE/FR geography, FR/EN/NL locale, 20
question, selector-policy, and distractor-policy assumptions in Phase 2B
materialization/export/runtime-consumption boundary modules or their contract
tests. If older localized-name or pack policies need to become reusable across
products, move them behind explicit policy contracts before expanding their use.

## Runtime Responsibilities

`runtime-app` may:

- read a `serving_bundle.v1` and project it into `session_snapshot.v2`
- read a frozen `session_snapshot.v2`
- persist the consumed snapshot for session scoring and availability
- render the stored option order
- submit answers by `selectedOptionId`
- export `runtime_answer_signals.v1`

`runtime-app` must not:

- invent labels
- select replacement distractors
- recalculate distractor scores
- repair taxonomy or referenced-only status
- call live iNaturalist, Gemini, or owner Postgres during quiz play

## Future Product Artifacts

`fixed_challenge.v1` and `assignment_materialization.v1` should reuse the same
internal compiler concepts before defining their own exported product contracts.
They must receive explicit schemas before runtime or institutional consumption.
