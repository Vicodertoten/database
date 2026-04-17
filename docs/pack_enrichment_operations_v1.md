# Pack And Enrichment Operations V1

## Objet du document

Ce document decrit les operations pack/enrichment V1 actuellement reelles dans `database`.
Il sert de reference owner-side pour une orchestration future par `runtime-app`, sans transfert de verite.

Il ne cree aucun nouveau schema, aucune nouvelle operation, et aucun nouveau transport reseau.

## Boundary owner/consumer

- Owner (`database`): verite des parametres valides, de la compilabilite, des diagnostics, des artefacts produits et des statuts d'enrichissement.
- Consumer (`runtime-app`): peut piloter ces operations plus tard via des facades adaptees, sans redefinir la semantique owner.

Rappel normatif:

- `runtime-app` ne doit pas re-coder la logique profonde de pack/enrichment.
- `runtime-app` ne doit pas reconstruire la verite owner en local.

## Principes V1

- Quand une sortie versionnee existe deja, elle est canonique.
- Quand aucune sortie versionnee n'existe encore, l'operation est documentee comme flow operationnel owner-side.
- `export.bundle.v4` ne devient pas une surface runtime live.

## Catalogue des operations V1

### 1. Creer pack

- Owner: `database`
- But: creer une specification de pack durable et versionnee
- Entree attendue:
  - `python scripts/manage_packs.py create ...`
  - parametres alignes avec `pack.spec.v1.parameters`
- Sortie attendue:
  - payload JSON `pack.spec.v1`
- Artefact versionne associe:
  - `schemas/pack_spec_v1.schema.json`
- Statut de stabilite:
  - stable versionne
- Ce que `runtime-app` pourra piloter plus tard:
  - emission d'une demande de creation pack avec parametres valides
- Ce que `runtime-app` ne doit pas posseder:
  - semantique des parametres, revision authority, validation owner

### 2. Lister packs

- Owner: `database`
- But: exposer les packs existants et leurs revisions depuis l'etat owner
- Entree attendue:
  - `python scripts/inspect_database.py pack-specs [--pack-id --limit]`
  - `python scripts/inspect_database.py pack-revisions --pack-id ... [--revision --limit]`
- Sortie attendue:
  - listes JSON de payloads `pack.spec.v1` (vue listing/revisions)
- Artefact versionne associe:
  - `schemas/pack_spec_v1.schema.json`
- Statut de stabilite:
  - stable versionne (vue basee sur `pack.spec.v1`)
- Ce que `runtime-app` pourra piloter plus tard:
  - lecture/filtering de listings
- Ce que `runtime-app` ne doit pas posseder:
  - verite de revision, semantics des vues owner

### 3. Diagnostiquer

- Owner: `database`
- But: calculer la compilabilite d'un pack pour la revision cible
- Entree attendue:
  - `python scripts/manage_packs.py diagnose --pack-id ... [--revision]`
- Sortie attendue:
  - payload JSON `pack.diagnostic.v1`
- Artefact versionne associe:
  - `schemas/pack_diagnostic_v1.schema.json`
- Statut de stabilite:
  - stable versionne
- Ce que `runtime-app` pourra piloter plus tard:
  - declencher un diagnostic et consommer le resultat
- Ce que `runtime-app` ne doit pas posseder:
  - criteres de compilabilite, reason-code semantics, seuils owner

### 4. Compiler

- Owner: `database`
- But: produire un build compile deterministe pour un pack/revision
- Entree attendue:
  - `python scripts/manage_packs.py compile --pack-id ... [--revision] [--question-count]`
- Sortie attendue:
  - payload JSON `pack.compiled.v1`
- Artefact versionne associe:
  - `schemas/pack_compiled_v1.schema.json`
- Statut de stabilite:
  - stable versionne
- Ce que `runtime-app` pourra piloter plus tard:
  - demander compilation et recuperer build compile
- Ce que `runtime-app` ne doit pas posseder:
  - logique de selection des questions/distracteurs et semantique de build

### 5. Materialiser

- Owner: `database`
- But: geler une materialization derivee d'un build compile
- Entree attendue:
  - `python scripts/manage_packs.py materialize --pack-id ... [--revision] [--question-count] [--purpose] [--ttl-hours]`
- Sortie attendue:
  - payload JSON `pack.materialization.v1`
- Artefact versionne associe:
  - `schemas/pack_materialization_v1.schema.json`
- Statut de stabilite:
  - stable versionne
- Ce que `runtime-app` pourra piloter plus tard:
  - demander une materialization et la lire
- Ce que `runtime-app` ne doit pas posseder:
  - semantique de gel, gestion TTL, regles owner de materialization

### 6. Lire statut enrichissement

- Owner: `database`
- But: observer l'etat de la queue enrichissement et son execution
- Entree attendue:
  - `python scripts/inspect_database.py enrichment-requests ...`
  - `python scripts/inspect_database.py enrichment-executions ...`
  - `python scripts/inspect_database.py enrichment-metrics`
- Sortie attendue:
  - vues operationnelles owner-side (etat requests/executions/metrics)
- Artefact versionne associe:
  - aucun contrat JSON public versionne explicite a ce stade
- Statut de stabilite:
  - operationnel, non encore schema-versionne comme contrat public
- Ce que `runtime-app` pourra piloter plus tard:
  - consultation d'etat via facade owner-defined
- Ce que `runtime-app` ne doit pas posseder:
  - semantique des statuts et calcul des metriques owner

### 7. Demander/preparer enrichissement

- Owner: `database`
- But: creer/fusionner une demande d'enrichissement puis enregistrer son execution
- Entree attendue:
  - `python scripts/manage_packs.py enrich-enqueue --pack-id ... [--revision] [--question-count]`
  - `python scripts/manage_packs.py enrich-execute --enrichment-request-id ... [--execution-status] [--error-info] [--trigger-recompile]`
- Sortie attendue:
  - envelopes operationnelles JSON (`enqueued`, `request`, `targets`, `execution_status`, `recompilation`)
- Artefact versionne associe:
  - aucun contrat JSON public versionne explicite a ce stade
- Statut de stabilite:
  - operationnel, non encore schema-versionne comme contrat public
- Ce que `runtime-app` pourra piloter plus tard:
  - demander enqueue/execute via facade owner-defined
- Ce que `runtime-app` ne doit pas posseder:
  - logique de merge des demandes, lifecycle request/execution, decision de recompilation

## Rappels de boundary

- `database` reste owner de la verite sur:
  - parametres valides
  - compilabilite
  - diagnostics
  - artefacts produits
  - statuts d'enrichissement
- `runtime-app` pourra piloter ces operations plus tard, sans en devenir owner.
- Ce document ne constitue pas un transfert de verite vers `runtime-app`.

## References

- `README.md`
- `docs/runtime_consumption_v1.md`
- `docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`
- `docs/adr/0004-runtime-consumption-transport-v1.md`
- `src/database_core/cli.py`
- `src/database_core/storage/pack_store.py`
- `src/database_core/storage/enrichment_store.py`
- `schemas/pack_spec_v1.schema.json`
- `schemas/pack_diagnostic_v1.schema.json`
- `schemas/pack_compiled_v1.schema.json`
- `schemas/pack_materialization_v1.schema.json`
