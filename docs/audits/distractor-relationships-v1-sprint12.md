---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-sprint12.md
scope: audit
---

# Distractor Relationships V1 Sprint 12 Closure

## Phases Completed

- Phase A: iNaturalist similarity enrichment gap audit and root-cause confirmation.
- Phase B: iNaturalist similarity enrichment refresh and candidate regeneration inputs.
- Phase C: localized names enrichment for canonical taxa used by distractor flows.
- Phase D: referenced taxon shell need/candidate audit in dry-run mode.
- Phase E: Sprint 11 vs Sprint 12 readiness comparison.
- Phase F: persistence decision with explicit deferral criteria and blockers.

## Files Changed

- docs/audits/distractor-relationships-v1-sprint12-persistence-decision.md
- docs/audits/distractor-relationships-v1-sprint12.md

## Tests Run

- ./.venv/bin/python scripts/check_docs_hygiene.py
  - Passed (after removing forbidden docs/.DS_Store and docs/audits/.DS_Store files).
- ./.venv/bin/python scripts/check_doc_code_coherence.py
  - Passed.
- ./.venv/bin/python -m pytest tests/test_audit_inat_similarity_enrichment_gap.py tests/test_inat_taxon_similarity_enrichment.py tests/test_taxon_localized_names_for_distractors.py tests/test_referenced_taxon_shell_prep_for_distractors.py tests/test_compare_distractor_readiness_sprint11_sprint12.py -q
  - Passed with PYTHONPATH=src (57 passed).
- ./.venv/bin/python scripts/verify_repo.py
  - Executed and reported broad-suite import-path issues (ModuleNotFoundError: database_core) in the environment's default invocation.

## Key Metrics

- Target taxa: 50
- Total candidate relationships: 407
- Source distribution:
  - inaturalist_similar_species: 323
  - taxonomic_neighbor_same_genus: 8
  - taxonomic_neighbor_same_family: 66
  - taxonomic_neighbor_same_order: 10
- Targets ready: 39
- Targets blocked: 11
- Targets with >=3 candidates: 49
- Targets with >=3 FR-usable candidates: 39
- Missing French names: 156
- Referenced taxon shells needed (strict need list): 0
- Referenced shell candidates requiring reviewed strategy: 156
- Emergency fallback generated: no

## Sprint 11 vs Sprint 12 Comparison

- iNat similar count: 0 -> 323 (delta +323)
- Total candidates: 244 -> 407 (delta +163)
- Targets ready: 0 -> 39 (delta +39)
- Targets blocked: 50 -> 11 (delta -39)
- Targets with >=3 FR-usable: 0 -> 39 (delta +39)
- Taxonomic-only dependency: 26 -> 1 (delta -25)
- Same-order dependency: 17 -> 1 (delta -16)
- Missing French names: 43 -> 156 (delta +113)

## Decision

- Final Phase F decision label: DEFER_PERSISTENCE_USE_ARTIFACTS_ONLY_FOR_NOW
- Persistence writes are deferred in Sprint 12.
- Sprint 12 generated JSON artifacts remain source of truth for Sprint 13 inputs.

## Remaining Blockers

- Candidate relationship artifacts need schema-compliant projection to distractor_relationship_v1.
- Referenced taxon shell storage/apply path needs reviewed implementation and auditability.
- Missing French labels remain high in expanded candidate universe.

## Recommended Sprint 13

A. AI ranking/proposals dry-run if source coverage improved but incomplete.
B. Persistence of DistractorRelationship if Phase F deferred writes and blockers are resolved.
C. First corpus distractor gate if enough targets are ready.
D. More localized names/manual completion if labels remain blocker.
