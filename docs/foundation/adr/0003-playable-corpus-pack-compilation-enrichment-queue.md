---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/foundation/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md
scope: foundation
---

# ADR-0003 — Boundaries doctrinaux de la chaîne playable/pack/compilation/enrichissement

Statut: `accepted`  
Date: `2026-04-09`  
Portée: doctrine d’architecture et discipline d’exécution séquentielle

## Contexte

Le noyau actuel (`database`) est stable sur le canonique, la qualification, l’export versionné et la gouvernance.
La prochaine chaîne (playable, packs, compilation, matérialisation, enrichissement, confusions runtime) doit être ajoutée sans dérive de périmètre, sans couplage runtime, et sans chevauchement de gates.

Ce texte verrouille la doctrine avant toute implémentation des gates suivants.

## Décision

La chaîne cible est adoptée doctrinalement avec les boundaries suivants:

1. `database` vs `runtime`
- `database` porte les surfaces de données (canonique, qualification, export, puis playable/pack/compilation/enrichissement/confusions agrégées).
- le runtime porte uniquement l’exécution produit (sessions, questions servies, réponses, score, progression, UX).
- le runtime ne lit jamais `export.bundle.v4`.

2. `pack` vs `partie`
- un pack est un objet durable et versionné (`pack_id` stable + `revision`).
- une partie est une exécution runtime éphémère.
- une matérialisation figée est un artefact dérivé d’un pack, sans état utilisateur.

3. `compilation` vs `enrichissement`
- la compilation est déterministe et opère uniquement sur l’offre déjà présente en base.
- la compilation n’appelle aucune source externe.
- l’enrichissement est asynchrone, traçable, gouverné, et séparé de la compilation.

4. discipline d’exécution
- exécution strictement séquentielle par gate, sans chevauchement.
- aucun gate `N+1` ne commence avant clôture complète de `N` (code/tests/docs/migrations/critères).

## Conséquences

- les futures implémentations gates 2+ doivent s’ajouter en aval du noyau existant, sans refonte abstraite.
- les changements de doctrine structurants restent reflétés dans `README.md` et `docs/runbooks/audit-reference.md`.
- ce gate 1 est documentaire uniquement: aucun changement de contrat technique, aucun changement de schéma export, aucune implémentation fonctionnelle des gates suivants.

## Références

- `docs/runbooks/execution-plan.md`
- `docs/runbooks/audit-reference.md`
- `docs/foundation/canonical-charter-v1.md`
- `README.md`
