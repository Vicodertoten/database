---
owner: database
status: in_progress
last_reviewed: 2026-05-09
source_of_truth: docs/runbooks/dynamic-pack-phase-1-corpus-gate.md
scope: dynamic_pack_phase_1_corpus_gate
---

# Dynamic Pack Phase 1 Corpus Gate

## Purpose

Phase 1 measures whether the current birds corpus can become the source pool for
the first dynamic pack.

This phase is audit-only until the gaps are understood. It must not launch new
iNaturalist harvesting, Gemini qualification, schema migrations, runtime changes,
or product APIs.

## Locked Decisions

- Phase 1 starts with a baseline audit against the current Postgres database.
- Do not fill gaps just to reach volume. New data must improve the corpus in a
  clean, traceable, maintainable way.
- First dynamic pack geography is Belgium + France (`BE`, `FR`), not Belgium
  alone.
- Each of the 50 target species must have exactly the intended minimum depth:
  `20` exportable/playable images per species.
- Distinguish:
  - raw images;
  - AI-qualified images;
  - exportable resources;
  - playable/exportable active resources.
- Product readiness uses BE+FR-scoped exportable/playable images as the
  practical target, not raw ingested media.
- Rebuild execution should happen first in a DB/schema clone, then be promoted
  only after audit.
- FR/EN/NL names and option labels are blocking for the target pack pool.
- Locale completion should first use iNaturalist re-enrichment and trusted source
  names. If no common name is available for a locale, the scientific name is an
  acceptable fallback.
- Long pedagogical feedback in FR/EN/NL is measured in Phase 1 but not blocking
  for the first corpus gate.
- Distractors are audited and recommendations are written in Phase 1; strategy is
  locked in Phase 2.
- `database` remains the source of truth. `runtime-app` is unchanged in Phase 1.

## Baseline Command Set

Run from the `database` repo with the intended `.env` database URL:

```bash
set -a; source .env; set +a

python scripts/inspect_database.py summary --database-url "$DATABASE_URL"
python scripts/inspect_database.py run-metrics --database-url "$DATABASE_URL"
python scripts/inspect_database.py playable-corpus --database-url "$DATABASE_URL" --limit 50
python scripts/inspect_database.py playable-invalidations --database-url "$DATABASE_URL" --limit 50

python scripts/generate_smoke_report.py \
  --database-url "$DATABASE_URL" \
  --fail-on-kpi-breach

python scripts/phase2_playable_corpus_v0_1.py \
  --database-url "$DATABASE_URL" \
  --skip-rebuild \
  --output-dir docs/archive/evidence/dynamic-pack-phase-1/2026-05-09-baseline \
  --target-country-code BE \
  --target-species-count 50 \
  --min-images-per-species 20 \
  --max-images-per-species 100 \
  --question-attempts 100 \
  --question-count 20
```

The `phase2_playable_corpus_v0_1.py --skip-rebuild` command is reused only as an
audit tool here. It does not relaunch harvest or Gemini.

This baseline command uses `BE` because the decision to make the first dynamic
pack `BE + FR` was locked after the baseline was produced. The next corpus gate
report must use the BE+FR target scope.

## Phase 1 Tooling

Minimal Phase 1 tooling is provided by:

```bash
python scripts/phase1_corpus_gate.py --run-id <run-id> preflight
python scripts/phase1_corpus_gate.py --run-id <run-id> select-pre-ai \
  --snapshot-id <be-fr-snapshot-id> \
  --output-snapshot-id <gemini-worklist-snapshot-id> \
  --final-input-snapshot-id <final-input-snapshot-id>
python scripts/phase1_corpus_gate.py --run-id <run-id> audit
```

Environment:

- `DATABASE_URL`: current production/reference DB, used read-only for baseline
  and already-seen media exclusion.
- `PHASE1_DATABASE_URL`: clone DB used for Phase 1 rebuild and final gate.

The tooling produces:

- `preflight_report.json`;
- `pre_ai_selection_report.json`;
- `gemini_cost_report.json`;
- `phase1_corpus_gate_report.json`;
- `phase1_corpus_gate_summary.md`.

`select-pre-ai` has two distinct snapshot outputs:

- `--output-snapshot-id`: Gemini worklist only. It excludes media already present
  in `DATABASE_URL` and is the only snapshot that should be sent to Gemini.
- `--final-input-snapshot-id`: full BE+FR corpus input. It preserves already-known
  media and new worklist media so the final Phase 1 corpus can merge cached
  existing qualifications with newly qualified images.

France is represented by iNaturalist `place_id=6753`. `FR` is now accepted as a
country filter in the iNaturalist harvest adapter.

