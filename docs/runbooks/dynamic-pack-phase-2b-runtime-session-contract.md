---
owner: database
status: in_progress
last_reviewed: 2026-05-09
source_of_truth: docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md
scope: dynamic_pack_phase_2b_runtime_session_contract
---

# Dynamic Pack Phase 2B - Runtime Session Contract

## Purpose

Phase 2B turns the Phase 2A dynamic pack pool into the first playable dynamic
runtime contract for `Common birds Belgium/France`.

Phase 2A proved that `database` can build a BE+FR birds `pack_pool.v1` and
target-only `session_snapshot.v1` fixtures. Phase 2B adds the missing playable
surface: snapshotted options and distractors that `runtime-app` can consume
without recomputing taxonomy, labels, distractors, scores, feedback, or media
qualification.

## Relationship To Existing Contracts

Locked contract direction:

- `pack_pool.v1` remains the dynamic source pool.
- `session_snapshot.v1` remains a Phase 2A target-only proof surface.
- `session_snapshot.v2` is the first playable dynamic session contract.
- `pack.compiled.v2` and `pack.materialization.v2` remain useful historical
  references for `QuestionOption` semantics, but they are not the primary
  dynamic runtime surface.

`runtime-app` must consume `session_snapshot.v2` as produced by `database`.
It must not locally derive labels, similar species, taxonomic proximity,
distractor scores, referenced-only status, or option correctness.

## Product Name

The first dynamic pack product name is:

```text
Common birds Belgium/France
```

The name may be migrated later, but Phase 2B and Phase 3 should use this name
for the first runtime-visible dynamic pack.

## Scope

Included:

- FR/EN/NL name repair audit for the target corpus.
- Referenced-only distractor readiness audit.
- `session_snapshot.v2` JSON schema.
- Session generation with unique media per session.
- Repeated taxa allowed inside a session.
- Question options with exactly one correct option and three distractors.
- Deterministic distractor scoring plus weighted random selection.
- At least three fixture seeds per locale (`fr`, `en`, `nl`).
- Postgres persistence and JSON fixtures.
- Runtime handoff documentation.

Excluded:

- `runtime-app` dynamic mode implementation.
- public release gate.
- accounts, personalization, revision mode, and assignment UI.
- `runtime_signal_batch.v1`.
- live runtime calls to iNaturalist, Gemini, or any external enrichment service.

## Blocking Name Repair Gate

Phase 2A reported FR/NL scientific-name fallbacks in the pool. The project
expects the initial corpus to have valid names in at least `fr`, `en`, and `nl`,
so Phase 2B must treat the fallback as a likely data selection or propagation
bug until proven otherwise.

Before Phase 2B can pass:

- identify where the correct FR/EN/NL names are stored;
- verify whether `playable_corpus_v1.common_names_i18n_json` is stale,
  incomplete, or incorrectly mapped;
- explain any case where an `en` label contains a French common name;
- correct the SQL, projection, enrichment propagation, or source run used by
  `pack_pool.v1`;
- regenerate the pool or document why regeneration is unnecessary;
- publish a strict FR/EN/NL name readiness report.

Scientific-name fallback remains allowed as an internal safety mechanism, but it
must not hide a known name propagation defect.

## Referenced-Only Readiness Gate

Referenced-only taxa may be used as distractors in normal dynamic sessions with
guardrails.

Requirements:

- scientific name is mandatory;
- source taxon ID is mandatory;
- mapping status is mandatory;
- provenance is mandatory;
- locale common names for `fr`, `en`, and `nl` must be audited;
- per-locale distractor eligibility must be explicit.

Policy:

- internal dynamic fixtures may use scientific-name-only referenced distractors;
- public release must not use referenced-only distractors without a locale common
  name unless an editorial exception is recorded;
- institutional assignments should disable referenced-only distractors by
  default;
- normal dynamic sessions may use at most `2` referenced-only distractors per
  question.

Phase 2B starts with an audit. Corrections happen before the next generation run
when missing names or mapping errors are confirmed.

