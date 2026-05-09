---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/runbooks/ingestion-quality-gates.md
scope: runbook
---

# Ingestion Quality Gates

Statut fonctionnel: draft  
Roadmap parente: `docs/runbooks/pre-scale-ingestion-roadmap.md`  
Périmètre immédiat: palier 1, oiseaux, Belgique, image-only, 50 espèces, 1 000 images qualifiées.

## 1. Purpose

Ce runbook transforme la roadmap pré-scale en système de décision opérable.

Il répond à sept questions:

1. Quels gates existent?
2. Quels statuts sont possibles?
3. Quels reason codes existent déjà?
4. Quels reason codes sont nécessaires mais pas encore stabilisés?
5. Qu'est-ce qui bloque?
6. Qu'est-ce qui part en review?
7. Qu'est-ce qui peut devenir playable?

Règle de pilotage:

- ne pas augmenter les volumes avant de savoir expliquer chaque acceptation, rejet, incertitude et review;
- ne pas envoyer à Gemini un média qui échoue à un gate pré-IA;
- ne pas créer de playable item sans licence, taxon actif, média exploitable, qualification, feedback minimal, distracteurs valides et trace complète.

## 2. Current active chantier

Active chantier: Phase A - Verrouiller les gates  
Status: in_progress  
Next concrete output: palier 1 audit preparation  

Do not start as structural implementation work before Phase A exit criteria:

- déduplication avancée par quasi-doublons;
- stratégie GBIF batch/download;
- feedback de confusion après erreur;
- ingestion palier 2;
- ingestion massive.

Phase A exit criteria:

- gates et reason codes documentés;
- reason codes existants inventoriés;
- mapping code actuel -> gates palier 1 produit dans
  `docs/runbooks/ingestion-code-to-gate-map.md`;
- gaps explicitement listés;
- gates bloquants palier 1 identifiés;
- aucun changement de frontière `database` / `runtime-app`.

## Phase A Decision

Status: `ready_for_palier_1_audit`

The current code-to-gate mapping shows no strict blocker before starting the
Palier 1 audit. The implementation is sufficient to audit the current pipeline
as-is, but not sufficient to promote Palier 1 as GO without a consolidated run
report, distractor v2 audit, feedback coverage review, cost estimate and
runtime E2E validation.

## 3. Status model

Statuts de gate:

| Status | Sens | Action |
|---|---|---|
| `accepted` | le gate est satisfait | continuer vers le gate suivant |
| `rejected` | le gate échoue pour une raison bloquante | ne pas promouvoir; ne pas appeler les étapes aval inutiles |
| `uncertain` | le signal est insuffisant ou contradictoire | appliquer la politique du run: reject ou review |
| `needs_review` | décision humaine ou opérateur requise | créer ou maintenir une entrée de review queue |

Mapping avec l'état actuel du code:

- `QualificationStatus.ACCEPTED` correspond à `accepted`;
- `QualificationStatus.REJECTED` correspond à `rejected`;
- `QualificationStatus.REVIEW_REQUIRED` correspond à `needs_review`;
- `uncertain` est aujourd'hui porté surtout par les flags, `uncertainty_reason` et `uncertain_policy`, pas comme statut de qualification séparé.

Conséquence:

- la roadmap peut parler de `uncertain`;
- le code actuel peut encore matérialiser cette incertitude en `review_required` ou `rejected` selon `uncertain_policy`;
- tout changement de modèle devra être traité comme un chantier code/schema séparé.

## 4. Existing reason code inventory

Cette section reflète l'état connu du code et des contrats au 2026-05-01. Elle ne crée pas de nouveaux codes par elle-même.

### 4.1 Qualification flags

Compliance rejection:

- `unsupported_media_type`
- `unsafe_license`

Fast semantic / pre-AI / AI-cache screening:

- `missing_cached_image`
- `missing_cached_ai_output`
- `cached_prompt_version_mismatch`
- `gemini_error`
- `invalid_gemini_json`
- `missing_fixture_ai_output`
- `insufficient_resolution`
- `insufficient_resolution_pre_ai`
- `decode_error_pre_ai`
- `blur_pre_ai`
- `duplicate_pre_ai`

Expert qualification / review:

- `incomplete_required_tags`
- `low_ai_confidence`
- `missing_visible_parts`
- `missing_view_angle`
- `insufficient_technical_quality`
- `review_required`
- `human_override`

### 4.2 Typed uncertainty reasons

- `none`
- `occlusion`
- `angle`
- `distance`
- `motion`
- `multiple_subjects`
- `model_uncertain`
- `taxonomy_ambiguous`

### 4.3 Playable invalidation reasons

