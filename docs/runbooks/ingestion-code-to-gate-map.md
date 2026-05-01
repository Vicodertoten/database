---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/runbooks/ingestion-code-to-gate-map.md
scope: runbook
---

# Ingestion Code-to-Gate Map

Statut fonctionnel: draft  
Roadmap parente: `docs/runbooks/pre-scale-ingestion-roadmap.md`  
Gate reference: `docs/runbooks/ingestion-quality-gates.md`  
Périmètre: état réel du code au 2026-05-01, sans changement de code.

## 1. Purpose

Ce document relie les quality gates pré-scale au code réellement présent.

Il distingue:

- ce qui est déjà opérationnel;
- ce qui est partiel;
- ce qui est seulement documenté;
- ce qui bloque le premier audit palier 1.

Statuts utilisés:

| Status | Meaning |
|---|---|
| `implemented` | le gate est appliqué par code avec reason codes ou validation exploitable |
| `partial` | le gate existe partiellement, mais il manque des contrôles, métriques ou reason codes |
| `documented_only` | le gate est décrit, mais pas encore appliqué par code |
| `missing` | aucun support réel identifié |
| `unclear` | le comportement existe peut-être, mais la trace n'est pas assez explicite |

## 2. Summary Table

| Gate | Fichiers/fonctions actuels | Reason codes existants | Reason codes cibles non implémentés | Statut | Gap | Action recommandée |
|---|---|---|---|---|---|---|
| Gate 1 - Source snapshot OK | `src/database_core/adapters/inaturalist_snapshot.py`: `load_snapshot_manifest`, `load_snapshot_dataset`, `is_supported_observation_result`; `scripts/fetch_inat_snapshot.py`; `scripts/run_pipeline.py` | erreurs `ValueError` sur `manifest_version` et authority source; pas de reason code gate dédié | `source_not_allowed`, `snapshot_incomplete`, `source_payload_missing`, `out_of_scope_source_record` | `partial` | source/snapshot validés, mais les rejets ne sont pas encore normalisés en reason codes auditables | Ajouter au rapport palier 1 un bloc source/snapshot avec compteurs et causes; ne pas coder un modèle lourd avant audit |
| Gate 2 - Licence and attribution OK | `src/database_core/adapters/inaturalist_snapshot.py`: `is_supported_observation_result`; `src/database_core/qualification/stages/compliance.py`; `src/database_core/qualification/policy.py`: `evaluate_license_safety`; `src/database_core/ops/phase2_playable_corpus.py` | `unsafe_license`; `LicenseSafetyResult.safe/review_required/unsafe`; métrique `attribution_completeness` | `license_not_allowed`, `license_ambiguous`, `missing_author`, `missing_attribution`, `missing_source_url` | `partial` | licence safe appliquée; attribution mesurée côté phase2, mais auteur/source manquants ne produisent pas encore des reason codes structurés | Pour audit palier 1, mesurer licence/attribution coverage depuis `playable_corpus.v1`; l'ajout de reason codes attribution peut attendre si couverture est bonne |
| Gate 3 - Canonical taxon OK | `src/database_core/adapters/inaturalist_snapshot.py`: `_build_canonical_taxon`; `src/database_core/qualification/engine.py`: `_qualify_single_media`; `src/database_core/storage/playable_store.py`: invalidations; `src/database_core/ops/smoke_report.py` | `deprecated_canonical_taxon` flag implicite; `taxonomy_ambiguous`; `canonical_taxon_not_active`; KPI `exportable_unresolved_or_provisional` | `taxon_unmapped`, `taxon_provisional`, `taxon_deprecated`, `mapping_ambiguous` | `implemented` pour export/playable; `partial` pour reason taxonomy fine | le hard gate canonique existe, mais les reason codes roadmap ne sont pas alignés champ par champ | Garder les contrôles existants; mapper les gaps dans l'audit plutôt que renommer immédiatement |
| Gate 4 - Exact dedup pre-AI OK | `src/database_core/adapters/inaturalist_qualification.py`: `_compute_pre_ai_rejections`; `src/database_core/adapters/inaturalist_snapshot.py`: `summarize_snapshot_manifest`; `src/database_core/ops/smoke_report.py` | `duplicate_pre_ai`; `pre_ai_rejection_reason_counts` | `duplicate_source_media`, `duplicate_file_hash`, `already_seen_media` | `partial` | dédup exact intra-snapshot par `sha256`; pas de preuve d'un dédoublonnage inter-runs complet ni de reason codes séparés source/hash déjà vu | Bloquant à clarifier avant palier 2; pour palier 1, auditer `duplicate_pre_ai` et vérifier présence `sha256` |
| Gate 5 - Technical media pre-AI OK | `src/database_core/adapters/inaturalist_qualification.py`: `_compute_pre_ai_rejections`; `src/database_core/qualification/stages/semantic.py`; `src/database_core/qualification/ai.py`: image inspection | `insufficient_resolution_pre_ai`, `decode_error_pre_ai`, `blur_pre_ai`, `insufficient_resolution`, `missing_cached_image`, `unsupported_media_type` | `image_too_small`, `image_broken`, `unsupported_format`, `image_too_blurry`, `subject_too_small` | `implemented` pour résolution/décodage/flou; `partial` pour sujet trop petit | le pré-filtrage technique existe; `subject_too_small` n'est pas détecté hors IA | Auditer les compteurs pré-IA existants; ne pas ajouter `subject_too_small` avant grille pédagogique IA/humaine |
| Gate 6 - AI qualification input OK | `src/database_core/adapters/inaturalist_qualification.py`: `qualify_inat_snapshot`; `src/database_core/qualification/ai.py`; `src/database_core/qualification/policy.py`; `scripts/qualify_inat_snapshot.py` | `missing_cached_ai_output`, `cached_prompt_version_mismatch`, `gemini_error`, `invalid_gemini_json`, `missing_fixture_ai_output` | aucun bloquant évident; éventuellement `ai_output_stale` si besoin de lisibilité | `implemented` | entrée IA versionnée et rejet/review existent; coût par image n'est pas encore consolidé dans un audit palier 1 | Inclure `images_sent_to_gemini`, `ai_valid_outputs`, pre-AI rejects et coût manuel/estimé dans l'audit |
| Gate 7 - Pedagogical qualification OK | `src/database_core/qualification/stages/expert.py`; `src/database_core/qualification/policy.py`; `src/database_core/qualification/engine.py`; `src/database_core/domain/models.py`: `AIQualification` | `incomplete_required_tags`, `low_ai_confidence`, `missing_visible_parts`, `missing_view_angle`, `insufficient_technical_quality`; typed fields `pedagogical_quality`, `learning_suitability`, `diagnostic_feature_visibility` | `diagnostic_features_not_visible`, `pedagogical_value_low`, `subject_visibility_low`, `ai_confidence_low` | `partial` | champs pédagogiques présents, mais les seuils 0-4 roadmap et reason codes pédagogiques fins ne sont pas implémentés | Pour audit palier 1, mesurer distribution des champs existants; ne pas changer le modèle avant audit humain 30-50 questions |
| Gate 8 - Feedback minimal OK | `src/database_core/pipeline/runner.py`: `_build_playable_items`, `_build_confusion_hint`; `src/database_core/storage/playable_store.py`: `_build_feedback_short`; `src/database_core/ops/phase2_playable_corpus.py` | pas de reason code stable; métriques indirectes `feedback_short`, `contract_field_completeness.feedback_short` | `feedback_missing`, `feedback_too_generic`, `feedback_too_long`, `feedback_confidence_low`, `feedback_conflicts_with_image` | `partial` | feedback existe comme projection owner-side, mais gate qualité feedback surtout audit/documenté | Audit palier 1 doit mesurer `feedback_short`, `what_to_look_at_specific`, `what_to_look_at_general`; corrections après mesure |
| Gate 9 - Distractors OK | `src/database_core/storage/pack_store.py`: `compute_pack_compilation_context_v2`, `_build_compiled_questions_v2`, `_map_inat_similarity_candidates`; `src/database_core/domain/models.py`: `QuestionOption`, `CompiledPackQuestionV2`; `scripts/audit_phase3_distractors.py` | `inat_similar_species`, `internal_similarity`, `diversity_fallback`, `out_of_pack`, `referenced_only`, `mapped`, `missing_label`, `low_confidence`, `auto_referenced_high_confidence`; pack reason codes | `no_valid_distractors`, `distractor_label_missing`, `distractor_mapping_ambiguous`, `distractor_unfair` | `implemented` structurally; `partial` pédagogiquement | v2 invariants solides; audit plausibilité humaine et reason codes pédagogiques de rejet restent à produire | Lancer `scripts/audit_phase3_distractors.py` sur un vrai `pack.materialization.v2`; review humaine des distracteurs avant promotion |
| Gate 10 - Traceability, export and runtime contract OK | `src/database_core/qualification/engine.py`: `ProvenanceSummary`; `src/database_core/export/json_exporter.py`; `src/database_core/ops/smoke_report.py`; `src/database_core/pack/contract.py`; `src/database_core/runtime_read/service.py`; `src/database_core/runtime_read/http_server.py` | `qualification_not_exportable`, `source_record_removed`, `policy_filtered`, `no_playable_items`, `insufficient_taxa_served`, `insufficient_media_per_taxon`, `insufficient_total_questions`; KPI trace/uncertainty | `trace_missing`, `source_lineage_missing`, `qualification_trace_missing`, `not_exportable`, `materialization_invalid`, `runtime_contract_invalid` | `implemented` pour contrats/KPI; `partial` pour audit palier 1 consolidé | validation contractuelle existe; pas encore de rapport palier 1 unique GO/NO_GO | Produire le premier audit palier 1 avec décision explicite |

