---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-sprint13.md
scope: audit
---

# Distractor Relationships V1 Sprint 13 Closure

## Phases Completed

- Phase A: Schema-compliant projection of 407 DistractorRelationship candidate records.
- Phase B: Localized names foundation — audit, schema, apply pipeline for canonical and referenced taxa.
- Phase C: Referenced taxon shell dry-run apply plan for 156 iNat-sourced shells.
- Phase D: Priority FR name completion for top 44 candidates and Sprint 13 readiness rerun.
- Phase E: Sprint 12 vs Sprint 13 readiness comparison and persistence decision.

## Files Changed

### New scripts
- scripts/project_distractor_candidates_to_relationships_v1.py
- scripts/audit_taxon_localized_names_v1.py
- scripts/apply_taxon_localized_name_patches_v1.py
- scripts/prepare_referenced_taxon_shell_apply_plan_v1.py
- scripts/select_priority_taxon_name_patches_for_distractors.py

### New tests
- tests/test_project_distractor_candidates_to_relationships_v1.py
- tests/test_taxon_localized_names_enrichment_v1.py
- tests/test_referenced_taxon_shell_apply_plan_v1.py
- tests/test_priority_taxon_name_completion_for_distractors.py

### New schemas
- schemas/taxon_localized_name_patch_v1.schema.json

### New docs (audits)
- docs/audits/distractor-relationships-v1-projection-sprint13.md
- docs/audits/taxon-localized-names-sprint13-audit.md
- docs/audits/taxon-localized-names-sprint13-apply.md
- docs/audits/referenced-taxon-shell-apply-plan-sprint13.md
- docs/audits/distractor-readiness-sprint12-vs-sprint13.md
- docs/audits/distractor-relationships-v1-sprint13-persistence-decision.md
- docs/audits/distractor-relationships-v1-sprint13.md

### New docs (foundation)
- docs/foundation/taxon-localized-names-enrichment-v1.md

### New evidence artifacts
- docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json
- docs/audits/evidence/taxon_localized_names_sprint13_audit.json
- docs/audits/evidence/taxon_localized_names_sprint13_apply.json
- docs/audits/evidence/referenced_taxon_shell_apply_plan_sprint13.json
- docs/audits/evidence/distractor_readiness_v1_sprint13.json
- docs/audits/evidence/distractor_readiness_sprint12_vs_sprint13.json

### New data artifacts
- data/manual/taxon_localized_name_patches_sprint13.csv
- data/enriched/taxon_localized_names_v1/canonical_taxa_patched.json
- data/enriched/taxon_localized_names_v1/referenced_taxa_patched.json

### Modified scripts
- scripts/apply_taxon_localized_name_patches_v1.py
  (bug fix: null-safe guard for existing_referenced_taxon_id in load_referenced_records)

## Tests Run

- ./.venv/bin/python -m pytest tests/test_project_distractor_candidates_to_relationships_v1.py tests/test_taxon_localized_names_enrichment_v1.py tests/test_referenced_taxon_shell_apply_plan_v1.py tests/test_priority_taxon_name_completion_for_distractors.py -q
  - Passed (19 tests across Sprint 13 test files).
- ./.venv/bin/python scripts/check_docs_hygiene.py
  - Passed.
- ./.venv/bin/python scripts/check_doc_code_coherence.py
  - Passed.

## Key Metrics

### Phase A — Projection
- Input candidate records: 407
- Projected records: 407
- Rejected records: 0
- Schema validation errors: 0

### Phase B — Localized Names
- Patches applied (Phase D priority run): 44
- Patch conflicts: 0
- Invalid patches: 0
- Provisional FR seeds (confidence=low): 44
- Localized names system supports canonical taxa: yes
- Localized names system supports referenced taxa: yes

### Phase C — Referenced Shell Plan
- Input iNat candidates assessed: 198
- Mapped to existing canonical taxa: 42
- New shell plan records: 156
- Ambiguous taxa: 0
- Mode: dry_run (shells not yet created)

### Phase D — Priority Selection
- Missing-FR candidates ranked: 156
- Top candidates selected for FR seeding: 44
- FR ratio before selection: 50.1%
- FR ratio after priority seed set: 29.9%

### Sprint 13 Readiness
- Targets ready: 47
- Targets blocked: 3
- Targets missing localized names: 2
- Targets insufficient distractors: 1
- Candidates missing FR name: 112

## Sprint 12 vs Sprint 13 Comparison

| Metric | Sprint 12 | Sprint 13 | Delta |
|--------|-----------|-----------|-------|
| Targets ready | 39 | 47 | +8 |
| Targets blocked | 11 | 3 | -8 |
| Targets with >=3 FR-usable candidates | 39 | 47 | +8 |
| Missing French names | 156 | 112 | -44 |
| Shell candidates with FR seed | 0 | 44 | +44 |
| iNat usable candidate count | 119 | 201 | +82 |
| Emergency fallback count | 0 | 0 | 0 |
| Taxonomic-only dependency | 1 | 1 | 0 |

Comparison decision: READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE

## Final Decision

Decision label: **READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE**

See: docs/audits/distractor-relationships-v1-sprint13-persistence-decision.md

Full criteria assessment result: 6 PASS, 3 PARTIAL, 0 FAIL.

DistractorRelationship rows are not persisted in Sprint 13. Sprint 13 artifacts
serve as the source of truth for Sprint 14 first corpus gate or shell apply work.

## Remaining Blockers

- 44 provisional FR seeds must be replaced with correct French common names by
  human reviewers before any corpus-facing use (confidence=low, scientific name
  used as FR placeholder).
- 156 referenced taxon shells are planned but not yet created. Shell apply must
  complete before those relationships can have usable FR candidates.
- 112 candidates still lack a French name (29.9% of relationships).
- 3 targets remain blocked (2 missing localized names, 1 insufficient distractors).

## Recommended Sprint 14

A. Persist DistractorRelationship (if criteria 2, 8, 9 are cleared):
   Execute referenced shell apply plan (dry_run -> apply), replace 44 provisional
   FR seeds with reviewed names, re-run criteria assessment, then issue
   PERSIST_DISTRACTOR_RELATIONSHIPS_V1.

B. AI ranking / proposals dry-run (if relationships are stable):
   Use Sprint 13 projection artifacts as input to an AI-ranking dry-run for
   distractor candidate scoring. Does not require shell persistence to proceed.

C. First corpus distractor gate (recommended — enough targets are ready):
   Select >=30 targets from the 47 ready targets. Run first corpus distractor gate
   pipeline using distractor_readiness_v1_sprint13.json as source of truth.
   Gate validates real usability before committing to full persistence.

D. More referenced taxon and name completion (if still blocked):
   If human review of 44 FR seeds or shell apply is delayed, continue expanding
   FR name coverage for the remaining 112 missing-FR candidates. Prioritize
   candidates that would unblock the 3 still-blocked targets.
