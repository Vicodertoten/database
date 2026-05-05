---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/taxon-localized-names-multisource-sprint14-dry-run.md
scope: sprint14b_localized_names
---

# Taxon Localized Names Multisource Sprint 14 Dry Run

Localized names remain the primary Sprint 14B blocker because runtime-safe FR labels are below first-corpus minimum.
Source-attested names are acceptable for MVP display when traceable and policy-selected, even if not fully human-reviewed.

- policy: `docs/foundation/localized-name-source-policy-v1.md`
- sources used: inaturalist(local artifacts), curated/manual existing
- unavailable sources: wikidata=not_configured, gbif=not_configured
- source preference: curated/manual > iNaturalist > Wikidata > GBIF > missing
- this is not human-reviewed perfection; it is deterministic, attested, and conflict-aware MVP safety
- projected FR displayable gain: 23
- projected safe ready targets: 36 / 30
- projected decision: READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS

## Remaining Warnings

- Non-human-reviewed source-attested names remain warning-level and should be sampled in later QA.
- Wikidata/GBIF local artifacts were unavailable in this run.

## Non-Actions

- No DistractorRelationship persistence
- No ReferencedTaxon shell creation
- No runtime app changes
- No invented labels
