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
- Gemini-ready image qualification over cached media
- review queue for uncertain cases
- JSON export bundle for downstream consumers
- lightweight inspection CLI

## AI-assisted qualification

The default local pipeline uses deterministic fixture AI outputs so the repository stays executable offline.

An optional Gemini adapter is included as a future-ready seam for image qualification. As of April 7, 2026, Google's official Gemini docs list `gemini-3-flash-preview` as a preview model and `gemini-2.5-flash` as a stable Flash model. The code defaults to the stable model ID until a live qualification workflow is tested against the preview series.

## Commands

```bash
python scripts/fetch_inat_snapshot.py --snapshot-id birds-20260407 --max-observations-per-taxon 1
python scripts/run_pipeline.py
python scripts/run_pipeline.py --db-path data/pilot.sqlite --qualifier-mode rules
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id birds-20260407
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id birds-20260407 --qualifier-mode gemini
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

Running `fetch_inat_snapshot.py` writes:

- raw iNaturalist responses to `data/raw/inaturalist/<snapshot_id>/responses/`
- cached candidate images to `data/raw/inaturalist/<snapshot_id>/images/`
- manifest to `data/raw/inaturalist/<snapshot_id>/manifest.json`

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
