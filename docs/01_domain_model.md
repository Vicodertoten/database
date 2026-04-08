# Domain Model

## CanonicalTaxon

Internal taxon identity. Upstream identifiers are mappings, not product identity.
Normative reference: `docs/06_charte_canonique_v1.md`.

Canonical v1 target structure:

Identity core (stable):

- `canonical_taxon_id` (immutable concept ID, target format `taxon:<group>:<padded_integer>`)
- `taxon_group`
- `canonical_rank`
- `taxon_status` (`active`, `deprecated`, `provisional`)

Current taxonomy layer:

- `accepted_scientific_name`
- `synonyms[]`
- `common_names[]`
- `authority_source`
- `external_source_mappings[]`

Derived enrichment layer (non-identitary):

- `display_slug`
- `key_identification_features`
- `external_similarity_hints`
- `similar_taxa`
- `similar_taxon_ids` (derived index for consumers)

Implementation note (2026-04-08):

- canonical v1 hard cutover is implemented
- legacy slug-style IDs and legacy `scientific_name` canonical field are removed from the active contract
- ID migration mapping is documented in `docs/07_canonical_id_migration_v1.md`
- governance implementation tracking is maintained in `docs/05_audit_reference.md` tasks `CAN-01` to `CAN-12`

## SourceObservation

Traceable upstream observation record.

Fields:

- source name
- source observation ID
- source taxon ID
- observed timestamp when known
- minimal location metadata
- source quality metadata
- raw payload reference
- resolved canonical taxon link when available

## MediaAsset

Source media attached to an observation.

Fields:

- stable internal media ID
- source name
- source media ID
- media type
- source URL
- attribution
- author
- license
- MIME type and extension when known
- basic dimensions when known
- checksum placeholder
- linked observation
- linked canonical taxon when resolved

## QualifiedResource

Derived resource that is explicitly judged usable or not usable for pedagogical reuse.

Fields:

- stable qualified resource ID
- canonical taxon ID
- source observation reference
- media asset ID
- qualification status
- qualification version
- technical quality
- pedagogical quality
- life stage
- sex
- visible parts
- view angle
- notes and flags
- provenance summary
- license safety result
- export eligibility

Qualification stays explicit. Unknown and review-required are first-class outcomes.
