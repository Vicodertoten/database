> Archived / superseded document.
> This document is preserved for historical context only.
> It does not define the current runtime contract stack.
> Current contract source of truth: `docs/architecture/contract-map.md`.
> Do not use this document as current implementation guidance.

---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/archive/superseded-contracts/adr-0004-runtime-consumption-transport-v1.md
scope: foundation
---

# ADR-0004 — Runtime Consumption Transport V1

Statut: `accepted`  
Date: `2026-04-17`  
Portée: doctrine de transport inter-repos entre `database` (owner) et `runtime-app` (consumer)

## Contexte

`database` reste owner de la vérité des artefacts runtime et de leur sémantique.
`runtime-app` consomme ces surfaces officielles sans les redéfinir.

Les surfaces concernées sont déjà verrouillées:

- `playable_corpus.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`

La séquence récente a établi:

- publication d'artefacts/fixtures de référence côté owner
- ingestion et validation consumer-side de ces fixtures
- ajout d'un adapter de lecture côté `apps/api`
- exposition d'une API minimale de lecture côté `apps/api` (INT-006 fermé côté `runtime-app`)

Cette ADR ne redéfinit pas ces surfaces. Elle verrouille la narration de transport entre les deux repos.

## Décision

La doctrine de transport suivante est adoptée:

1. V1: transport par artefacts/fixtures publiés
- usage: verrouiller contrats, consommation locale, tests d'intégration, séparation owner/consumer

2. V1.5: transport par API de lecture minimale
- usage: faire de `apps/api` le point d'entrée unique produit
- `web` et `mobile` ne doivent pas être exposés à l'origine réelle des données

2.5. Phase 1: transport owner-side réel minimal en lecture
- usage: sortir du mode nominal fixtures-only pour les lectures runtime
- portée: uniquement `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`
- implementation owner-side minimale dans `database` (facade + HTTP borné)

3. Plus tard: opérations éditoriales plus riches
- ces capacités restent owned par `database`
- elles ne sont pas réinventées dans `runtime-app`

Rappels normatifs:

- `export.bundle.v4` reste hors surface live runtime
- cette ADR ne change pas la frontière de responsabilité déjà décidée
- cette ADR ne spécifie pas auth, transport réseau, déploiement, cache, ni synchronisation

## Conséquences

- Cette ADR formalise une séquence de transport; elle n'introduit aucune nouvelle vérité de surface.
- L'état courant conserve les étapes transitoires utiles (`fixtures owner-side` + `API minimale côté runtime`) et ajoute un transport owner-side réel minimal en lecture.
- Le mode nominal runtime n'est plus limité à des fixtures locales consumer-side: une lecture owner-side réelle minimale est en place.
- Les fixtures restent utiles pour tests/dev et fallback explicite, sans redevenir la jonction nominale.
- Les futurs besoins éditoriaux doivent être explicités par des contrats et flows dédiés, adossés aux capacités owned par `database`.
- Toute évolution de transport ultérieure doit partir de cette base et ne pas la contredire.
- `apps/api` est le point d'entrée produit, pas un lieu de redéfinition de la vérité data.
- Extension additive phase 3 validée sur `playable_corpus.v1` (sans bump de version):
  - `taxon_label`
  - `feedback_short`
  - `media_render_url`
  - `media_attribution`
  - `media_license`
  Ces champs restent owner-side et sont consommés en miroir strict côté runtime.
- Phase 4 runtime-side confirmée:
  - `runtime-app` peut projeter des DTOs player-ready (question/correction/progrès) à partir de ces champs
  - sans introduire de nouveau contrat owner-side dans `database`

## Références

- `README.md`
- `docs/foundation/runtime-consumption-v1.md`
- `docs/foundation/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`
- `docs/archive/chantiers/INT-003.md`
- `docs/archive/chantiers/INT-004.md`
- `runtime-app/docs/archive/chantiers/INT-006.md`
