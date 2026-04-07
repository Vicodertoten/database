# Pipeline

The pipeline is deliberately small and reproducible.

## 1. Ingest

- either read a tiny local bird fixture or a cached iNaturalist snapshot
- for live harvesting, cache raw API responses and one candidate image per observation
- preserve raw payload references as local artifact paths

## 2. Normalize

- resolve source taxon mappings to canonical taxa
- assign stable internal media IDs
- persist normalized objects in SQLite
- write a normalized JSON snapshot

## 3. Qualify

- enforce image-only scope
- evaluate commercial-safe license policy
- run either fixture AI outputs, rules-only mode, or Gemini over cached images
- mark uncertain records as `review_required`
- write qualified resources and review queue entries

## 4. Export

- export only `QualifiedResource` records with `export_eligible = true`
- include canonical taxa needed by downstream consumers
- write a deterministic JSON bundle

## 5. Inspect

- provide summary counts
- list exportable resources
- list review queue items
- report snapshot health for cached iNaturalist snapshots
