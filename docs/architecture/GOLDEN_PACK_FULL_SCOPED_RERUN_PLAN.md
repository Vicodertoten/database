---
owner: database
status: draft_for_implementation
last_reviewed: 2026-05-06
source_of_truth: docs/architecture/GOLDEN_PACK_FULL_SCOPED_RERUN_PLAN.md
scope: golden_pack_v1_full_scoped_rerun
---

# Golden Pack V1 Full Scoped Rerun Plan

## Contexte et garde-fous

Ce document définit un plan d'exécution complet pour rendre le full scoped rerun de la pipeline `golden_pack.v1` réellement exécutable, sans coder l'implémentation finale dans cette étape.

Contraintes non négociables:

- runtime consomme uniquement `pack.json` + `media/`;
- logique métier reste côté database;
- `basic_identification=eligible` obligatoire pour image principale;
- pas de pack partiel runtime-consumable;
- pas de persistence canonique `DistractorRelationship`;
- `DATABASE_PHASE_CLOSED=false`;
- `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=false`.

---

## 1) Inventory des capacités existantes

### 1.1 Orchestration Golden

- `scripts/run_golden_pack_v1_full_scoped_pipeline.py`
  - Rôle: orchestrateur dry-run/apply "scoped" (actuel: mostly diagnostic/local snapshots).
  - Inputs: constantes de `materialize_golden_pack_belgian_birds_mvp_v1.py` (`PLAN_PATH`, `DISTRACTOR_PATH`, `QUALIFIED_EXPORT_PATH`, snapshot iNat/PMP, schemas).
  - Outputs: `data/runs/golden_pack_belgian_birds_mvp_v1_full_scoped_*/` avec `run_manifest.json`, `pipeline_plan.json`, `input_inventory.json`, `policy/`, `localized_names/`, `distractors/`, `readiness/`, `reports/`.
  - Run isolé: partiel uniquement (pas de vrai refresh source/normalization/qualification/PMP generation/materialization scoped).
  - Hardcodé legacy paths: oui (via constantes du materializer).
  - Réseau/API/Gemini: non directement.
  - Statut: `needs refactor`.

- `scripts/run_golden_pack_v1_local_canonical_pipeline.py`
  - Rôle: diagnostic de cohérence locale (`candidate_readiness`, `lineage_checks`) sur artefacts existants.
  - Inputs: mêmes artefacts hardcodés que materializer.
  - Outputs: `data/intermediate/golden_pack/.../local_*`.
  - Run isolé: oui pour audit local seulement.
  - Hardcodé: oui.
  - Réseau/API/Gemini: non.
  - Statut: `reusable` (diagnostic), `needs wrapper` (full rerun).

### 1.2 Materialization Golden

- `scripts/materialize_golden_pack_belgian_birds_mvp_v1.py`
  - Rôle: construit `pack.json`, `manifest.json`, `validation_report.json`, copie `media/`, applique gates strictes.
  - Inputs: `localized_name_apply_plan_v1.json`, projection distractors sprint13, `pack_materialization_v2.json`, `qualified export`, snapshot iNat manifest + `ai_outputs`.
  - Outputs: `data/exports/golden_packs/belgian_birds_mvp_v1/` (+ `failed_build/partial_pack.json` en échec).
  - Run isolé: non (output et inputs hardcodés).
  - Hardcodé: oui (paths + pack id + scope label).
  - Réseau/API/Gemini: non (lit `ai_outputs` existant).
  - Statut: `needs refactor`.

### 1.3 iNaturalist fetch / media materialization

- `scripts/fetch_inat_snapshot.py` (wrapper CLI `database_core fetch-inat-snapshot`)
  - Rôle: harvest observations iNat + download images + manifest snapshot.
  - Inputs: `snapshot_id`, `pilot_taxa`, `max_observations_per_taxon`, géofiltres (`place_id`/`country_code`/`bbox`), fenêtre dates.
  - Outputs: `data/raw/inaturalist/<snapshot_id>/{responses,taxa,images,manifest.json}`.
  - Run isolé: oui (snapshot-id dédié).
  - Hardcodé: non critique (defaults paramétrables).
  - Réseau/API/Gemini: iNaturalist API + downloads image.
  - Statut: `reusable`.

