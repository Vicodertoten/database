---
owner: database
status: draft_for_implementation
last_reviewed: 2026-05-09
source_of_truth: docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md
scope: dynamic_pack_product_roadmap
---

# Dynamic Pack Product Roadmap

## Purpose

This document defines the post-Golden-Pack product direction for Inaturaquizz.

The immediate target is no longer a single static 30-question artifact. The next
target is a broad, qualified BE+FR birds corpus that can power dynamic packs,
fixed shared challenges, institutional assignments, and later user-created packs.

This document is a product/architecture roadmap. It does not replace:

- `docs/architecture/MASTER_REFERENCE.md` for the current `golden_pack.v1` MVP handoff;
- `docs/runbooks/pre-scale-ingestion-roadmap.md` for ingestion hardening;
- `docs/runbooks/phase3-distractor-strategy.md` for distractor policy details.

Phase 0 execution is tracked in
`docs/runbooks/dynamic-pack-phase-0-plan.md`.

Phase 2B execution is tracked in
`docs/runbooks/dynamic-pack-phase-2b-runtime-session-contract.md`.

## Locked Decisions

### Short-Term Corpus Target

- Scope: birds of Belgium + France.
- Target coverage: 50 species.
- Target media depth: 1,000 exportable/playable images, with `20` images per
  target species.
- Runtime locale support: `fr`, `en`, `nl`.
- External source: iNaturalist-first, through snapshots/caches, not live runtime calls.
- Locale names/options: iNaturalist re-enrichment first, trusted source names
  accepted, scientific name fallback allowed when no locale common name exists.
- Corpus rebuild posture: execute first in a DB/schema clone, then promote after
  audit.
- Runtime loop: no live iNaturalist calls, no live Gemini calls, no runtime invention of names,
  distractors, feedback, taxonomy, or pedagogy.

### Dynamic Pack Model

The first strategic dynamic pack product name is:

```text
Common birds Belgium/France
```

`Belgian Birds` is too narrow because the first pack uses Belgium and France as
the target corpus scope.

It is not a fixed list of 20 questions. It is a pack definition over a broad
qualified pool.

When a user starts a normal dynamic session:

1. runtime requests or receives a generated question set from a serving-ready pack pool;
2. the session is generated at start time;
3. the generated session is snapshotted and remains fixed until completion;
4. answers are scored against the snapshotted options;
5. user signals are stored by `runtime-app` and later batched back to `database`.

Selection should be random enough to feel fresh, but constrained enough to avoid
bad experiences.

Initial policy:

- target count: 20 questions per session;
- random media selection from the qualified pool;
- no duplicate image/media item inside one generated session;
- repeated species/taxa are allowed in the first dynamic implementation;
- anti-abuse limits against excessive repetition of the same species are later
  personalization/selection-policy work, not a Phase 2B blocker;
- beginner learning mode may allow repeated species, but limited;
- evaluation mode should avoid or tightly control repeated species;
- a generated session must be immutable once started.

Recommended implementation principle:

```text
randomized, not naive-random
```

The system should avoid letting highly covered taxa dominate the session simply
because they have more images.

For normal dynamic sessions, immutability applies after generation only. The
same species or image candidate must not be bound permanently to the same
distractors across all future sessions. The selector should use controlled
randomness before snapshotting, then freeze the exact displayed media, options,
labels, order, and feedback for that one attempt.

The first playable dynamic session contract is `session_snapshot.v2`.
`session_snapshot.v1` is retained as the Phase 2A target-only proof surface and
is not considered a playable runtime contract because it intentionally defers
option generation.

### Fixed Modes

Some modes intentionally freeze the generated question set.

#### Daily Challenge

- Same quiz for every user.
- Same questions, images, and options for every user.
- Runtime display is localized to the fixed session locale (`fr`, `en`, `nl`).
- Generated once for a daily window.
- Stored as a fixed materialization.
- All users answer the same questions and options.

#### Institutional Assignment

- Fixed and reproducible.
- Generated or selected by an institution/teacher.
- Must be stable for fairness, grading, correction, and audit.
- Should not adapt per student during the assignment attempt unless explicitly
  defined by a future assignment mode.

### User-Created Packs

User-created packs are a future product feature.

Initial version should be controlled:

