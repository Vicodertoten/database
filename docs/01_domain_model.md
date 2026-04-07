# Domain Model

## CanonicalTaxon

Internal taxon identity. Upstream identifiers are mappings, not product identity.

Fields:

- stable internal ID
- scientific name
- canonical rank
- optional common names
- bird scope compatibility flag
- external source mappings
- reserved list for similar/confusable taxa

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

