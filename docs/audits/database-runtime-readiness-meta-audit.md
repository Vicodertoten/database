---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-06
source_of_truth: docs/audits/database-runtime-readiness-meta-audit.md
scope: database_runtime_readiness_meta_audit
---

# Database Runtime Readiness Meta-Audit

## 1. Executive Verdict

- **Golden Pack 30/30 readiness now:** **NO**.
- **Current blocker nature:** predominantly **data/pipeline coherence gap**, not a pure materializer bug.
- **Dominant issue:** media eligibility gate (`basic_identification=eligible`) fails for many selected targets under current joined artifacts.
- **Recommended rerun strategy:** **`LOCAL_CANONICAL_RERUN_RECOMMENDED`** (orchestrated local canonical refresh of aligned artifacts), with targeted PMP and distractor refresh inside that coherent run.

Evidence-backed facts:
- `safe_ready_targets=32`, `selected_targets=7`, `rejected_targets=25` (`docs/audits/evidence/golden_pack_v1_blocker_diagnosis.json`).
- Fail buckets: `no_basic_identification_eligible_media=19`, `no_local_media_file=1`, `insufficient_label_safe_distractors=7`.
- Golden materializer/tests pass contract behavior and fail safely (partial pack is isolated as failed artifact).

## 2. Current Repo State

### Canonical docs
- `docs/architecture/MASTER_REFERENCE.md`
- `docs/architecture/GOLDEN_PACK_SPEC.md`

### Historical / governance docs
- `docs/audits/*` (inventory, sprint audits, decisions)
- `docs/foundation/*` (policy and model contracts)

### Evidence JSON
- `docs/audits/evidence/*` includes mixed sprint/run artifacts (`sprint12`, `sprint13`, `sprint14b/14b.3`, broader PMP snapshots).

### Runtime artifacts
- Canonical target path: `data/exports/golden_packs/belgian_birds_mvp_v1/`
- Failed builds now isolated via `failed_build/partial_pack.json`.

### Intermediate artifacts
- `data/normalized/*`, `data/qualified/*`, `data/enriched/*`, `data/raw/inaturalist/*`, `data/exports/palier1_*`.

### Active scripts for Golden path
- `scripts/materialize_golden_pack_belgian_birds_mvp_v1.py`
- `scripts/diagnose_golden_pack_belgian_birds_mvp_v1_blockers.py`
- `scripts/synthesize_sprint14b_final_runtime_handoff_readiness.py`

### Legacy / non-MVP runtime surfaces still present
- `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1/v2` ecosystem remains in repo and evidence.
- Explicitly documented as non-MVP for Golden runtime handoff.

### Active tests for Golden path
- `tests/test_golden_pack_v1_schemas.py`
- `tests/test_golden_pack_v1.py`
- `tests/test_sprint14c_runtime_handoff.py`

## 3. Active Contracts and Status

- `golden_pack.v1`: **active MVP runtime contract**.
- `golden_pack_manifest.v1`: **active**.
- `golden_pack_validation_report.v1`: **active**.
- Localized names source/display policy (`docs/foundation/localized-name-source-policy-v1.md`): **active**.
- PMP qualification policy (`docs/foundation/pmp-qualification-policy-v1.md`): **active policy layer**.
- Distractor projection (`docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json`): **active supporting artifact, older sprint**.
- Runtime handoff synthesis (`sprint14b_final_runtime_handoff_readiness.json`): **active decision artifact with warnings**.
- `pack.materialization.v2`: **legacy/historical/non-MVP** for runtime contract.

## 4. Actual Pipeline Map (Observed)

### A. Source/raw
- Inputs: iNaturalist snapshot folders under `data/raw/inaturalist/*`.
- Golden script currently pins PMP raw snapshot: `palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`.
- Risk: snapshot/version divergence from other upstream artifacts.

### B. Normalized
- Inputs: raw snapshot.
- Outputs: `data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json` (+ variants).
- Risk: multiple normalized variants coexist.

