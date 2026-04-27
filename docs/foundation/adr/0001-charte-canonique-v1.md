---
owner: database
status: stable
last_reviewed: 2026-04-27
source_of_truth: docs/foundation/adr/0001-charte-canonique-v1.md
scope: foundation
---

# ADR-0001 — Adoption et implémentation de la Charte Canonique v1

Statut: `accepted`  
Date: `2026-04-08`  
Décideurs: owner data, owner canonique, owner IA  
Portée: gouvernance canonique interne (`birds`, phase 1)

## Contexte

Le repo a validé un pipeline birds-first iNaturalist-first, mais le canonique restait partiellement couplé aux noms et aux conventions historiques (IDs legacy de type slug, absence de statut canonique explicite, transitions taxonomiques non contractualisées).

Sans doctrine explicite et implémentée:

- le risque de dérive d’identité augmente à chaque changement de taxonomie source,
- les migrations split/merge deviennent implicites et peu auditables,
- les sources secondaires peuvent polluer le référentiel si les garde-fous sont insuffisants,
- l’IA peut être surexposée sur des décisions qui relèvent de la gouvernance, pas de l’enrichissement.

La charte canonique v1 (`docs/foundation/canonical-charter-v1.md`) formalise la politique. Cet ADR transforme cette politique en spécification d’implémentation.

## Décision

Le projet adopte officiellement la charte canonique v1 et implémente le canonique comme un noyau d’identité stable, gouverné par règles explicites, avec iNaturalist comme source d’autorité en phase 1 birds.

La décision est normative pour:

- le modèle de données canonique,
- les règles automatiques autorisées/interdites,
- les transitions de statut et de relation taxonomique,
- la migration depuis les IDs legacy,
- le hard cutover sans compatibilité legacy lecture/écriture,
- les garde-fous pipeline/export/IA.

## Spécification canonique v1 (cible implémentation)

### 1) Champs obligatoires par taxon canonique

| Champ | Type | Obligatoire | Identitaire | Mutable | Notes |
|---|---|---|---|---|---|
| `canonical_taxon_id` | string | oui | oui | non | format `taxon:<group>:<padded_integer>` |
| `taxon_group` | enum | oui | oui | non (phase 1) | `birds` en phase 1 |
| `canonical_rank` | enum | oui | oui | oui (cas exceptionnels) | `species/genus/family` |
| `taxon_status` | enum | oui | oui | oui | `active/deprecated/provisional` |
| `accepted_scientific_name` | string | oui | non | oui | nom accepté courant |
| `synonyms` | string[] | oui | non | oui | anciens noms/variantes |
| `common_names` | string[] | oui | non | oui | non identitaire |
| `authority_source` | enum | oui | non | oui | `inaturalist` en phase 1 |
| `external_source_mappings` | object[] | oui | non | oui | mappings inter-sources |
| `display_slug` | string | oui | non | oui | lisibilité/URL/debug |

### 2) Champs enrichis non identitaires

| Champ | Type | Obligatoire | Notes |
|---|---|---|---|
| `key_identification_features` | string[] | non | enrichissement avec provenance |
| `external_similarity_hints` | object[] | non | hints non canoniques |
| `similar_taxa` | object[] | non | relations canoniques résolues |
| `similar_taxon_ids` | string[] | non | index dérivé pour consommation |

### 3) Types de similarité canonique officiels

- `taxonomic_neighbor`
- `visual_lookalike`
- `educational_confusion`

`similar_species` est considéré legacy et est retiré du contrat canonique v1.

## Règles de gouvernance

### 1) Invariant d’identité

- `canonical_taxon_id` représente un concept, jamais un nom.
- changement de nom accepté/synonymes/mappings: ID inchangé.
- renommage d’un `canonical_taxon_id`: interdit.

### 2) Autorité de création

- création automatique canonique autorisée uniquement via la source d’autorité.
- phase 1 birds: source d’autorité = `iNaturalist`.
- sources secondaires: mapping/enrichissement seulement, pas de création automatique.

### 3) Statuts canoniques

- `active`: taxon courant, peut recevoir de nouveaux assets, exportable (si autres règles OK).
- `deprecated`: conservé pour historique, reçoit 0 nouveaux assets.
- `provisional`: ambigu/temporaire, non exporté par défaut.

### 4) Split / merge / replacement

- aucun remapping silencieux de l’historique.
- transitions explicites via relations:
- `split_into`
- `merged_into`
- `replaced_by`
- `derived_from`

### 5) IA

- IA autorisée sur enrichissements.
- IA interdite sur décisions identitaires (création canonique, split/merge, statuts officiels).

## Matrice de transitions de statut

| De | Vers | Autorisé | Condition |
|---|---|---|---|
| `active` | `deprecated` | oui | remplacement/split/merge clair depuis source d’autorité |
| `active` | `provisional` | oui | ambiguïté taxonomique détectée |
| `provisional` | `active` | oui | ambiguïté levée avec signal clair |
| `provisional` | `deprecated` | oui | remplacement clarifié |
| `deprecated` | `active` | non (par défaut) | nécessite ADR explicite exceptionnel |
| `deprecated` | `provisional` | non (par défaut) | nécessite ADR explicite exceptionnel |

