---
owner: database
status: in_progress
last_reviewed: 2026-05-02
source_of_truth: docs/runbooks/palier-1-run-003.md
scope: runbook
---

# Palier 1 Run 003 (Policy Compare)

## 1. Purpose

Run003 couvre la comparaison de doctrine qualification `v1` vs `v1.1` sur le snapshot closure run002, avec profils pack `core`/`mixed`.

Snapshot source:

- `palier1-be-birds-50taxa-run002-closure`

## 2. Execution commands

Pipeline compare:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-50taxa-run002-closure \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --qualification-policy v1 \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_v1_compare.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_v1_compare.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_v1_compare.export.json

python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-50taxa-run002-closure \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --qualification-policy v1.1 \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_v11_compare.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_v11_compare.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_v11_compare.export.json
```

Pack diagnose profiles:

```bash
python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run003-core" \
  --pack-profile core

python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run003-mixed" \
  --pack-profile mixed
```

## 3. Results reference

Resultats chiffres et decision:

- `docs/audits/qualification-policy-v1-v11-comparison.md`

Artifacts techniques:

- `data/exports/qualification_policy_v1_v11_comparison.json`
