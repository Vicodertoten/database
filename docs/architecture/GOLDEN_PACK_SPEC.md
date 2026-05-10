---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-10
source_of_truth: docs/architecture/GOLDEN_PACK_SPEC.md
scope: golden_pack_v1_contract
---

# Golden Pack V1 Specification

## Purpose

`golden_pack.v1` is the fallback runtime contract for the Belgian birds first
corpus. The active runtime contract stack is defined in
`docs/foundation/runtime-contract-stack-v1.md`.

It is separate from `pack.materialization.v2`. `pack.materialization.v2` remains
legacy / historical context and must not be deleted now, but it is not the
active runtime handoff specification.

The Golden Pack is a pedagogical product artifact first. It contains a strict
runtime contract so the fallback runtime path can display the quiz flow without making
domain decisions.

## Output Layout

The canonical export path is:

```text
data/exports/golden_packs/belgian_birds_mvp_v1/
  manifest.json
  pack.json
  validation_report.json
  media/
```

Responsibilities:

| File / directory | Responsibility |
|---|---|
| `pack.json` | Runtime payload required for the Golden Pack fallback quiz flow. |
| `manifest.json` | Artifact identity, versioning, gates, warnings, checksums, build metadata, links to evidence. |
| `validation_report.json` | Validation results, rejected targets, warnings, blockers, and diagnostics. |
| `media/` | Pack-local copied quiz images referenced by `pack.json`. |

Audits and evidence remain in `docs/audits/` and `docs/audits/evidence/`. They
are linked from `manifest.json`, but runtime must not consume them.

## `pack.json` Contract

`pack.json` must be runtime-sufficient but not evidence-heavy.

Required top-level invariants:

- `schema_version = "golden_pack.v1"`
- `pack_id = "belgian_birds_mvp_v1"`
- `locale = "fr"`
- exactly 30 questions
- no raw audit evidence
- no apply plans
- no unresolved candidate records
- no debug traces
- no detailed blockers

Each question must contain:

- stable `question_id` independent from taxon id, for example `gbbmvp1_q0001`
- one target taxon reference
- one primary media object
- exactly four options
- exactly one correct option
- exactly three database-selected distractors
- `feedback_short`
- `feedback_source`
- media attribution fields required for display

Each question must satisfy:

- no duplicate option `taxon_ref`
- no duplicate normalized option `display_label`
- no placeholder labels
- no empty labels
- no invented labels
- no scientific fallback as primary runtime-facing label
- no emergency fallback distractors

## `taxon_ref` Rules

Options must use generic taxon references:

```json
{
  "taxon_ref": {
    "type": "canonical_taxon",
    "id": "taxon:birds:000001"
  }
}
```

Allowed `taxon_ref.type` values:

- `canonical_taxon`
- `referenced_taxon`

Do not use `canonical_taxon_id` as the generic option field in
`golden_pack.v1`.

Runtime must not:

- map `referenced_taxon` to `canonical_taxon`
- fetch missing taxon data
- correct names
- replace options
- add distractors
- recalculate difficulty or pedagogy

Runtime may:

- display options
- shuffle only the options already present in `pack.json`
- record the displayed option order
- orchestrate answer and transition UX

## Referenced Taxon Distractors

`referenced_taxon` options are allowed only for distractors.

Rules:

- `referenced_only = true`
- FR label is runtime-safe
- provenance is clear enough for artifact traceability
- the artifact does not claim `DistractorRelationship` persistence
- runtime does not need to resolve or complete the taxon

`PERSIST_DISTRACTOR_RELATIONSHIPS_V1` remains false.

## Media Rules

Every question must have exactly one primary image.

Media requirements:

- image is copied into pack-local `media/`
- `runtime_uri` is pack-local, for example `media/<filename>`
- runtime does not depend on remote fetch
- PMP policy for the selected primary media is `basic_identification=eligible`
- borderline media are excluded from MVP primary quiz images
- media attribution is complete

Required media display/source fields:

- `runtime_uri`
- `source_url`
- `source`
- `creator`
- `license`
- `license_url`
- `attribution_text`
- checksum

Pack size target:

- `media/` should stay below 50 MB for local MVP testing
- if final copied media size is `<= 50 MB`, commit `media/`
- if final copied media size is `> 50 MB`, generate `media/` locally and commit
  only JSON plus the generation instructions

