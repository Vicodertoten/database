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

- Documentation index: `docs/README.md`
- Living audit reference: `docs/05_audit_reference.md`
- Stable canonical charter v1: `docs/06_charte_canonique_v1.md`
- Canonical implementation ADR: `docs/adr/0001-charte-canonique-v1.md`
- Noyau canonique fort ADR: `docs/adr/0002-noyau-canonique-fort-execution-sequentielle.md`
- Chaîne playable/pack/compilation/enrichissement ADR: `docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`
- Program KPI checklist: `docs/10_program_kpis.md`

## Boundaries doctrinaux

- runtime never reads `export.bundle.v4`
- `database` owns canonical, qualification, export, and future playable/pack/materialization/enrichment/confusion aggregates
- runtime owns session/question serving/answers/score/progression UX
- pack is a durable specification object; a runtime game session is separate and ephemeral
- compilation is deterministic on existing data (no external calls); enrichment is asynchronous and traceable

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/postgres'
python scripts/verify_repo.py
python scripts/migrate_database.py --database-url "$DATABASE_URL"
python scripts/run_pipeline.py
python scripts/inspect_database.py summary
```

Installed entrypoints mirror the script wrappers:
`database-run-pipeline`, `database-inspect`, `database-fetch-inat-snapshot`,
`database-qualify-inat-snapshot`, `database-review-overrides`,
`database-governance-review`, and `database-migrate`.

## What works now

- typed domain models for the four core objects
- PostgreSQL/PostGIS storage with explicit migration versioning
- native geospatial columns and queries for `bbox` and `point + radius`
- deterministic fixture-driven ingestion
- manual iNaturalist snapshot harvesting with local raw cache
- cached snapshot normalization without live network access
- explicit canonical taxon enrichment from cached taxon payloads
- separation between resolved canonical similarity and unresolved external similarity hints
- staged qualification with license safety enforcement
- persisted Gemini image qualification over cached media with prompt-version checks
- structured review queue with stage, reason code, and priority
- canonical governance review queue with close/resolve workflow metadata (`resolved_at`, `resolved_note`, `resolved_by`)
- snapshot-scoped review overrides that can be replayed on rerun
- versioned normalized, qualification, and export artifacts
- JSON export bundles validated against versioned JSON Schemas before write
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
python scripts/migrate_database.py --database-url "$DATABASE_URL"
python scripts/run_pipeline.py
python scripts/run_pipeline.py --database-url "$DATABASE_URL" --qualifier-mode rules
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode cached --uncertain-policy reject
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --allow-schema-reset --qualifier-mode cached --uncertain-policy reject
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode cached --uncertain-policy reject --apply-review-overrides
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode cached --uncertain-policy reject --export-v3-sidecar
python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id inaturalist-birds-20260408T123456Z --qualifier-mode gemini --uncertain-policy reject
python scripts/inspect_database.py summary
python scripts/inspect_database.py run-metrics --snapshot-id inaturalist-birds-20260408T123456Z --run-id run:20260408T123456Z:aaaaaaaa
python scripts/inspect_database.py review-queue --review-reason-code human_override
python scripts/inspect_database.py canonical-governance-review-queue --snapshot-id inaturalist-birds-20260408T123456Z --review-status open
python scripts/governance_review.py resolve --snapshot-id inaturalist-birds-20260408T123456Z --governance-review-item-id cgr:run:20260408T123456Z:aaaaaaaa:event:taxon:birds:000001:split:demo --note "validated against source delta" --resolved-by operator:alice
python scripts/inspect_database.py snapshot-health --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/review_overrides.py init --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/review_overrides.py upsert --snapshot-id inaturalist-birds-20260408T123456Z --media-asset-id media:inaturalist:810001 --status review_required --note "manual spot-check requested"
python scripts/review_overrides.py list --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/generate_smoke_report.py --snapshot-id inaturalist-birds-20260408T123456Z
python scripts/generate_smoke_report.py --snapshot-id inaturalist-birds-20260408T123456Z --fail-on-kpi-breach
python scripts/build_goldset_v1.py --clean
python scripts/optimize_goldset_media.py
python scripts/verify_goldset_v1.py
python scripts/run_goldset_live_pipeline.py --snapshot-id goldset-birds-v1-live-$(date -u +%Y%m%dT%H%M%SZ)
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

## Canonical governance operator workflow

Canonical governance decisions with `manual_reviewed` status are pushed into
`canonical_governance_review_queue`.

Recommended flow:

1. inspect open items with `python scripts/inspect_database.py canonical-governance-review-queue --snapshot-id <id> --review-status open`
2. resolve one item with `python scripts/governance_review.py resolve --snapshot-id <id> --governance-review-item-id <item_id> --note "<mandatory note>" --resolved-by <operator>`
3. re-inspect queue/backlog and verify closure metadata (`resolved_at`, `resolved_note`, `resolved_by`)

## Outputs

Running the fixture pipeline writes:

- normalized snapshot to `data/normalized/normalized_snapshot.json`
- qualification snapshot to `data/qualified/qualification_snapshot.json`
- export bundle to `data/exports/qualified_resources_bundle.json`
- materialized/latest state + history into the configured PostgreSQL schema (`DATABASE_URL`)

In `inat_snapshot` mode, the default derived outputs become snapshot-scoped:

- normalized: `data/normalized/<snapshot_id>.json`
- qualified: `data/qualified/<snapshot_id>.json`
- export: `data/exports/<snapshot_id>.json`
- optional sidecar export (`v3`, opt-in only): `data/exports/<snapshot_id>.v3.json`

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

- schema version: `database.schema.v8`
- snapshot manifest version: `inaturalist.snapshot.v3`
- normalized snapshot version: `normalized.snapshot.v3`
- canonical enrichment version: `canonical.enrichment.v2`
- qualification version: `qualification.staged.v1`
- export version: `export.bundle.v4`
- sidecar export version: `export.bundle.v3` (transition mode, opt-in only)
- review override version: `review.override.v1`

Snapshot manifests without `manifest_version` are rejected.
Unknown manifest versions are rejected explicitly.
The primary export bundle (`v4`) is validated against
`schemas/qualified_resources_bundle_v4.schema.json` before write.
The optional sidecar (`v3`) is generated only with `--export-v3-sidecar` and validated against
`schemas/qualified_resources_bundle_v3.schema.json`.

## Canonical enrichment

Canonical taxa now carry a small enrichment layer in addition to their internal identity and external mappings:

- `taxon_group`
- `key_identification_features`
- `source_enrichment_status`
- `external_similarity_hints`
- `similar_taxa`
- derived `similar_taxon_ids`
- `authority_taxonomy_profile`

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

Gold set verification is explicit and separate:

```bash
python scripts/verify_goldset_v1.py
```

Pipeline writes use overwrite semantics for run-output tables in one transaction
to avoid stale rows between runs.

Gold set full live E2E (Gemini + pipeline):

```bash
python scripts/run_goldset_live_pipeline.py \
  --snapshot-id goldset-birds-v1-live-$(date -u +%Y%m%dT%H%M%SZ) \
  --uncertain-policy reject
```

The command creates a snapshot-like workspace under `data/raw/inaturalist/<snapshot_id>/`,
runs `qualify_inat_snapshot` with Gemini, then runs the full pipeline in `inat_snapshot` mode
using cached outputs.
It fails fast if any image is below Gemini minimum resolution (512x512), unless
`--allow-insufficient-resolution` is provided.

It runs, in order:

1. `python -m compileall src tests`
2. `pytest -q -p no:capture`
3. `python scripts/check_doc_code_coherence.py`
4. `python -m ruff check src tests scripts`

If `ruff` is missing, the script fails with an explicit message and recommends `pip install -e ".[dev]"`.

For the live 15-taxon smoke workflow, see [docs/04_smoke_runbook.md](docs/04_smoke_runbook.md).

## Continuous integration

GitHub Actions runs `python scripts/verify_repo.py` on pull requests and pushes to `main`
via `.github/workflows/verify-repo.yml`, with a PostGIS service and
`python scripts/migrate_database.py --database-url "$DATABASE_URL"` before verification.