- `src/database_core/adapters/inaturalist_harvest.py`
  - Rôle: implémentation fetch/download.
  - Contrats utiles: applique `quality_grade=research`, `photos=true`, `license/photo_license=cc0,cc-by,cc-by-sa`, `captive=false`, place/country resolution.
  - Attribution/license/source: `source_url`, `source_media_id`, `download_status`, checksum, dimensions, blur.
  - Statut: `reusable`.

- `scripts/build_controlled_inat_snapshot_subset.py`
  - Rôle: sous-échantillon déterministe d'un snapshot existant.
  - Usage: smoke/scoped test sans nouveau fetch réel.
  - Statut: `reusable`.

### 1.4 Qualification / normalization pipeline

- `scripts/run_pipeline.py` (wrapper CLI `database_core run-pipeline`)
  - Rôle: normalisation + qualification + export bundle (fixture ou inat snapshot).
  - Inputs: `--source-mode inat_snapshot`, `--snapshot-id`, DB URL, modes qualifier (`fixture|rules|cached|gemini`), policy `v1|v1.1`.
  - Outputs: `data/normalized/*`, `data/qualified/*`, `data/exports/*` (paths paramétrables), + état DB pipeline.
  - Run isolé: oui si `run_id/snapshot_id` dédiés + output paths run-scoped.
  - Hardcodé: defaults seulement.
  - Réseau/API/Gemini: optionnel (si `qualifier-mode gemini`).
  - Statut: `reusable`.

- `scripts/qualify_inat_snapshot.py` (wrapper CLI `database_core qualify-inat-snapshot`)
  - Rôle: produit/refresh `ai_outputs.json` pour un snapshot iNat via Gemini.
  - Inputs: snapshot + Gemini config (model, retries, concurrency).
  - Outputs: `ai_outputs.json` + update `manifest.ai_outputs_path` + `pre_ai_rejection_reason`.
  - Run isolé: oui.
  - Réseau/API/Gemini: oui.
  - Statut: `reusable`.

### 1.5 PMP policy / uplift ciblé

- `scripts/refresh_golden_pack_v1_targeted_pmp_policy.py`
  - Rôle: recalcule policy sur batch ciblé, génère queue pour médias sans PMP.
  - Inputs: plan d'uplift + ai_outputs existants + manifest.
  - Outputs: run dir `targeted_pmp_policy_refresh_*`, `refresh_results.json`, `updated_ai_outputs.json`, `pmp_evaluation_queue.json`.
  - Run isolé: oui.
  - Réseau/API/Gemini: non (policy locale), mais peut signaler besoin externe.
  - Statut: `reusable` (bridge opérationnel).

- `scripts/plan_golden_pack_v1_targeted_media_uplift.py`
  - Rôle: plan médias/PMP pour targets bloquées.
  - Inputs: coverage plan + qualified + snapshot manifest + ai outputs.
  - Outputs: `docs/audits/evidence/golden_pack_v1_targeted_media_uplift_plan.json`.
  - Statut: `reusable`.

- `scripts/plan_golden_pack_v1_coverage_uplift.py`
  - Rôle: priorisation blockers readiness.
  - Statut: `reusable`.

- `scripts/audit_pedagogical_media_profile_v1_live_mini_run.py`
  - Rôle: audit/sonde live Gemini (mini-run), pas pipeline batch de prod.
  - Statut: `legacy` pour full rerun productif.

### 1.6 Localized names

- `scripts/enrich_taxon_localized_names_multisource_v1.py`
  - Rôle: enrichissement evidence multisource.
  - Statut: `reusable`.

- `scripts/apply_taxon_localized_name_patches_v1.py`
  - Rôle: appliquer patches noms localisés + sorties audit.
  - Statut: `reusable`.

