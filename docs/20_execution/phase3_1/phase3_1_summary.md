# Phase 3.1 Summary

- created_at: `2026-04-22T18:36:22.976242+00:00`
- phase3 closure: `closed_go_with_gaps`
- scale decision: `STOP_RETARGET`

## Run-Level Table

| run | type | accepted_new | gemini | pre_ai_reject | est_cost_eur | exportable | delta_insufficient | delta_ratio | cost_per_exportable |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| scale_run1 | scale | 0 | 0 | 0 | 0.0 | 0 | 0 | 0.0 | None |
| scale_run2 | scale | 0 | 0 | 0 | 0.0 | 0 | 0 | 0.0 | None |
| scale_run3 | scale | 0 | 0 | 0 | 0.0 | 0 | 0 | 0.0 | None |
| extension_run1 | extension | 200 | 186 | 14 | 0.2232 | 129 | 0 | 4.0 | 0.00173 |

## Decision Narrative

- ce qui marche: Protocol and observability are stable and decision-ready.
- ce qui ne marche pas: Cost rises without meaningful compile-deficit improvement.
- hypothese causale: Current acquisition strategy maximizes volume novelty, not compile-relevant novelty.
- action suivante recommandee: Stop scale expansion and redesign targeting logic to maximize compile-impact per Gemini call.

## Analysis Questions

- Q1 novelty-seeking reduit le churn doublons: `False`
- Q2 nouveaute reduit deficits compile: `False`
- Q3 cout IA marginal acceptable pour gain compile: `False`
- Q4 extension taxons meilleure valeur marginale que scale: `False`
