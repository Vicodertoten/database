---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-broader-run-plan.md
scope: audit
---

# Sprint 8 P1 — Broader corpus run plan

## Purpose

Enable a real broader PMP policy audit by building a deterministic 300–500 image subset of an existing bird-only iNaturalist snapshot and then qualifying that subset with `pedagogical_media_profile_v1`.

This is the blocking P1 work before any threshold calibration, because only a broader run can validate the current `pmp_qualification_policy.v1` distributions outside the Sprint 6 controlled sample.

## Implementation status

- Tooling now exists to build the broader subset deterministically.
- A helper script is available to prepare the subset and print the exact live Gemini qualification command.
- A broader PMP `ai_outputs.json` snapshot has now been produced for
  `palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`.
- Broader PMP audit evidence, broader PMP policy audit evidence, and a 60-row
  human review sample now exist in the repo.

## Executed broader run

Executed subset:
- source snapshot: `palier1-be-birds-50taxa-run003-v11-baseline`
- output snapshot: `palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`
- selected media: `400`
- selected taxa: `48`
- max media per taxon: `10`

Executed outputs:
- `data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json`
- `docs/audits/evidence/pedagogical_media_profile_v1_broader_400_20260504_snapshot_audit.json`
- `docs/audits/evidence/pmp_policy_v1_broader_400_20260504_snapshot_audit.json`
- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sample.csv`
- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sample.jsonl`

## Recommended flow

1. Build the broader subset from the source snapshot:

```bash
./.venv/bin/python scripts/prepare_pmp_policy_broader_run.py \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \
  --output-snapshot-id palier1-be-birds-50taxa-run003-pmp-policy-broader-400 \
  --max-media-count 400 \
  --max-media-per-taxon 10
```

2. Run the printed Gemini qualification command.

3. Run the existing PMP audit tooling on the resulting snapshot.

## Command reference

Use the helper script to build the subset and print the exact follow-on command.

- subset builder: `scripts/build_controlled_inat_snapshot_subset.py`
- broader run helper: `scripts/prepare_pmp_policy_broader_run.py`
- PMP qualification CLI: `database-qualify-inat-snapshot`

## Success criteria

- a broader controlled subset snapshot exists with `300 <= selected_media_count <= 500`
- the generated broader snapshot contains a deterministic `subset_audit.json`
- `pedagogical_media_profile_v1` is executed live on the broader subset
- `profile_valid >= 85%` on the broader subset
- policy distributions can be compared against Sprint 6

## Deliverables

- broader subset snapshot directory under `data/raw/inaturalist`
- `ai_outputs.json` for the broader subset
- audit evidence from `scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py`
- audit evidence from `scripts/audit_pmp_policy_v1_snapshot.py`
- human review export sample for the broader run
- a short calibration note summarizing the new distribution results

## Notes

- The broader run is a validation audit, not a runtime rollout.
- The helper script uses the current Python interpreter to print the command, which ensures the correct environment path is visible when the script runs.

## Outcome

- Broader run execution succeeded.
- `profile_valid` success criterion is met with margin.
- The next step is calibration on the broader sample, not another tooling pass.

