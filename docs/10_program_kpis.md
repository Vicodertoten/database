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
| `governance_reason_and_signal_coverage` | `1.0` (100%) | couverture des événements de gouvernance avec `decision_reason` + `signal_breakdown` complet |
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

