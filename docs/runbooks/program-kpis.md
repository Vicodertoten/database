---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/runbooks/program-kpis.md
scope: runbook
---

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

## Phase 1 instrumentation (additif, non-bloquant)

Regle de compatibilite `smoke.report.v1`:

1. aucun renommage des champs historiques
2. aucune suppression des champs historiques
3. aucune modification semantique des champs historiques
4. ajout uniquement en mode additif (`extended_kpis`, `compile_deficits_summary`)
5. `overall_pass` conserve sa definition historique (KPI verrouilles uniquement)

KPI etendus publies en Phase 1 (`extended_kpis`):

1. `taxon_playable_coverage_ratio`
   - formule: `playable_taxa / accepted_taxa_total`
   - stats: `playable_taxa`, `accepted_taxa_total`, `provisional_taxa_total`
2. `taxon_with_min2_media_ratio`
   - formule: `taxa_with_min2_media / accepted_taxa_total`
   - stats: `taxa_with_min2_media`, `accepted_taxa_total`
3. `country_code_completeness_ratio`
   - formule: `playable_items_with_country / playable_items_total`
   - stats: `playable_items_with_country`, `playable_items_total`
4. `distractor_diversity_index` (v1 simple)
   - formule: `unique_directed_pairs(target,distractor) / total_distractor_slots`
   - stats: `unique_directed_pairs`, `total_distractor_slots`, `latest_compiled_payloads`

Resume deficits compile (`compile_deficits_summary`):

- `attempts_total`
- `non_compilable_attempts`
- `reason_counts`
- `top_blocking_taxa`

Interpretation Phase 1:

- KPI etendus sont des signaux de pilotage baseline (non bloquants pour ce chantier)
- les decisions pass/fail operationnelles restent portees par les KPI verrouilles

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
