# Gold Set IA V1

Statut: actif  
Version: `goldset.birds.v1`  
Date: `2026-04-08`  
Périmètre: `birds` / iNaturalist / 100 images / 20 taxons

## Objectif

Fournir un lot de référence stable pour les non-régressions IA sur la qualification image.

## Contrat V1

- 20 taxons (liste fermée)
- 5 images par taxon
- 100 images au total
- licences commerciales sûres (`cc0`, `cc-by`, `cc-by-sa`)
- observations `research`, `photos=true`, `captive=false`

## Artefacts

- Manifest: `data/goldset/birds_v1/manifest.json`
- Images: `data/goldset/birds_v1/images/`

Le manifest contient par taxon:

- `scientific_name`
- `source_taxon_id`
- `requested_order_by` / `effective_order_by`
- `images[]` avec `source_observation_id`, `source_media_id`, `image_path`, `source_url`, licences, hash.

## Construction

Commande:

```bash
python scripts/build_goldset_v1.py
```

Le script applique une limite API explicite (`--api-request-interval-seconds`, défaut `1.1s`) pour rester sous 60 req/min côté iNaturalist.

## Vérification

Commande:

```bash
python scripts/verify_goldset_v1.py
```

Contrôles:

- cardinalité taxons/images (`20 x 5`)
- unicité `source_media_id`
- existence physique des fichiers image
- cohérence du `total_images` déclaré dans le manifest