### C. Qualified
- Outputs include `data/qualified/palier1_be_birds_50taxa_run003_v11_baseline.qualified.json`.
- Golden script currently consumes `data/exports/palier1_be_birds_50taxa_run003_v11_baseline.export.json` for provenance joins.
- Risk: qualified/export and PMP snapshot may not be same run lineage.

### D. PMP profile + policy
- Golden gate is evaluated dynamically via `evaluate_pmp_profile_policy` over snapshot `ai_outputs.json`.
- Status in synthesis audit: readiness with warnings (not hard pass for all media).
- Risk: policy recalculation over one snapshot while target set derives from different artifacts.

### E. Localized names
- Input: `localized_name_apply_plan_v1.json` with `plan_hash=8adeed...`.
- Output: `safe_ready_targets_from_plan` (32).
- Reconciliation evidence indicates hash consistency inside localized-name pipeline.
- Risk: this consistency does not guarantee coherence with PMP and distractor datasets.

### F. Distractor projection
- Input artifact consumed by golden materializer: `distractor_relationships_v1_projected_sprint13.json`.
- This is sprint13 projection; names are refreshed sprint14b.3.
- Risk: cross-sprint drift for label-safe distractor availability.

### G. Readiness synthesis
- `sprint14b_final_runtime_handoff_readiness.json` confirms contract-level readiness with warnings.
- It does not assert Golden 30/30 media eligibility under current strict primary-media gate.

### H. Golden materialization
- Script produces passed pack only if all hard gates pass.
- On failure: writes `validation_report.json` + `manifest.json` + `failed_build/partial_pack.json`; does not publish canonical `pack.json`.

### I. Runtime handoff
- Runtime artifact-only consumption expected from `data/exports/golden_packs/.../pack.json`.
- Current state: failed build, no canonical `pack.json` published.

## 5. Artifact Inventory (Key)

| Path | Role | Class | Version/Run Signal | Drift Risk |
|---|---|---|---|---|
| `docs/audits/evidence/localized_name_apply_plan_v1.json` | name decisions + safe targets | evidence | `plan_hash=8adeed...` | medium |
| `docs/audits/evidence/localized_name_projection_vs_14b_audit_reconciliation.json` | localized-name reconciliation | evidence | same hash | low (names only) |
| `docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json` | distractor candidate projection | evidence/intermediate | sprint13 | high |
| `docs/audits/evidence/database_integrity_runtime_handoff_audit.json` | decision audit | evidence | sprint14b.3 | medium |
| `data/exports/palier1_be_birds_50taxa_run003_v11_baseline.export.json` | qualified export/provenance join | intermediate | run003 v11 baseline | high |
| `data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json` | PMP profile outcomes | intermediate | 2026-05-04 broader snapshot | high |
| `data/exports/golden_packs/belgian_birds_mvp_v1/validation_report.json` | golden validation state | runtime-support | golden_pack_validation_report.v1 | low |
| `data/exports/golden_packs/.../failed_build/partial_pack.json` | failed diagnostic payload | non-runtime | golden_pack.v1 shape partial | low |

## 6. Script Inventory

### `scripts/materialize_golden_pack_belgian_birds_mvp_v1.py`
- Role: build Golden pack + manifest + validation report.
- Inputs: localized apply plan, sprint13 distractor projection, pack_materialization_v2 baseline, qualified export, PMP snapshot manifest + ai outputs.
- Output: runtime artifacts under `data/exports/golden_packs/...`.
- Status: active.
- Risks: hard-coded mixed-era inputs (sprint13 + sprint14 + run003 baseline) create coherence risk.

### `scripts/diagnose_golden_pack_belgian_birds_mvp_v1_blockers.py`
- Role: classify per-target rejection reasons for golden selection.
- Status: active diagnostic.
- Risks: classification depends on same mixed-source joins.

### `scripts/synthesize_sprint14b_final_runtime_handoff_readiness.py`
- Role: high-level readiness synthesis.
- Status: active decision support.
- Limitation: does not guarantee media gate pass for 30/30 golden selection.

## 7. Test Inventory

