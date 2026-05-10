---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/audits/palier-1-run001-coverage-audit.md
scope: audit
---

> Historical audit note.
> This audit may reference superseded pack/materialization contracts.
> Current contract source of truth: `docs/architecture/contract-map.md`.
> Do not use this audit as current runtime implementation guidance.
> Status: stable historical evidence; not an active implementation workstream.


# Palier 1 Run001 Coverage Audit

Generated: `2026-05-02 09:40 UTC`

## Context
- Pack: `pack:palier1:be:birds:run001`
- Historical contract target: `pack.compiled.v2` / `pack.materialization.v2`
- Observed compile blocker: `insufficient_media_per_taxon` (minimum required per taxon = `2`)

## Summary
- Taxa in scope: `50`
- Taxa compilable individually for pack threshold (active playable >=2): `41/50`
- Blocking taxa (active playable <2): `9`
- No playable items: `7`
- Low playable coverage (exactly 1 active playable): `2`
- Source undercovered taxa (<10 candidates): `9`

Category counts:
- `OK_FOR_PACK`: `41`
- `LOW_PLAYABLE_COVERAGE`: `0`
- `NO_PLAYABLE_ITEMS`: `0`
- `SOURCE_UNDERCOVERED`: `2`
- `QUALIFICATION_TOO_STRICT_OR_FAILED`: `4`
- `NEEDS_TAXON_REPLACEMENT`: `1`
- `NEEDS_MANUAL_REVIEW`: `2`

## Taxon Coverage Table

