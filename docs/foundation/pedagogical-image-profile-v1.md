---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-02
source_of_truth: docs/foundation/pedagogical-image-profile-v1.md
scope: foundation
---

# PedagogicalImageProfile v1

## 1. Purpose

`PedagogicalImageProfile` transforme des images qualifiees en ressources pedagogiques comparables, auditables, et selectionnables.

Le profil v1 sert a:

- produire un score global explicable (`0-100`),
- produire des sous-scores lisibles,
- produire des scores d'usage pedagogique,
- structurer un feedback IA/owner reutilisable,
- appliquer une doctrine de maturite commune pour eviter une base heterogene.

Cette couche est possedee par `database`.

## 2. Core principles

Principes v1:

- scoring first, tagging second;
- AI-assisted, rule-calibrated;
- same maturity level for playable-ready images;
- profile is database-owned;
- runtime should only consume a lightweight subset later;
- bird/image first, taxon-group extensible;
- hard gates before scoring;
- score is explainable through subscores and reason codes.

## 3. Scope and extensibility

Version: `pedagogical_image_profile.v1`.

Scope immediat:

- taxon group: `birds`
- media type: `image`

Le design reste extensible a d'autres groupes taxonomiques et media plus tard.
La v1 autorise un bloc specifique `bird_image` sans verrouiller la structure globale sur les seuls oiseaux.

## 4. Maturity doctrine

Champ principal: `profile_status`.

Statuts:

- `pending_ai`
- `profiled`
- `profiled_with_warnings`
- `rejected_for_playable_use`
- `manual_review_required`

Regles:

- `pending_ai`: image non passee par une analyse IA minimale valide.
- `profiled`: profil complet et utilisable pour les futures selections packs.
- `profiled_with_warnings`: profil utilisable seulement avec guardrails explicites.
- `manual_review_required`: incoherence, signaux contradictoires, ou confiance insuffisante.
- `rejected_for_playable_use`: image non admissible pour le corpus jouable.

Doctrine anti-heterogeneite:

- une image sans maturite IA minimale ne peut pas etre marquee `profiled`;
- elle reste `pending_ai` (ou `manual_review_required` selon cas stale/contradictoire);
- les usages jouables recommandes sont vides tant que la maturite minimale n'est pas atteinte.

## 5. Hard gates

Les hard gates sont evalues avant tout scoring exploitable.

Hard gates minimaux v1:

- unsafe license => `rejected_for_playable_use`;
- rejected qualification => `rejected_for_playable_use`;
- missing media URL ou missing media asset => `rejected_for_playable_use`;
- missing AI qualification => `pending_ai`;
- AI status not ok => `pending_ai` ou `manual_review_required` selon le type de signal;
- very low technical quality => blocage des usages `primary_question_*`;
- very low confidence => `manual_review_required` ou `rejected_for_playable_use` selon seuil.

## 6. Overall score

`overall_score` est toujours sur `0-100`.

`score_band`:

- `A`: `85-100`
- `B`: `70-84`
- `C`: `55-69`
- `D`: `40-54`
- `E`: `0-39`

Le score global doit etre explicable par sous-scores et reason codes.

## 7. Subscores

Tous les sous-scores sont sur `0-100`.

Sous-scores minimum v1:

- `technical_quality`
- `subject_visibility`
- `diagnostic_value`
- `pedagogical_clarity`
- `representativeness`
- `difficulty_fit`
- `feedback_potential`
- `confusion_potential`
- `context_value`
- `confidence`

## 8. Usage scores

Tous les usage scores sont sur `0-100`.

Usages minimum v1:

- `primary_question_beginner`
- `primary_question_intermediate`
- `primary_question_expert`
- `context_learning`
- `confusion_training`
- `feedback_explanation`

`recommended_usages` et `avoid_usages` sont derives des usage scores, hard gates, warnings, et reason codes.

## 9. Feedback fields

Le profil inclut un feedback structure:

- `feedback_short`
- `feedback_long`
- `what_to_look_at`
- `why_good_example`
- `why_not_ideal`
- `post_answer_feedback.correct.short`
- `post_answer_feedback.correct.long`
- `post_answer_feedback.incorrect.short`
- `post_answer_feedback.incorrect.long`
- `post_answer_feedback.identification_tips`
- `post_answer_feedback.confidence`
- `feedback_confidence`

Le feedback peut etre construit via IA ou fallback deterministe prudent.

Decision candidate v1.2:

- les indices pre-reponse (`beginner_hint`, `expert_hint`, `confusion_hint`) sont de-priorises
- le signal principal est le feedback post-reponse, image-specifique

Regle v1/v1.2:

- si aucun feedback pertinent ne peut etre produit, l'image est degradee pour les usages necessitant feedback (notamment `feedback_explanation`).

## 10. Bird/image specific block

Bloc extensible v1:

```json
"bird_image": {
  "visible_bird_parts": [],
  "pose": "...",
  "plumage_visibility": "...",
  "field_marks_visible": [],
  "sex_or_life_stage_relevance": "...",
  "habitat_visible": "..."
}
```

Ce bloc est optionnel et specifique au scope `birds/image`.
Les futures extensions pourront ajouter d'autres blocs taxon/media sans casser la structure principale.

## 11. Relationship with existing fields

Positionnement des couches:

- `AIQualification`: observation/analyse brute IA + metadata de qualification;
- `DerivedClassification`: classification derivee minimale;
- `PedagogicalImageProfile`: couche de decision pedagogique, scoring, maturite et feedback;
- `PlayableItem`: surface exportable/consommable runtime.

Regle d'integration:

- les futures logiques de selection pack doivent s'appuyer sur `PedagogicalImageProfile`;
- cette phase ne modifie pas encore la selection pack principale.

## 12. Scoring policy v1 (reference)

Ponderation lisible du score global:

- `technical_quality`: 20%
- `subject_visibility`: 20%
- `diagnostic_value`: 25%
- `pedagogical_clarity`: 15%
- `representativeness`: 10%
- `feedback_potential`: 5%
- `confidence`: 5%

Notes:

- `confusion_potential` et `context_value` sont principalement des signaux d'usage specialise;
- ils n'augmentent pas fortement le score global v1.

## 13. AI requirement

Regle forte:

- sans `AIQualification` minimale valide (ou outcome status `ok` compatible), une image ne peut pas etre `profiled`.

Cas minimum v1:

- missing AI => `pending_ai`
- cached prompt mismatch => `pending_ai` ou `manual_review_required`
- gemini_error => `pending_ai`
- low confidence => `manual_review_required` ou `profiled_with_warnings` selon seuil

Le fallback deterministe est autorise pour completer/auditer,
mais ne doit jamais promouvoir une image sans maturite IA vers `profiled`.

## 14. Future integration

1. Audit Palier-1 v1.1 with PedagogicalImageProfile.
2. Calibrate thresholds manually.
3. Add pack selection filters:
   - min overall_score;
   - allowed recommended_usages;
   - min usage score.
4. Expose lightweight profile subset in playable corpus or pack compiled v3 later.
5. Use feedback fields for multilingual feedback pipeline.
