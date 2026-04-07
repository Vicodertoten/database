# database

Minimal knowledge-core MVP for a future biodiversity learning platform.

This repository is intentionally narrow. It exists to prove a clean, traceable data core around:

- `CanonicalTaxon`
- `SourceObservation`
- `MediaAsset`
- `QualifiedResource`

Phase 1 is bird-only and pipeline-first:

- ingest a very small pilot dataset
- normalize it into internal canonical objects
- qualify media for pedagogical use
- keep uncertain cases reviewable
- export only qualified resources

The repository is not the quiz app, frontend, or product runtime.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_pipeline.py
python scripts/inspect_database.py summary
pytest
```

## What works now

- typed domain models for the four core objects
- local SQLite storage
- deterministic fixture-driven ingestion
- manual iNaturalist snapshot harvesting with local raw cache
- cached snapshot normalization without live network access
- qualification with license safety enforcement
- persisted Gemini image qualification over cached media
- fully automated rejection path for uncertain snapshot records
- optional review queue for audit, not required for the nominal snapshot flow
- JSON export bundle for downstream consumers
- lightweight inspection CLI

## AI-assisted qualification

The default local fixture pipeline uses deterministic AI outputs so the repository stays executable offline.

For cached iNaturalist snapshots, the nominal flow is:

1. `fetch-inat-snapshot`
2. `qualify-inat-snapshot`
3. `run-pipeline --source-mode inat_snapshot --snapshot-id <id> --qualifier-mode cached --uncertain-policy reject`

The CLI auto-loads `.env` and expects `GEMINI_API_KEY` there for the live Gemini step. The default live model is `gemini-3.1-flash-lite-preview`. Snapshot qualification now applies built-in pacing and retry/backoff to reduce Gemini rate-limit losses on larger batches.

## Commands

```bash
python scripts/fetch_inat_snapshot.py --snapshot-id birds-20260407 --max-observations-per-taxon 1
python scripts/run_pipeline.py
python scripts/run_pipeline.py --db-path data/pilot.sqlite --qualifier-mode rules
python scripts/qualify_inat_snapshot.py --snapshot-id birds-20260407
python scripts/qualify_inat_snapshot.py --snapshot-id birds-20260407 --request-interval-seconds 4.5 --max-retries 4
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id birds-20260407 --qualifier-mode cached --uncertain-policy reject
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id birds-20260407 --qualifier-mode gemini --uncertain-policy reject
python scripts/inspect_database.py summary
python scripts/inspect_database.py review-queue
python scripts/inspect_database.py snapshot-health --snapshot-id birds-20260407
```

## Outputs

Running the pipeline writes:

- normalized snapshot to `data/normalized/normalized_snapshot.json`
- qualification snapshot to `data/qualified/qualification_snapshot.json`
- export bundle to `data/exports/qualified_resources_bundle.json`
- SQLite database to `data/database.sqlite`

In `inat_snapshot` mode, the default derived outputs become snapshot-scoped:

- SQLite: `data/databases/<snapshot_id>.sqlite`
- normalized: `data/normalized/<snapshot_id>.json`
- qualified: `data/qualified/<snapshot_id>.json`
- export: `data/exports/<snapshot_id>.json`

Running `fetch_inat_snapshot.py` writes:

- raw iNaturalist responses to `data/raw/inaturalist/<snapshot_id>/responses/`
- cached candidate images to `data/raw/inaturalist/<snapshot_id>/images/`
- manifest to `data/raw/inaturalist/<snapshot_id>/manifest.json`

The harvester now filters the iNaturalist request to commercial-safe licenses and `captive=false`, tries `order_by=votes`, and falls back to `order_by=observed_on` if needed. The manifest records which sort was requested and which one was actually used.

Running `qualify_inat_snapshot.py` writes:

- cached AI outputs to `data/raw/inaturalist/<snapshot_id>/ai_outputs.json`
- an updated manifest pointing to that AI cache

## Fixture scope

The pilot fixture is deliberately tiny. It is enough to exercise the architecture, legal filtering, provenance handling, and export contract without pretending to be a full ingestion program.

## Pilot taxa

The checked-in iNaturalist seed list covers 6 species:

- `Turdus merula`
- `Erithacus rubecula`
- `Passer domesticus`
- `Cyanistes caeruleus`
- `Parus major`
- `Pica pica`