- `qualification_not_exportable`
- `canonical_taxon_not_active`
- `source_record_removed`
- `policy_filtered`

### 4.4 Pack compilation reason codes

- `compilable`
- `no_playable_items`
- `insufficient_taxa_served`
- `insufficient_media_per_taxon`
- `insufficient_total_questions`

### 4.5 Referenced taxon mapping statuses

- `mapped`
- `auto_referenced_high_confidence`
- `auto_referenced_low_confidence`
- `ambiguous`
- `ignored`

### 4.6 Distractor reason codes observed in v2 flow

- `inat_similar_species`
- `internal_similarity`
- `diversity_fallback`
- `out_of_pack`
- `referenced_only`
- `mapped`
- `missing_label`
- `low_confidence`
- `auto_referenced_high_confidence`

## 5. Gate definitions

### Gate 1 - Source snapshot OK

Question:

La donnée brute provient-elle d'un snapshot traçable, reproductible et dans le périmètre?

Accepted:

- source autorisée;
- snapshot manifest présent;
- payload source brut référencé;
- périmètre palier 1 respecté.

Rejected:

- source hors politique;
- snapshot incomplet;
- payload brut absent;
- donnée hors périmètre volontaire.

Needs review:

- source plausible mais statut non documenté;
- payload partiel mais potentiellement récupérable;
- divergence entre manifest et fichiers locaux.

Reason codes cibles:

- `source_not_allowed`
- `snapshot_incomplete`
- `source_payload_missing`
- `out_of_scope_source_record`

Implementation note:

- certains de ces codes sont cibles roadmap et ne sont pas encore tous des constantes applicatives.

### Gate 2 - Licence and attribution OK

Question:

Le média peut-il être réutilisé dans le corpus jouable avec attribution correcte?

Accepted:

- licence média ou observation safe selon politique;
- auteur présent ou attribution complète;
- source URL présente;
- attribution exportable.

Rejected:

- licence non autorisée;
- média commercialement non safe si le contexte le requiert;
- attribution impossible à produire.

Needs review:

- licence ambiguë;
- auteur manquant mais attribution source récupérable;
- divergence licence observation / média.

Reason codes existants:

- `unsafe_license`

Reason codes cibles:

- `license_not_allowed`
- `license_ambiguous`
- `missing_author`
- `missing_attribution`
- `missing_source_url`

Blocking palier 1:

- licence unsafe;
- attribution absente sur playable item;
- source URL absente.

### Gate 3 - Canonical taxon OK

Question:

Le taxon source est-il rattaché à un taxon canonique actif, sans pollution de l'identité canonique?

Accepted:

- `canonical_taxon_id` résolu;
- taxon `active`;
- mapping compatible avec la charte canonique;
- pas de taxon `provisional` exporté.

Rejected:

- taxon non résolu;
- taxon deprecated pour nouvel asset;
- taxon hors scope;
- mapping source secondaire utilisé comme création canonique libre.

Needs review:

- mapping ambigu;
- conflit source;
- changement taxonomique non clair.

Reason codes existants proches:

- `taxonomy_ambiguous`
- `canonical_taxon_not_active`

Reason codes cibles:

- `taxon_unmapped`
- `taxon_provisional`
- `taxon_deprecated`
- `mapping_ambiguous`
- `ambiguous_source_mapping_conflict`

Blocking palier 1:

- aucun playable item sans taxon canonique actif.

### Gate 4 - Exact dedup pre-AI OK

Question:

Ce média est-il nouveau et utile à qualifier, ou est-il un doublon exact déjà connu?

Accepted:

- `source_media_id` non déjà vu;
- `file_hash` non déjà vu si disponible;
- média non dupliqué dans le snapshot;
- média non réingéré entre runs sans changement utile.

Rejected:

- doublon exact source;
- doublon exact fichier;
- média déjà traité avec résultat encore valide.

Needs review:

- plusieurs sources semblent pointer vers le même média mais la preuve exacte manque;
- attribution divergente pour un média possiblement identique.

Reason codes existants:

- `duplicate_pre_ai`

Reason codes cibles:

- `duplicate_source_media`
- `duplicate_file_hash`
- `already_seen_media`
- `duplicate_pre_ai`

Blocking palier 1:

- un doublon exact ne doit pas partir en qualification Gemini lourde.

Hors scope court terme:

- quasi-doublons perceptuels;
- crops;
- redimensionnements;
- reposts multi-sources.

### Gate 5 - Technical media pre-AI OK

Question:

Le média est-il techniquement exploitable avant de payer une qualification IA?

Accepted:

- image lisible;
- format supporté;
- dimensions minimales suffisantes;
- décodage réussi;
- flou pré-IA non bloquant.