## Schéma de persistance cible (minimum)

### Table `canonical_taxa` (extension)

Ajouts obligatoires:

- `taxon_status`
- `accepted_scientific_name` (remplacement définitif de `scientific_name` dans le contrat v1)
- `synonyms_json`
- `authority_source`
- `display_slug`

### Table `canonical_taxon_relationships` (nouvelle)

Colonnes minimales:

- `source_canonical_taxon_id`
- `relationship_type` (`split_into`, `merged_into`, `replaced_by`, `derived_from`)
- `target_canonical_taxon_id`
- `source_name`
- `created_at`
- contrainte d’unicité `(source_canonical_taxon_id, relationship_type, target_canonical_taxon_id)`

### Table `canonical_taxon_events` (nouvelle, historique)

Colonnes minimales:

- `event_id`
- `event_type` (`create`, `name_update`, `status_change`, `split`, `merge`, `replace`)
- `canonical_taxon_id`
- `source_name`
- `effective_at`
- `payload_json`

Objectif: audit trail explicite non destructif.

Note d'évolution (`2026-04-08`, schema `v7`):
- cette table a été remplacée par les journaux séparés
  `canonical_state_events`, `canonical_change_events`,
  `canonical_governance_events`,
- puis retirée du schéma standard (drop en migration `v7`) pour éviter
  la redondance sémantique.

## Plan de migration

### Phase A — Documentation et gouvernance (DONE)

- charte stable publiée (`docs/foundation/canonical-charter-v1.md`)
- audit aligné avec plan CAN-01..CAN-12
- présent ADR publié

### Phase B — Modèle et stockage (CAN-01, CAN-07, CAN-08, CAN-09)

- introduire nouveaux champs canoniques
- introduire tables de relations/événements
- migrer enum de similarité vers 3 types v1

Critère de sortie:
- schéma DB versionné + tests de validation modèle.

### Phase C — IDs et migration totale (CAN-02, CAN-03)

- service d’allocation d’ID `taxon:<group>:<padded_integer>`
- migration des IDs legacy par backfill lexical déterministe (documentée)
- hard cutover immédiat: suppression de toute compatibilité legacy en lecture/écriture

Critère de sortie:
- zéro ID legacy accepté dans le code, les fixtures et les artefacts versionnés.

### Phase D — Enforcement pipeline/export/IA (CAN-04, CAN-05, CAN-06, CAN-10)

- auto-création uniquement via iNaturalist
- rejet création auto depuis sources secondaires
- blocage nouveaux assets sur `deprecated`
- exclusion `provisional` de l’export pédagogique par défaut
- interdiction des mutations identitaires par enrichissement IA

Critère de sortie:
- règles R1-R12 implémentées sur chemins critiques.

### Phase E — Validation (CAN-11)

- tests unitaires + intégration + non-régression fixtures
- cas nominaux + cas d’échec explicites

Critère de sortie:
- jeu de tests vert + vérifications d’intégrité export.

## Critères d’acceptation

Les points suivants doivent être vrais pour considérer la décision implémentée:

- aucun `canonical_taxon_id` renommé en place,
- tout nouveau taxon canonique auto-provient d’iNaturalist en phase 1,
- aucun taxon `provisional` exporté par défaut,
- aucun nouvel asset rattaché à `deprecated`,
- split/merge/replacement traçables via relations + événements,
- IA incapable de muter les champs identitaires sans voie explicite de gouvernance.

## Conséquences

Effets positifs:

- stabilité d’identité canonique durable,
- auditabilité des changements taxonomiques,
- réduction des dérives automatiques,
- séparation nette gouvernance vs enrichissement IA.

Coûts/contraintes:

- migration de schéma et de fixtures nécessaire,
- changement cassant assumé pour les consumers internes non migrés,
- surface de tests élargie.

## Alternatives rejetées

1. Conserver des IDs slug basés nom scientifique.  
Rejet: couplage fort au nom, faible robustesse split/merge.

2. Autoriser création canonique multi-sources automatiquement.  
Rejet: bruit canonique et conflits d’autorité.

3. Autoriser l’IA à arbitrer le canonique.  
Rejet: décision de gouvernance non auditée et non déterministe.

## Risques et mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| Migration ID casse consumers internes | élevé | mapping de migration documenté + migration repo complète + tests d’intégration |
| Mauvaise détection des changements taxonomiques | moyen | fallback `provisional` + revue manuelle |
| Dette d’implémentation partielle | moyen | suivi explicite CAN-01..CAN-12 dans audit |
| Complexité relationnelle split/merge | moyen | tables dédiées + invariants + tests |

## Références

- `docs/foundation/canonical-charter-v1.md`
- `docs/runbooks/audit-reference.md`
- `docs/foundation/canonical-id-migration-v1.md`
- `docs/runbooks/open-questions.md`
