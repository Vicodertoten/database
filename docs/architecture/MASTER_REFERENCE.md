---
owner: database
status: draft
last_reviewed: 2026-05-05
source_of_truth: docs/architecture/MASTER_REFERENCE.md
scope: golden_pack_runtime_handoff
---

# Database Runtime Master Reference

## Executive Summary

The current architectural direction is to contract the database work around one
first runtime-safe artifact: `golden_pack.v1`.

`golden_pack.v1` is primarily a pedagogical product artifact. It also contains a
strict runtime data contract so the runtime can render a real quiz experience
without performing domain decisions.

The immediate priority is:

1. Materialize a Belgian birds MVP Golden Pack as an artifact-only export.
2. Validate the manifest, pack payload, media, names, distractors, feedback, and
   provenance.
3. Connect the runtime to that artifact without business-data transformation.
4. Smoke-test the minimal image-first quiz UI/UX.

This is not a database perfection milestone. It is the first audited,
runtime-safe, pedagogically usable artifact sufficient to test the real product
experience.

Current decision state:

| Decision | Status |
|---|---|
| `READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE` | true |
| `READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS` | true |
| `PERSIST_DISTRACTOR_RELATIONSHIPS_V1` | false |
| `DATABASE_PHASE_CLOSED` | false |

Main architectural verdict: the database architecture is strong enough to produce
the first Golden Pack, but the MVP runtime surface must be narrowed. Older
runtime-serving contracts remain historical or strategic-later references. They
must not compete with `golden_pack.v1` as the MVP handoff.

## Product And Philosophy

Inaturaquizz / Inaturamouche is a biodiversity learning product. It is not an
automatic identification product.

The product goal is to help users learn to recognize species themselves from
real observations, supported by quizzes, feedback, pedagogical distractors,
lightweight progression, and later field, audio, institutional, and localized
educational use cases.

The database-first doctrine remains:

- The database collects, normalizes, enriches, qualifies, scores, audits, and
  documents.
- Runtime consumes clean artifacts.
- Runtime does not invent names.
- Runtime does not choose distractors.
- Runtime does not recalculate pedagogy.
- Runtime does not map or correct taxa.
- AI can produce signals, but AI is never an unaudited source of taxonomic truth.

## Architecture Map

The current MVP path is:

```text
source snapshots / cached evidence
  -> raw data
  -> normalization
  -> canonical taxa and referenced taxa
  -> taxonomic enrichment and iNaturalist similar-species hints
  -> localized-name evidence and apply plan
  -> media qualification through PMP
  -> PMP policy interpretation
  -> distractor candidates and projected relationships
  -> readiness gates and evidence
  -> golden_pack.v1 materialization
  -> artifact-only runtime handoff
  -> minimal UI/UX smoke test
```

Non-MVP or strategic-later surfaces may continue to exist in the repo, including
`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`, owner-side
runtime-read HTTP transport, and editorial write transport. For the MVP Golden
Pack milestone, these are not the primary runtime contract.

## Database Vs Runtime Responsibilities

Database owns:

- Canonical taxon identity and referenced taxon shells.
- Localized-name resolution, provenance, display status, and placeholder
  exclusion.
- Distractor candidate generation, projection, ordering, and pack-scoped
  selection.
- PMP media qualification.
- PMP policy interpretation for usage-specific eligibility.
- Media attribution and legal/source metadata.
- Golden Pack materialization and validation.
- Evidence links, plan hashes, audit reports, and readiness gates.

Runtime owns:

- Reading a versioned local Golden Pack artifact.
- Rendering the image-first quiz experience.
- Shuffling display order among already-provided options, if desired.
- Recording the displayed option order.
- Handling answers, transitions, animations, UI state, and session UX.
- Displaying database-provided feedback and attribution.
- Collecting optional telemetry after the artifact is displayed.

Runtime must not:

- Replace, add, or remove distractors.
- Choose another taxon.
- Fetch or invent localized names.
- Generate feedback.
- Recalculate media policy.
- Recalculate difficulty or pedagogical value.
- Map referenced taxa to canonical taxa.
- Correct taxonomy.

## Golden Pack V1

### Definition

`golden_pack.v1` is the first canonical MVP handoff artifact. It is a
pedagogical product artifact containing a strict runtime contract.

It is intentionally separate from `pack.materialization.v2` because the pipeline
and runtime handoff have changed enough to justify a clean contract. The older
pack/materialization family remains useful historical context and may inform
implementation, but it is not the MVP artifact contract.

### Canonical Export Location

Consumable artifacts live under:

```text
data/exports/golden_packs/belgian_birds_mvp_v1/
  manifest.json
  pack.json
  validation_report.json
```

Documentation and traceability live elsewhere:

| Path | Role |
|---|---|
| `data/exports/` | Runtime-consumable artifacts |
| `docs/architecture/` | Specifications and contracts |
| `docs/audits/` | Historical audits and audit decisions |
| `docs/audits/evidence/` | Evidence JSON and traceability artifacts |

### `manifest.json`

The manifest describes the artifact identity and audit boundary.

It should contain:

- `schema_version`: `golden_pack_manifest.v1`
- `pack_contract_version`: `golden_pack.v1`
- `pack_id`
- `artifact_id`
- `created_at`
- `scope`
- `locale_policy`
- `target_count`
- `question_count`
- `media_policy`
- `name_policy`
- `distractor_policy`
- `gates`
- `warnings`
- `non_actions`
- `source_artifacts`
- `evidence_links`
- `checksums`
- `build_info`

The manifest is the place to state that:

- `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=false`
- `DATABASE_PHASE_CLOSED=false`
- referenced taxa can appear as pack-scoped distractors
- runtime-facing placeholders, emergency fallback, invented names, and
  scientific fallback labels are forbidden

### `pack.json`

`pack.json` contains the runtime-consumable quiz payload.

Minimum shape:

```json
{
  "schema_version": "golden_pack.v1",
  "pack_id": "belgian_birds_mvp_v1",
  "locale": "fr",
  "questions": []
}
```

Each question must include:

- stable question id or position
- target taxon reference
- primary media object
- four answer options
- one correct option
- three database-selected distractors
- short feedback
- media attribution
- evidence/provenance references sufficient for audit

Options must use generic taxon references:

```json
{
  "option_id": "q1:opt:2",
  "taxon_ref": {
    "type": "canonical_taxon",
    "id": "taxon:birds:000001"
  },
  "label": "Pigeon ramier",
  "is_correct": false,
  "referenced_only": false,
  "source": "distractor_projection",
  "reason_codes": []
}
```

Allowed `taxon_ref.type` values:

- `canonical_taxon`
- `referenced_taxon`

If `taxon_ref.type="referenced_taxon"`, then:

- `referenced_only` must be `true`
- the label must be runtime-safe
- provenance must be present
- the artifact must not claim that the relation is a persisted canonical
  `DistractorRelationship`
- runtime must not resolve or complete the taxon

### `validation_report.json`

The validation report records whether the artifact is safe to consume.

It should contain:

- schema validation result
- question count result
- option count result
- FR label safety result
- media locality/stability result
- media attribution result
- PMP policy eligibility result
- feedback coverage result
- distractor coverage result
- fallback exclusion result
- warnings
- blocking errors

### MVP Inclusion Criteria

A question can enter the MVP Golden Pack only if:

- target is part of the selected Belgian birds MVP scope
- primary label is FR runtime-safe
- every displayed option has a FR runtime-safe label
- exactly four options are present
- exactly one option is correct
- exactly three options are database-selected distractors
- option labels are distinct after normalization
- no runtime-facing placeholder is present
- no runtime-facing scientific fallback is present
- no emergency diversity fallback is present
- primary media is runtime-stable and locally materialized or referenced by a
  stable local path
- primary media is eligible for quiz/basic-identification under PMP policy
- media attribution is complete
- short feedback is present
- feedback source is explicit

### MVP Exclusion Criteria

Exclude from runtime-facing Golden Pack:

- missing labels
- invented labels
- placeholders
- scientific fallback as primary display label
- emergency fallback distractors
- media without attribution
- media requiring remote fetch to render the first UI test
- media that is only borderline for quiz/basic-identification
- unresolved taxon options
- options requiring runtime taxon mapping or name lookup

### Minimal Target

The MVP Golden Pack should contain at least:

- 30 target questions
- 1 primary quiz image per question
- 4 options per question
- 3 usable distractors per question
- 0 emergency fallbacks
- 0 runtime-facing placeholders
- 0 runtime-facing scientific fallback labels

## Runtime Contract

The runtime contract is the technical interface inside and around
`golden_pack.v1`.

Runtime reads:

- `manifest.json`
- `pack.json`
- optionally `validation_report.json` for local/dev diagnostics

Runtime displays:

- media from `primary_media.runtime_uri`
- labels from provided options
- feedback from the question payload
- attribution from media metadata

Runtime may:

- shuffle the provided options
- record displayed order
- orchestrate transitions and answer states

Runtime must fail fast or refuse a pack when:

- pack schema version is unknown
- question count is below the MVP threshold
- any question lacks exactly four options
- any question lacks exactly one correct option
- any displayed option lacks a label
- any displayed media lacks a runtime URI
- any displayed media lacks attribution
- any required validation report status is failing

Runtime must not compensate for invalid data. Missing data is a database artifact
failure, not a runtime task.

## Localized Names

Localized names are a database governance concern, not a UI-only concern.

MVP policy:

- FR runtime-safe label is required for every displayed taxon.
- EN may be present as support/future data, but must not block the francophone
  MVP Golden Pack.
- NL may be preserved if available, but must not block the MVP.

Runtime-displayable values are:

- `displayable_curated`
- `displayable_source_attested`

Non-displayable values are:

- missing names
- placeholders
- low-confidence internal seeds without source attestation
- scientific fallback labels
- unresolved conflicts
- invented names

For MVP, a source-attested name from an approved source can be runtime-displayable
without human review if:

- source is approved
- source is recorded
- source priority is recorded
- locale is recorded
- value is not empty
- value is not a placeholder
- value is not a scientific fallback
- value does not silently overwrite curated/manual data

This is an MVP display policy, not institutional-quality certification.

## Distractor Relationships

Distractors are pedagogical taxon-to-taxon relations. They are not merely “three
wrong answers”.

Current state:

- Sprint 13 projected schema-compliant candidate records.
- The first corpus distractor gate is ready.
- Emergency fallback count is zero.
- Full `DistractorRelationship` persistence remains deferred.

Golden Pack rule:

- The Golden Pack may materialize pack-scoped distractors from audited projected
  artifacts.
- This does not imply that repo-wide `DistractorRelationship` persistence is
  closed.
- Referenced taxa may be used as pack-scoped distractors when label-safe and
  provenance-safe.

Persistence remains blocked until explicit criteria are satisfied, including
referenced shell handling, name quality, rollback/apply semantics, and persistence
risk.

## PMP And Media Policy

PMP is descriptive. PMP policy is usage-aware interpretation.

PMP answers:

- what is visible
- what kind of evidence the media contains
- how strong the visual evidence is
- which traits or limitations are present
- which use-specific scores can be computed

PMP policy answers:

- whether a media item is eligible, borderline, not recommended, or not
  applicable for a specific database use

For the MVP Golden Pack:

- quiz question media must be eligible for quiz/basic-identification usage
- borderline media must not be used as primary quiz images
- species-card, field-observation, habitat, nest, track, audio, and other
  future uses are not MVP blockers
- visible answer text or UI/screenshot contamination must block quiz media
- media attribution must be runtime-facing and complete

Runtime must not reinterpret PMP or PMP policy.

## Audits, Gates, And Evidence

Audits remain preserved. They are not deleted, flattened, or aggressively cleaned.

The role split is:

| Layer | Role |
|---|---|
| `docs/architecture/` | Current canonical direction and contracts |
| `docs/foundation/` | Stable domain foundations and historical doctrine |
| `docs/audits/` | Audit history, readiness decisions, and evidence reports |
| `docs/audits/evidence/` | Machine-readable evidence JSON |
| `data/exports/` | Runtime-consumable artifacts |

Required audit distinctions:

- corpus gate is not persistence
- persistence is not database closure
- runtime handoff readiness is not runtime UI proof
- database closure requires artifact validation plus runtime smoke evidence

`docs/audits/AUDIT_INDEX.md` should be created in the next documentation pass. It
should classify:

- active audits
- historical audits
- superseded audits
- evidence JSON
- canonical documents that replace or narrow older conclusions

Initial audits/evidence to index:

- `docs/audits/distractor-relationships-v1-sprint13.md`
- `docs/audits/distractor-relationships-v1-sprint13-persistence-decision.md`
- `docs/audits/database-phase-closure-inventory.md`
- `docs/audits/database-integrity-runtime-handoff-audit.md`
- `docs/audits/sprint14b-final-runtime-handoff-readiness.md`
- `docs/audits/evidence/database_integrity_runtime_handoff_audit.json`
- `docs/audits/evidence/localized_name_apply_plan_v1.json`
- `docs/audits/evidence/localized_name_projection_vs_14b_audit_reconciliation.json`
- `docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json`
- `docs/audits/evidence/distractor_readiness_v1_sprint13.json`

## Documentation Organization

Recommended hierarchy:

```text
docs/
  README.md
  architecture/
    MASTER_REFERENCE.md
    GOLDEN_PACK_SPEC.md          # optional, create only if needed
    RUNTIME_CONTRACT.md          # optional, create only if needed
  foundation/
    ...
    adr/
      ...
  decisions/
    ADR-0001-golden-pack-v1-artifact-only.md
    ADR-0002-localized-names-mvp-display-policy.md
    ADR-0003-distractor-persistence-deferred.md
  runbooks/
    build-golden-pack.md
    runtime-handoff-checklist.md
  audits/
    AUDIT_INDEX.md
    evidence/
    human_review/
  archive/
```

Do not create every listed file immediately. Create secondary documents only when
they reduce ambiguity or become operationally useful.

### Existing Document Migration Table

| Current document | Proposed role |
|---|---|
| `docs/architecture/MASTER_REFERENCE.md` | Current canonical MVP direction |
| `docs/foundation/localized-name-source-policy-v1.md` | Canonical localized-name MVP policy |
| `docs/foundation/taxon-localized-names-enrichment-v1.md` | Canonical localized-name enrichment workflow |
| `docs/foundation/distractor-relationships-v1.md` | Canonical distractor domain foundation, with MVP wording to clarify later |
| `docs/foundation/pedagogical-media-profile-v1.md` | Canonical PMP descriptive contract |
| `docs/foundation/pmp-qualification-policy-v1.md` | Canonical PMP policy interpretation |
| `docs/foundation/runtime-consumption-v1.md` | Historical/current non-MVP runtime-serving foundation; clarify MVP Golden Pack relationship later |
| `docs/foundation/adr/*` | Historical ADRs, keep in place |
| `docs/audits/*sprint13*` | Historical active evidence |
| `docs/audits/*sprint14*` | Historical active evidence |
| `docs/audits/evidence/*.json` | Evidence, keep in place |
| `docs/runbooks/inter-repo/*` | Inter-repo tracking, keep as operational history |

## Roadmap

### Now / Before Golden Pack

- Finalize `golden_pack.v1` shape.
- Materialize `manifest.json`, `pack.json`, and `validation_report.json`.
- Ensure every displayed taxon has a FR runtime-safe label.
- Ensure every question has three database-selected distractors.
- Ensure every primary quiz image is locally stable and policy-eligible.
- Ensure every question has short database-authored feedback.
- Add validation checks for all blocking criteria.

### After Golden Pack

- Connect runtime to the local artifact.
- Render the minimal image-first quiz flow.
- Verify runtime does not transform domain data.
- Record warnings and debt.

### Before Runtime MVP

- Run UI/UX smoke test:
  - image-first question
  - four options
  - answer state
  - short feedback
  - visible attribution
  - next question
- Validate that the runtime remains artifact-only.

### After First User Tests

- Adjust distractor ordering or scoring upstream in database if needed.
- Improve feedback quality.
- Review localized-name quality for confusing or visible edge cases.
- Decide whether persistence of `DistractorRelationship` is worth pursuing.

### Later

- Multi-taxon expansion.
- Audio.
- Field observation modes.
- Species cards.
- Localized educational activities.
- Institutional workflows.
- Owner-side HTTP runtime transport.
- Editorial/institutional backends.

These later tracks must not block the first Golden Pack runtime smoke test unless
a current decision would make them impossible later.

## Non-Actions

Do not do the following now:

- Do not wait for a perfect database before testing runtime.
- Do not persist `DistractorRelationship` prematurely.
- Do not delete or aggressively archive historical audits.
- Do not make runtime invent, fetch, or correct names.
- Do not make runtime choose distractors.
- Do not make AI a source of taxonomic truth.
- Do not expand into audio, multi-taxon, institutions, or field activities before
  MVP runtime validation.
- Do not revive older runtime-serving contracts as competing MVP handoff
  surfaces.
- Do not refactor broad documentation history before the Golden Pack is proven.

## Database Phase Closure

`DATABASE_PHASE_CLOSED` must remain false until all of the following are true:

1. Golden Pack produced.
2. Manifest valid.
3. Runtime contract valid.
4. Runtime consumes the artifact without business-data transformation.
5. Minimal UI/UX smoke test succeeds.
6. Warnings are documented.
7. Remaining debt is explicitly listed.

The database phase does not require a full production runtime, but it does require
proof that the artifact works in a real UI flow.

## Open Decisions

The main remaining decisions are:

- exact `golden_pack.v1` JSON schema
- exact validation report schema
- exact media local materialization convention
- checksum policy
- final warning severity vocabulary
- whether `GOLDEN_PACK_SPEC.md` should be split out after this reference
- whether `RUNTIME_CONTRACT.md` should be split out after implementation starts
- when `PERSIST_DISTRACTOR_RELATIONSHIPS_V1` can be reconsidered
- when `DATABASE_PHASE_CLOSED` can become true