### `tests/test_golden_pack_v1_schemas.py`
- Protects strict schema contracts (`golden_pack.v1`, manifest, validation report).
- Does not validate real-data coherence.

### `tests/test_golden_pack_v1.py`
- Protects success fixture and failed mode safety.
- Protects runtime safety (no canonical `pack.json` on failed build).
- Protects cross-file invariants.
- Does not prove current repo data can reach 30/30.

### `tests/test_sprint14c_runtime_handoff.py`
- Protects readiness synthesis invariants and materializer contract behavior under mocked inputs.
- Does not cover full raw->normalized->qualified->PMP->golden end-to-end coherence.

## 8. Golden Pack Blocker Analysis

Confirmed facts:
- 32 safe-ready targets from localized plan.
- 7 pass all golden gates.
- 25 rejected.
- 19 rejected by missing `basic_identification=eligible` primary media gate.
- 7 rejected by insufficient label-safe distractors.

Interpretation:
- **Not a materializer regression**: tests confirm deterministic selection and fail-safe behavior.
- **Likely coherence issue**: target set quality derives from localized-name readiness (sprint14b.3), while distractors come from sprint13 projection and media policy from 20260504 broader PMP snapshot.
- **Media failures likely include true data gaps + join lineage mismatch**:
  - some targets may have eligible media in other snapshots/exports not wired to current source_media_id path;
  - one explicit local-media missing case confirms at least one concrete asset mismatch.
- **Distractor failures likely include projection staleness** under updated label policy and target subset.

Hypotheses ranked:
1. **High**: mixed-run artifact drift is suppressing eligible media count.
2. **High**: distractor projection is stale relative to current name policy and target set.
3. **Medium**: some genuine corpus gaps remain even after coherent rerun.
4. **Low**: core materializer logic bug (not supported by tests/evidence).

## 9. Pipeline Coherence Risks

- Localized-name readiness is sprint14b.3; distractor projection is sprint13.
- PMP snapshot path (`...broader-400-20260504`) may not match qualified/export lineage used for playables.
- `pack_materialization_v2` baseline target media IDs may point to candidates that are no longer best/eligible under latest PMP policy.
- Runtime handoff audit says “with warnings”; Golden strict gate converts some warnings into hard blockers for primary media.

## 10. Rerun Recommendation

**Recommendation:** `LOCAL_CANONICAL_RERUN_RECOMMENDED`.

Rationale:
- Blocker pattern indicates multi-stage lineage incoherence, not one isolated file defect.
- Need a coherent rerun producing aligned artifacts for: localized-name plan, distractor projection, qualified export, PMP snapshot/policy, and golden selection from same run boundary.
- A purely targeted PMP rerun alone may reduce media failures but leave distractor drift unresolved.

## 11. Minimal Next Commits

1. Add a coherence orchestrator/report script that prints exact input lineage hashes and run IDs consumed by golden materializer.
2. Produce aligned local canonical rerun artifacts (single run boundary) for qualified export + PMP policy + distractor projection.
3. Re-run blocker diagnosis on aligned artifacts and compare delta vs current 7/32.
4. Regenerate golden pack; require 30/30 hard pass and `validation_report.status=passed`.
5. Runtime smoke test using canonical `pack.json` only after pass.

## 12. Non-Actions (Explicit)

- Do **not** relax `basic_identification=eligible`.
- Do **not** accept borderline primary quiz images.
- Do **not** ship 7/30 as MVP.
- Do **not** let runtime consume `failed_build/partial_pack.json`.
- Do **not** persist `DistractorRelationship`.
- Do **not** set `DATABASE_PHASE_CLOSED=true`.
- Do **not** set `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=true`.
- Do **not** perform aggressive cleanup or move historical evidence.
- Do **not** move business logic into runtime.

## Confidence and Limits

- Confidence: **medium-high** on diagnosis category (coherence/data gap, not materializer bug).
- Limits:
  - no full recomputation of upstream pipelines in this phase;
  - several artifacts carry different sprint/run timestamps by design;
  - exact proportion of "true media scarcity" vs "join drift" needs aligned rerun to disambiguate.
