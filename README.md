# database

database is the knowledge core of a future biodiversity learning product.
It builds an internal canonical reference of living taxa, ingests traceable real-world naturalist data, and qualifies media for pedagogical reuse.
External sources feed the system, but do not define its internal identity.
Raw observations and images are not yet learning resources; they become usable only after qualification.
Qualification is evidence- and pedagogy-driven: what is visible, what can be learned, and what is reliable enough to reuse.
The system is designed to automate most of this work while keeping uncertain cases reviewable.
Its job is to turn observed reality into a canonical, traceable, exportable corpus for future learning experiences.
The current implementation is an intentionally narrow pilot: birds-only, iNaturalist-first, image-only.
That narrow scope is a proving ground for a structure meant to scale toward a broader multi-taxa knowledge core.

This repository currently proves the core around:

- `CanonicalTaxon`
- `SourceObservation`
- `MediaAsset`
- `QualifiedResource`

The current pilot stays narrow on purpose:

- birds-only
- iNaturalist-only source implementation
- image-only qualification
- research-grade source quality only
- commercial-safe export only
- reviewable uncertain cases through a structured review queue and snapshot-scoped overrides

The repository is not the quiz app, frontend, or product runtime.

## Reference docs

- Living audit reference: `docs/05_audit_reference.md`
- Stable canonical charter v1: `docs/06_charte_canonique_v1.md`
- Canonical implementation ADR: `docs/adr/0001-charte-canonique-v1.md`
- Canonical ID migration table: `docs/07_canonical_id_migration_v1.md`

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/verify_repo.py
python scripts/run_pipeline.py
python scripts/inspect_database.py summary
```

Installed entrypoints mirror the script wrappers:
`database-run-pipeline`, `database-inspect`, `database-fetch-inat-snapshot`,
`database-qualify-inat-snapshot`, and `database-review-overrides`.

## What works now

- typed domain models for the four core objects
- local SQLite storage with explicit schema versioning
- deterministic fixture-driven ingestion
- manual iNaturalist snapshot harvesting with local raw cache
- cached snapshot normalization without live network access
- explicit canonical taxon enrichment from cached taxon payloads
- separation between resolved canonical similarity and unresolved external similarity hints
- staged qualification with license safety enforcement
- persisted Gemini image qualification over cached media with prompt-version checks
- structured review queue with stage, reason code, and priority
- snapshot-scoped review overrides that can be replayed on rerun
- versioned normalized, qualification, and export artifacts
- JSON export bundle validated against a JSON Schema before write
- lightweight inspection CLI

## AI-assisted qualification

The default local fixture pipeline uses deterministic AI outputs so the repository stays executable offline.

For cached iNaturalist snapshots, the nominal flow is:

1. `fetch-inat-snapshot`
2. `qualify-inat-snapshot`
3. `run-pipeline --source-mode inat_snapshot --snapshot-id <id> --qualifier-mode cached --uncertain-policy reject`

The CLI auto-loads `.env` and expects `GEMINI_API_KEY` there for the live Gemini step.
The default live model is `gemini-3.1-flash-lite-preview`.
Snapshot qualification keeps a sequential flow, but the default Gemini pacing is tuned for faster paid-account usage.
`qualify_inat_snapshot.py` now prints per-image progress so long runs are observable.
Cached AI outputs are version-governed through a prompt bundle version, so stale caches are rejected rather than silently mixed with current qualification logic.

## Commands

```bash
python scripts/fetch_inat_snapshot.py --snapshot-id inaturalist-birds-20260408T123456Z --max-observations-per-taxon 1
python scripts/qualify_inat_snapshot.py --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/qualify_inat_snapshot.py --snapshot-id inaturalist-birds-20260408T123456Z --request-interval-seconds 0.5 --max-retries 2 --initial-backoff-seconds 1 --max-backoff-seconds 8
python scripts/run_pipeline.py
python scripts/run_pipeline.py --db-path data/pilot.sqlite --qualifier-mode rules
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode cached --uncertain-policy reject
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode cached --uncertain-policy reject --apply-review-overrides
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode gemini --uncertain-policy reject
python scripts/inspect_database.py summary
python scripts/inspect_database.py review-queue --review-reason-code human_override
python scripts/inspect_database.py snapshot-health --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/review_overrides.py init --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/review_overrides.py upsert --snapshot-id inaturalist-birds-20260408T123456Z --media-asset-id media:inaturalist:810001 --status review_required --note "manual spot-check requested"
python scripts/review_overrides.py list --snapshot-id inaturalist-birds-20260408T123456Z
```

## Review workflow

The review queue is no longer audit-only.
It is a lightweight operator workflow for cases that need explicit human intervention.

Recommended flow:

1. inspect the queue with `python scripts/inspect_database.py review-queue --snapshot-id <id>`
2. initialize the override file with `python scripts/review_overrides.py init --snapshot-id <id>`
3. add or update decisions with `python scripts/review_overrides.py upsert ...`
4. rerun the pipeline with `python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id <id> --qualifier-mode cached --uncertain-policy reject --apply-review-overrides`

Override files live by default in `data/review_overrides/<snapshot_id>.json`.
They are snapshot-scoped, versioned, and never mutate raw snapshot artifacts.

## Outputs

Running the fixture pipeline writes:

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

- raw iNaturalist observation responses to `data/raw/inaturalist/<snapshot_id>/responses/`
- cached taxon detail payloads to `data/raw/inaturalist/<snapshot_id>/taxa/`
- cached candidate images to `data/raw/inaturalist/<snapshot_id>/images/`
- manifest to `data/raw/inaturalist/<snapshot_id>/manifest.json`

Running `qualify_inat_snapshot.py` writes:

- cached AI outputs to `data/raw/inaturalist/<snapshot_id>/ai_outputs.json`
- an updated manifest pointing to that AI cache

The harvester filters iNaturalist requests to commercial-safe licenses and `captive=false`, prefers `order_by=votes`, and falls back to `order_by=observed_on` if needed.
The manifest records which sort was requested and which one was actually used.

## Versioned artifacts

The repository now writes explicit stage versions into generated artifacts:

- schema version: `database.schema.v3`
- snapshot manifest version: `inaturalist.snapshot.v3`
- normalized snapshot version: `normalized.snapshot.v3`
- canonical enrichment version: `canonical.enrichment.v2`
- qualification version: `qualification.staged.v1`
- export version: `export.bundle.v2`
- review override version: `review.override.v1`

Snapshot manifests without `manifest_version` are rejected.
Unknown manifest versions are rejected explicitly.
The export bundle is validated against `schemas/qualified_resources_bundle.schema.json` before it is written.

## Canonical enrichment

Canonical taxa now carry a small enrichment layer in addition to their internal identity and external mappings:

- `taxon_group`
- `key_identification_features`
- `source_enrichment_status`
- `external_similarity_hints`
- `similar_taxa`
- derived `similar_taxon_ids`

The important distinction is:

- canonical identity is internal
- external mappings identify source records
- external similarity hints remain source suggestions
- resolved `similar_taxa` are internal canonical relationships

The enrichment stage is offline and deterministic for cached snapshots: it reads only the local taxon payload cache stored in the snapshot.

## Fixture scope

The fixture dataset remains deliberately tiny.
It exercises the architecture, legal filtering, provenance handling, enrichment, review workflow, and export contract without pretending to be a full ingestion program.

## Pilot taxa

The checked-in iNaturalist seed list now covers 15 bird species:

- `Turdus merula`
- `Erithacus rubecula`
- `Passer domesticus`
- `Cyanistes caeruleus`
- `Parus major`
- `Pica pica`
- `Fringilla coelebs`
- `Columba palumbus`
- `Sturnus vulgaris`
- `Turdus philomelos`
- `Sylvia atricapilla`
- `Motacilla alba`
- `Garrulus glandarius`
- `Corvus corone`
- `Troglodytes troglodytes`

## Maintenance

Use the repository verification script for the standard local check:

```bash
python scripts/verify_repo.py
```

It runs, in order:

1. `python -m compileall src tests`
2. `pytest -q`
3. `python -m ruff check src tests`

If `ruff` is missing, the script fails with an explicit message and recommends `pip install -e ".[dev]"`.

For the live 15-taxon smoke workflow, see [docs/04_smoke_runbook.md](docs/04_smoke_runbook.md).
