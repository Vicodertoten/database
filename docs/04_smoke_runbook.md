# Smoke Runbook

This runbook describes the manual live smoke workflow for the 15-taxon bird pilot.
It is intentionally a manual operator procedure, not a CI test.

## Preconditions

- `GEMINI_API_KEY` is available in `.env` or the shell environment
- the local environment is installed with `pip install -e ".[dev]"`
- the operator is ready to record observations from a live run

## Recommended snapshot naming

Use the strict snapshot format:

- `inaturalist-birds-YYYYMMDDTHHMMSSZ`

Example:

- `inaturalist-birds-20260408T123456Z`

## Live flow

1. Fetch the snapshot.

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id inaturalist-birds-20260408T123456Z
```

2. Run Gemini qualification over the cached images.

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id inaturalist-birds-20260408T123456Z
```

This command now prints progress as it advances through the cached media set.

3. Build the normalized, qualified, and export artifacts from the cached snapshot.

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id inaturalist-birds-20260408T123456Z \
  --qualifier-mode cached \
  --uncertain-policy reject
```

4. Inspect snapshot health.

```bash
python scripts/inspect_database.py \
  snapshot-health \
  --snapshot-id inaturalist-birds-20260408T123456Z
```

5. Inspect the review queue.

```bash
python scripts/inspect_database.py \
  review-queue \
  --snapshot-id inaturalist-birds-20260408T123456Z
```

6. If manual overrides are needed, initialize or update them and rerun with explicit application.

```bash
python scripts/review_overrides.py init --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/review_overrides.py upsert \
  --snapshot-id inaturalist-birds-20260408T123456Z \
  --media-asset-id media:inaturalist:810001 \
  --status review_required \
  --note "manual spot-check requested"
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id inaturalist-birds-20260408T123456Z \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --apply-review-overrides
```

7. Generate the standardized smoke report and enforce KPI thresholds.

```bash
python scripts/generate_smoke_report.py \
  --snapshot-id inaturalist-birds-20260408T123456Z \
  --fail-on-kpi-breach
```

## What to inspect

During the smoke, focus on:

- how many taxa return usable observations
- how many images survive harvesting and resolution checks
- how many Gemini outcomes are valid versus missing, rate-limited, or malformed
- how many resources are accepted, rejected, or sent to review
- how many taxon enrichments end as `complete` versus `partial`
- whether unresolved similarity hints are common or rare
- which rejection flags dominate the run

Do not impose hard numeric thresholds yet.
This runbook is for observation and diagnosis, not pass/fail gating.

## Report template

Use the following template for a local operator note.
Do not commit a live report by default.

```text
snapshot_id:
observations_harvested:
images_downloaded:
images_sent_to_gemini:
accepted_resources:
review_required_resources:
rejected_resources:
review_queue_size:
top_rejection_flags:
enriched_taxa_complete:
enriched_taxa_partial:
example_unresolved_similarity_hints:
elapsed_time:
observed_cost:
notes:
```

## Security guardrail for versioned reports

- Any report committed under `docs/smoke_reports/` must redact credential-bearing fields.
- `database_url` values must be redacted (`user:***@host`) before commit.
- If a raw secret is committed, follow `docs/security_incident_runbook.md` immediately.

## Expected artifacts

After a successful live smoke, the main artifacts should be present:

- `data/raw/inaturalist/<snapshot_id>/manifest.json`
- `data/raw/inaturalist/<snapshot_id>/responses/`
- `data/raw/inaturalist/<snapshot_id>/taxa/`
- `data/raw/inaturalist/<snapshot_id>/images/`
- `data/raw/inaturalist/<snapshot_id>/ai_outputs.json`
- PostgreSQL materialized/history state in the configured schema (`DATABASE_URL`)
- `data/normalized/<snapshot_id>.json`
- `data/qualified/<snapshot_id>.json`
- `data/exports/<snapshot_id>.json`
- `docs/smoke_reports/<snapshot_id>.smoke_report.v1.json`
