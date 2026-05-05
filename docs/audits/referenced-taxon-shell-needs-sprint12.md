---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/referenced-taxon-shell-needs-sprint12.md
scope: audit
---

# Referenced Taxon Shell Needs — Sprint 12

## Purpose

Audit iNaturalist similar-species candidates and prepare referenced taxon shell candidates for unmapped taxa without creating active canonical taxa.

## Summary Metrics

| Metric | Value |
|---|---|
| Total candidate taxa from iNat similar species | 198 |
| Candidates mapped to canonical taxa | 42 |
| Candidates already existing as referenced taxa | 0 |
| Candidates needing new referenced shell | 156 |
| Candidates ambiguous | 0 |
| Candidates ignored | 0 |
| Candidates missing scientific name | 0 |
| Candidates with FR name | 42 |
| Candidates without FR name | 156 |

## Decision

**NEEDS_REFERENCED_TAXON_STORAGE_WORK**

Shell candidates identified. Implement a reviewed storage apply path before creation.

## Shell Creation Mode

- mode: dry_run
- safe_apply_pathway_available: False

## Required Future Storage Changes

- Provide a reviewed admin script to upsert ReferencedTaxon records outside runtime paths.
- Use transaction-safe writes with explicit dry-run and --apply confirmation.
- Enforce mapping_status invariants and unique (source, source_taxon_id).
- Capture before/after snapshots and conflict logs for governance review.

## Guardrails

- No active CanonicalTaxon was created automatically.
- No canonical promotion was performed automatically.
- Runtime, pack materialization, compile_pack_v2, and QuestionOption were untouched.
- This phase only prepares shell candidates and governance evidence.
