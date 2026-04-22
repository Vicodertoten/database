# KPIs Programme — Noyau Canonique Fort

Date d'activation: `2026-04-08`  
Source de vérité: `scripts/generate_smoke_report.py` (`smoke.report.v1`)

## Règles

1. Les KPIs sont calculés à chaque run smoke.
2. Le format de rapport est stable et diffable (`JSON trié`, versionné).
3. Un KPI est considéré atteint uniquement si son seuil est respecté sans exception.

## KPIs verrouillés (Gate 0)

| KPI | Seuil | Mesure |
|---|---|---|
| `exportable_unresolved_or_provisional` | `0` | nombre de ressources exportables liées à un taxon absent/provisional ou non-accepted |
| `governance_reason_and_signal_coverage` | `1.0` (100%) | couverture des événements de gouvernance avec `decision_reason` + `signal_breakdown` + `source_delta` complet |
| `export_trace_flags_uncertainty_coverage` | `1.0` (100%) | couverture des ressources exportables avec trace qualification/IA + flags + incertitude typée |

## Commande standard

```bash
python scripts/generate_smoke_report.py \
  --snapshot-id inaturalist-birds-20260408T123456Z \
  --fail-on-kpi-breach
```

Sortie par défaut:
- `docs/smoke_reports/<snapshot_id>.smoke_report.v1.json`

## Interprétation

- `overall_pass=true`: les 3 KPIs verrouillés sont atteints.
- `overall_pass=false`: au moins un KPI est hors seuil; le run est bloqué pour promotion.

## Gate 8 clarification

Gate 8 etend l'inspection operateur et la lisibilite des metriques, sans changer les KPI verrouilles.

Contraintes appliquees:

- aucun renommage de KPI verrouille
- aucun changement de seuil
- aucune rupture de format `smoke.report.v1`

Surfaces inspect metriques ajoutees en Gate 8:

- `inspect enrichment-metrics`
- `inspect confusion-metrics`

Ces vues sont des surfaces de lecture operateur et ne changent pas le contrat smoke KPI.

## Promotion P0 -> P1 (doctrine de decision)

Statuts autorises:

- `GO`
- `GO_WITH_GAPS`
- `NO_GO`

Regle de classement:

- `GO`: hard gates passes et KPI etendus dans la cible
- `GO_WITH_GAPS`: hard gates passes et au moins un KPI etendu hors cible non bloquante
- `NO_GO`: hard gate casse ou seuil bloquant depasse

Hard gates P0 -> P1:

1. `compile_success_ratio_segment == 1.0` sur 3 runs comparables
2. `overall_pass == true` sur 3 runs comparables
3. comparabilite demontree (segment, snapshot/policy, commandes, formules, `difficulty_policy`)
4. contrats runtime inchanges + smoke nominal vert
5. latence consumer: aucun run au-dessus du seuil bloquant

KPI etendus P0 -> P1 (non bloquants a l'entree P1):

- `owner_distractor_diversity_vs_prototype`
- `consumer_latency_vs_prototype`

Budget latence P1 (`latency_e2e_segment_p95`, cote consumer):

- vert: `<= 900ms`
- ambre: `> 900ms` et `<= 1500ms` (gap suivi)
- rouge: `> 1500ms` (bloquant)

Regle de stabilite latence (3 runs):

- au plus 1 run au-dessus de `900ms`
- 0 run au-dessus de `1500ms`

Objectifs distractor diversity P1:

- amelioration obligatoire vs baseline P0
- plancher minimal de sortie P1: `0.15`
- cible recommandee de sortie P1: `0.25`
