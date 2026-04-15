# Chantier Brief Template

## ID

[INT-000]

## Title

[Titre court, stable et oriente resultat]

## Status

[not_started | in_progress | blocked | validated | closed]

## Objective

[Decrire le resultat concret attendu. Exemple: verrouiller la surface de consommation runtime pour les materializations figees sans changer les contrats existants.]

## Why this chantier exists

[Expliquer le probleme reel a resoudre, la dependance inter-repos et la raison pour laquelle ce chantier doit rester borne et trace.]

## Repo owner

- Repo: [database]
- Reason: [Ce repo porte la verite du contrat, de l'artefact ou de la doctrine concernee]

## Repo consumer

- Repo: [runtime-app]
- Reason: [Ce repo doit consommer la surface officielle sans la redefinir]

## Source of truth

- [README.md]
- [docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md]
- [docs/runtime_consumption_v1.md]
- [Autre document ou contrat owner strictement necessaire]

## Files to read first

- [README.md]
- [docs/README.md]
- [docs/codex_execution_plan.md]
- [docs/03_open_questions.md]
- [docs/20_execution/handoff.md]
- [docs/20_execution/integration_log.md]
- [runtime-app/README.md or equivalent dans l'autre repo]

## Planned actions

1. [Relire et confirmer la frontiere owner/consumer]
2. [Mettre a jour ou produire la doc de reference cote owner]
3. [Adapter ensuite uniquement la consommation cote consumer]
4. [Executer les commandes de verification definies]
5. [Documenter la validation et la prochaine etape]

## Risks

- [Risque de derive de perimetre vers de la logique runtime]
- [Risque de contradiction avec un contrat ou une ADR deja verrouilles]
- [Risque de faire avancer owner et consumer en parallele sans etat valide]

## Acceptance criteria

- [Le role du repo owner est explicite et non ambigu]
- [Le role du repo consumer est explicite et non ambigu]
- [La prochaine etape inter-repos est sequentielle et verifiable]
- [Aucune surface interdite n'est utilisee comme surface live]
- [Le chantier est repris possible sans recherche large de contexte]

## Verification commands

- [python scripts/check_doc_code_coherence.py]
- [python -m pytest -q -m "not integration_db" -p no:capture]
- [Commande de verification cote runtime-app si applicable]

## Out of scope

- [Modification des schemas existants]
- [Refonte de la pipeline]
- [Ajout de logique session, score, progression ou UX dans `database`]
- [Redefinition des contrats runtime dans le repo consumer]

## Handoff note

[Indiquer l'etat exact a transmettre, la prochaine etape executable, et les fichiers a relire en premier lors de la reprise.]

## Closure summary

[A remplir a la fin: resultat obtenu, decisions finales, verification executee, ecarts volontaires restants.]