---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-sprint8-plan.md
scope: audit
---

# Sprint 8 plan - broader profiled corpus audit with PMP policy

## Purpose

Prepare and, if safely feasible, execute the next broader profiled corpus audit
for `pedagogical_media_profile_v1` plus `pmp_qualification_policy.v1`.

## Explicit scope boundaries

- no runtime changes,
- no materialization,
- no Supabase/Postgres writes,
- no default behavior change,
- no pack generation,
- no production rollout.

## Current workspace status

Observed in workspace:
- Sprint 6 controlled PMP snapshot exists:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`
- No broader PMP `ai_outputs.json` snapshot was identified in current workspace.

## Sprint 8 execution mode

Chosen mode:
- **C. prepare run scripts but defer live broader PMP run**

Reason:
- broader live Gemini execution was not explicitly approved in this step,
- no broader PMP snapshot already exists locally,
- Sprint 8 can still deliver higher-quality audit and human review preparation on
  the real Sprint 6 outputs.

## Broader corpus target (prepared)

Recommended broader controlled target:
- source snapshot: `palier1-be-birds-50taxa-run003-v11-baseline`
- output snapshot id example:
  `palier1-be-birds-50taxa-run003-pmp-policy-broader-400`
- target media count: 300 to 500
- optional max media per taxon: 8 to 12
- deterministic subset selection only

## Deterministic subset builder

Use:
- `scripts/build_controlled_inat_snapshot_subset.py`

Suggested command:

```bash
./.venv/bin/python scripts/build_controlled_inat_snapshot_subset.py \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \
  --output-snapshot-id palier1-be-birds-50taxa-run003-pmp-policy-broader-400 \
  --max-media-count 400 \
  --max-media-per-taxon 10
```

This builder:
- performs no Gemini calls,
- performs no database writes,
- produces a deterministic subset snapshot,
- preserves source snapshot unchanged.

## Broader run command (prepared, not executed here)

```bash
./.venv/bin/python -m database_core.cli qualify-inat-snapshot \
  --snapshot-id palier1-be-birds-50taxa-run003-pmp-policy-broader-400 \
  --ai-review-contract-version pedagogical_media_profile_v1 \
  --gemini-model gemini-3.1-flash-lite-preview \
  --gemini-concurrency 4 \
  --gemini-api-key-env GEMINI_API_KEY
```

Expected outputs:
- snapshot `ai_outputs.json`,
- PMP snapshot audit evidence,
- PMP policy audit evidence,
- human review export sample.

## Sprint 8 concrete deliverables from current run

Using existing Sprint 6 real outputs:
- improved policy audit with metadata/taxon join,
- Sprint 8 policy evidence JSON,
- human review CSV/JSONL sample,
- human review README,
- open questions and calibration warnings,
- closure audit document.
