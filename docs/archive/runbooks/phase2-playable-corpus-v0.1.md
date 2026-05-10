> Archived / superseded document.
> This document is preserved for historical context only.
> It does not define the current runtime contract stack.
> Current contract source of truth: `docs/architecture/contract-map.md`.
> Do not use this document as current implementation guidance.

---
owner: database
status: in_progress
last_reviewed: 2026-04-29
source_of_truth: docs/archive/runbooks/phase2-playable-corpus-v0.1.md
scope: runbook
---

# Phase 2 - Premier corpus jouable interne v0.1

Statut: CLOSED
Date: 2026-04-29
Objectif: passer de l'interrogation live iNaturalist a un corpus jouable interne stable, pedagogique, et souverain.

## Decisions verrouillees

- base cible: nouvelle base dediee v0.1, simple et compatible avec un futur usage Supabase
- strategie corpus: reconstruction
- zone: Belgique stricte des l'ingestion
- taxons cibles: 50 especes d'oiseaux les plus populaires
- common_name_fr: obligatoire sur 100% des PlayableItem
- signalement v0.1: niveau operateur uniquement
- gate de sortie: strict 50 especes avec au moins 10 images chacune

## Cible corpus minimale

- 50 especes d'oiseaux jouables
- 10 a 30 images qualifiees par espece
- licences exploitables et attribution preservee
- lien observation source conserve
- taxon canonique interne conserve
- feedback court disponible
- difficulte approximative disponible
- distracteurs plausibles generables

## Objets et responsabilites

- CanonicalTaxon: identite espece interne gouvernee
- SourceObservation: observation source traceable
- MediaAsset: image source avec auteur/licence/url
- QualifiedResource: image jugee pedagogiquement exploitable
- PlayableItem: unite de jeu prete a servir

## Criteres d'acceptation fonctionnelle

Un item de question est consideré generable si le systeme produit:

- 1 image cible
- 1 bonne reponse
- 3 distracteurs
- 1 feedback court
- 1 attribution claire

Le flux doit fonctionner sans appel live iNaturalist pendant la generation de question.

## KPI Phase 2

- nombre d'especes jouables
- nombre d'images jouables par espece
- taux d'images rejetees
- taux d'especes avec au moins 10 images
- taux de questions generables sans erreur
- taux de completude common_name_fr
- taux de completude country_code (scope Belgique)

## Plan d'execution

### Etape 1 - Socle v0.1 dedie

- isoler la base v0.1 des environnements historiques
- conserver les contrats et schemas existants
- eviter toute derive de frontiere owner/runtime

Sortie attendue:

- environnement v0.1 identifiable et stable
- aucune ambiguite de source de verite entre historique et v0.1

### Etape 2 - Ingestion Belgique stricte

- appliquer un filtrage geo coherent avec la Belgique au niveau ingestion
- propager un country_code exploitable dans les objets observation et playable
- maintenir la tracabilite source complete

Sortie attendue:

- observations conformes au scope Belgique
- country_code exploitable dans le corpus jouable

### Etape 3 - Reconstruction corpus 50 especes populaires

- figer la liste des 50 especes cibles (popularite)
- reconstruire le corpus autour de cette liste
- prioriser la densite par espece (>=10) avant extension volumique

Sortie attendue:

- 50 especes presentes dans le corpus actif
- comblement des deficits de densite taxon par taxon

### Etape 4 - Qualification pragmatique

- conserver une qualification tracable, corrigeable, testable, ameliorable
- ne pas surqualifier au detriment de la couverture jouable
- monitorer les motifs de rejet dominants

Sortie attendue:

- qualite suffisante pour usage pedagogique
- deficits explicables et priorisables

### Etape 5 - common_name_fr a 100%

- etablir une strategie multi-source ordonnee
- completer les trous FR par gouvernance editoriale explicite
- garder la coherence canonique interne

Sortie attendue:

- common_name_fr renseigne sur 100% des PlayableItem actifs

### Etape 6 - Validation de jouabilite

- valider la generation de questions complete sur corpus interne
- valider les metadonnees pedagogiques et attribution
- verifier l'absence d'appel live iNaturalist dans la boucle de jeu

Sortie attendue:

- production stable de questions conformes au contrat

## Gate de sortie Phase 2

La phase est terminee uniquement si toutes les conditions suivantes sont vraies:

- 50 especes jouables actives
- chaque espece a au moins 10 images qualifiees actives
- common_name_fr complet sur 100% des items actifs
- questions generables sans erreur au seuil attendu
- aucune dependance live iNaturalist pour le jeu

## Risque principal

Surqualifier trop tot et perdre la dynamique de couverture.

Position de pilotage:

- d'abord jouable, traceable, corrigeable
- ensuite raffinement qualitatif iteratif

## Hors scope de cette phase

- extension multi-taxa (plantes, champignons, insectes)
- audio
- offline avance
- IA premium
- dashboard institutionnel avance
- multi-pays complexe
- marketplace de packs

## References

- README.md
- docs/runbooks/v0.1-scope.md
- docs/foundation/runtime-consumption-v1.md
- docs/runbooks/execution-plan.md
- docs/runbooks/audit-reference.md

## Execution automatisable (implementee)

Script operatoire phase 2:

- `scripts/phase2_playable_corpus_v0_1.py`

Le script execute, dans l'ordre:

1. audit initial du corpus jouable actif
2. recommandation de strategie (`reconstruction`, `reuse_and_complete`, `reuse_and_expand`)
3. reconstruction pilotee (`fetch-inat-snapshot` -> `qualify-inat-snapshot` -> `run-pipeline`)
4. validation de jouabilite (compilation de questions + verification feedback/attribution)
5. gate final GO/NO_GO avec KPI explicites

Artefact de sortie:

- `docs/archive/evidence/<YYYY-MM>/phase2_playable_corpus_report.v1.json`

Commande nominale v0.1 (scope Belgique):

```bash
./.venv/bin/python scripts/phase2_playable_corpus_v0_1.py \
	--database-url '<DATABASE_URL_ISOLE>' \
	--target-country-code BE \
	--max-attempts 3
```

Commande de remediaton d'urgence (diagnostic hors contrainte pays):

```bash
./.venv/bin/python scripts/phase2_playable_corpus_v0_1.py \
	--database-url '<DATABASE_URL_ISOLE>' \
	--target-country-code ANY \
	--max-attempts 1
```

Gate appliquee par le script:

- `species_count >= 50`
- `species_with_min_images >= 50` (seuil min par espece: 10)
- `common_name_fr_effective_completeness == 1.0`
- `country_code_completeness == 1.0` (si scope pays actif)
- `question_generation_success_rate >= 0.99`
- `attribution_completeness == 1.0`

## Verdict final

Date de cloture: 2026-04-29
Statut: CLOSED
Gate final: GO

KPI de cloture:

- `species_count = 50`
- `species_with_min_images = 50` (seuil min par espece: 10)
- `question_generation_success_rate = 1.0`
- `phase2_closed = true`

Artefacts finaux:

- rapport final: `docs/archive/evidence/2026-04/phase2_playable_corpus_report.v1.json`
- snapshot source: `data/raw/inaturalist/phase2-birds-be-20260429T083143Z-a1`
- normalized: `data/normalized/phase2-close-gemini-normalized.json`
- qualified: `data/qualified/phase2-close-gemini-qualified.json`
- export: `data/exports/phase2-close-gemini-export.json`