## Session Selection Policy

Initial dynamic session policy:

- `20` questions per session;
- no duplicate `media_asset_id` inside a session;
- repeated `canonical_taxon_id` values are allowed inside a session;
- selection uses controlled randomness;
- the generated session is immutable once snapshotted;
- the seed is stored for audit and reproducibility.

The first implementation must not permanently bind one image or species to the
same distractor set. Distractors are selected during session generation, then
frozen only for that one attempt.

Anti-repetition rules for taxa, recently seen images, personalized mastery, and
mode-specific difficulty are later selection-policy work.

## Seed Policy

Seed policy by mode:

- normal dynamic session: random seed generated server-side and stored;
- daily challenge: deterministic seed derived from date, locale, and challenge
  identity;
- assignment: deterministic seed derived from assignment identity and revision;
- tests and handoff fixtures: explicit deterministic seed strings.

The seed is an audit and reproducibility input. It is not a user-facing product
feature.

Phase 2B fixtures must include at least:

```text
3 seeds x 3 locales = 9 session_snapshot.v2 fixtures
```

This proves that controlled randomness varies the generated sessions while
preserving invariants.

## Distractor Policy

Candidate sources:

- iNaturalist similar species;
- same genus;
- same family;
- same order;
- referenced-only taxa when policy permits;
- taxonomic fallback when stronger sources are insufficient.

Selection rules:

- exclude the target taxon from distractors;
- no duplicate taxon among the four options for a question;
- exactly three distractors per question;
- maximum `2` referenced-only distractors per question;
- every displayed option must have a non-empty display label;
- every distractor must carry source, score, and reason codes;
- selection uses deterministic scoring plus weighted random sampling without
  replacement.

Initial scoring should stay simple and explainable. A first scoring model may
weight iNaturalist similar-species candidates highest, then same genus, same
family, same order, and fallback candidates. Later calibration can adjust the
weights after runtime signal batches exist.

## Runtime Display Payload

`session_snapshot.v2` must include everything `runtime-app` displays or scores
against:

- prompt or display text;
- media render URL;
- media attribution;
- media license;
- correct option;
- option order;
- common name when available;
- scientific name;
- label source;
- referenced-only status;
- feedback shown during or after answer review;
- distractor source, score, and reason codes.

Runtime may render common name as the primary option label and scientific name
below it in smaller, italic, lower-emphasis text. Runtime must not repair,
translate, or derive labels locally.

## Persistence And Handoff

Nominal production direction:

- `database` generates `session_snapshot.v2`;
- `database` persists generated snapshots for audit and lineage;
- `runtime-app` persists the consumed snapshot for session scoring and
  availability;
- JSON fixtures remain required for CI, handoff tests, debug, and rollback.

Postgres is the operational source. JSON fixtures are the handoff and evidence
surface.

## Phase 2B Gate

Blocking criteria:

- FR/EN/NL name repair gate completed or remaining fallbacks explicitly justified;
- referenced-only readiness audit completed;
- at least `9` fixtures generated (`3` seeds x `3` locales);
- each fixture validates against `session_snapshot.v2`;
- every session has exactly `20` questions;
- no session repeats a `media_asset_id`;
- every question has exactly `4` options;
- every question has exactly `1` correct option and `3` distractors;
- every question has no duplicate option taxon;
- every question has no target taxon as distractor;
- every question has at most `2` referenced-only distractors;
- every displayed option has a non-empty display label;
- distractor score, source, and reason codes are present;
- no runtime dependency on live iNaturalist or Gemini calls.

Warnings:

- scientific-name fallback remains for an internal fixture;
- referenced-only candidate lacks public-ready common names;
- distractor diversity is weak for a target taxon;
- fallback taxonomic distractors are used because similar-species candidates are
  insufficient.

`GO_WITH_WARNINGS` is acceptable for internal runtime handoff. Public release
requires a separate editorial threshold for labels and referenced-only usage.

## Phase 3 Handoff Boundary

Phase 3 may start only after Phase 2B produces a validated `session_snapshot.v2`
fixture set and handoff document.