- `scripts/convert_source_attested_names_to_localized_name_patches_sprint14.py`
  - Rôle: convertit CSV source-attested vers patches.
  - Statut: `reusable`.

### 1.7 Distractors

- `scripts/run_inat_taxon_similarity_enrichment.py`
  - Rôle: enrichissement iNat similar species (place-scoped).
  - Statut: `reusable` (réseau iNat).

- `scripts/generate_distractor_relationship_candidates_v1.py`
  - Rôle: génère candidats distractors (iNat similar + taxonomy neighbors).
  - Statut: `reusable`.

- `scripts/project_distractor_candidates_to_relationships_v1.py`
  - Rôle: projection valide schema des relations candidates (non persistence canonique).
  - Statut: `reusable`.

- `scripts/build_distractor_readiness_v1.py`
  - Rôle: audit readiness distractors.
  - Statut: `reusable`.

### 1.8 Candidate readiness / diagnostics

- `scripts/diagnose_golden_pack_belgian_birds_mvp_v1_blockers.py`
  - Rôle: buckets de rejet (media/pmp/distractors/names).
  - Statut: `reusable`.

- `tests/test_golden_pack_full_scoped_pipeline.py`
  - Rôle: garantit sécurité dry-run/apply actuel et non-modification evidence historique.
  - Statut: `reusable` (base de test orchestrateur).

---

## 2) Analyse des blockers actuels

### 2.1 `source_inat_refresh`

Manque actuel:

- l'orchestrateur full scoped ne déclenche pas `fetch_inat_snapshot` avec scope run-idé;
- pas de gestion explicite pagination/rate limit/retry/report iNat au niveau orchestration;
- pas de wiring vers run-dir de sortie.

Capacité existante:

- oui, `database_core fetch-inat-snapshot` + adapter harvest gèrent déjà filtres principaux et téléchargement local.

Action requise:

- ajouter un wrapper stage `source_inat_refresh` dans l'orchestrateur avec paramètres scope.

Paramètres requis:

- `snapshot_id` run-scoped;
- `pilot_taxa_path` (50 baseline ou 32 subset);
- `max_observations_per_taxon`;
- `country_code=BE` ou `place_id=7083`;
- période (`observed_from`, `observed_to`) si décidée;
- `timeout_seconds`.

Credentials/API/rate limits:

- iNaturalist public API (pas de clé), mais throttling 429 possible;
- intégrer pacing/retry/backoff côté orchestration (ou enrichir adapter).

Garantie attribution/license/source_url:

- déjà présent dans manifest snapshot + `qualified export` provenance;
- à compléter par validation gate `all_primary_media_have_attribution_fields` avant materialization.

### 2.2 `normalization`

Manque actuel:

- non rejouée dans run isolé par `run_golden_pack_v1_full_scoped_pipeline.py`.

Capacité existante:

- `database_core run-pipeline --source-mode inat_snapshot` produit normalized/qualified/export.

Outputs attendus:

- `normalized_snapshot.json` scoped run;
- persistance run metadata (`run_id`, `snapshot_id`) et evidence de lineage.

Contrats/schemas:

- schema snapshot manifest v1;
- invariants canonical IDs stables;
- qualité licence safe via policy.

### 2.3 `qualification`

Manque actuel:

- étape non orchestrée dans full scoped run.

Capacité existante:

- `run-pipeline` (rules/cached/gemini) et `qualify-inat-snapshot` pour `ai_outputs` snapshot.

Export qualifié scoped:

- écrire `qualified`/`export` dans dossier run (`data/runs/.../qualified/` + copie source-of-truth dans `data/qualified/` si décidé);
- stocker `lineage.json` liant snapshot_id -> normalized -> qualified -> export.

Alignement taxon/media IDs:

- verrouiller clé `source_media_id`/`canonical_taxon_id` à chaque stage;
- checks d'intersection obligatoires (targets, media ids, counts).

### 2.4 `pmp_profile_generation`

Manque actuel:

- génération nouveaux profiles non pilotée par orchestrateur full scoped;
- dépendance externe Gemini non encapsulée en mode resume.

Capacité existante:

- `database_core qualify-inat-snapshot` génère `ai_outputs.json` avec retries/concurrency/pacing.

Besoins:

- mode `--skip-external` et `--resume` pour exécuter pipeline sans bloquer;
- cache par `source_media_id + image_sha256 + prompt_version + model + contract_version`;
- batch control (`max-media-per-taxon`, `max-total`), retry, budget report.

Anti-source-of-truth AI:

- output AI limité à profil média + signaux policy;
- taxonomie/noms/distractors restent déterminés par pipeline DB;
- tracer explicitement `ai_role = signal_only` dans manifest run.

Output attendu:

- `pmp/ai_outputs.json` run-scoped;
- `pmp/pmp_profile_generation_report.json` (success/fail/retries/cost est.).

### 2.5 `golden_pack_materialization`

Cause blocage:

- `materialize_golden_pack_belgian_birds_mvp_v1.py` lit/écrit des chemins constants globaux et écrit directement export canonique.

Refactor nécessaire:

- paramétrer tous les inputs (plan, distractors, qualified export, snapshot manifest, ai outputs, materialization source) et outputs (`output_dir`).
- supporter write run-scoped, puis promotion explicite séparée.

Promotion:

- écrire d'abord dans `data/runs/.../golden_pack/`.
- promotion vers `data/exports/golden_packs/belgian_birds_mvp_v1/` seulement si `validation_report.status=passed`.

---

## 3) Architecture cible du full scoped run

Base:

`data/runs/golden_pack_belgian_birds_mvp_v1_full_scoped_<timestamp>/`

Contenu cible:

- `run_manifest.json`
  - run_id, mode, flags, versions scripts, timestamps, scope.
- `pipeline_plan.json`
  - stages, statuts, dépendances, commandes exécutées/skipped.
- `input_inventory.json`
  - hashes + lineage des inputs.
- `source_fetch/`
  - journal fetch iNat, paramètres API, stats, raw request metadata.
- `raw/`
  - snapshot iNat (`manifest.json`, `responses/`, `taxa/`, `images/`).
- `normalized/`
  - normalized snapshot run-scoped.
- `qualified/`
  - qualification snapshot + export bundle run-scoped.
- `media/`
  - inventaire media runtime-candidate et checksums intermédiaires.
- `pmp/`
  - `ai_outputs.json`, cache metadata, queue/retry reports.
- `policy/`
  - projection PMP policy, stats eligible/borderline/rejected.
- `localized_names/`
  - plan utilisé/généré, coverage report FR runtime-safe.
- `distractors/`
  - candidates + projection + readiness scoped.
- `readiness/`
  - candidate readiness consolidé (per-target).
- `golden_pack/`
  - `pack.json` (seulement si pass), `manifest.json`, `validation_report.json`, `media/`, `failed_build/partial_pack.json`.
- `reports/`
  - rapport final, blockers, coûts, décisions.

Classification:

- Runtime-facing: uniquement `golden_pack/pack.json` + `golden_pack/media/`.
- Intermediate: `raw/`, `normalized/`, `qualified/`, `pmp/`, `policy/`, `localized_names/`, `distractors/`, `readiness/`.
- Evidence: `run_manifest.json`, `pipeline_plan.json`, `input_inventory.json`, `reports/*`, `golden_pack/manifest.json`, `golden_pack/validation_report.json`.
- Jamais runtime-consumé: tout sauf `pack.json` + `media/`.

---

## 4) Contrat d’orchestration (`run_golden_pack_v1_full_scoped_pipeline.py`)

### CLI cible

- `--dry-run`
- `--apply`
- `--resume <run_id>`
- `--stop-after <stage>`
- `--skip-external`
- `--max-media-per-taxon <int>`
- `--target-scope 32-safe-ready|50-baseline`

### Stages cibles

