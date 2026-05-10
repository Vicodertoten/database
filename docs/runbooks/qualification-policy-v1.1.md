---
owner: database
status: in_progress
last_reviewed: 2026-05-02
source_of_truth: docs/runbooks/qualification-policy-v1.1.md
scope: runbook
---

# Qualification Policy v1.1

## 1. Doctrine

Objectif v1.1: separer l'acceptation data de la selection pedagogique.

- v1 gardait une logique binaire: de nombreux defauts pedagogiques/visuels passaient en rejet.
- v1.1 conserve plus d'observations en base (accepted + flags) et deplace la selectivite vers les profils de pack.
- Le runtime reste separe: il ne lit jamais `export.bundle.v4`. Le contrat
  runtime jouable actif est maintenant `session_snapshot.v2`, avec
  `golden_pack.v1` comme fallback. `playable_corpus.v1` et les packs
  compiles/materialises restent owner-side, historiques, ou strategic-later.

## 2. Activation

Le pipeline accepte maintenant un flag explicite:

```bash
python scripts/run_pipeline.py ... --qualification-policy v1
python scripts/run_pipeline.py ... --qualification-policy v1.1
```

Comportement par defaut:

- `v1` reste le defaut.
- `v1.1` est opt-in uniquement.

## 3. Politique v1.1

### 3.1 Hard rejects v1.1

Hard rejects limites en v1.1:

- `unsafe_license`
- `unsupported_media_type`
- `insufficient_resolution_pre_ai`
- `decode_error_pre_ai`
- `blur_pre_ai`
- `duplicate_pre_ai`
- `low_ai_confidence_below_floor`

Seuil ajoute:

- `AI_CONFIDENCE_REJECT_FLOOR = 0.35`

Regle:

- `ai_confidence < 0.35` -> `low_ai_confidence_below_floor` -> `rejected`
- `0.35 <= ai_confidence < 0.80` -> `low_ai_confidence` (flag), mais pas reject automatique

### 3.2 Technical failures (non relaches)

Ces flags ne deviennent pas accepted_with_flags:

- `missing_cached_ai_output`
- `cached_prompt_version_mismatch`
- `gemini_error`
- `invalid_gemini_json`
- `missing_fixture_ai_output`
- `missing_cached_image`

Ils restent `review`/`reject` selon `--uncertain-policy`.

### 3.3 Accepted with flags (sans nouveau statut)

v1.1 n'introduit pas de nouveau `QualificationStatus`.

Le mode accepted_with_flags est encode via:

- `qualification_status = accepted`
- `qualification_flags` non vide
- note trace `policy:v1.1:accepted_with_flags`

Flags relaches en v1.1:

- `missing_visible_parts`
- `missing_view_angle`
- `insufficient_technical_quality`
- `incomplete_required_tags`
- `low_ai_confidence` (si `>= 0.35`)

## 4. Invariant export

Invariant conserve:

- exportable seulement si `qualification_status=accepted` **et** license safe
- `unsafe_license` n'est jamais exportable

## 5. Classification derivee minimale

Nouveau module:

- `src/database_core/qualification/classification.py`

Fonctions exposees:

- `derive_observation_kind(...)`
- `derive_diagnostic_strength(...)`
- `derive_pedagogical_role(...)`
- `derive_difficulty_band(...)`
- `derive_minimal_classification(...)`

Valeurs:

- `observation_kind`: `full_bird`, `in_flight`, `partial`, `nest_or_eggs`, `trace_or_feather`, `carcass`, `habitat_context`, `unknown`
- `diagnostic_strength`: `high`, `medium`, `low`, `unknown`
- `pedagogical_role`: `core_id`, `advanced_id`, `context`, `forensics`, `excluded`
- `difficulty_band`: `starter`, `intermediate`, `expert`, `unknown`

Injection actuelle:

- la classification est ajoutee dans `QualifiedResource.derived_classification`
- visible dans les artefacts `qualified` JSON
- pas de migration SQL lourde introduite

## 6. Pack profiles minimal

Nouveau flag pack:

```bash
python scripts/manage_packs.py diagnose ... --pack-profile core
python scripts/manage_packs.py diagnose ... --pack-profile mixed
```

Par defaut (sans `--pack-profile`): comportement legacy inchangé.

### 6.1 Profile `core`

Filtrage strict:

- role derive `core_id` uniquement
- `diagnostic_strength` high/medium
- exclusion `trace_or_feather`, `carcass`, `habitat_context`
- exclusion des flags critiques:
  - `missing_visible_parts`
  - `missing_view_angle`
  - `insufficient_technical_quality`

### 6.2 Profile `mixed`

Filtrage modere:

- inclut `core_id` + `advanced_id`
- `context` autorise de facon limitee (si diagnostic high/medium)
- exclut `forensics`/`excluded`
- exclut `trace_or_feather` et `carcass`

## 7. Contrats et limites

- pas de changement runtime
- pas de changement strategie distracteurs
- pas de changement modele feedback
- pas de changement de schema runtime actif (`session_snapshot.v2`) dans cette iteration
- `pack.diagnostic.v1` reste le contrat de diagnose

## 8. Verification minimale

Commandes locales recommandees:

```bash
python scripts/check_docs_hygiene.py
python scripts/check_doc_code_coherence.py
python -m ruff check src tests scripts
python scripts/verify_repo.py
```