- users choose from existing database-backed filters;
- no free-form external ingestion;
- no automatic creation of canonical taxa;
- no runtime-generated taxonomy;
- no free prompt-to-pack until pack coverage, safety, and review workflows are mature.

First useful controls:

- taxon group;
- geography;
- difficulty;
- season/date when data supports it;
- families/orders/common categories;
- known curated pack templates.

### Personalization

Runtime personalization is desirable, but it must not move corpus truth into the
runtime.

Initial personalization signals:

- global user level;
- mastery per taxon;
- confusion matrix between taxa;
- image difficulty;
- future spaced-repetition/revision mode inspired by Anki-like scheduling.

Recommended sequencing:

1. Global level.
2. Mastery per taxon.
3. Confusion matrix.
4. Image difficulty calibration.
5. Revision mode with spaced repetition.

Runtime may adapt session selection based on these signals. `database` remains
owner of corpus quality, distractor validity, taxon identity, labels, feedback,
and media qualification.

### Accounts And Identity

Accounts are required for long-term personalization, institutional use, and
cross-device history.

They are not technically difficult compared with the data pipeline, but they add
real product and operational weight:

- authentication provider or custom auth decision;
- user profile storage;
- privacy policy and data retention;
- institution/teacher/student roles later;
- account deletion and export expectations;
- anonymous-to-account migration if the MVP starts without login.

Recommendation:

- do not block the dynamic corpus roadmap on full accounts;
- design runtime telemetry so it can work with either `anonymous_user_id` or
  `user_id`;
- introduce real accounts before serious personalization, assignments, or
  cross-device progress;
- keep institution-specific auth and roles as a later product layer, not inside
  `database`.

### Referenced-Only Distractors

`referenced_only` means a taxon is known and governed as a referenced external
taxon, but is not yet a fully playable canonical taxon with its own qualified
media.

In product terms:

- it may appear as a distractor;
- it should not be the correct answer for a normal image question;
- it may not have images in the current qualified corpus;
- it must carry safe labels and traceable source/mapping status.

Policy:

- acceptable in MVP and dynamic packs with guardrails;
- in normal dynamic sessions, `referenced_only` distractors are allowed with a
  maximum of `2` per question;
- in institutional assignment modes, `referenced_only` should be disabled by
  default unless a future assignment policy explicitly enables it;
- selected `referenced_only` answers should still be logged as confusion signals;
- sensitive institutional modes may later disable `referenced_only` by default
  until human validation is stronger.

Referenced-only taxa require their own readiness audit before Phase 2B runtime
handoff. Scientific name and provenance are mandatory. Locale common names
(`fr`, `en`, `nl`) should be harvested or repaired when available. Internal
fixtures may use scientific-name-only referenced distractors, but public release
must not use referenced-only distractors without a locale common name unless a
specific editorial exception is recorded.

Phase 2B audit status on the isolated Phase 1/2A clone:

- correction run: `phase2b-name-repair-v18`;
- source run: `run:20260509T180000Z:2b18beef`;
- Phase 2A audit: `GO`;
- Phase 2B `name-repair`: `NO_ISSUE_FOUND`;
- Phase 2B `referenced-only`: `NO_ISSUE_FOUND`;
- referenced taxa total in the clone: `0`.

### Locale Policy

Session locale is fixed at session start.

Initial supported locales:

- `fr`;
- `en`;
- `nl`.

Runtime must not switch labels or feedback language mid-session. This keeps
questions auditable and makes user-performance signals interpretable.

The Phase 2A audit reported FR/NL scientific-name fallback usage. Because the
project expects FR/EN/NL names to exist for the initial corpus, Phase 2B must
treat that fallback as a likely data selection or propagation defect until
proven otherwise. Phase 2B validation is blocked until the FR/NL label source is
diagnosed and corrected or the remaining fallback cases are explicitly justified.

Phase 2B name repair has corrected this for internal runtime handoff. The
`database.schema.v19` pipeline persists multilingual canonical names from
iNaturalist `localized_taxa`, rebuilds `playable_items.common_names_i18n_json`,
projects `pack_pool.v1` with `2313/2313` common-name labels in each of `fr`,
`en`, and `nl`, and adds Palier A `distractor_relationships` persistence for
canonical-only validated distractors. Phase 2B now also exports and persists
`9` `session_snapshot.v2` fixtures for internal runtime handoff. The v2 audit is
`GO_WITH_WARNINGS` only because traced `taxonomic_fallback_db` distractors are
used where canonical relationship depth is still below `3`.

