---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/localized-name-source-policy-v1.md
scope: localized_name_runtime_display
---

# Localized Name Source Policy V1

## Purpose

Define a deterministic, source-attested localized-name policy for MVP runtime display so first-corpus handoff does not require full human review of every name.

## Approved Sources

1. Existing curated/manual database name
2. iNaturalist localized common name
3. Wikidata localized label / structured localized name
4. GBIF vernacular name

## Source Preference Order

For each language (`fr`, `en`, `nl`):

1. `manual_or_curated_existing`
2. `inaturalist`
3. `wikidata`
4. `gbif`
5. no displayable localized name

## Runtime-Displayable Criteria

A localized name is runtime-displayable only when all of the following hold:

- source-attested in an approved source
- source is recorded
- source priority is recorded
- language is recorded
- value is not empty
- value is not an internal placeholder/provisional seed
- value does not silently overwrite existing curated/manual data

## Non-Displayable Criteria

A localized name is non-displayable when any of the following holds:

- missing name
- internal placeholder/provisional seed
- manual low-confidence seed without external attestation
- scientific-name fallback used as standard FR common-name display
- unresolved conflict against curated/manual value

## Confidence and Display Status Vocabulary

- `displayable_curated`
- `displayable_source_attested`
- `needs_review_conflict`
- `not_displayable_missing`
- `not_displayable_placeholder`
- `not_displayable_scientific_fallback`

## Conflict Handling

- Existing curated/manual name wins unless explicitly reviewed later.
- If iNaturalist and Wikidata disagree, select iNaturalist and record conflict.
- If iNaturalist is absent and Wikidata exists, select Wikidata.
- If iNaturalist and Wikidata are absent and GBIF exists, select GBIF.
- If no source has usable value, mark `not_displayable_missing`.
- Never silently overwrite curated/manual values.

## Runtime Contract Implication

Runtime may display only:

- `displayable_curated`
- `displayable_source_attested`

Runtime must not display:

- `needs_review_conflict`
- any `not_displayable_*` value

Runtime must not invent/fetch names.

## Important Distinction

Source-attested names are acceptable for MVP display even when not human-reviewed. Full human review remains desirable for quality hardening, but is not a first-corpus blocker when source-attested policy criteria are met.