## 3. Gate Details

### Gate 1 - Source snapshot OK

Operational pieces:

- `load_snapshot_manifest` rejects missing or unsupported `manifest_version`.
- `load_snapshot_dataset` rejects non-iNaturalist authority for current phase 1 auto-creation.
- `is_supported_observation_result` keeps only research-grade observations with photos, safe observation/photo license, non-captive status and matching taxon ancestry.
- `summarize_snapshot_manifest` already reports harvested observations, taxa with results and downloaded images.

Current limitation:

- rejected source records are filtered during snapshot normalization without persisted gate-level reason codes per observation.
- source rejection counters are not yet exposed in the smoke report except through aggregate snapshot metrics.

Palier 1 audit implication:

- enough to report source/snapshot health;
- not enough to explain every skipped raw observation with a normalized reason code.

### Gate 2 - Licence and attribution OK

Operational pieces:

- iNaturalist snapshot loading filters unsafe observation/photo licenses before dataset creation.
- compliance screening adds `unsafe_license`.
- `export_eligible` requires accepted qualification and `LicenseSafetyResult.SAFE`.
- phase2 metrics measure attribution completeness from player-facing fields.

Current limitation:

- missing author, missing attribution and missing source URL are not first-class reason codes.
- attribution defaults can mask weak upstream attribution as `"unknown attribution"` in `MediaAsset`.

