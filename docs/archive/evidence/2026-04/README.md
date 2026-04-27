# Phase 3.1 - Complete Measurement Protocol

## Goal

Produce an auditable synthesis across four axes per run:
- novelty
- compile impact
- AI cost
- quality/exportable

## Execution command

```bash
set -a; source .env; set +a; python scripts/phase3_1_complete_measurement.py
```

## Expected outputs

- `docs/20_execution/phase3_1/phase3_1_summary.v1.json`
- `docs/20_execution/phase3_1/phase3_1_summary.md`
- run artifacts `*.phase3_remediation.v1.json` for:
  - `scale_run1`
  - `scale_run2`
  - `scale_run3`
  - `extension_run1`

## Locked protocol defaults

- base pack: `pack:pilot:birds-v2-nogeo:20260421T215543Z`
- scale: 3 runs, same segment (80 taxa)
- extension: +20 taxa in dedicated pack
- novelty query: `observed_on asc`, `2010-01-01` -> `2022-12-31`
- run limits: `max_passes=3`, `max_observations_per_taxon=10`

## Notes

- This is owner-only measurement work (no runtime contract change).
- If interrupted before completion, no decision should be published without `phase3_1_summary.v1.json`.
