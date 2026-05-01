---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/audits/phase3-distractor-audit.md
scope: phase3_distractor_validation
---

# Phase 3 Distractor Audit

Date: 2026-05-01

## Scope

Validation technique et pedagogique ciblee de la phase 3 sur artefacts `pack.compiled.v2` et `pack.materialization.v2` avec un echantillon de 50 questions.

## Executions reelles

1. Verification repo database

```bash
./.venv/bin/python scripts/verify_repo.py
```

Resultat: PASS (`177 passed`, coherence docs/code, hygiene docs, ruff).

2. Generation d'artefacts v2 calibres (50 questions)

```bash
set -a; source .env; set +a
./.venv/bin/python scripts/prepare_phase3_pedagogical_run.py --question-count 50
```

Sorties:

- `data/exports/phase3_pedagogical/pack_compiled_v2_pedagogical_calibrated.json`
- `data/exports/phase3_pedagogical/pack_materialization_v2_pedagogical_calibrated.json`
- `data/exports/phase3_pedagogical/phase3_pedagogical_audit_report.json`

## Resultats invariants contrat v2

Source: `phase3_pedagogical_audit_report.json` (compiled + materialization).

- Questions avec 4 options: 50/50 (100%)
- Questions avec 1 seule bonne reponse: 50/50 (100%)
- Distracteurs avec `reason_codes`: 150/150 (100%)
- Labels non vides: 200/200 (100%)
- Distracteurs != cible: 150/150 (100%)
- IDs taxons uniques dans chaque question: 50/50 (100%)

Conclusion contrat: PASS.

## Couverture et qualite distracteurs

- Distracteurs `inat_similar_species`: 100/150 (66.67%)
- Distracteurs out-of-pack: 100/150 (66.67%)
- Distracteurs `referenced_only`: 50/150 (33.33%)
- `diversity_fallback` seul: 50/150 (33.33%)

Repetition:

- taxon distracteur le plus repete: 50 occurrences
- reutilisation de paires cible/distracteur: 37.5%
- cardinalite paire intra-question: toujours 3 (pas de duplication interne)

## Evaluation pedagogique (proxy data-driven)

Signal positif:

- la branche iNaturalist est effectivement active dans l'artefact calibre
- les distracteurs sont traçables (source + score + reason codes)

Signal de vigilance:

- 33.33% des distracteurs reposent sur `diversity_fallback` seul
- repetition marquee de certains distracteurs sur l'echantillon

Interpretation:

- techniquement, la phase 3 est valide
- pedagogiquement, la qualite est heterogene et necessite calibration supplementaire avant extension feedback phase 4

## Decision phase 3 (distracteurs)

Decision: GO technique, GO pedagogique conditionnel.

Conditions avant phase 4:

1. reduire `diversity_fallback` seul sous 20% sur un echantillon reel non calibre
2. limiter la repetition des top distracteurs sur 50 questions
3. produire une notation manuelle 0-3 sur 50 questions reelles (hors calibration injectee)