Phase 3 runtime work should:

- add `dynamic_pack` session mode;
- store `pool_id`, `session_snapshot_id`, and `locale`;
- persist the consumed snapshot;
- submit answers with `selectedOptionId`;
- derive selected taxon from the snapshotted option;
- preserve `golden_pack.v1` as fallback until dynamic mode is validated.

## Immediate Next Steps

Current status after the Phase 2B name-repair correction run, Palier A
distractor persistence, and `session_snapshot.v2` fixture generation:

- correction run: `phase2b-name-repair-v18`;
- database schema: `database.schema.v19`;
- source run: `run:20260509T180000Z:2b18beef`;
- `pack_pool.v1` pool: `pack-pool:be-fr-birds-50:v1`;
- Phase 2A audit: `GO`;
- Phase 2B `name-repair` audit: `NO_ISSUE_FOUND`;
- Phase 2B `referenced-only` audit: `NO_ISSUE_FOUND`;
- Phase 2B distractor relationships Palier A audit: `GO_WITH_WARNINGS`;
- FR/EN/NL labels: `2313/2313` common-name labels per locale;
- scientific-name fallbacks in FR/EN/NL: `0`;
- persisted distractor relationships: `203` canonical-only rows, all `validated`;
- referenced-only distractors: `0` in Palier A.
- `session_snapshot.v2` fixtures: `9` persisted and exported;
- `session_snapshot.v2` audit: `GO_WITH_WARNINGS`;
- `session_snapshot.v2` fallback options: `117` `taxonomic_fallback_db` options,
  all canonical-only and traced.

Evidence:

- `docs/archive/evidence/dynamic-pack-phase-2a/phase2b-name-repair-v18/`;
- `docs/audits/phase2b-name-repair-audit.md`;
- `docs/audits/phase2b-referenced-only-audit.md`;
- `docs/audits/phase2b-distractor-relationships-palier-a.md`;
- `docs/audits/evidence/phase2b/name_repair_audit.json`;
- `docs/audits/evidence/phase2b/referenced_only_audit.json`;
- `docs/audits/evidence/phase2b/distractor_relationships_palier_a_audit.json`.
- `docs/archive/evidence/dynamic-pack-phase-2b/session-snapshot-v2-palier-a/`.

Palier A intentionally imports only `canonical_taxon` distractor relationships
from the Sprint 13 projection. The DB-first audit currently reports
`GO_WITH_WARNINGS` because `11` pool targets have fewer than `3` persisted
canonical distractors. `session_snapshot.v2` uses these validated relationships
first, then a database-side traced taxonomic fallback where needed. Runtime must
still receive fully snapshotted options and must not derive distractors.

Phase 2B now has a playable internal dynamic session contract. The next
implementation step is the Phase 3 `runtime-app` dynamic pack mode, while
`golden_pack.v1` remains the runtime fallback until dynamic mode is validated.

Reference command sequence used for the correction:

1. Configure the clone database target.
   - Set `PHASE1_DATABASE_URL` to the isolated Phase 1/2A clone.
   - The URL must use `options=-csearch_path=phase1_be_fr_20260509,public`.
   - Do not run Phase 2B audits against `public` unless the runbook is revised.

2. Migrate the clone to `database.schema.v19`.

   ```bash
   python scripts/migrate_database.py --database-url "$PHASE1_DATABASE_URL"
   ```

3. Re-run the Phase 1 cached pipeline from the final snapshot.

   ```bash
   python scripts/run_pipeline.py \
     --source-mode inat_snapshot \
     --snapshot-id phase1-be-fr-20260509-final-input-v3 \
     --database-url "$PHASE1_DATABASE_URL" \
     --qualifier-mode cached \
     --qualification-policy v1.1 \
     --uncertain-policy reject
   ```

4. Rebuild `pack_pool.v1` from the corrected run.

   ```bash
   python scripts/phase2a_dynamic_pack.py \
     --database-url "$PHASE1_DATABASE_URL" \
     --run-id phase2b-name-repair-v18 \
     build-pool \
     --pool-id pack-pool:be-fr-birds-50:v1 \
     --source-run-id run:20260509T180000Z:2b18beef
   ```