Phase 1 BE+FR harvest must be captured as a single iNaturalist snapshot, not as
separate BE and FR snapshots merged later:

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id phase1-be-fr-20260509-be-fr-smoke \
  --pilot-taxa-path data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json \
  --country-code BE,FR \
  --max-observations-per-taxon 1
```

Smoke validation must pass before a full harvest:

```bash
test -d data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/responses
test -d data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/taxa
test -d data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/images
test -f data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/manifest.json
find data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/images -type f | wc -l
jq '[.media_downloads[] | select(.download_status == "downloaded")] | length' \
  data/raw/inaturalist/phase1-be-fr-20260509-be-fr-smoke/manifest.json
```

Full harvest, only after smoke validation:

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id phase1-be-fr-20260509-be-fr-raw-v1 \
  --pilot-taxa-path data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json \
  --country-code BE,FR \
  --max-observations-per-taxon 60
```

Progress monitor:

```bash
SNAPSHOT=data/raw/inaturalist/phase1-be-fr-20260509-be-fr-raw-v1
date
find "$SNAPSHOT/responses" -type f 2>/dev/null | wc -l
jq -s '[.[].results[]?] | length' "$SNAPSHOT"/responses/*.json
jq -s '[.[].results[]?.photos[]?] | length' "$SNAPSHOT"/responses/*.json
find "$SNAPSHOT/images" -type f 2>/dev/null | wc -l
jq '[.media_downloads[]?.download_status] | group_by(.) | map({status: .[0], count: length})' \
  "$SNAPSHOT/manifest.json"
```

Pre-AI selection, after full harvest validation:

```bash
python scripts/phase1_corpus_gate.py \
  --run-id phase1-be-fr-20260509-pre-ai-v3 \
  select-pre-ai \
  --snapshot-id phase1-be-fr-20260509-be-fr-raw-v1 \
  --output-snapshot-id phase1-be-fr-20260509-gemini-worklist-v3 \
  --final-input-snapshot-id phase1-be-fr-20260509-final-input-v3
```

Gemini must run only on the worklist snapshot:

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id phase1-be-fr-20260509-gemini-worklist-v3
```

Merge Gemini outputs back into the final input snapshot before running the cached
pipeline:

```bash
python scripts/phase1_corpus_gate.py \
  --run-id phase1-be-fr-20260509-ai-merge-v4 \
  merge-ai-outputs \
  --final-input-snapshot-id phase1-be-fr-20260509-final-input-v3 \
  --gemini-worklist-snapshot-id phase1-be-fr-20260509-gemini-worklist-v3
```

The merge writes `ai_outputs.json` into
`phase1-be-fr-20260509-final-input-v3` and updates that snapshot manifest. It
must report `missing=0` before `run_pipeline`.

Final cached pipeline must use the isolated Phase 1 schema, never `public`:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id phase1-be-fr-20260509-final-input-v3 \
  --qualifier-mode cached \
  --qualification-policy v1.1 \
  --uncertain-policy reject
```

Final gate:

```bash
python scripts/phase1_corpus_gate.py \
  --run-id phase1-be-fr-20260509-final-audit-v1 \
  audit \
  --question-generation-success-rate 0.99
```

## Baseline Findings - 2026-05-09

Evidence:

- `docs/archive/evidence/dynamic-pack-phase-1/2026-05-09-baseline/phase2_playable_corpus_report.v1.json`
- `docs/archive/evidence/smoke-reports/postgres.smoke_report.v1.json`

Current DB summary:

- canonical taxa: `50`
- source observations: `817`
- media assets: `816`
- qualified resources: `816`
- exportable resources: `408`
- playable items in table: `3182`
- BE-scoped exportable/playable items: `408`
- BE-scoped exportable/playable taxa: `49`
- review queue: `0`

Smoke report status:

- locked MVP smoke KPIs: `overall_pass=true`
- export trace / flags / uncertainty coverage: `1.0`
- unresolved or provisional exportables: `0`
- governance reason/signal coverage: `1.0`

Dynamic corpus gate status:

- gate decision: `NO_GO`
- species count target: `50`; actual BE exportable/playable taxa: `49`
- media target: `1000`; actual BE exportable/playable items: `408`
- species with at least `20` BE exportable/playable images: `0`
- question generation success rate: `0.0`
- attribution completeness: `1.0`
- country completeness on the BE exportable/playable audit set: `1.0`
- qualification rejection rate: `0.5`
- estimated AI-qualified images: `526`
- estimated AI cost: `EUR 0.6312`

Multilingual strict readiness on BE exportable/playable items:

- strict `fr` names: `0 / 408`
- strict `en` names: `392 / 408`
- strict `nl` names: `0 / 408`

Important interpretation:

- The current DB is healthy enough for the Golden Pack MVP smoke contract.
- It is not ready as a dynamic pack pool.
- The active BE exportable/playable corpus is too sparse and uneven.
- The strict FR/NL label readiness is not sufficient for dynamic runtime options.
- `playable_items` contains broader/stale rows beyond the BE exportable product
  subset, so Phase 1 reporting must always scope counts by country, exportability,
  and product target.

## Phase 1 Checklist

### 1. Baseline Audit

- Generate the smoke report.
- Generate the skip-rebuild corpus report.
- Record DB summary, run metrics, invalidations, and top rejection flags.
- Confirm no new ingestion, Gemini call, migration, runtime change, or product API.

### 2. Product-Scoped Metrics

Measure and publish:

- raw/source observations;
- media assets;
- qualified resources;
- exportable resources;
- BE+FR exportable/playable items;
- BE+FR exportable/playable taxa;
- images per taxon;
- median images per taxon;
- taxa below `20` images;
- taxa with `0` exportable/playable images;
- invalidated playable items by reason;
- top qualification rejection flags;
- estimated Gemini cost per AI-qualified image;
- estimated Gemini cost per BE+FR exportable/playable image.

### 3. Locale Readiness

Blocking for target pack pool:

- taxon label exists for every target and option in `fr`;
- taxon label exists for every target and option in `en`;
- taxon label exists for every target and option in `nl`;
- locale is fixed per session.

Measured but not blocking in early Phase 1:

- long feedback localized to `fr`;
- long feedback localized to `en`;
- long feedback localized to `nl`;
- photo-specific explanation quality per locale.

### 4. Distractor Audit

Measure:

- question generation success rate;
- distractor slot coverage;
- unique directed target/distractor pairs;
- repeated pairs;
- missing labels per locale;
- `referenced_only` usage;
- unfair or too-obvious distractors found by manual review.

Phase 1 output is recommendations, not a locked distractor strategy.

### 5. Data Posture Decision

Classify the next data action:

- `reuse_current`: current DB can serve as direct base.
- `targeted_repair`: current DB is usable but needs targeted enrichment or
  repair.
- `targeted_rebuild`: current corpus should be rebuilt for the target segment
  while preserving repo architecture and governance.
- `clean_start`: new DB/repo is required.

Current baseline recommendation: `targeted_rebuild`.

Reason: the repo architecture and DB structures are valuable, but the current BE
exportable/playable corpus is too sparse for dynamic serving. A targeted,
measured reconstruction of the first BE+FR birds pack pool in a DB/schema clone
is cleaner than patching until counts look good.

## Exit Criteria

Phase 1 can close with `GO`, `GO_WITH_WARNINGS`, or `NO_GO`.

Minimum `GO` criteria for dynamic pack pool work:

- `50` target BE+FR bird species are represented.
- Each target species has `20` BE+FR exportable/playable images.
- At least `1000` BE+FR exportable/playable images are available.
- No target species has `0` BE+FR exportable/playable images.
- FR/EN/NL target and option labels are complete for the target pool.
- Attribution and country completeness are `1.0` on the target pool.
- Question generation succeeds at `>= 0.99` for the target policy.
- Distractor audit has no blocking fairness issue.
- Cost per AI-qualified image and cost per playable item are measured.
- No live iNaturalist or Gemini call is required in runtime.

`GO_WITH_WARNINGS` is acceptable only if hard product gates pass and remaining
gaps are non-blocking measurements, such as long-form feedback localization.

`NO_GO` applies when the corpus cannot reliably produce dynamic 20-question
sessions without runtime patching or unmeasured data repair.

## Recommended Next Work

1. Keep the Phase 1 baseline as the current source of truth.
2. Add a product-scoped audit query/report that does not confuse all historical
   `playable_items` with BE+FR exportable/playable pool readiness.
3. Produce a targeted rebuild plan for BE+FR birds:
   - exact 50 target taxa;
   - 20 exportable/playable images per taxon;
   - clone-first execution and promotion criteria;
   - pre-AI dedup and rejection accounting;
   - iNaturalist re-enrichment for FR/EN/NL names, with scientific-name fallback
     when no locale common name exists;
   - Gemini budget estimate before execution.
4. Do not implement `pack_pool.v1` until this corpus gate has a clean
   `GO` or an explicit `GO_WITH_WARNINGS`.

## Remaining Questions For Phase 1 Completion

- What is the minimum acceptable median images per taxon for dynamic launch?
- Should the first dynamic pack product label remain `Belgian Birds`, or be
  renamed to reflect BE+FR scope?
- Should strict `en` names be corrected where current data appears to contain
  French labels in the `en` slot before or during re-enrichment?
- What promotion mechanism will move the clone-audited corpus into the primary
  database: full replacement, schema swap, or targeted table promotion?
