---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/runbooks/golden-pack-v1-runtime-handoff.md
scope: golden_pack_runtime_handoff
---

# Golden Pack v1 Runtime Handoff

This runbook defines the database-owned Golden Pack handoff. `golden_pack.v1` is
now the runtime fallback; the active runtime contract stack is defined in
`docs/foundation/runtime-contract-stack-v1.md`.

## Current Promoted Artifact

Canonical local export:

```text
data/exports/golden_packs/belgian_birds_mvp_v1/
  pack.json
  media/
  manifest.json
  validation_report.json
```

The promoted clean-room run is:

```text
golden_pack_v1_clean_room_20260507_195209_256856
```

The export is runtime-consumable only when:

```text
validation_report.status = passed
```

## Runtime Contract

`runtime-app` consumes only:

```text
pack.json
media/
```

`runtime-app` must not read or depend on:

```text
manifest.json
validation_report.json
data/runs/
data/raw/
export_bundle.json
Postgres
iNaturalist
Gemini
```

The runtime may shuffle provided options and manage sessions, answers, scoring,
and progression. It must not invent labels, replace distractors, fetch missing
data, repair taxonomy, or map taxa.

## Verify Before Handoff

Run:

```bash
python scripts/verify_golden_pack_runtime_handoff.py \
  --pack-dir data/exports/golden_packs/belgian_birds_mvp_v1
```

This verifies the strict runtime boundary: passed validation, 30 questions,
30 copied media files, local `media/` URIs, option counts, checksums, and no
partial build.

## Export To Runtime-App

For the first MVP smoke, use a controlled copy instead of a release artifact:

```bash
python scripts/export_golden_pack_runtime_handoff.py \
  --pack-dir data/exports/golden_packs/belgian_birds_mvp_v1 \
  --output-dir ../runtime-app/data/golden-packs/belgian_birds_mvp_v1
```

By default this copies only `pack.json + media/`. To include operator evidence
for humans, add:

```bash
--include-audit
```

Audit files are copied under `audit/` and remain non-runtime inputs.