| canonical_taxon_id | scientific_name | source_taxon_id | candidates_obs | downloaded_media | qualified_total | accepted | rejected | review_required | playable_active | playable_invalidated | reject_reasons_top | invalidation_reasons_top | feedback_coverage | compilable_for_pack | category | recommended_action |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|
| taxon:birds:000014 | Turdus merula | 12716 | 20 | 20 | 20 | 9 | 11 | 0 | 9 | 0 | distance:5, occlusion:3, none:2 | none | specific 9/9; general 0/9; confusion_hint 0/9 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000004 | Erithacus rubecula | 13094 | 20 | 20 | 20 | 12 | 8 | 0 | 12 | 0 | distance:5, angle:1, none:1 | none | specific 12/12; general 0/12; confusion_hint 0/12 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000009 | Passer domesticus | 13858 | 20 | 20 | 20 | 11 | 9 | 0 | 11 | 0 | occlusion:4, none:3, distance:2 | none | specific 11/11; general 0/11; confusion_hint 0/11 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000003 | Cyanistes caeruleus | 144849 | 20 | 20 | 20 | 8 | 12 | 0 | 8 | 0 | distance:8, none:2, angle:1 | none | specific 8/8; general 0/8; confusion_hint 0/8 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000008 | Parus major | 203153 | 20 | 20 | 20 | 7 | 13 | 0 | 7 | 0 | distance:9, occlusion:3, none:1 | none | specific 7/7; general 0/7; confusion_hint 0/7 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000010 | Pica pica | 464394 | 20 | 20 | 20 | 5 | 15 | 0 | 5 | 0 | distance:10, none:4, motion:1 | none | specific 5/5; general 0/5; confusion_hint 0/5 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000005 | Fringilla coelebs | 10070 | 20 | 20 | 20 | 9 | 11 | 0 | 9 | 0 | distance:8, none:2, occlusion:1 | none | specific 9/9; general 0/9; confusion_hint 0/9 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000001 | Columba palumbus | 124821 | 20 | 20 | 20 | 8 | 12 | 0 | 8 | 0 | distance:10, none:2 | none | specific 8/8; general 0/8; confusion_hint 0/8 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000011 | Sturnus vulgaris | 14850 | 20 | 20 | 20 | 5 | 15 | 0 | 5 | 0 | distance:10, none:4, occlusion:1 | none | specific 5/5; general 0/5; confusion_hint 0/5 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000015 | Turdus philomelos | 12748 | 20 | 20 | 20 | 10 | 10 | 0 | 10 | 0 | distance:8, none:1, occlusion:1 | none | specific 10/10; general 0/10; confusion_hint 0/10 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000012 | Sylvia atricapilla | 15282 | 20 | 20 | 20 | 9 | 11 | 0 | 9 | 0 | distance:5, occlusion:3, none:3 | none | specific 9/9; general 0/9; confusion_hint 0/9 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000007 | Motacilla alba | 13695 | 20 | 20 | 20 | 7 | 13 | 0 | 7 | 0 | distance:11, none:2 | none | specific 7/7; general 0/7; confusion_hint 0/7 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000006 | Garrulus glandarius | 8088 | 20 | 20 | 20 | 4 | 16 | 0 | 4 | 0 | distance:8, none:5, occlusion:3 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000002 | Corvus corone | 204496 | 20 | 20 | 20 | 9 | 11 | 0 | 9 | 0 | distance:5, none:5, model_uncertain:1 | none | specific 9/9; general 0/9; confusion_hint 0/9 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000013 | Troglodytes troglodytes | 145363 | 20 | 20 | 20 | 8 | 12 | 0 | 8 | 0 | distance:5, occlusion:4, none:3 | none | specific 8/8; general 0/8; confusion_hint 0/8 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000016 | Carduelis carduelis | 9398 | 20 | 20 | 20 | 4 | 16 | 0 | 4 | 0 | distance:10, none:5, occlusion:1 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000017 | Chloris chloris | 145360 | 13 | 13 | 13 | 3 | 10 | 0 | 3 | 0 | occlusion:4, distance:4, angle:1 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000018 | Acrocephalus scirpaceus | 204455 | 6 | 6 | 6 | 5 | 1 | 0 | 5 | 0 | none:1 | none | specific 5/5; general 0/5; confusion_hint 0/5 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000019 | Coccothraustes coccothraustes | 9801 | 11 | 11 | 11 | 3 | 8 | 0 | 3 | 0 | distance:4, none:3, occlusion:1 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000020 | Phoenicurus ochruros | 13000 | 20 | 20 | 20 | 8 | 12 | 0 | 8 | 0 | distance:8, none:4 | none | specific 8/8; general 0/8; confusion_hint 0/8 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000021 | Anas platyrhynchos | 236935 | 20 | 20 | 20 | 16 | 4 | 0 | 16 | 0 | none:2, distance:2 | none | specific 16/16; general 0/16; confusion_hint 0/16 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000022 | Anser anser | 120479 | 20 | 20 | 20 | 16 | 4 | 0 | 16 | 0 | distance:3, none:1 | none | specific 16/16; general 0/16; confusion_hint 0/16 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000023 | Cygnus olor | 6921 | 20 | 20 | 20 | 15 | 5 | 0 | 15 | 0 | distance:3, none:2 | none | specific 15/15; general 0/15; confusion_hint 0/15 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000024 | Fulica atra | 482 | 20 | 20 | 20 | 10 | 10 | 0 | 10 | 0 | distance:8, angle:1, none:1 | none | specific 10/10; general 0/10; confusion_hint 0/10 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000025 | Gallinula chloropus | 201282 | 20 | 20 | 20 | 10 | 10 | 0 | 10 | 0 | distance:5, none:5 | none | specific 10/10; general 0/10; confusion_hint 0/10 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000026 | Larus michahellis | 59202 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | none | none | specific 1/1; general 0/1; confusion_hint 0/1 | no | SOURCE_UNDERCOVERED | Increase candidate observations for this taxon; target >=20 source candidates. |
| taxon:birds:000027 | Larus argentatus | 204533 | 20 | 20 | 20 | 14 | 6 | 0 | 14 | 0 | none:3, distance:3 | none | specific 14/14; general 0/14; confusion_hint 0/14 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000028 | Phalacrocorax carbo | 4270 | 20 | 20 | 20 | 10 | 10 | 0 | 10 | 0 | distance:8, none:2 | none | specific 10/10; general 0/10; confusion_hint 0/10 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000029 | Ardea cinerea | 4954 | 20 | 20 | 20 | 7 | 13 | 0 | 7 | 0 | distance:12, none:1 | none | specific 7/7; general 0/7; confusion_hint 0/7 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000030 | Egretta garzetta | 4943 | 13 | 13 | 13 | 3 | 10 | 0 | 3 | 0 | distance:8, none:2 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000031 | Buteo buteo | 204472 | 20 | 20 | 20 | 4 | 16 | 0 | 4 | 0 | distance:14, none:2 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000032 | Accipiter nisus | 5106 | 11 | 11 | 11 | 0 | 11 | 0 | 0 | 0 | distance:6, none:5 | none | n/a (no active playable items) | no | NEEDS_MANUAL_REVIEW | Manual audit of qualification outcomes recommended; rejection dominates this taxon. |
| taxon:birds:000033 | Falco tinnunculus | 472766 | 20 | 20 | 20 | 3 | 17 | 0 | 3 | 0 | distance:14, none:2, occlusion:1 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000034 | Falco peregrinus | 4647 | 20 | 20 | 20 | 4 | 16 | 0 | 4 | 0 | distance:11, none:4, model_uncertain:1 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000035 | Strix aluco | 19898 | 11 | 11 | 11 | 3 | 8 | 0 | 3 | 0 | none:5, distance:2, occlusion:1 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000036 | Asio otus | 142698 | 10 | 10 | 10 | 4 | 6 | 0 | 4 | 0 | occlusion:5, none:1 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000037 | Athene noctua | 19998 | 2 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | distance:1, none:1 | none | n/a (no active playable items) | no | QUALIFICATION_TOO_STRICT_OR_FAILED | Inspect rejected qualification reasons and sample media; decide manual review or more candidates. |
| taxon:birds:000038 | Picus viridis | 144243 | 20 | 20 | 20 | 7 | 13 | 0 | 7 | 0 | distance:12, none:1 | none | specific 7/7; general 0/7; confusion_hint 0/7 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000039 | Dendrocopos major | 17871 | 20 | 20 | 20 | 4 | 16 | 0 | 4 | 0 | distance:11, none:3, occlusion:2 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000040 | Dryocopus martius | 17835 | 6 | 6 | 6 | 2 | 4 | 0 | 2 | 0 | distance:2, none:2 | none | specific 2/2; general 0/2; confusion_hint 0/2 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000041 | Apus apus | 6638 | 13 | 13 | 13 | 0 | 13 | 0 | 0 | 0 | distance:13 | none | n/a (no active playable items) | no | NEEDS_MANUAL_REVIEW | Manual audit of qualification outcomes recommended; rejection dominates this taxon. |
| taxon:birds:000042 | Delichon urbicum | 64705 | 14 | 14 | 14 | 3 | 11 | 0 | 3 | 0 | occlusion:5, distance:4, none:2 | none | specific 3/3; general 0/3; confusion_hint 0/3 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000043 | Hirundo rustica | 11901 | 20 | 19 | 19 | 9 | 10 | 0 | 9 | 0 | distance:6, none:4 | none | specific 9/9; general 0/9; confusion_hint 0/9 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000044 | Riparia riparia | 11941 | 3 | 3 | 3 | 1 | 2 | 0 | 1 | 0 | distance:1, none:1 | none | specific 1/1; general 0/1; confusion_hint 0/1 | no | SOURCE_UNDERCOVERED | Increase candidate observations for this taxon; target >=20 source candidates. |
| taxon:birds:000045 | Alauda arvensis | 7347 | 4 | 4 | 4 | 0 | 4 | 0 | 0 | 0 | distance:2, none:2 | none | n/a (no active playable items) | no | QUALIFICATION_TOO_STRICT_OR_FAILED | Inspect rejected qualification reasons and sample media; decide manual review or more candidates. |
| taxon:birds:000046 | Galerida cristata | 578607 | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | distance:1 | none | n/a (no active playable items) | no | QUALIFICATION_TOO_STRICT_OR_FAILED | Inspect rejected qualification reasons and sample media; decide manual review or more candidates. |
| taxon:birds:000047 | Lanius collurio | 12038 | 7 | 7 | 7 | 0 | 7 | 0 | 0 | 0 | distance:5, none:2 | none | n/a (no active playable items) | no | QUALIFICATION_TOO_STRICT_OR_FAILED | Inspect rejected qualification reasons and sample media; decide manual review or more candidates. |
| taxon:birds:000048 | Coloeus monedula | 336399 | 20 | 20 | 20 | 7 | 13 | 0 | 7 | 0 | distance:12, none:1 | none | specific 7/7; general 0/7; confusion_hint 0/7 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000049 | Corvus frugilegus | 8029 | 12 | 12 | 12 | 4 | 8 | 0 | 4 | 0 | distance:5, none:3 | none | specific 4/4; general 0/4; confusion_hint 0/4 | yes | OK_FOR_PACK | Keep taxon in pack; coverage currently satisfies min_media_per_taxon=2. |
| taxon:birds:000050 | Corvus cornix | 144757 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | none | none | n/a (no active playable items) | no | NEEDS_TAXON_REPLACEMENT | Replace taxon for run001 pack scope or broaden source filters/area before retry. |