Rejected:

- image cassée;
- format non supporté;
- résolution insuffisante;
- décodage impossible;
- flou pré-IA bloquant.

Needs review:

- média proche du seuil;
- signal technique contradictoire.

Reason codes existants:

- `unsupported_media_type`
- `insufficient_resolution`
- `insufficient_resolution_pre_ai`
- `decode_error_pre_ai`
- `blur_pre_ai`
- `missing_cached_image`

Reason codes cibles:

- `image_too_small`
- `image_broken`
- `unsupported_format`
- `image_too_blurry`
- `subject_too_small`

Blocking palier 1:

- image cassée, non décodable ou sous seuil technique ne part pas en playable.

### Gate 6 - AI qualification input OK

Question:

La qualification IA peut-elle être exécutée ou relue avec une entrée versionnée fiable?

Accepted:

- image cached disponible;
- prompt bundle compatible;
- réponse Gemini ou fixture exploitable;
- JSON valide;
- sortie versionnée.

Rejected:

- erreur Gemini non récupérée;
- JSON invalide en mode reject;
- sortie absente en mode cached obligatoire.

Needs review:

- cache manquant mais média autrement valide;
- prompt version mismatch;
- Gemini error ponctuel.

Reason codes existants:

- `missing_cached_ai_output`
- `cached_prompt_version_mismatch`
- `gemini_error`
- `invalid_gemini_json`
- `missing_fixture_ai_output`

Blocking palier 1:

- aucun mélange silencieux de sorties IA stale et prompt courant.

### Gate 7 - Pedagogical qualification OK

Question:

L'image aide-t-elle réellement à apprendre à reconnaître l'espèce?

Accepted:

- qualité technique acceptable;
- sujet visible;
- angle/vue exploitable;
- parties visibles renseignées;
- traits diagnostiques ou valeur pédagogique suffisants;
- confiance IA/humaine suffisante.

Rejected:

- confiance faible en mode reject;
- parties visibles absentes;
- angle manquant ou inexploitable;
- qualité technique insuffisante;
- tags obligatoires incomplets.

Needs review:

- image correcte mais pédagogiquement douteuse;
- incertitude taxonomique ou visuelle;
- scores proches du seuil.

Reason codes existants:

- `incomplete_required_tags`
- `low_ai_confidence`
- `missing_visible_parts`
- `missing_view_angle`
- `insufficient_technical_quality`

Reason codes cibles:

- `diagnostic_features_not_visible`
- `pedagogical_value_low`
- `subject_visibility_low`
- `ai_confidence_low`

Blocking palier 1:

- pas de playable item sans qualification pédagogique suffisante ou review résolue.

### Gate 8 - Feedback minimal OK

Question:

Le playable item contient-il un feedback utile, court, affichable et traçable?

Accepted:

- `feedback_taxon_general` disponible ou équivalent owner-side;
- `feedback_photo_specific` disponible ou équivalent owner-side;
- texte compatible mobile;
- pas d'hallucination évidente;
- provenance ou génération traçable.

Rejected:

- feedback absent pour un item devant être jouable;
- feedback manifestement faux;
- texte inutilisable côté mobile.

Needs review:

- feedback trop générique;
- feedback faible mais améliorable;
- conflit entre feedback général et image.

Reason codes cibles:

- `feedback_missing`
- `feedback_too_generic`
- `feedback_too_long`
- `feedback_confidence_low`
- `feedback_conflicts_with_image`

Blocking palier 1:

- les seuils quantitatifs restent ceux de la roadmap: viser >= 70% playable items avec feedback utile avant promotion.

Implementation note:

- ce gate est encore principalement un gate de roadmap/audit; il doit être relié aux surfaces feedback existantes avant d'être un hard gate code généralisé.

### Gate 9 - Distractors OK

Question:

La question peut-elle afficher trois distracteurs plausibles, traçables et non injustes?

Accepted:

- exactement 3 distracteurs valides;
- labels non vides;
- taxons distincts;
- aucun distracteur identique au taxon cible;
- reason codes présents;
- source traçable;
- politique `referenced_only` respectée.

Rejected:

- pas assez de distracteurs;
- label manquant;
- mapping ambigu;
- distracteur manifestement injuste;
- `referenced_only` non autorisé dans le contexte.

Needs review:

- distracteur plausible mais sensible;
- `referenced_only` utilisé dans un pack important;
- question signalée par utilisateurs.

Reason codes existants:

- `inat_similar_species`
- `internal_similarity`
- `diversity_fallback`
- `out_of_pack`
- `referenced_only`
- `missing_label`
- `low_confidence`

Reason codes cibles:

- `no_valid_distractors`
- `distractor_label_missing`
- `distractor_mapping_ambiguous`
- `distractor_unfair`

Blocking palier 1:

- pas de question materialized sans options valides;
- maximum recommandé de 1 `referenced_only` par question;
- `referenced_only` désactivé par défaut en institutionnel.

### Gate 10 - Traceability, export and runtime contract OK

Question:

L'artefact final est-il traçable, exportable et consommable par la surface
runtime verrouillee pour la phase concernee?

Accepted:

- source lineage complet;
- licence et attribution complètes;
- qualification trace complète;
- MVP: `golden_pack.v1` valide et runtime-consumable;
- legacy / strategic-later: playable item actif, pack compiled valide, et
  materialization valide quand cette famille de surfaces est explicitement dans
  le scope du run;
- runtime E2E vérifié avec `selectedOptionId` pour v2.

Rejected:

- trace manquante;
- item non exportable;
- materialization invalide;
- contrat runtime invalide;
- `export.bundle.v4` utilisé comme surface live.

Needs review:

- trace incomplète mais récupérable;
- artefact ancien avant migration;
- divergence owner/runtime à investiguer.

Reason codes existants:

- `qualification_not_exportable`
- `source_record_removed`
- `policy_filtered`
- `no_playable_items`
- `insufficient_taxa_served`
- `insufficient_media_per_taxon`
- `insufficient_total_questions`

Reason codes cibles:

- `trace_missing`
- `source_lineage_missing`
- `qualification_trace_missing`
- `not_exportable`
- `materialization_invalid`
- `runtime_contract_invalid`

Blocking palier 1:

- aucun item ou pack promu sans trace complète, attribution, qualification et contrat runtime valide.

## 6. Palier 1 hard gates

Les gates suivants sont bloquants pour le palier 1:

1. Licence et attribution complètes.
2. Taxon canonique actif.
3. Dédoublonnage exact pré-IA.
4. Média techniquement exploitable.
5. Qualification pédagogique suffisante ou review résolue.
6. Trace complète.
7. Materialization valide.
8. Aucun appel live source externe dans la boucle runtime.

Les gates suivants peuvent être `GO_WITH_WARNINGS` au palier 1 si documentés:

- feedback utile sous la cible mais au-dessus d'un minimum opérable;
- distracteurs plausibles sous la cible mais sans cas juridiquement ou pédagogiquement absurde;
- review queue plus volumineuse que prévu mais encore exploitable par l'opérateur.

## 7. Review routing

Envoyer en review quand:

- la décision automatique est incertaine;
- le média est proche d'un seuil;
- le taxon mapping est ambigu;
- la licence est ambiguë;
- le feedback est faible;
- un distracteur est potentiellement injuste;
- `referenced_only` apparaît dans un pack sensible;
- les signaux runtime montrent une confusion persistante.

Priorité haute:

- packs institutionnels;
- erreurs juridiques possibles;
- taxon mapping ambigu;
- `referenced_only` institutionnel;
- questions très jouées ou très signalées.

## 8. Gap list before implementation

Gaps déjà visibles:

1. Le front-matter documentaire actif n'accepte pas `draft`; les docs draft doivent donc utiliser un statut technique accepté et un statut fonctionnel dans le corps.
2. Les reason codes roadmap ne sont pas tous des constantes applicatives.
3. `uncertain` n'est pas un statut de qualification distinct dans le modèle actuel.
4. Le gate feedback est encore plus audit/pilotage que hard gate applicatif.
5. Le gate quasi-doublons visuels est explicitement hors implémentation court terme.
6. La stratégie GBIF/iNaturalist batch n'est pas encore documentée.
7. Les seuils définitifs de scores pédagogiques restent à valider par audit palier 1.

## 9. Immediate next actions

1. Mapper chaque gate aux fonctions/scripts existants.
2. Produire un tableau `existing_code -> gate -> reason_code`.
3. Identifier les reason codes à renommer, conserver ou ajouter.
4. Définir le rapport palier 1 minimal.
5. Lancer un audit palier 1 actuel.
6. Produire une décision `GO`, `GO_WITH_WARNINGS` ou `NO_GO`.

## 10. References

- `docs/runbooks/pre-scale-ingestion-roadmap.md`
- `docs/runbooks/ingestion-code-to-gate-map.md`
- `docs/runbooks/v0.1-scope.md`
- `docs/runbooks/program-kpis.md`
- `docs/runbooks/phase3-distractor-strategy.md`
- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`
- `docs/foundation/runtime-consumption-v1.md`
- `src/database_core/qualification/policy.py`
- `src/database_core/domain/enums.py`