1. `scope_resolution`
2. `source_inat_refresh`
3. `normalization`
4. `qualification`
5. `pmp_profile_generation`
6. `pmp_policy_projection`
7. `localized_names`
8. `distractors_projection`
9. `candidate_readiness`
10. `golden_pack_materialization_run_scoped`
11. `promotion_check`
12. `promotion_apply` (option séparée explicite)

### Comportement dry-run

- crée run dir + manifest/plan/inventory;
- valide présence scripts/inputs/credentials attendues;
- ne fait aucun fetch/API call/Gemini;
- ne copie pas media runtime finals;
- produit plan exécutable + blockers + commandes exactes.

### Comportement apply

- exécute stages locaux et externes autorisés;
- si `--skip-external`: stop propre avant `source_inat_refresh` ou `pmp_profile_generation` selon état;
- si external indisponible: marque stage `blocked_external`, écrit queue et instructions `resume`.

### Resume

- `--resume <run_id>` recharge état stage et reprend à partir du prochain stage non `completed`;
- support clé pour reprise après génération PMP externe.

### Protection artefacts historiques

- aucune écriture dans anciens runs;
- aucun overwrite de `docs/audits/evidence/*` historiques;
- promotion canonique uniquement commande dédiée et conditionnée au `passed`.

---

## 5) Strategy iNaturalist

Source:

- API officielle iNaturalist `v1/observations` + `v1/taxa` via adapter existant.

Détermination observations:

- scope taxons depuis `pilot_taxa` (50 baseline ou subset 32);
- BE via `country_code=BE` (résolu `place_id=7083`) ;
- photos only ;
- quality grade `research` ;
- `captive=false`.

Médias par taxon:

- recommandation défaut: `max_observations_per_taxon=8` pour absorber rejets PMP/policy puis downselect à 1 primary.

Licences:

- défaut conservateur existant: `cc0,cc-by,cc-by-sa`.
- stocker license observation + license media.

Pagination/rate limits:

- état actuel: `per_page=max_observations_per_taxon`, pas boucle multi-pages;
- plan: garder ce mode MVP (N borné) + retry/backoff sur 429/5xx;
- si besoin > per_page, implémenter pagination explicite commit dédié.

Stockage raw:

- conserver `responses/*.json` et `taxa/*.json` run-scoped;
- stocker `query_params` effectifs dans manifest.

Stockage images:

- `raw/images/<media_id>.<ext>` + sha256 + dimensions + blur score + download_status.

Attribution:

- conserver `source_url`, `source_media_id`, `source_observation_id` dans manifest;
- enrichir via qualified provenance pour `creator/license/license_url/attribution_text` au materializer.

---

## 6) Strategy Gemini/PMP

Périmètre envoi:

- médias du run scoped éligibles pré-AI (résolution, blur, non-duplicates), priorisés sur targets bloquées readiness.

Volume par taxon:

- cible par défaut: jusqu’à 3 médias candidats/taxon pour targets en échec media; 1–2 pour targets déjà passants.

Entrée:

- image locale (`cached_image_path`) + contexte taxon minimal via contrat review.

Sortie:

- `ai_outputs.json` (profil pédagogique, flags, status, note, contract version, prompt version).

Cache:

- clé de cache: `source_media_id + image_sha256 + model + contract + prompt_version`.
- ne relancer Gemini que si clé absente/changée.

Retry/cost/batch:

- utiliser paramètres existants (`request_interval`, `max_retries`, backoff, `gemini_concurrency`);
- batch contrôlé par orchestrateur (`max-media-per-taxon`, `max-total`);
- écrire rapport coût estimé (compteurs appels/success/fail/retry).

Validation réponses:

- rejeter outputs invalides (`model_output_invalid`, schema fail);
- marquer explicitement `needs_manual_or_retry`.

Policy ensuite:

- appliquer `evaluate_pmp_profile_policy` localement;
- gate strict: primary doit être `basic_identification=eligible`.

Trace "signal-only":

