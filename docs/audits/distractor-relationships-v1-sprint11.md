---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-relationships-v1-sprint11.md
scope: sprint_closure
---

# Distractor Relationships V1 — Sprint 11 Closure

## Phases Completed

| Phase | Title | Status |
|---|---|---|
| Phase 1 | DistractorRelationship domain foundation | ✓ complete |
| Phase 2 | Current-state audit | ✓ complete |
| Phase 3 | Candidate relationship generation | ✓ complete |
| Phase 4 | AI pedagogical proposal strategy | ✓ complete |
| Phase 5 | Distractor readiness synthesis | ✓ complete |

---

## Files Created / Modified

### Domain

| File | Change |
|---|---|
| `src/database_core/domain/enums.py` | Added 7 new enum classes: `DistractorRelationshipSource`, `DistractorRelationshipStatus`, `CandidateTaxonRefType`, `DistractorConfusionType`, `DistractorLearnerLevel`, `DistractorPedagogicalValue`, `DistractorDifficultyLevel` |
| `src/database_core/domain/models.py` | Added `DistractorRelationship` model with full validation |

### Schemas

| File | Change |
|---|---|
| `schemas/distractor_relationship_v1.schema.json` | New — strict JSON schema for DistractorRelationship |
| `schemas/distractor_ai_proposal_v1.schema.json` | New — strict JSON schema for AI proposal output |

### Docs

| File | Change |
|---|---|
| `docs/foundation/distractor-relationships-v1.md` | New — domain foundation doc |
| `docs/foundation/distractor-ai-proposals-v1.md` | New — AI proposal contract + prompt draft |
| `docs/audits/distractor-relationships-v1-current-state-audit.md` | New — Phase 2 audit report |
| `docs/audits/distractor-relationship-candidates-v1.md` | New — Phase 3 candidate report |
| `docs/audits/distractor-readiness-v1.md` | New — Phase 5 readiness synthesis |
| `docs/audits/distractor-relationships-v1-sprint11.md` | New — this closure doc |

### Scripts

| File | Change |
|---|---|
| `scripts/audit_distractor_relationships_v1_current_state.py` | New — Phase 2 audit script |
| `scripts/generate_distractor_relationship_candidates_v1.py` | New — Phase 3 candidate generator |
| `scripts/build_distractor_readiness_v1.py` | New — Phase 5 readiness synthesiser |

### Evidence (generated artefacts)

| File | Change |
|---|---|
| `docs/audits/evidence/distractor_v1_current_state_audit.json` | New — Phase 2 output |
| `docs/audits/evidence/distractor_relationship_candidates_v1.json` | New — Phase 3 output |
| `docs/audits/evidence/distractor_readiness_v1.json` | New — Phase 5 output |

### Tests

| File | Change |
|---|---|
| `tests/test_distractor_relationship_model.py` | New — 14 tests |
| `tests/test_audit_distractor_relationships_v1_current_state.py` | New — 11 tests |
| `tests/test_generate_distractor_relationship_candidates_v1.py` | New — 13 tests |
| `tests/test_distractor_ai_proposal_schema.py` | New — 13 tests |
| `tests/test_build_distractor_readiness_v1.py` | New — Phase 5 tests |

---

## Tests Run

```
./.venv/bin/python -m pytest \
  tests/test_build_distractor_readiness_v1.py \
  tests/test_generate_distractor_relationship_candidates_v1.py \
  tests/test_audit_distractor_relationships_v1_current_state.py \
  tests/test_distractor_relationship_model.py \
  tests/test_distractor_ai_proposal_schema.py \
  -q
```

All tests pass. Ruff clean. Docs hygiene clean (except pre-existing `.DS_Store`).

---

## Key Metrics

| Metric | Value |
|---|---|
| Target taxa (snapshot) | 50 |
| Total candidate relationships generated | 244 (with `--include-same-order`) |
| iNaturalist similar-species hints | 0 |
| Same-genus candidates | 8 |
| Same-family candidates | 66 |
| Same-order candidates | 170 |
| Targets with ≥3 candidates | 26 / 50 |
| Targets with ≥3 FR-usable candidates | 0 / 50 |
| Unresolved candidates | 0 |
| Referenced taxon shells needed | 0 |
| Candidates missing French name | 43 |
| Targets ready for first corpus gate | 0 |
| Targets blocked | 50 |

---

## Open Questions

1. **iNat enrichment**: The `similar_taxa` field is empty for all 50 taxa in the current
   snapshot. When will the iNat enrichment pass populate it?
   This is the highest-priority blocker for quality distractor coverage.

2. **French names**: The normalized dataset currently only has English names.
   French (and Dutch) names must be sourced — from iNat, Wikidata, or manual entry.
   This is the second blocker for the first Belgian/francophone corpus gate.

3. **referenced_taxa**: The export bundle has 0 referenced taxa. Should referenced taxon
   shells be created for candidate taxa that are not in the 50 canonical taxa?
   (Currently all 44 unique candidate taxa are canonical — this may change after iNat enrichment.)

4. **AI ranking dry-run**: Phase 4 defines the AI proposal contract but does not run it.
   Should Sprint 12 include a dry-run AI ranking pass over existing taxonomic candidates?

5. **Region filtering**: Currently not applied at the relationship layer.
   Should a Belgian-region filter be applied at the pack-compilation layer instead?

---

## Final Decision

**`NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS`**

The domain foundation, audit infrastructure, and candidate generation pipeline are fully
operational. The blocking gap is the absence of iNaturalist similar-species hints and
French common names in the normalized dataset.

No relationships have been persisted to Postgres. No runtime or pack changes have been made.

---

## Recommended Sprint 12

### Option A — iNat enrichment + referenced taxon harvest + persistence (recommended)

1. Trigger iNaturalist similar-species enrichment for all 50 targets.
2. Re-run `generate_distractor_relationship_candidates_v1.py` after enrichment.
3. Harvest or manually populate French (fr) and Dutch (nl) names for candidate taxa.
4. Create referenced taxon shell records for any candidates not yet in the canonical pool.
5. Persist `DistractorRelationship` candidate records to the database (first write phase).
6. Re-run `build_distractor_readiness_v1.py` to verify gate readiness.

### Option B — AI ranking/proposals dry-run

1. Run AI pedagogical proposal against targets with ≥1 but <3 candidates.
2. Validate AI output against `distractor_ai_proposal_v1.schema.json`.
3. Promote high-confidence AI-proposed candidates to `DistractorRelationship` with
   `source = ai_pedagogical_proposal` and `status = needs_review`.
4. Do not persist until human review.

### Option C — First corpus distractor gate (blocked until A or B)

Not yet unblocked. Requires at least 3 FR-usable candidates per target.

**Recommended path: Option A first, then reassess for B or C.**