5. Re-run Phase 2A audit.

   ```bash
   python scripts/phase2a_dynamic_pack.py \
     --database-url "$PHASE1_DATABASE_URL" \
     --run-id phase2b-name-repair-v18 \
     audit \
     --pool-id pack-pool:be-fr-birds-50:v1
   ```

6. Run the name repair audit.

   ```bash
   python scripts/phase2b_audit.py \
     --database-url "$PHASE1_DATABASE_URL" \
     name-repair \
     --pool-id pack-pool:be-fr-birds-50:v1
   ```

   Expected outputs:

   - `docs/audits/evidence/phase2b/name_repair_audit.json`
   - `docs/audits/phase2b-name-repair-audit.md`

7. Run the referenced-only audit.

   ```bash
   python scripts/phase2b_audit.py \
     --database-url "$PHASE1_DATABASE_URL" \
     referenced-only
   ```

   Expected outputs:

   - `docs/audits/evidence/phase2b/referenced_only_audit.json`
   - `docs/audits/phase2b-referenced-only-audit.md`

8. Import Palier A canonical distractor relationships.

   ```bash
   python scripts/phase2b_distractor_relationships.py \
     --database-url "$PHASE1_DATABASE_URL" \
     import-canonical
   ```

9. Run the DB-first distractor relationship audit.

   ```bash
   python scripts/phase2b_distractor_relationships.py \
     --database-url "$PHASE1_DATABASE_URL" \
     audit-db \
     --pool-id pack-pool:be-fr-birds-50:v1
   ```

   Expected outputs:

   - `docs/audits/evidence/phase2b/distractor_relationships_palier_a_audit.json`
   - `docs/audits/phase2b-distractor-relationships-palier-a.md`

10. Generate `session_snapshot.v2` fixtures.

   ```bash
   python scripts/phase2b_session_snapshot.py \
     --database-url "$PHASE1_DATABASE_URL" \
     build-fixtures \
     --pool-id pack-pool:be-fr-birds-50:v1
   ```

11. Run the `session_snapshot.v2` audit.

   ```bash
   python scripts/phase2b_session_snapshot.py \
     --database-url "$PHASE1_DATABASE_URL" \
     audit \
     --pool-id pack-pool:be-fr-birds-50:v1
   ```

   Expected outputs:

   - `docs/archive/evidence/dynamic-pack-phase-2b/session-snapshot-v2-palier-a/session_fixture_index.json`
   - `docs/archive/evidence/dynamic-pack-phase-2b/session-snapshot-v2-palier-a/session_snapshot_v2_audit.json`
   - `docs/archive/evidence/dynamic-pack-phase-2b/session-snapshot-v2-palier-a/session_snapshot_v2_audit.md`
   - `9` locale/seed fixture JSON files.

12. Classify the audit decisions.
   - `NO_ISSUE_FOUND`: proceed to Phase 2B contract work for that axis.
   - `READY_FOR_CORRECTION`: patch the source/projection/enrichment issue before
     the next generation run.
   - `BLOCKED_BY_UNKNOWN_SOURCE`: stop and inspect manually before writing any
     `session_snapshot.v2` schema or generator.

If this sequence regresses later, apply corrections in a separate correction run.

   - Name repairs should update the durable source used by `pack_pool.v1`, not
     patch runtime fixtures.
   - Referenced-only repairs should update governed referenced taxon data or
     localized-name evidence, not create active canonical taxa.
   - Keep corrections dry-run/audited before applying.

Regenerate or refresh `pack_pool.v1` only after corrections are understood.

   - Preserve lineage to the corrected source run.
   - Re-run Phase 2A/2B audits after regeneration.

Start `session_snapshot.v2` only when both audit axes are unblocked.

   - The first implementation must use the corrected label source.
   - The first fixture set must include at least `3` seeds for each of `fr`,
     `en`, and `nl`.
