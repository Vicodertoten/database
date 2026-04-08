# Directive De Remédiation En Exécution

Document de pilotage opérationnel lié à l’audit (`docs/05_audit_reference.md`) et aux ADRs (`docs/adr/0001-...`, `docs/adr/0002-...`).

## Directive active

Passer de "core gouverné et traçable" à "core gouverné, pédagogiquement expressif, contractuellement robuste", en exécution strictement séquentielle.

## Cadre verrouillé

1. Cadence: `gates séquentiels` sans chevauchement.
2. Politique canonique: `auto_clear équilibrée` (hard blockers + score `>= 3`).
3. Export: `v4` principal breaking + sidecar `v3` sur 2 cycles.

Référence de verrouillage: `docs/adr/0002-noyau-canonique-fort-execution-sequentielle.md`.

## Statut des gates (cycle actuel)

| Gate | Statut | Résultat |
|---|---|---|
| Gate 0 | DONE | ADR de cadrage publié + checklist KPI publiée |
| Gate 1 | DONE | signaux canoniques explicites + `reason_code` + `signal_breakdown` persistés |
| Gate 2 | DONE | séparation des logs `state` / `canonical_change` / `governance_decision` |
| Gate 3 | DONE | ontologie pédagogique V1 intégrée (`difficulty_level`, `media_role`, `confusion_relevance`, `uncertainty_reason`) |
| Gate 4 | DONE | `export.bundle.v4` principal stable + sidecar `v3` opt-in, validation schéma/tests |
| Gate 5 | DONE | métriques run-level + rapport smoke standardisé (`smoke.report.v1`) |

## Discipline d'exécution maintenue

1. Toute évolution doit être reliée à un risque explicite de `docs/05_audit_reference.md`.
2. Toute règle automatique doit avoir un test de non-régression.
3. Toute décision canonique doit être persistée avec `decision_reason` + `signal_breakdown`.
4. Toute évolution de contrat export doit être versionnée et validée par schéma.
