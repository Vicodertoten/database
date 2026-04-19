# Execution And Inter-Repo Coordination

Ce dossier sert a piloter un chantier de facon sequentielle, traçable et compatible avec un travail partage entre `database` et `runtime-app`.

Il ne definit ni nouvelle architecture produit ni nouvelle logique metier.
Il formalise uniquement la maniere de conduire un chantier documentaire, technique ou d'integration quand plusieurs repos doivent avancer sans ambiguite.

## Regles de travail inter-repos

- un seul chantier structurant actif a la fois
- chaque chantier a un identifiant stable et un statut explicite
- chaque decision doit etre rattachee a un chantier, un repo owner et un repo consumer
- les etapes doivent rester sequentielles et verifiables
- un handoff doit permettre de reprendre le chantier dans une nouvelle session IA sans perdre le contexte utile
- un integration log doit garder la trace des decisions, validations et prochaines etapes inter-repos

## Etat courant visible (reference inter-repos)

Ce bloc sert de reference de wording pour eviter toute derive narrative entre `database` et `runtime-app`:

- lecture runtime nominale: owner-side read minimal reel en place (`database`), sur 3 surfaces officielles uniquement
- sessions runtime: nominales et persistees cote `runtime-app`
- web runtime: surface minimale pedagogique
- mobile runtime: surface minimale reelle image-first (rendu image prioritaire en UI)

Cette reference de statut doit rester coherente entre README/docs/UI des deux repos.

## Notions

### Chantier

Un chantier est une unite de travail borne, nommee et suivie dans le temps.
Il porte un objectif clair, des contraintes connues, des actions prevues, des criteres d'acceptation et un etat de cloture.

### Repo owner

Le repo owner est le repo qui porte la verite de reference pour le sujet traite.
Dans ce cadre, `database` reste owner pour les contrats data, les packs, la compilation, la materialization, l'enrichissement et les surfaces de serving qui en derivent.

### Repo consumer

Le repo consumer est le repo qui consomme une surface officielle sans la redefinir.
Dans ce cadre, `runtime-app` est consumer des surfaces runtime officielles publiees par `database`.

### Handoff

Le handoff est l'etat de passage entre deux sessions de travail.
Il indique le chantier actif, le role du repo courant, l'etat valide, les contraintes deja verrouillees, la prochaine etape exacte et les fichiers a relire avant toute reprise.

### Integration log

L'integration log est le journal de synchronisation inter-repos.
Il sert a garder une trace courte mais exploitable de chaque chantier: ce qui a ete decide, ce qui a ete valide, quels fichiers sont touches, quels commits sont lies et quelle est la prochaine etape.

Seules les entrees reelles doivent vivre dans `integration_log.md`.
Les exemples fictifs, templates pedagogiques et archives doivent etre ranges dans `docs/20_execution/archive/`.

## Frontieres a respecter

- `database` reste le knowledge core et ne devient pas le backend runtime
- `database` reste owner pour les sujets: contrats data, packs, compilation, materialization, enrichissement
- `runtime-app` consomme les surfaces runtime officielles; il ne redefinit pas les contrats du knowledge core
- `export.bundle.v4` ne doit jamais etre utilise comme surface live par le runtime

## Discipline de tracabilite

Toute modification inter-repos doit pouvoir etre suivie dans cet ordre:

1. ouverture du chantier
2. clarification du repo owner et du repo consumer
3. execution sequentielle et verification locale
4. mise a jour du handoff
5. ecriture dans l'integration log
6. cloture explicite du chantier

Si une decision touche une frontiere doctrinale, elle doit d'abord etre verrouillee dans le repo owner avant toute adaptation dans le repo consumer.