# Gold Set IA V1

Statut: actif  
Version: `goldset.birds.v1`  
Date: `2026-04-08`  
Périmètre: `birds` / iNaturalist / 100 images / 20 taxons

## Objectif

Fournir un lot de référence stable pour les non-régressions IA sur la qualification image.
Servir aussi de base de montée en charge vers le corpus pilote V2 (~80 taxons) puis goldset V2 (100x5).

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
python scripts/build_goldset_v1.py --clean
```

Le script applique une limite API explicite (`--api-request-interval-seconds`, défaut `1.1s`) pour rester sous 60 req/min côté iNaturalist.
Il sélectionne uniquement des images qui satisfont le minimum Gemini (`512x512` par défaut).

Variante V2 (100 taxons x 5 images) :

```bash
python scripts/build_goldset_v1.py \
  --taxa-path data/fixtures/goldset_birds_v2_taxa.json \
  --goldset-version goldset.birds.v2 \
  --output-root data/goldset/birds_v2 \
  --images-per-taxon 5 \
  --clean
```

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

Variante V2:

```bash
python scripts/verify_goldset_v1.py \
  --manifest-path data/goldset/birds_v2/manifest.json \
  --expected-taxa-path data/fixtures/goldset_birds_v2_taxa.json \
  --expected-images-per-taxon 5 \
  --expected-goldset-version goldset.birds.v2
```

## Optimisation media

Pour convertir les GIF restants en JPEG plus légers:

```bash
python scripts/optimize_goldset_media.py
python scripts/verify_goldset_v1.py
```

## Test live E2E sur pipeline complète

Commande:

```bash
python scripts/run_goldset_live_pipeline.py \
  --snapshot-id goldset-birds-live-$(date -u +%Y%m%dT%H%M%SZ) \
  --uncertain-policy reject
```

Le script:

- matérialise un snapshot iNaturalist compatible pipeline depuis le manifest goldset
- lance la qualification Gemini en live
- exécute `run_pipeline` en `inat_snapshot` avec `qualifier_mode=cached`
- imprime les métriques clés (`processed`, `ai_ok`, `qualified`, `exportable`, `review`)

Le script échoue explicitement si des images du snapshot sont sous `512x512`
(option de contournement: `--allow-insufficient-resolution`).

Variante V2:

```bash
python scripts/run_goldset_live_pipeline.py \
  --goldset-manifest data/goldset/birds_v2/manifest.json \
  --pilot-taxa-path data/fixtures/birds_pilot_v2.json \
  --snapshot-id goldset-birds-v2-live-$(date -u +%Y%m%dT%H%M%SZ) \
  --uncertain-policy reject
```

## Extension corpus pilote V2 (R2a)

Fichier seed V2 : `data/fixtures/birds_pilot_v2.json` (80 taxons).
Le seed historique `data/fixtures/inaturalist_pilot_taxa.json` reste inchangé pour rétrocompatibilité.

Critères de sélection appliqués:

- fréquence d'observation élevée en Belgique (densité média iNaturalist)
- diversité taxonomique (objectif >= 10 familles)
- présence de paires de confusion (pour alimenter `similar_taxa` et les distracteurs)
- couverture inter-saisons (espèces observables toute l'année ou complémentaires)

Méthode et règle d'évolution:

- ajout uniquement via une liste explicite (pas de sampling aléatoire)
- validation de chaque taxon par `source_taxon_id` iNaturalist résolu
- continuité canonique: conservation des `canonical_taxon_id` existants, nouveaux IDs alloués séquentiellement
- retrait d'un taxon: documenter la raison (faible qualité média, ambiguïté taxonomique, licence insuffisante)

Run R2a recommandé (snapshot live + qualif + pipeline):

```bash
python -m database_core.cli fetch-inat-snapshot \
  --snapshot-id inaturalist-birds-v2-$(date -u +%Y%m%dT%H%M%SZ) \
  --pilot-taxa-path data/fixtures/birds_pilot_v2.json \
  --max-observations-per-taxon 10 \
  --bbox 2.50,49.45,6.40,51.60 \
  --observed-from 2023-01-01 \
  --observed-to 2026-12-31

python -m database_core.cli qualify-inat-snapshot --snapshot-id <SNAPSHOT_ID>

python -m database_core.cli run-pipeline \
  --source-mode inat_snapshot \
  --snapshot-id <SNAPSHOT_ID> \
  --qualifier-mode cached \
  --uncertain-policy reject
```

`--bbox`, `--place-id`, `--observed-from`, `--observed-to` sont optionnels et opt-in.
Sans ces flags, le comportement `fetch-inat-snapshot` reste inchangé.