Palier 1 audit implication:

- must measure `media_attribution`, `media_license`, `media_render_url`, `source_name`;
- if any playable item has missing attribution fields, this is a hard audit gap before scale.

### Gate 3 - Canonical taxon OK

Operational pieces:

- canonical seeds are validated as iNaturalist authority in the current snapshot flow.
- `canonical_taxon_id` is attached during snapshot dataset construction.
- deprecated canonical taxa force rejection in qualification.
- provisional taxa are excluded from export eligibility.
- smoke KPI `exportable_unresolved_or_provisional` blocks exportable unresolved/provisional resources.
- playable lifecycle invalidates items when canonical taxon is not active.

Current limitation:

- the model has strong governance, but gate-specific reason codes such as `taxon_unmapped` are not normalized across all paths.

Palier 1 audit implication:

- canonical hard gate is operational enough for audit;
- use current KPI and invalidation reasons rather than introducing new reason codes first.

### Gate 4 - Exact dedup pre-AI OK

Operational pieces:

- `_compute_pre_ai_rejections` tracks `seen_hashes` from snapshot `sha256`.
- duplicate hashes inside one qualification pass become `duplicate_pre_ai`.
- `qualify_inat_snapshot` writes pre-AI rejected outcomes and updates manifest `pre_ai_rejection_reason`.
- `summarize_snapshot_manifest` exposes `pre_ai_rejection_reason_counts`.
- `generate_smoke_report` includes `pre_ai_rejection_reason_counts` when a snapshot id is provided.

Current limitation:

- dedup appears intra-snapshot/in-pass, not clearly persistent across historical runs.
- source media ID uniqueness exists in storage, but not yet as a pre-AI gate report.
- `duplicate_source_media`, `duplicate_file_hash`, and `already_seen_media` are roadmap terms, not implemented reason codes.