- ajouter dans manifest run et golden manifest:
  - `ai_role: signal_only`
  - `ai_not_allowed_for: taxonomy,names,distractors,canonical_truth`.

---

## 7) Localized names dans le rerun

Règles:

- FR obligatoire pour runtime;
- EN/NL non bloquants MVP;
- source-attested acceptable;
- aucun placeholder;
- aucun nom inventé;
- aucun scientific fallback en label principal.

Plan recommandé:

- ne pas figer uniquement l’ancien `localized_name_apply_plan_v1.json`;
- générer ou reprojeter un apply plan scoped au run (`localized_names/apply_plan.json`) basé sur l’état taxons du run;
- fallback temporaire: réutiliser plan existant si hash-compatible et coverage 30/32 confirmée.

Contrôle final:

- vérifier que 30 cibles sélectionnées ont label FR runtime-safe.
- manual overrides autorisées si tracées dans `localized_names/manual_overrides.json` + report.

---

## 8) Distractors dans le rerun

Règles:

- projection sur même scope run;
- candidats via iNat similar + taxonomy neighbors;
- `referenced_taxon` autorisé pack-scoped;
- labels FR runtime-safe obligatoires;
- pas d’emergency fallback;
- pas de persistence `DistractorRelationship`.

Plan recommandé:

- ne pas réutiliser tel quel sprint13 projection;
- régénérer projection fraîche scoped run;
- enrichir labels referenced_taxon (si nécessaires) avant projection finale;
- inclure neighbors taxonomiques pour combler trous.

Outputs:

- `distractors/candidates.json`
- `distractors/projection.json`
- `distractors/readiness.json`

---

## 9) Materializer run-scoped

### Modifications proposées

Refactor `scripts/materialize_golden_pack_belgian_birds_mvp_v1.py` autour d’une config explicite.

Option recommandée: `dataclass` + CLI args.

- `--plan-path`
- `--distractor-path`
- `--qualified-export-path`
- `--inat-manifest-path`
- `--inat-ai-outputs-path`
- `--materialization-source-path`
- `--output-dir`
- `--pack-id` (default `belgian_birds_mvp_v1`)
- `--locale` (default `fr`)
- `--target-count` (default `30`)

API interne:

- `build_golden_pack(config)` pure function
- `write_outputs(config)`
- `promote_if_passed(run_output_dir, canonical_export_dir)` séparé.

### Flux d’écriture

1. write dans `data/runs/.../golden_pack/`.
2. si failed: conserver `validation_report.json` + `failed_build/partial_pack.json`, pas de `pack.json` promu.
3. promotion explicite seulement si `status=passed`.

### Promotion séparée

Créer script dédié `scripts/promote_golden_pack_v1_run_output.py`:

- vérifie `validation_report.status=passed`;
- vérifie checksums;
- copie vers `data/exports/golden_packs/belgian_birds_mvp_v1/`;
- log de promotion immuable.

---

## 10) Tests à ajouter (phase implémentation)

- dry-run contract orchestrateur (`--dry-run` sans side effects).
- création structure run directory complète.
- non-destruction artefacts historiques (`docs/audits/evidence/*`, exports existants).
- materializer run-scoped avec inputs paramétrés.
- promotion only-if-passed.
- no runtime pack when failed.
- mocks external steps iNat/Gemini.
- PMP cache hit/miss behavior.
- iNaturalist fetch mocked (429/retry/fallback order_by).
- assertion `borderline != eligible primary`.
- assertion `DATABASE_PHASE_CLOSED` reste false.
- assertion no persistence distractor relationships.

---

## 11) Roadmap de commits

### Commit A — Introduire le contrat run-scoped d’orchestration
- objectif: étendre `run_golden_pack_v1_full_scoped_pipeline.py` (CLI + state machine + run manifest stage-based).
- fichiers probables: `scripts/run_golden_pack_v1_full_scoped_pipeline.py`, `tests/test_golden_pack_full_scoped_pipeline.py`.
- tests: dry-run/apply/skip-external/resume scaffold.
- risque: faible.
- done criteria: orchestration stage-aware stable sans exécution externe réelle.

