# Pipeline

The pipeline is deliberately small and reproducible.

## 1. Ingest

- either read a tiny local bird fixture or a cached iNaturalist snapshot
- for live harvesting, cache raw API responses and one candidate image per observation
- for live snapshots, prefer real image variants over `square.jpg` thumbnails
- preserve raw payload references as local artifact paths

## 2. Normalize

- resolve source taxon mappings to canonical taxa
- assign stable internal media IDs
- persist normalized objects in SQLite
- write a normalized JSON snapshot
- use measured downloaded image dimensions for qualification decisions

## 3. Qualify

- enforce image-only scope
- evaluate commercial-safe license policy
- run either fixture AI outputs, cached AI outputs, rules-only mode, or Gemini over cached images
- persist Gemini outputs back into the snapshot cache
- reject uncertain snapshot records automatically in the nominal flow
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
