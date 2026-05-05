---
owner: database
status: stable
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/taxon-localized-names-enrichment-v1.md
scope: foundation
---

# Taxon Localized Names Enrichment V1

## Purpose

Define a durable, reusable localized name enrichment and patch workflow for FR/EN/NL across canonical taxa and referenced taxon shells.

## Why This Is Structural (Not UI-only)

Localized names are required by database-level quality gates:

- Distractor readiness and persistence decisions depend on FR availability.
- Distractor candidate usability flags derive from localized names.
- Compile-time and governance decisions require stable multilingual provenance.

This is a data-governance capability, not a presentation layer feature.

## Language Policy FR/EN/NL

- FR: mandatory for first Belgian/francophone corpus usability.
- EN: required for source support and cross-review clarity.
- NL: required for Belgian multilingual forward compatibility.

Operational flags:

- can_be_used_now_fr: common_name_fr exists.
- can_be_used_now_multilingual: common_name_fr, common_name_en, and common_name_nl exist.

## Source Priority

Use strict source precedence in this order:

1. existing common_names_i18n
2. iNaturalist localized/common names
3. manual override patch file (with source, reviewer, confidence)
4. future external sources (documented; not implemented in v1)

## Canonical vs Referenced Taxa

- canonical_taxon patches target CanonicalTaxon identity space.
- referenced_taxon patches target ReferencedTaxon shell identity space.
- unresolved_taxon patches are audit-only and cannot be auto-applied.

## Manual Override Rules

- Manual override is allowed only when source=manual_override and reviewer is explicit.
- confidence must be present (high|medium|low).
- Silent overwrite is forbidden.

## Conflict Handling

- Existing identical value: skip, no mutation.
- Existing different value: conflict by default.
- Conflict can be resolved only under explicit manual override conditions.
- All conflicts must be reported in evidence output.

## Dry-run / Apply Behavior

- Default mode is dry-run.
- Dry-run computes and reports changes, but does not mutate inputs.
- --apply is explicit and required for writing patched outputs.
- No broad database writes are performed by default.

## Audit Fields

Patch schema and evidence require provenance fields:

- patch_id
- taxon_ref_type
- source
- confidence
- reviewer (optional but required for manual conflict override)
- notes

## How This Feeds Distractor Readiness

Localized-name coverage directly impacts distractor readiness by reducing unavailable_missing_localized_name pathways and increasing can_be_used_now_fr and can_be_used_now_multilingual rates.

## Future External Sources

Future sources can be added in later versions (for example GBIF vernacular profiles) under the same precedence and conflict governance model.
