# Runtime Consumption V1

Cette note fixe la frontiere de consommation entre `database` et `runtime-app`.

`database` porte la verite des contrats et des artefacts de reference.
`runtime-app` consomme ces surfaces officielles; il ne les redefinit pas.

## Surfaces officiellement consommables

`runtime-app` peut consommer les surfaces suivantes comme surfaces runtime officielles:

- `playable_corpus.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`

## Surface interdite pour le runtime

`runtime-app` ne doit jamais utiliser `export.bundle.v4` comme surface live.
Ce bundle peut servir a des usages d'export ou d'inspection, mais pas a la lecture runtime officielle.

## Regle de responsabilite

- `database` possede la verite des contrats, des artefacts et de leur semantique
- `runtime-app` consomme ces artefacts, mais ne les redefinit pas
- toute evolution d'une surface officielle doit d'abord etre verrouillee dans `database`

## Schemas de reference officielle

Les schemas JSON suivants sont la source de verite officielle pour les types de consommation runtime.
Tout type consumer (TypeScript ou autre) doit refleter ces schemas champ par champ, sans renommage local.

- `schemas/playable_corpus_v1.schema.json` — reference pour `playable_corpus.v1`
- `schemas/pack_compiled_v1.schema.json` — reference pour `pack.compiled.v1`
- `schemas/pack_materialization_v1.schema.json` — reference pour `pack.materialization.v1`

## Regle de non-renommage

Aucun consommateur n'est autorise a renommer, abrevger ou simplifier les champs de ces schemas.
Les noms de champs definis dans `database` sont les noms officiels.
Toute deviation locale constitue une derive qui doit etre corrigee du cote consumer.

## Consequence pratique

Les futures operations editoriales ou institutionnelles doivent respecter cette frontiere.
Elles peuvent s'appuyer sur les artefacts publies par `database`, mais ne doivent pas deplacer la source de verite hors du knowledge core.
Tout besoin runtime non couvert par ces surfaces doit d'abord etre formalise et verrouille dans `database`.