Runtime option display should receive both common and scientific names from
`database`. The runtime may render the common name as the primary option label
and the scientific name beneath it in smaller, italic, lower-emphasis text. The
runtime must not derive or repair these labels locally.

## Target Architecture

### Repository Responsibilities

`database` owns:

- canonical taxon identity;
- referenced taxon governance;
- source ingestion and traceability;
- media qualification;
- localized names and provenance;
- feedback content;
- distractor candidate generation and governance;
- qualified corpus and serving-ready pools;
- pack definitions and fixed materializations;
- batch ingestion of runtime confusion/performance signals;
- audits and GO/GO_WITH_WARNINGS/NO_GO run decisions.

`runtime-app` owns:

- session creation;
- session snapshot persistence;
- question presentation;
- answer submission;
- scoring against snapshotted options;
- user/session telemetry;
- dynamic session selection using serving-ready data;
- daily challenge and assignment play flows.

Future product/institutional layer owns:

- accounts and identity;
- organizations/classes/cohorts;
- teacher workflows;
- assignments;
- reporting dashboards;
- permissions and institution-level policy.

This layer should be introduced when product requirements justify it. It should
not be forced into `database`.

### Serving Surface Direction

`golden_pack.v1` remains the current MVP handoff contract.

The next serving surface should support:

- large qualified pools;
- dynamic 20-question session generation;
- fixed materializations for daily challenge and assignments;
- locale-safe labels and feedback;
- stable question snapshots;
- performance telemetry identifiers.

Candidate future contract family:

```text
pack_pool.v1
session_snapshot.v1
fixed_challenge.v1
assignment_materialization.v1
runtime_signal_batch.v1
```

Exact names are candidate names and remain unlocked until Phase 2
implementation. The important distinction is the object model:

- pack definition: what the pack means;
- pack pool: eligible serving-ready items;
- session snapshot: the exact generated attempt;
- fixed materialization: shared/reproducible quiz;
- signal batch: user outcomes flowing back to `database`.

## Data Model Implications

### Database-Side Needs

Before broad dynamic serving, `database` needs stronger persistent objects for:

- qualified media pool membership;
- image-level pedagogical/difficulty score;
- locale readiness by taxon and option;
- distractor relationship/candidate status;
- pack pool coverage metrics;
- fixed materialization lineage;
- Gemini cost metrics;
- pre-AI rejection and dedup metrics;
- runtime signal batch ingestion.

Existing structures already cover part of this:

- `playable_items`;
- `playable_item_lifecycle`;
- `pack_specs`;
- `compiled_pack_builds`;
- `pack_materializations`;
- `referenced_taxa`;
- `confusion_events`;
- `confusion_aggregates_global`.

But the current Golden Pack path still relies too heavily on run-scoped files and
clean-room scripts. The next workstream should move durable decisions into
explicit persistent stores while keeping artifacts for audit/export.

### Runtime-Side Needs

`runtime-app` already persists:

- session;
- session questions;
- selected option;
- selected taxon;
- expected taxon;
- shown distractors;
- correctness.

This is a good base for future metrics.

Likely additions:

- anonymous/user identity;
- session locale;
- session mode (`dynamic_pack`, `daily_challenge`, `assignment`, later `revision`);
- generated pool/materialization id;
- response time if useful;
- question/image difficulty metadata copied into snapshot;
- selected taxon ref type (`canonical_taxon` or `referenced_taxon`);
- telemetry export jobs to `database`.

## Selection Policy

The dynamic session selector should be deterministic enough to audit and random
enough to feel alive.

Recommended first policy:

1. Filter serving-ready pool by pack definition and locale.
2. Exclude unsafe or incomplete records.
3. Apply user/mode constraints.
4. Select candidate target taxa with diversity limits.
5. Select one media item per target with weighted randomness.
6. Select three pre-approved distractors.
7. Freeze the result as a session snapshot.

Anti-abuse constraints:

- cap repeats of the same taxon per session;
- cap recently seen image repetition for logged-in users;
- avoid duplicate media across the same session;
- avoid overusing the same distractor pair;
- ensure all labels and feedback match the session locale;
- preserve exact displayed option order for scoring and telemetry.