### Commit B — Refactor materializer en config run-scoped
- objectif: dé-hardcoder inputs/outputs du materializer.
- fichiers probables: `scripts/materialize_golden_pack_belgian_birds_mvp_v1.py`, nouveaux tests materializer.
- tests: output-dir isolé, failed build isolation, schema checks.
- risque: moyen (contract regressions).
- done criteria: materializer peut écrire dans `data/runs/.../golden_pack/`.

### Commit C — Ajouter promotion explicite only-if-passed
- objectif: script de promotion séparé et sûr.
- fichiers probables: `scripts/promote_golden_pack_v1_run_output.py`, tests dédiés.
- tests: reject failed run, copy passed run + checksum verify.
- risque: faible.
- done criteria: aucune promotion silencieuse automatique.

### Commit D — Brancher stage source iNaturalist run-scoped
- objectif: wrapper orchestration pour `fetch-inat-snapshot` avec paramètres scope.
- fichiers probables: orchestrateur + utilitaires lineage.
- tests: mocks fetch + inventory + raw outputs links.
- risque: moyen (réseau/timeout).
- done criteria: stage exécuté en apply avec run snapshot id.

### Commit E — Brancher normalization + qualification run-scoped
- objectif: intégrer `run-pipeline` et outputs normalized/qualified/export run-aligned.
- fichiers probables: orchestrateur + tests integration mocked.
- tests: lineage coherence checks, ids alignment checks.
- risque: moyen.
- done criteria: normalized/qualified/export produits et référencés dans run.

### Commit F — PMP generation queue/execution contrôlée
- objectif: intégrer `qualify-inat-snapshot` (ou queue) + cache report + resume.
- fichiers probables: orchestrateur, pmp helpers, tests cache/retry/skip-external.
- tests: no external mode, resume after external.
- risque: moyen/élevé (API variability/coût).
- done criteria: pipeline reprend proprement avec/without Gemini.

### Commit G — Relancer policy, localized names, distractors, readiness scoped
- objectif: produire artifacts scoped frais pour ces couches.
- fichiers probables: orchestrateur + wrappers scripts existants.
- tests: no persistence distractor, FR label-safe constraints.
- risque: moyen.
- done criteria: readiness consolidé run-scoped, blockers explicites.

### Commit H — Materialization 30/30 et gate strict
- objectif: produire `golden_pack/` run-scoped avec pass/fail strict.
- fichiers probables: materializer + orchestrateur + tests gates.
- tests: 30/30 pass path, failed path no pack runtime.
- risque: moyen.
- done criteria: `validation_report.status` pilote la suite.

### Commit I — Promotion vers `data/exports` + smoke test runtime
- objectif: promotion manuelle conditionnelle + smoke test de consommation runtime artifact-only.
- fichiers probables: promote script/tests + runbook update.
- tests: smoke contract runtime (`pack.json` + `media/` only).
- risque: faible.
- done criteria: export canonique promu seulement si passed.

---

## 12) Décisions à trancher avant implémentation

1. Scope initial `32-safe-ready` vs `50-baseline`
- pourquoi: coût/temps/API et probabilité d’atteindre 30/30.
- recommandation: démarrer `32-safe-ready` pour cycle court puis élargir à 50 si déficit.
- risque si non tranché: orchestration ambiguë et comparaisons non reproductibles.

2. `max_observations_per_taxon` / `max-media-per-taxon`
- pourquoi: couverture media vs coût PMP.
- recommandation: 8 fetch, 3 PMP max par taxon bloqué.
- risque: sous-échantillonnage (pas d’eligible) ou coût excessif.

3. Filtres iNaturalist exacts
- pourquoi: qualité et pertinence corpus.
- recommandation: `research + photos + captive=false + BE + safe licenses`.
- risque: bruit qualité ou dataset trop pauvre.

