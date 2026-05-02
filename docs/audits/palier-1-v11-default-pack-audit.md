---
owner: database
status: stable
last_reviewed: 2026-05-02
source_of_truth: docs/audits/palier-1-v11-default-pack-audit.md
scope: audit
---

# Palier 1 v1.1 Default Pack Audit

## Decision snapshot

- Decision: `GO_WITH_GUARDRAILS`
- Technical status: `pass`
- Pedagogical status: `pending manual review / quality-limited`
- Baseline reference: `docs/runbooks/palier-1-v11-baseline.md`

This audit documents an intermediate/default state. The active baseline contract and program framing are maintained in `docs/runbooks/palier-1-v11-baseline.md`.

## 1. Scope

Objectif: fermer le dernier blocage de couverture v1.1 sans changer la policy/thresholds.

Contraintes respectees:

- policy `v1.1` inchangée
- seuils inchangés
- strategie distracteurs inchangée
- runtime-app inchangé
- pipeline rerun en mode `cached` sur snapshot closure existant

Snapshot:

- `palier1-be-birds-50taxa-run002-closure`

## 2. Taxon replacement decision

Taxon retire du scope palier 1 run003 v1.1 default:

- `taxon:birds:000026` / `Larus michahellis`

Statut:

- `source_limited`
- `not_palier1_ready`

Justification:

- confirme en run001/run002 et en compare v1/v1.1 comme unique taxon bloquant residuel (`min_media_per_taxon`)
- dans les donnees locales closure actives, le taxon reste sous le minimum de medias exportables requis

Fixture selection run003:

- `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_selected.json`

Note operationnelle:

- la fixture garde 50 entrees, avec remplacement de la ligne `000026` par un taxon robuste (`taxon:birds:000001`, `Columba palumbus`)
- sur snapshot closure sans refetch, la selection operationnelle est dedupee a `49` taxons uniques

## 3. Pipeline and pack execution

Pipeline v1.1 cached rerun:

- run id: `run:20260502T150048Z:85c4371b`
- qualified: `1413`
- exportable: `1284`

Pack created:

- `pack:palier1:be:birds:run003-v11-default`
- revision: `1`
- canonical taxa (operational unique set): `49`

Diagnose default v1.1:

- compilable: `yes`
- reason_code: `compilable`
- blocking_taxa: `0`

Compile v2:

- build_id: `packbuild:pack:palier1:be:birds:run003-v11-default:1:3fe3a627`
- question_count_built: `20`

Materialize v2:

- artifact: `data/exports/palier1_be_birds_run003_v11_default_selected.materialize_v2.json`

Distractor audit:

- script: `python scripts/audit_phase3_distractors.py`
- input: `data/exports/palier1_be_birds_run003_v11_default_selected.compile_v2.json`
- output: `data/exports/palier1_be_birds_run003_v11_default_selected.distractors_audit.json`
- key outcome: invariants OK, reason_code mix dominated by `diversity_fallback`

## 4. Manual quality audit plan (60 items)

Sampling artifact:

- `data/exports/palier1_be_birds_run003_v11_default_manual_audit_sample.json`

Strata:

- `20` items: `core_id`
- `20` items: `advanced_id/context` accepted_with_flags
- `20` items: `insufficient_technical_quality`

Execution guidance:

- review visuelle manuelle et scoring qualitatif par item
- valider signal diagnostique, adequation pedagogique, risque confusion
- decider go/no-go pour adoption v1.1 par profil pack

## 5. Recommendation

- adopter `v1.1` pour run palier 1 en mode explicite (`--qualification-policy v1.1`)
- maintenir `v1` default global tant que l'audit manuel n'est pas cloture
- traiter `Larus michahellis` hors scope palier 1 courant (source-limited)
- ouvrir une remediation source dediee si ce taxon redevient prioritaire


## 6. Manual review sheet

- `docs/audits/palier-1-v11-manual-review-sheet.md`
