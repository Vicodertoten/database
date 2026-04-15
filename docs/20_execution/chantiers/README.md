# Chantiers

Ce dossier contient un fichier par chantier inter-repos ou structurant.
Chaque chantier doit rester borne, nomme, traçable et compatible avec une reprise par une autre session IA.

## Ouvrir un nouveau chantier

1. verifier qu'il n'existe pas deja un chantier structurant actif
2. creer un nouveau fichier a partir de `_template.md`
3. attribuer un identifiant stable de type `INT-XXX`
4. definir clairement le repo owner et le repo consumer
5. lister les fichiers a lire avant toute action
6. remplir les criteres d'acceptation et les commandes de verification avant de commencer

## Convention de nommage

Nommer chaque chantier avec un identifiant `INT-XXX`, ou `XXX` est un numero a trois chiffres.

Exemples:

- `INT-001`
- `INT-002`
- `INT-014`

Le nom du fichier peut reprendre uniquement l'identifiant ou l'identifiant plus un slug court, selon la pratique retenue par l'equipe.
L'important est de garder l'identifiant stable dans tous les documents de suivi.

## Choisir le repo owner et le repo consumer

Choisir `database` comme owner des qu'un chantier touche:

- un contrat data
- une surface playable ou pack
- une compilation
- une materialization
- une file d'enrichissement
- un artefact ou une regle de reference que le runtime doit consommer

Choisir `runtime-app` comme consumer quand le chantier consiste a:

- lire une surface officielle publiee par `database`
- adapter un chargement runtime a un contrat deja verrouille
- verifier l'integration produit sans redefinir le contrat de reference

Si le doute existe, verrouiller d'abord le sujet dans le repo owner.

## Utiliser le template

Le template doit etre rempli de facon concrete.
Il doit permettre a une autre session de comprendre immediatement:

- pourquoi le chantier existe
- quelle est la verite de reference
- quels fichiers relire avant toute modification
- quelles actions sont prevues et dans quel ordre
- quels risques sont connus
- comment verifier le resultat

Eviter les formulations vagues du type `ajuster si besoin` ou `mettre a jour plus tard`.
Chaque prochaine etape doit etre executable telle quelle.

## Cloturer un chantier proprement

1. verifier que les criteres d'acceptation sont remplis
2. noter les decisions finales et le resultat reel du chantier
3. mettre a jour le handoff si une reprise reste possible ou necessaire
4. ajouter ou completer l'entree correspondante dans `integration_log.md`
5. passer le statut a `closed` seulement quand owner et consumer sont alignes ou quand la frontiere du chantier est explicitement arretee