## Metrics Roadmap

### Corpus Metrics

- qualified images total;
- qualified images per taxon;
- median qualified images per taxon;
- locale readiness `fr/en/nl`;
- feedback coverage;
- distractor coverage;
- referenced-only distractor usage;
- pre-AI rejection rates;
- Gemini cost per qualified image;
- Gemini cost per playable item.

### Runtime/User Metrics

- global accuracy;
- accuracy by taxon;
- accuracy by image difficulty;
- confusion pair counts;
- repeated confusion pairs;
- session completion rate;
- image/question report rate;
- future spaced-repetition due counts.

### Database Feedback Loop

Runtime signals should flow back through batch ingestion.

Example flow:

```text
runtime_session_answers
  -> runtime_signal_batch.v1
  -> database confusion_events / review queue / aggregate metrics
  -> corpus and distractor improvements
  -> next pack pool build
```

Runtime signals must not directly mutate canonical taxonomy, labels, media
qualification, or distractor validity.

## Roadmap

### Phase 0 - Document And Align

Goal: align docs and decisions after the Golden Pack MVP.

Actions:

- keep `golden_pack.v1` documented as the current MVP surface;
- document the dynamic pack target;
- remove or annotate stale docs that still present old materialization surfaces
  as the active runtime contract;
- define the object model for pack definition, pool, session snapshot, fixed
  materialization, and signal batch.

Exit criteria:

- one clear source of truth for post-MVP dynamic pack direction;
- no ambiguity between MVP artifact and future dynamic serving.

### Phase 1 - Corpus Scale Gate

Goal: reach a reliable BE+FR birds corpus target.

Execution is tracked in
`docs/runbooks/dynamic-pack-phase-1-corpus-gate.md`.

Targets:

- 50 species;
- 1,000 exportable/playable images;
- 20 exportable/playable images per species;
- measured Gemini cost;
- measured pre-AI rejection;
- measured locale readiness;
- measured distractor coverage.

Actions:

- harden pre-AI filtering and dedup across runs;
- execute targeted rebuilds in a DB/schema clone before promotion;
- produce cost metrics per run;
- complete FR/EN/NL name readiness gates with iNaturalist re-enrichment and
  scientific-name fallback when needed;
- keep `referenced_only` usage visible in audit;
- produce GO/GO_WITH_WARNINGS/NO_GO corpus report.

Exit criteria:

- corpus is large enough to support fresh 20-question sessions;
- operator can explain why images/options are accepted or rejected.

### Phase 2 - Dynamic Pack Pool And Runtime Session Contract

Goal: create a serving-ready pool and a playable dynamic session contract for
`Common birds Belgium/France`.

Phase 2 is split into:

- Phase 2A: `pack_pool.v1` and `session_snapshot.v1` target-only fixtures.
- Phase 2B: `session_snapshot.v2` playable runtime contract with options.

Actions:

- define pool contract;
- persist eligible question/media candidates;
- persist locale readiness;
- persist distractor candidate readiness;
- implement pool diagnostics;
- define first randomized selection policy;
- repair or explicitly justify FR/NL locale fallbacks before runtime handoff;
- audit referenced-only distractor locale readiness;
- define `session_snapshot.v2` with snapshot-ready options;
- generate at least three deterministic seeds per locale (`fr`, `en`, `nl`) to
  prove controlled random variation.

Exit criteria:

- a dynamic 20-question session can be generated from the pool without live
  external calls;
- generated sessions are auditable and reproducible from stored inputs;
- every generated session contains no duplicate media item;
- every generated question contains exactly four snapshotted options, exactly
  one correct option, and exactly three distractors;
- distractors are selected by deterministic scoring plus weighted randomness,
  using iNaturalist similar-species signals and taxonomic proximity with
  traceable fallback when needed;
- public/runtime handoff receives a complete contract owned by `database`, not
  locally redefined runtime logic.

### Phase 3 - Runtime Dynamic Sessions

Goal: move from static `pack.json` sessions to dynamic pack sessions.

Actions:

- extend runtime session modes;
- snapshot generated questions at session start;
- store locale, generated pool id, and `session_snapshot_id`;
- record selected taxon ref type;
- preserve existing scoring model;
- keep `golden_pack.v1` compatibility until dynamic mode is validated.