Palier 1 audit implication:

- audit can report exact dedup through `duplicate_pre_ai`;
- before palier 2, decide whether inter-run dedup must become a hard gate.

### Gate 5 - Technical media pre-AI OK

Operational pieces:

- pre-AI qualification rejects low resolution, decode failures, blur below threshold and duplicates.
- fast semantic screening adds `insufficient_resolution`.
- media dimensions are read from downloaded images or manifest metadata.

Current limitation:

- no non-IA subject-size detector.
- blur threshold exists but should be calibrated with real palier 1 images.

Palier 1 audit implication:

- report `insufficient_resolution_pre_ai`, `decode_error_pre_ai`, `blur_pre_ai`, `insufficient_resolution`;
- keep `subject_too_small` as a future qualification/review flag.

### Gate 6 - AI qualification input OK

Operational pieces:

- Gemini qualification writes versioned `ai_outputs.json`.
- cached qualification rejects stale prompt versions through `cached_prompt_version_mismatch`.
- parsing failures are traced as `invalid_gemini_json`.
- API failures are traced as `gemini_error`.
- missing cached outputs are traced.

Current limitation:

- no automatic cost accounting per request in the gate itself.
- mode distinction cost-efficient vs dev x4/x8 remains operational policy, not code-level gate.

Palier 1 audit implication:

- audit should calculate or manually annotate Gemini cost from media sent to Gemini and model pricing assumptions.

### Gate 7 - Pedagogical qualification OK

Operational pieces:

- `AIQualification` carries technical quality, pedagogical quality, difficulty, media role, confusion relevance, diagnostic visibility, learning suitability, uncertainty and confidence.
- expert qualification flags low confidence, missing visible parts, missing view angle and insufficient technical quality.
- `resolve_qualification_status` converts flags to accepted/review/rejected depending on `uncertain_policy`.

Current limitation:

- roadmap 0-4 scoring does not exist as explicit numeric fields.
- current enums are coarse (`unknown/low/medium/high`) rather than 0-4.
- reason codes for diagnostic/pedagogical value are not yet granular.

Palier 1 audit implication:

- use current enum distribution and manual review scores;
- do not convert the model to numeric scores before seeing the audit result.

### Gate 8 - Feedback minimal OK

Operational pieces:

- `what_to_look_at_specific` comes from qualified visible parts.
- `what_to_look_at_general` comes from canonical key identification features.
- `confusion_hint` comes from similar taxa.
- `feedback_short` is projected in the playable serving payload from specific, general or confusion hint fields.
- phase2 metrics already count `feedback_short` contract completeness.

Current limitation:

- no dedicated feedback quality reason codes.
- no separate `feedback_taxon_general` / `feedback_photo_specific` storage names yet; current fields are equivalent-ish but not named exactly that way.
- no automated hallucination or usefulness gate.

Palier 1 audit implication:

- measure coverage first;
- human audit must judge usefulness before adding more generation logic.

### Gate 9 - Distractors OK

Operational pieces:

- `QuestionOption` requires non-empty labels/source and reason codes for distractor options.
- `CompiledPackQuestionV2` enforces exactly 4 options, exactly 1 correct option, unique taxa and target inclusion.
- v2 compilation selects internal similarity, iNaturalist similar species, out-of-pack and referenced-only candidates under policy.
- referenced-only caps are enforced through `max_referenced_only_distractors_per_question`.
- low-confidence iNaturalist hints are stored as low confidence and not displayed as candidates.
- materialization v2 validates schema before persistence.
- `scripts/audit_phase3_distractors.py` audits v2 compiled/materialized payloads.

Current limitation:

- `distractor_unfair` is a human/audit decision, not code.
- no palier 1 report currently combines v2 distractor audit with corpus coverage.

Palier 1 audit implication:

- v2 distractor mechanics are ready enough to audit;
- run a real v2 materialization audit before promotion.

### Gate 10 - Traceability, export and runtime contract OK

Operational pieces:

- `ProvenanceSummary` captures source IDs, raw payload refs, run ID, licenses and AI status.
- export bundle validation exists.
- smoke KPI validates export trace, flags and typed uncertainty for exportable resources.
- pack compiled/materialization schemas validate v1 and v2 contracts.
- runtime read owner service exposes official surfaces only.
- playable lifecycle invalidates missing or non-active items with explicit reasons.

