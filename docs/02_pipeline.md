# Pipeline

The pipeline is deliberately small, versioned, and reproducible.

## 1. Ingest

- either read a tiny local bird fixture or a cached iNaturalist snapshot
- for live harvesting, cache raw observation API responses, taxon detail payloads, and one candidate image per observation
- preserve raw payload references as local artifact paths
- write a versioned snapshot manifest

## 2. Normalize

- resolve source taxon mappings to canonical taxa
- assign stable internal media IDs
- persist normalized objects in SQLite
- write a normalized JSON snapshot
- use measured downloaded image dimensions for qualification decisions

## 3. Enrich canonical taxa

- read only cached local taxon payloads from the snapshot
- populate canonical enrichment fields such as `key_identification_features`
- extract source-side similarity hints when available
- resolve similarity into internal `similar_taxa` only when the target taxon already exists in the canonical seed
- keep unresolved source hints separate from canonical relationships

## 4. Qualify

- run explicit stages:
  - compliance screening
  - fast semantic screening
  - expert qualification
  - review queue assembly
- enforce image-only scope
- evaluate commercial-safe license policy
- run either fixture AI outputs, cached AI outputs, rules-only mode, or Gemini over cached images
- persist Gemini outputs back into the snapshot cache
- reject uncertain snapshot records automatically in the nominal snapshot flow
- write qualified resources and structured review queue entries

## 5. Optional review overrides

- inspect the structured review queue
- create or update snapshot-scoped overrides in `data/review_overrides/<snapshot_id>.json`
- rerun the pipeline with `--apply-review-overrides`
- replay human decisions without mutating raw snapshot artifacts

## 6. Export

- export only `QualifiedResource` records with `export_eligible = true`
- include only canonical taxa needed by downstream consumers
- keep unresolved external hints out of the public export bundle
- validate the export against `schemas/qualified_resources_bundle.schema.json` before writing

## 7. Inspect

- provide summary counts
- list exportable resources
- list review queue items with filters
- report snapshot health for cached iNaturalist snapshots

## Versioning

Generated artifacts carry explicit stage versions:

- `schema_version`
- `manifest_version`
- `normalized_snapshot_version`
- `enrichment_version`
- `qualification_version`
- `export_version`

The current writers always emit snapshot manifests as `inaturalist.snapshot.v2`.
Legacy manifests without `manifest_version` remain readable.
Unknown manifest versions are rejected explicitly.