4. Licences acceptées
- pourquoi: conformité légale runtime.
- recommandation: `cc0, cc-by, cc-by-sa` (aligné existant).
- risque: retrait ultérieur d’images non conformes.

5. Fenêtre temporelle observations
- pourquoi: cohérence saisonnière et fraîcheur.
- recommandation: pas de fenêtre stricte MVP (ou 10 ans glissants si volume trop large).
- risque: biais de représentativité.

6. Politique Gemini: exécution directe vs queue-only
- pourquoi: coût/dépendance externe.
- recommandation: supporter les deux; défaut `queue+resume` en CI, `direct` local owner.
- risque: pipeline bloquée sans mode de reprise.

7. Budget API plafond
- pourquoi: contrôle coût.
- recommandation: cap explicite appels/run + stop si dépassement.
- risque: dépassement silencieux.

8. Emplacement secrets
- pourquoi: sécurité + reproductibilité.
- recommandation: `.env` local owner-side (`GEMINI_API_KEY`), jamais commit.
- risque: fuite secrets ou exécution impossible.

9. Commit des médias dans git
- pourquoi: taille repo vs reproductibilité runtime.
- recommandation: commit si `media/ <= 50MB`; sinon JSON + script de reconstruction.
- risque: repo trop lourd ou runtime non reproductible.

10. Seuil de réussite pack
- pourquoi: gouvernance release.
- recommandation: strict `30/30` uniquement.
- risque: dérive vers pack partiel.

11. Promotion automatique ou manuelle
- pourquoi: sécurité release.
- recommandation: manuelle explicite uniquement.
- risque: publication accidentelle d’un run non validé.

12. Source localized names
- pourquoi: stabilité labels runtime.
- recommandation: reprojeter plan scoped et autoriser source-attested traçable.
- risque: mismatch labels entre couches.

13. Politique distractors referenced_taxon
- pourquoi: couverture distractors.
- recommandation: autoriser pack-scoped avec labels FR safe et provenance.
- risque: collisions labels ou options faibles.

---

## 13) Non-actions (rappel explicite)

- ne pas relâcher `basic_identification=eligible`;
- ne pas accepter borderline en image principale MVP;
- ne pas générer un pack 7/30 consommable runtime;
- ne pas faire consommer `failed_build/partial_pack.json` au runtime;
- ne pas persister `DistractorRelationship`;
- ne pas passer `DATABASE_PHASE_CLOSED=true`;
- ne pas passer `PERSIST_DISTRACTOR_RELATIONSHIPS_V1=true`;
- ne pas supprimer les audits historiques;
- ne pas déplacer logique métier vers runtime;
- ne pas lancer implémentation réseau/API sans paramètres/rate-limit/lineage clairs.

---

## Conclusion exécutable

### 1. Verdict

Le full scoped rerun n'est pas encore exécutable de bout en bout. Le gap principal est d'orchestration/cohérence inter-artefacts, pas un bug isolé du materializer.

### 2. Architecture cible

Un run directory isolé et traçable par stage est requis, avec materialization run-scoped et promotion manuelle conditionnée au `passed`.

### 3. Blockers actuels

`source_inat_refresh`, `normalization`, `qualification`, `pmp_profile_generation`, `golden_pack_materialization` restent bloquants dans l'orchestrateur actuel.

### 4. Plan de rerun

Implémenter d'abord contrat d'orchestration stage-aware + materializer paramétrable; ensuite brancher fetch/normalize/qualify/PMP; enfin recomposer names+distractors+readiness et générer Golden Pack strict 30/30.

### 5. Roadmap commits

Séquence A->I ci-dessus, avec gates testés à chaque étape.

### 6. Décisions à trancher

Les 13 décisions listées doivent être fixées avant implémentation pour éviter ambiguïtés de scope, coût et conformité.

### 7. Première étape d'implémentation recommandée

Commencer par **Commit A + Commit B** (contrat orchestration run-scoped + refactor materializer paramétrable). Sans ces deux briques, aucun rerun full scoped fiable/promouvable n'est possible.
