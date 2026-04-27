---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/foundation/canonical-charter-v1.md
scope: foundation
---

# Charte Canonique v1

Statut: stable (référence normative)  
Version: `v1`  
Date d’adoption: `2026-04-08`  
Périmètre: taxons canoniques internes (`birds`, phase 1)

---

## 1. Définition officielle du canonique

Un taxon canonique est un concept taxonomique interne stable reconnu par le système comme unité de référence.

Il n’est pas:
- un simple nom scientifique,
- un simple taxon externe recopié,
- un simple nœud technique.

Il possède:
- un identifiant interne immuable,
- un nom scientifique accepté courant,
- des synonymes éventuels,
- des noms communs éventuels,
- un statut de cycle de vie,
- des mappings vers des sources externes.

Principe fondamental: l’identité canonique survit aux changements de nom et, autant que possible, aux changements taxonomiques ordinaires.

## 2. Invariant d’identité

`canonical_taxon_id` représente un concept interne, pas un nom.

Conséquences:
- le nom accepté peut changer,
- les synonymes peuvent évoluer,
- les mappings externes peuvent évoluer,
- l’ID ne change jamais.

## 3. Format officiel des IDs

Format:

`taxon:<group>:<padded_integer>`

Exemples:
- `taxon:birds:000001`
- `taxon:birds:000002`

Règles:
- ID généré automatiquement,
- ID unique,
- ID immuable,
- ID sans signification taxonomique forte,
- ID jamais renommé à cause d’un changement de nom scientifique.

Champ complémentaire non identitaire:
- `display_slug` (ex: `turdus-merula`) pour lisibilité, URL, debug et exports humains.

## 4. Source d’autorité taxonomique (phase 1)

Pour `birds` phase 1, la source d’autorité est `iNaturalist`.

Conséquences:
- un nouveau taxon canonique peut être créé automatiquement à partir d’un taxon iNaturalist inconnu,
- les évolutions taxonomiques ordinaires sont lues d’abord via iNaturalist,
- les autres sources ne redéfinissent pas seules le canonique.

## 5. Politique de création automatique

Autorisé:
- seule la source d’autorité crée automatiquement un nouveau taxon canonique.

Interdit:
- création automatique d’un taxon canonique depuis une source secondaire (GBIF, Wikimedia Commons, etc.).

Comportement des sources secondaires:
- proposer un mapping,
- enrichir un taxon existant,
- rester non résolues temporairement si mapping absent.

## 6. Structure minimale d’un taxon canonique

### A. Noyau identitaire (obligatoire)
- `canonical_taxon_id`
- `taxon_group`
- `canonical_rank`
- `taxon_status`

### B. Couche taxonomique courante (obligatoire)
- `accepted_scientific_name`
- `synonyms[]`
- `common_names[]`
- `authority_source`
- `external_source_mappings[]`

### C. Couche enrichie dérivée (non identitaire)
- `key_identification_features`
- `similar_taxa`
- `external_similarity_hints`
- futurs champs pédagogiques

Règle: ce qui change souvent ne doit pas définir l’identité.

## 7. Politique officielle sur les noms

Le système distingue explicitement:
- `accepted_scientific_name`
- `synonyms[]`
- `common_names[]`

Règles:
- un taxon canonique a un nom accepté courant,
- les anciens noms et variantes vont dans `synonyms[]`,
- les noms communs ne définissent jamais l’identité,
- un changement de nom accepté ne change pas `canonical_taxon_id`.

## 8. Statuts canoniques officiels

### `active`
- taxon utilisable normalement,
- peut recevoir de nouveaux assets,
- peut sortir dans le corpus.

### `deprecated`
- ancien concept conservé pour l’historique,
- ne reçoit plus de nouveaux assets,
- reste traçable dans l’historique/exports internes.

### `provisional`
- concept temporaire ou ambigu,
- peut exister en base,
- n’alimente pas l’export pédagogique par défaut.

## 9. Politique de split / merge / replacement

Principe absolu: le système ne réécrit jamais silencieusement l’histoire.