Current planning estimate for 30 candidate images is about 33 MB, so committing
`media/` is expected if final selection remains similar.

## Feedback Rules

`feedback_short` is mandatory for every question.

Allowed sources:

- existing database-authored feedback
- deterministic database-owned MVP fallback template

If fallback is used:

- set `feedback_source = "fallback_database_mvp"`
- do not ask runtime to generate or repair feedback

Runtime must never generate feedback.

## `manifest.json` Rules

`manifest.json` describes artifact identity and traceability.

Required content:

- artifact identity
- build timestamp
- contract version
- scope
- `runtime_surface = "artifact_only"`
- `contract_status = "before_mvp_candidate"`
- gates
- warnings
- non-actions
- checksums for `pack.json`, `validation_report.json`, and media files
- links to evidence JSON
- links to audit docs
- `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=false`
- `DATABASE_PHASE_CLOSED=false`

`manifest.json` may reference heavy evidence. That evidence must not be embedded
in `pack.json`.

## `validation_report.json` Rules

`validation_report.json` explains validation results and operator diagnostics.

It must include:

- schema validity
- count checks
- target candidates considered
- selected targets
- rejected targets with reasons
- label checks
- distractor checks
- media checks
- media copy/checksum checks
- media pack size check
- attribution checks
- feedback checks
- warnings
- blockers

Runtime does not need this file to display the MVP quiz. It is for build
validation, debugging, and auditability.

## Blocking Validations

A Golden Pack build must fail if any blocking validation is present:

- not exactly 30 questions
- any question missing a stable `question_id`
- any `question_id` tied directly to taxon id
- any question missing a primary image
- any question with other than four options
- any question with other than one correct option
- any question with fewer or more than three distractors
- duplicate option `taxon_ref` within a question
- duplicate normalized `display_label` within a question
- missing FR runtime-safe label
- empty label
- placeholder label
- invented label
- scientific fallback as primary runtime-facing label
- emergency fallback distractor
- unresolved taxon option
- primary media missing local copied file
- primary media requiring remote fetch
- primary media not `basic_identification=eligible`
- missing source, creator, license, source URL, or attribution text
- missing `feedback_short`
- schema validation failure

If fewer than 30 target candidates pass all gates, the build must fail and write
or return blockers. Do not weaken criteria.

## Non-Blocking Warnings

Allowed warning-level issues:

- source-attested label is not human-reviewed but is runtime-safe
- license has not been institutionally reviewed, if source, creator, license,
  source URL, and attribution text are present
- `feedback_short` uses the deterministic MVP fallback
- referenced taxon appears as a distractor with `referenced_only=true`

Warnings must be visible in `manifest.json` and `validation_report.json`.

## Expected Tests

Test coverage must include:

- strict schema tests for all three Golden Pack JSON files
- materializer writes `manifest.json`, `pack.json`, `validation_report.json`,
  and `media/`
- exactly 30 questions
- exactly one primary image per question
- exactly four options per question
- exactly one correct option
- exactly three distractors
- stable `question_id` independent from taxon id
- options use `taxon_ref`
- `referenced_taxon` distractors require `referenced_only=true`
- no duplicate option `taxon_ref`
- no duplicate normalized `display_label`
- FR runtime-safe labels required
- placeholder / empty / invented / scientific fallback labels rejected
- emergency fallback distractors rejected
- non-eligible primary media rejected
- copied media checksum validated
- attribution completeness enforced
- `feedback_short` required
- fallback feedback marked with `feedback_source="fallback_database_mvp"`
- `pack.json` excludes raw audit evidence, apply plans, unresolved candidates,
  debug traces, and detailed blockers
- Sprint 14B / 14C readiness regression remains valid
- runtime MVP artifact does not depend on owner-side HTTP or
  `pack.materialization.v2`

## Non-Actions

- Do not move or delete historical audits.
- Do not move or delete evidence JSON.
- Do not persist `DistractorRelationship`.
- Do not set `DATABASE_PHASE_CLOSED=true`.
- Do not add runtime business logic to database.
- Do not make runtime invent, fetch, correct, or map names.
- Do not make runtime choose or replace distractors.
