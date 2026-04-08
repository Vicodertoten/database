# Canonical ID Migration v1

Statut: appliqué  
Date: `2026-04-08`  
Règle d’allocation: tri lexical déterministe des IDs legacy `bird:*`, puis numérotation `taxon:birds:000001+`.

## Mapping legacy -> v1

| Legacy ID | Canonical v1 ID |
|---|---|
| `bird:columba-palumbus` | `taxon:birds:000001` |
| `bird:corvus-corone` | `taxon:birds:000002` |
| `bird:cyanistes-caeruleus` | `taxon:birds:000003` |
| `bird:erithacus-rubecula` | `taxon:birds:000004` |
| `bird:fringilla-coelebs` | `taxon:birds:000005` |
| `bird:garrulus-glandarius` | `taxon:birds:000006` |
| `bird:motacilla-alba` | `taxon:birds:000007` |
| `bird:parus-major` | `taxon:birds:000008` |
| `bird:passer-domesticus` | `taxon:birds:000009` |
| `bird:pica-pica` | `taxon:birds:000010` |
| `bird:sturnus-vulgaris` | `taxon:birds:000011` |
| `bird:sylvia-atricapilla` | `taxon:birds:000012` |
| `bird:troglodytes-troglodytes` | `taxon:birds:000013` |
| `bird:turdus-merula` | `taxon:birds:000014` |
| `bird:turdus-philomelos` | `taxon:birds:000015` |

## Périmètre migré

- fixtures versionnées (`data/fixtures`, `tests/fixtures`)
- manifests snapshots versionnés
- sorties versionnées (`data/normalized`, `data/qualified`, `data/exports`)
- tests et assertions associées
- chemins de cache dérivés (`taxon_birds_XXXXXX` en remplacement des anciens slugs)

## Politique de compatibilité

- hard cutover: aucune compatibilité lecture/écriture legacy maintenue dans le code v1
- tout ID non conforme au format `taxon:<group>:<padded_integer>` est désormais invalide pour `CanonicalTaxon`
