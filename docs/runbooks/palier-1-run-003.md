---
owner: database
status: stable
last_reviewed: 2026-05-02
source_of_truth: docs/runbooks/palier-1-run-003.md
scope: runbook
---

# Palier 1 Run 003 (Policy Compare + v1.1 Default Closure)

Superseded baseline note:

- this document records the intermediate run003 default closure (`49` unique taxa)
- the frozen Palier 1 v1.1 baseline contract is now tracked in
  `docs/runbooks/palier-1-v11-baseline.md`

## 1. Purpose

Run003 couvre:

- comparaison doctrine qualification `v1` vs `v1.1` sur snapshot closure run002
- fermeture du dernier blocage de couverture en mode `v1.1 default` sans refetch
- preparation d'un audit qualite manuel cible

Snapshot source:

- `palier1-be-birds-50taxa-run002-closure`

## 2. Taxon scope decision

Taxon retire du scope run003 default:

- `taxon:birds:000026` / `Larus michahellis`

Statut run003:

- `source_limited`
- `not_palier1_ready`

Fixture selection:

- `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_selected.json`

Note:

- remplacement explicite de `000026` par un taxon robuste deja couvert
- selection operationnelle dedupee a `49` taxons uniques sur closure

## 3. Execution commands

Pipeline v1/v1.1 compare:

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

Pipeline v1.1 default selected rerun:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-50taxa-run002-closure \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --qualification-policy v1.1 \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_run003_v11_selected.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_run003_v11_selected.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_run003_v11_selected.export.json
```

Pack default v1.1:

```bash
python scripts/manage_packs.py create \
  --database-url "$DATABASE_URL" \
  --pack-id pack:palier1:be:birds:run003-v11-default \
  --difficulty-policy mixed \
  --canonical-taxon-id <...deduped from run003_v11_selected fixture...>

python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id pack:palier1:be:birds:run003-v11-default

python scripts/manage_packs.py compile \
  --database-url "$DATABASE_URL" \
  --pack-id pack:palier1:be:birds:run003-v11-default \
  --revision 1 \
  --contract-version v2

python scripts/manage_packs.py materialize \
  --database-url "$DATABASE_URL" \
  --pack-id pack:palier1:be:birds:run003-v11-default \
  --revision 1 \
  --contract-version v2 \
  --purpose assignment
```

Distractor audit:

```bash
python scripts/audit_phase3_distractors.py \
  data/exports/palier1_be_birds_run003_v11_default_selected.compile_v2.json \
  --output-json data/exports/palier1_be_birds_run003_v11_default_selected.distractors_audit.json
```

## 4. Outcomes

- v1.1 compare outcome: see `docs/audits/qualification-policy-v1-v11-comparison.md`
- run003 v1.1 default selected:
  - diagnose: `compilable=yes`
  - blocking taxa: `0`
  - compile v2: success
  - materialize v2: success

## 5. Quality audit prep

Manual audit sample prepared:

- `data/exports/palier1_be_birds_run003_v11_default_manual_audit_sample.json`

Strata:

- 20 `core_id`
- 20 `advanced_id/context accepted_with_flags`
- 20 `insufficient_technical_quality`

## 6. References

- manual review sheet: `docs/audits/palier-1-v11-manual-review-sheet.md`


- comparison audit: `docs/audits/qualification-policy-v1-v11-comparison.md`
- default pack audit: `docs/audits/palier-1-v11-default-pack-audit.md`
- comparison metrics json: `data/exports/qualification_policy_v1_v11_comparison.json`