### Split
Si `A` est divisé en `A1` et `A2`:
- `A` passe `deprecated`,
- `A1` et `A2` passent `active`,
- `A.split_into = [A1, A2]`,
- `A1.derived_from = A`, `A2.derived_from = A`.

### Merge
Si `A` et `B` fusionnent en `C`:
- `A` et `B` passent `deprecated`,
- `C` passe `active`,
- `A.merged_into = C` et `B.merged_into = C`.

Décision opérationnelle:
- changement clair via source d’autorité: dépréciation immédiate,
- changement ambigu: `provisional` sans casser l’existant.

## 10. Similarité canonique officielle

Types minimaux:
- `taxonomic_neighbor`
- `visual_lookalike`
- `educational_confusion`

Une paire de taxons peut cumuler plusieurs relations.

## 11. Place de l’IA

L’IA n’a aucun pouvoir canonique direct.

L’IA peut:
- proposer des traits,
- aider à formuler `key_identification_features`,
- proposer des similarités,
- aider à résumer/normaliser.

L’IA ne peut pas:
- créer seule un taxon canonique,
- décider seule un split/merge,
- arbitrer seule entre taxonomies,
- modifier seule le statut canonique officiel.

Règle: l’IA enrichit, elle ne gouverne pas.

## 12. Politique sur `key_identification_features`

`key_identification_features` appartient à la couche canonique enrichie pédagogique, pas au noyau identitaire strict.

Règles:
- champ autorisé sur `CanonicalTaxon`,
- champ non identitaire,
- provenance obligatoire,
- origine possible: source-assisted, manual, AI-assisted with rules.

## 13. Règles automatiques officielles

### Règles 100 % automatiques

- `R1` créer un taxon canonique si un taxon iNaturalist inconnu entre dans le scope.
- `R2` générer un ID `taxon:<group>:<padded_integer>`.
- `R3` générer/mettre à jour `display_slug`.
- `R4` mettre à jour `accepted_scientific_name` si le nom change sans changement de concept.
- `R5` ajouter les anciens noms utiles dans `synonyms[]`.
- `R6` empêcher tout nouvel asset sur un taxon `deprecated`.
- `R7` déprécier automatiquement un taxon si la source d’autorité signale un remplacement clair.
- `R8` créer les relations `split_into`, `merged_into`, `replaced_by`.
- `R9` empêcher l’export pédagogique par défaut des taxons `provisional`.

### Règles automatiques prudentes

- `R10` source secondaire non résolue: tenter mapping, sinon laisser non résolu, sans création automatique.
- `R11` changement taxonomique ambigu: ne pas trancher automatiquement; passer `provisional` si nécessaire.
- `R12` suggestions IA: stocker comme enrichissement proposé/dérivé, jamais comme modification identitaire.

### Règles interdites

Le système ne doit jamais:
- renommer un `canonical_taxon_id`,
- créer automatiquement un taxon canonique depuis une source secondaire,
- remapper silencieusement un corpus historique après split/merge,
- laisser l’IA gouverner le canonique,
- exporter par défaut un taxon `provisional`,
- confondre nom scientifique et identité.

## 14. Gouvernance documentaire

Cette charte est la référence canonique stable v1.

ADR initial d’implémentation: `docs/adr/0001-charte-canonique-v1.md`.

Tout changement ultérieur:
- doit être tracé dans un ADR dédié,
- doit préciser impact de migration,
- doit mettre à jour `docs/runbooks/audit-reference.md` (tâches, priorités, statut).

## 15. Version courte officielle

Le canonique du projet est un ensemble de concepts taxonomiques internes stables, identifiés par des IDs immuables indépendants des noms scientifiques. En phase 1 birds, iNaturalist est la source d’autorité pour la création et l’évolution automatiques du canonique. Les changements de nom n’affectent pas l’identité; les changements taxonomiques explicites déprécient les anciens concepts sans réécriture silencieuse de l’historique. Les sources secondaires enrichissent ou se mappent à l’existant sans pouvoir canonique direct. L’IA peut assister l’enrichissement, mais ne gouverne jamais le canonique.
