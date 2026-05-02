---
owner: database
status: stable
last_reviewed: 2026-05-02
source_of_truth: docs/audits/qualification-policy-v1-v11-comparison.md
scope: audit
---

# Qualification Policy v1 vs v1.1 Comparison

## 1. Scope and protocol

Snapshot compare cible:

- `palier1-be-birds-50taxa-run002-closure`

Runs executes le 2026-05-02:

- v1: `run:20260502T143602Z:1924ebb0`
- v1.1: `run:20260502T143628Z:d2e5e547`

Mode pipeline:

- `--source-mode inat_snapshot`
- `--qualifier-mode cached`
- `--uncertain-policy reject`
- `--qualification-policy v1` puis `v1.1`

Aucun refetch iNaturalist.
Aucune relance Gemini (cache reutilise).

## 2. Global outcome (v1 vs v1.1)

| Metric | v1 | v1.1 | Delta |
|---|---:|---:|---:|
| total candidates | 1413 | 1413 | 0 |
| accepted | 581 | 1284 | +703 |
| rejected | 832 | 129 | -703 |
| review_required | 0 | 0 | 0 |
| accepted_with_flags (accepted + flags) | 0 | 703 | +703 |
| exportable total | 581 | 1284 | +703 |

Observation cle:

- v1.1 convertit exactement `703` rejets v1 en accepted_with_flags exportables.

## 3. Export/playable/taxa impact

Pack diagnose sans profile (comportement default) sur la fixture 50 taxons:

| Metric | v1 | v1.1 | Delta |
|---|---:|---:|---:|
| playable total | 581 | 1284 | +703 |
| taxa_served | 45 | 50 | +5 |
| blocking taxa count | 8 | 1 | -7 |

Blocking taxa default:

- v1: `taxon:birds:000026`, `000032`, `000037`, `000040`, `000041`, `000044`, `000045`, `000047`
- v1.1: `taxon:birds:000026`

Interpretation:

- La policy v1.1 ferme quasi completement le gap de couverture run002 closure.
- Le pack reste non compilable uniquement a cause de `min_media_per_taxon` pour un taxon (1 image).

## 4. Media per taxon distribution (exportable)

| Metric | v1 | v1.1 |
|---|---:|---:|
| taxa with >=1 media | 45 | 50 |
| min media/taxon | 1 | 1 |
| p10 media/taxon | 3 | 5 |
| median media/taxon | 12 | 35 |
| p90 media/taxon | 23 | 38 |
| max media/taxon | 32 | 39 |

## 5. Flags in accepted v1.1

Top flags parmi les accepted_with_flags:

1. `insufficient_technical_quality`: 662
2. `insufficient_resolution`: 86
3. `incomplete_required_tags`: 41
4. `missing_view_angle`: 41
5. `low_ai_confidence`: 36
6. `missing_visible_parts`: 10

Low confidence floor rejects:

- `low_ai_confidence_below_floor` rejects: 1

## 6. Newly accepted by v1.1

- newly accepted count: `703`
- newly exportable count: `703`

Ces items correspondent principalement aux anciens rejets v1 sur defauts pedagogiques/visuels (et non a des erreurs techniques IA/cache).

## 7. Derived classification distribution

Distribution sur tous les candidats qualifies (`1413`):

### observation_kind

- `habitat_context`: 693
- `full_bird`: 499
- `partial`: 134
- `trace_or_feather`: 35
- `nest_or_eggs`: 29
- `in_flight`: 22
- `carcass`: 1

### diagnostic_strength

- v1: `high=377`, `medium=198`, `low=806`, `unknown=32`
- v1.1: `high=377`, `medium=198`, `low=807`, `unknown=31`

### pedagogical_role

- v1: `core_id=340`, `advanced_id=157`, `context=56`, `forensics=28`, `excluded=832`
- v1.1: `core_id=340`, `advanced_id=266`, `context=642`, `forensics=36`, `excluded=129`

### difficulty_band

- `starter=433`, `intermediate=395`, `expert=457`, `unknown=128` (stable v1/v1.1)

Interpretation:

- v1.1 deplace massivement des items de `excluded` vers `context`/`advanced_id`.
- Le noyau `core_id` reste stable (`340`) ; le gain se fait sur la base elargie et le role pedagogique.

## 8. Pack readiness by profile

Diagnose `pack:palier1:be:birds:run003-core` et `pack:palier1:be:birds:run003-mixed`:

| Context | compilable | reason_code | taxa_served | total_playable_items | blocking_taxa |
|---|---|---|---:|---:|---:|
| v1 default (no profile) | no | `insufficient_media_per_taxon` | 45 | 581 | 8 |
| v1 core profile | no | `insufficient_media_per_taxon` | 43 | 340 | 12 |
| v1 mixed profile | no | `insufficient_media_per_taxon` | 45 | 522 | 9 |
| v1.1 default (no profile) | no | `insufficient_media_per_taxon` | 50 | 1284 | 1 |
| v1.1 core profile | no | `insufficient_media_per_taxon` | 43 | 340 | 12 |
| v1.1 mixed profile | no | `insufficient_media_per_taxon` | 48 | 631 | 8 |

Compilation/materialization status:

- default/core/mixed: **not compilable** (bloque par `min_media_per_taxon`)
- compile attempts retournent: `reason_code=insufficient_media_per_taxon`

## 9. Conclusion and decision framing

Conclusion:

- `v1.1` is technically useful because it expands coverage (`+703` exportables).
- `v1` remains the safer default global policy unless explicitly overridden.
- `v1.1` is accepted for Palier-1 under guardrails.
- Pack profiles must control quality more strictly than raw exportability.

Operational recommendation:

1. keep `v1` as global default (backward-safe),
2. enable `v1.1` explicitly on Palier-1 pipelines,
3. keep stricter pack-level gates for adoption-quality outputs,
4. rely on manual quality review for pedagogical adoption decisions.

## 10. Artifacts produced

- `data/qualified/palier1_be_birds_50taxa_v1_compare.qualified.json`
- `data/exports/palier1_be_birds_50taxa_v1_compare.export.json`
- `data/qualified/palier1_be_birds_50taxa_v11_compare.qualified.json`
- `data/exports/palier1_be_birds_50taxa_v11_compare.export.json`
- `data/exports/qualification_policy_v1_v11_comparison.json`
- `data/exports/palier1_be_birds_run003_default_v1.diagnose.json`
- `data/exports/palier1_be_birds_run003_default_v11.diagnose.json`
- `data/exports/palier1_be_birds_run003_core_v11profile.diagnose.json`
- `data/exports/palier1_be_birds_run003_mixed_v11profile.diagnose.json`
