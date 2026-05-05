---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/localized-name-projection-vs-14b-audit-reconciliation.md
scope: sprint14b_reconciliation
---

# Localized Name Projection vs 14B Audit Reconciliation

- plan_hash: 8adeed82edfd168cd560740820b45678cca1f362e1ef8d85502d33d98821fbe1
- dry_run_plan_hash: 8adeed82edfd168cd560740820b45678cca1f362e1ef8d85502d33d98821fbe1
- audit_plan_hash: 8adeed82edfd168cd560740820b45678cca1f362e1ef8d85502d33d98821fbe1
- hashes_match: true
- projected_safe_targets_dry_run_count: 32
- audited_safe_targets_after_apply_count: 32

## Outcome

- Dry-run, apply and audit are reconciled through `LocalizedNameApplyPlan`.
- No separate localized-name projection logic is used here.
