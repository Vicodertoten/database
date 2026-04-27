---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/foundation/adr/0005-editorial-write-transport-v1.md
scope: foundation
---

# ADR 0005 — Editorial Write Transport v1

Date: 2026-04-19
Status: accepted
Portee: transport owner-side minimal pour les operations editoriales critiques pack/enrichment.

## Contexte

`database` expose deja des artefacts versionnes stables (`pack.spec.v1`, `pack.diagnostic.v1`,
`pack.compiled.v1`, `pack.materialization.v1`) et des flows enrichissement operationnels.

`runtime-app` utilisait encore une facade mock semantique pour ces operations.

## Decision

Un service HTTP owner-side write minimal est introduit, separe du runtime-read service.

Principes verrouilles:

- perimetre strict: create/diagnose/compile/materialize + enrichment status/enqueue/execute
- aucune logique session/runtime UX
- aucune transformation en backend produit generaliste
- validation schema/version pour chaque envelope d'operation
- reutilisation exclusive des stores owner (`pack_store`, `enrichment_store`)

## Contrats v1

Envelopes versionnees par operation:

- `pack.create.v1`
- `pack.diagnose.v1`
- `pack.compile.v1`
- `pack.materialize.v1`
- `enrichment.request.status.v1`
- `enrichment.enqueue.v1`
- `enrichment.execute.v1`

Les payloads artefacts restent gouvernes par les contrats existants:

- `pack.spec.v1`
- `pack.diagnostic.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`

## Endpoints owner-side write

- `GET /health`
- `POST /editorial/packs`
- `POST /editorial/packs/{pack_id}/diagnose`
- `POST /editorial/packs/{pack_id}/compile`
- `POST /editorial/packs/{pack_id}/materialize`
- `POST /editorial/packs/{pack_id}/enrichment/enqueue`
- `GET /editorial/enrichment-requests/{enrichment_request_id}`
- `POST /editorial/enrichment-requests/{enrichment_request_id}/execute`

## Erreurs

Taxonomie minimale stable:

- `invalid_request` (400)
- `not_found` (404)
- `conflict` (409)
- `internal_error` (500)

## Non scope

- auth forte
- cache distribue
- orchestration backend produit complete
- transport write pour sessions runtime