Exit criteria:

- dynamic sessions work end-to-end;
- static Golden Pack remains available as fallback/reference.

### Phase 4 - Dynamic Pack Generator V1 And Runtime Signals

Goal: move runtime dynamic sessions from frozen fixture replay to local
generation from a serving-ready bundle.

Actions:

- export `serving_bundle.v1` with eligible pool items, labels, media,
  validated canonical distractor relationships, and taxonomy fallback profiles;
- copy the validated serving bundle into `runtime-app`;
- generate a fresh `session_snapshot.v2` per runtime start from `{poolId,
  locale, seed}`;
- keep the 9 Phase 2B snapshots as regression presets;
- keep `golden_pack.v1` as disabled/unavailable fallback;
- persist answer signals with expected/selected canonical taxa and option
  source metadata.

Exit criteria:

- random Dynamic Pack sessions vary by generated seed;
- the same `{poolId, locale, seed}` reproduces the same snapshot;
- answer submission writes one non-idempotent runtime signal;
- bundle audit is `GO` or `GO_WITH_WARNINGS` with fallback explicitly traced.

### Phase 5 - Fixed Challenges And Assignments

Goal: support shared fixed quiz experiences.

Actions:

- define daily challenge materialization;
- define assignment materialization;
- ensure same quiz for every user in daily challenge;
- ensure institutional assignments are fixed/reproducible;
- add lineage and audit for generated fixed sets.

Exit criteria:

- daily challenge can be generated and served;
- assignment materialization can be reproduced and audited.

### Phase 6 - User Metrics And Adaptation

Goal: introduce simple personalization without corrupting corpus ownership.

Actions:

- introduce anonymous or account-linked user identity;
- compute global user level;
- compute mastery by taxon;
- ingest confusion matrix signals into `database`;
- apply basic adaptive selection policy for normal learning sessions.

Exit criteria:

- runtime can adapt question selection using user metrics;
- `database` receives batch signals and updates aggregate insights.

### Phase 7 - Revision Mode

Goal: introduce spaced repetition.

Actions:

- define revision queue model;
- schedule taxon/image reviews based on performance;
- keep revision mode separate from normal dynamic pack mode;
- use Anki-like ideas without copying a full card system too early.

Exit criteria:

- user has a meaningful personal revision queue;
- mastery improves selection without changing corpus truth.

### Phase 7 - User-Created Packs

Goal: allow users to create controlled packs from existing database coverage.

Actions:

- expose safe filters;
- validate coverage before pack creation;
- prevent unsupported free-form taxonomy;
- generate pack diagnostics before session start;
- later consider free-form natural language pack creation.

Exit criteria:

- user-created packs are constrained, explainable, and only use existing
  qualified database content.

### Phase 8 - Institution/Product Layer

Goal: separate institutional workflows from core runtime and database concerns.

Actions:

- accounts and roles;
- organizations/classes;
- assignment creation;
- reporting;
- privacy/data-retention policies;
- institution-level pack restrictions.

Exit criteria:

- institutional product flows exist without moving knowledge-core logic into
  `runtime-app` or account logic into `database`.

## Open Questions

- What is the exact future contract name after `golden_pack.v1`?
- Should dynamic pack pools be exported as artifacts, served from Postgres, or both?
- What are the first hard thresholds for dynamic session quality?
- What should the first BE+FR dynamic pack be called in product UI?
- When should `DistractorRelationship` persistence be enabled?
- Should `referenced_only` be disabled by default for institutional assignments?
- Which auth provider or account architecture should be used when accounts become necessary?
- How long should anonymous session history be retained?
- What privacy policy applies to user performance/confusion metrics?
- Should image difficulty be database-owned, runtime-calibrated, or both?

## Current Recommendation

Do not create a new repository or database from scratch now.

The current `database` repository already contains valuable architecture:

- canonical governance;
- Postgres migrations;
- media qualification;
- pack/materialization history;
- referenced taxa;
- confusion aggregates;
- Golden Pack export validation.

The better path is:

1. keep `database` as the knowledge core;
2. keep `runtime-app` as runtime/session layer;
3. convert clean-room file-script decisions into durable stores where needed;
4. introduce dynamic pack pools after corpus metrics are solid;
5. introduce accounts and institution layer only when product requirements demand it.