Current limitation:

- no single palier 1 audit report combines source, qualification, playable, feedback, distractors, materialization and runtime E2E into one decision.
- runtime E2E `selectedOptionId` is a cross-repo validation condition, not fully proven by this repo alone.

Palier 1 audit implication:

- database can produce most evidence;
- final promotion still needs runtime-app E2E evidence.

## 4. Really Operational Gates

Operational enough for palier 1 audit:

1. Gate 2 - licence safety for media/observation.
2. Gate 3 - canonical active/export eligibility guard.
3. Gate 5 - technical media pre-AI for resolution/decode/blur.
4. Gate 6 - AI qualification input/cache/version handling.
5. Gate 9 - v2 structural distractor/materialization invariants.
6. Gate 10 - traceability and contract validation.

Operational but requiring audit interpretation:

1. Gate 1 - source snapshot health.
2. Gate 4 - exact dedup within snapshot qualification.
3. Gate 7 - pedagogical qualification.
4. Gate 8 - feedback minimal coverage.

## 5. Documented-Only or Partial Gates

Documented or mostly audit-level today:

- missing author / missing attribution reason taxonomy;
- inter-run exact dedup as an explicit gate;
- quasi-doublons visual dedup;
- subject-too-small detection;
- numeric 0-4 pedagogical scores;
- feedback quality reason codes;
- distractor fairness reason codes;
- unified palier 1 `GO` / `GO_WITH_WARNINGS` / `NO_GO` report.

## 6. Blocking Gaps Before Palier 1 Audit

Strictly blocking before starting the audit:

- none identified in code; current implementation can be audited as-is.

Blocking before promoting palier 1 as `GO`:

1. No consolidated palier 1 report exists yet.
2. Feedback quality is not measured beyond coverage/projection.
3. Distractor validity needs a real v2 artifact audit.
4. Dedup exact is not clearly measured across runs.
5. Runtime `selectedOptionId` E2E must be verified in `runtime-app`.
6. Cost per playable item is not currently calculated in a run report.

## 7. Minimal Actions Before Palier 1 Audit

1. Generate or select the current palier 1 dataset/run.
2. Run `generate_smoke_report.py` with the relevant snapshot id.
3. Run phase2/palier corpus metrics to capture species coverage, attribution and feedback coverage.
4. Build/locate one real `pack.materialization.v2`.
5. Run `scripts/audit_phase3_distractors.py` on that v2 artifact.
6. Count review queue volume and top reason codes.
7. Manually review 30 to 50 questions for image clarity, feedback usefulness and distractor plausibility.
8. Record runtime-app E2E status for `selectedOptionId`.
9. Publish `docs/audits/palier-1-ingestion-audit-2026-05-01.md` with `GO`, `GO_WITH_WARNINGS` or `NO_GO`.

## 8. Recommended Palier 1 Audit Sections

The first audit should include:

1. Scope and inputs.
2. Source snapshot health.
3. Candidate and pre-AI filtering counts.
4. Qualification status distribution.
5. Species coverage and images per species.
6. Licence and attribution coverage.
7. Feedback coverage.
8. Distractor/materialization v2 validity.
9. Review queue volume and reason codes.
10. Cost estimate.
11. Runtime E2E status.
12. Manual pedagogical review.
13. Decision: `GO`, `GO_WITH_WARNINGS` or `NO_GO`.

## 9. References

- `docs/runbooks/pre-scale-ingestion-roadmap.md`
- `docs/runbooks/ingestion-quality-gates.md`
- `docs/runbooks/v0.1-scope.md`
- `src/database_core/adapters/inaturalist_snapshot.py`
- `src/database_core/adapters/inaturalist_qualification.py`
- `src/database_core/qualification/policy.py`
- `src/database_core/qualification/engine.py`
- `src/database_core/qualification/stages/compliance.py`
- `src/database_core/qualification/stages/semantic.py`
- `src/database_core/qualification/stages/expert.py`
- `src/database_core/qualification/stages/review.py`
- `src/database_core/pipeline/runner.py`
- `src/database_core/storage/playable_store.py`
- `src/database_core/storage/pack_store.py`
- `src/database_core/ops/smoke_report.py`
- `src/database_core/ops/phase2_playable_corpus.py`
- `scripts/audit_phase3_distractors.py`
- `scripts/generate_smoke_report.py`
