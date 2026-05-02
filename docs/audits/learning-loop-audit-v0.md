---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/audits/learning-loop-audit-v0.md
scope: cross_repo_learning_loop_audit
---

# Learning Loop Audit v0

Date: 2026-05-01
Perimetre: `database -> materialization.v2 -> runtime session -> answer -> learning -> revision -> distractors -> feedback readiness`

## 1. Etat des contrats

Verification:

- `schemas/pack_compiled_v2.schema.json` present
- `schemas/pack_materialization_v2.schema.json` present
- `QuestionOption` governes dans `src/database_core/domain/models.py`

Constat:

- contrats v2 formalises et valides sur artefact reel (50 questions)
- transition v1/v2 preservee

Verdict: PASS.

## 2. Etat database

Verification executee:

```bash
./.venv/bin/python scripts/verify_repo.py
set -a; source .env; set +a
./.venv/bin/python scripts/prepare_phase3_pedagogical_run.py --question-count 50
```

Resultat:

- verification repo: PASS (177 tests)
- generation `pack.compiled.v2` et `pack.materialization.v2`: PASS
- audit auto des invariants v2: PASS

Verdict: PASS.

## 3. Etat runtime (session/reponse v1 + v2 + idempotence)

Verification executee dans `/Users/ryelandt/Documents/runtime-app`:

```bash
set -a; source .env; set +a
if [[ -z "${TEST_RUNTIME_DATABASE_URL:-}" ]]; then
	echo "TEST_RUNTIME_DATABASE_URL is required for owner/Postgres runtime tests"
	exit 1
fi
if [[ "${ALLOW_RUNTIME_TEST_DB_RESET:-}" != "true" ]]; then
	echo "ALLOW_RUNTIME_TEST_DB_RESET=true is required to authorize runtime test DB reset"
	exit 1
fi
pnpm --filter @runtime-app/api run migrate:runtime-db
pnpm --filter @runtime-app/api run test:sessions:postgres
pnpm --filter @runtime-app/api run test:sessions:postgres:learning
```

Resultat:

- migrations runtime DB: PASS
- `sessions.postgres.integration.test.ts`: PASS
- `sessions.learning.postgres.integration.test.ts`: PASS

Constats cibles verifies:

- soumission idempotente testee
- conflit sur resoumission differente teste
- learning events non dupliques en retry idempotent (1 event persiste)
- `selectedOptionId` supporte pour v2, `selectedPlayableItemId` conserve legacy
- `selectedTaxonId` resolu depuis option snapshot v2

Verdict: PASS.

## 4. Etat learning/revision

Elements verifies:

- tables `user_answer_events`, `user_taxon_mastery`, `user_confusion_events` actives
- endpoints `/me/mastery` et `/me/confusions` verifies via tests Postgres
- mode revision present cote runtime et reason codes consommes sans recalcul distracteur

Resultat:

- mode pack collecte learning
- mode revision exploite learning sans casser mode pack
- absence de double ecriture lors des retries idempotents

Verdict: PASS (avec calibration produit continue recommandee).

## 5. Etat distracteurs (qualite)

Base mesuree:

- audit artefact v2 calibre 50 questions

Resultat:

- invariants techniques: 100% conformes
- `inat_similar_species`: 66.67% des distracteurs
- `diversity_fallback` seul: 33.33%
- repetition de distracteurs: elevee sur certains taxons

Verdict: PASS technique, RISQUE pedagogique modere.

## 6. Etat feedback actuel (readiness phase 4)

Mesure executee sur `playable_items` (database reel):

- total items: 1855
- `what_to_look_at_specific_json` non vide: 1855/1855 (100%)
- `what_to_look_at_general_json` non vide: 0/1855 (0%)
- `confusion_hint` non vide: 0/1855 (0%)

Interpretation:

- le feedback photo-specifique minimal est present
- le feedback general et confusion hint sont absents en pratique
- readiness fonctionnelle phase 4 incomplete si l'objectif est feedback dual (general + photo)

Verdict: NO-GO partiel pour phase 4 complete.

## 7. Risques

1. Risque pedagogique distracteurs: fallback diversity encore trop frequent sur echantillon calibre.
2. Risque produit feedback: champs general/confusion quasi vides en base reelle.
3. Risque de faux vert: echantillon calibre injecte, a completer par un echantillon non injecte.

## 8. Decision

Decision globale: GO pour consolidation 3.5 technique, NO-GO pour lancer directement une phase 4 complete.

Condition de passage phase 4:

1. remplir reellement le feedback general (`what_to_look_at_general`) sur corpus pilote
2. remplir `confusion_hint` avec qualite minimale
3. reduire fallback diversity et repetition sur un audit non calibre de 50 questions
4. produire un mini rapport GO/NO-GO final apres ces correctifs