## Blocking Taxa For v2 Compile
- `taxon:birds:000026` (Larus michahellis): active_playable=`1`, candidates=`1`, accepted=`1`, rejected=`0`
- `taxon:birds:000032` (Accipiter nisus): active_playable=`0`, candidates=`11`, accepted=`0`, rejected=`11`
- `taxon:birds:000037` (Athene noctua): active_playable=`0`, candidates=`2`, accepted=`0`, rejected=`2`
- `taxon:birds:000041` (Apus apus): active_playable=`0`, candidates=`13`, accepted=`0`, rejected=`13`
- `taxon:birds:000044` (Riparia riparia): active_playable=`1`, candidates=`3`, accepted=`1`, rejected=`2`
- `taxon:birds:000045` (Alauda arvensis): active_playable=`0`, candidates=`4`, accepted=`0`, rejected=`4`
- `taxon:birds:000046` (Galerida cristata): active_playable=`0`, candidates=`1`, accepted=`0`, rejected=`1`
- `taxon:birds:000047` (Lanius collurio): active_playable=`0`, candidates=`7`, accepted=`0`, rejected=`7`
- `taxon:birds:000050` (Corvus cornix): active_playable=`0`, candidates=`0`, accepted=`0`, rejected=`0`

## Decision
1. Peut-on corriger run001 avec plus de candidates ?
- Oui. Les taxons bloquants sont principalement des taxons à `0` ou `1` playable actif avec couverture source faible; augmenter les candidates est le levier principal sans changer les seuils.
2. Faut-il remplacer certains taxons ?
- Oui, au moins pour les taxons sans candidates (`NEEDS_TAXON_REPLACEMENT`) si la contrainte temporelle run001 est stricte; sinon tenter un fetch ciblé avant remplacement.
3. Faut-il relancer qualification ?
- Oui après nouveau fetch/candidates, en mode déjà validé du run (sans changement de logique). Une relance qualification sans nouvelles candidates a peu de chance de lever le blocage coverage.
4. Faut-il créer un pack réduit temporaire de 20 questions pour auditer les distracteurs ?
- Oui, recommandé en parallèle pour débloquer l’audit distracteurs v2 rapidement sur un sous-ensemble compilable (`questions_possible=20` observé au diagnostic).
5. Quelles actions sont P0 avant run002 ?
- P0.1: traiter les 9 taxons bloquants (fetch ciblé BE / décision remplacement).
- P0.2: rerun pipeline cached sur run001 enrichi (sans changement de seuils/stratégie).
- P0.3: re-run `pack diagnose` puis `compile/materialize v2` sur pack 50 taxons.
- P0.4: en fallback immédiat, produire un pack réduit 20 questions pour audit distracteurs opérationnel.
