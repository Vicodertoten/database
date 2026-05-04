---
owner: database
status: stable
last_reviewed: 2025-07-01
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint5-closure.md
scope: audit
---

# Sprint 5 closure — pedagogical_media_profile_v1 opt-in integration

**Sprint:** 5  
**Status:** closed  
**Date:** 2025-07  

---

## Summary

Sprint 5 wires `pedagogical_media_profile_v1` into the qualification pipeline
as an opt-in AI review contract version, behind the selector
`--ai-review-contract-version pedagogical_media_profile_v1`.

`v1_1` remains the default. `v1_2` is unaffected.

---

## Phases completed

| Phase | Description | Status |
|---|---|---|
| 1 | Add `neck` to body_part enum (schema, normalizer, prompt) | ✅ |
| 2 | Add `AI_REVIEW_CONTRACT_PMP_V1` constant, resolver aliases, CLI choices | ✅ |
| 3 | Add `pedagogical_media_profile` / `pedagogical_media_profile_score` to `AIQualificationOutcome` | ✅ |
| 4 | Implement `GeminiVisionQualifier._qualify_pedagogical_media_profile_v1()` | ✅ |
| 5 | Wire PMP fields through `_normalize_qualification_outcome_from_qualifier`, `_validate_cached_outcome`, `_infer_review_contract_version` | ✅ |
| 6 | Integration audit docs | ✅ |

---

## Tests

19 new tests in `tests/test_sprint5_pmp_pipeline.py` covering:
- Phase 1: `neck` normalizer and prompt
- Phase 2: selector resolution, aliases, backward compatibility
- Phase 3: PMP outcome serialization round-trip (valid, failed, old payloads, v1_2 isolation)
- Phase 4: Gemini PMP path (mocked — valid, failed, no bird_image pollution)
- Phase 5: cached pipeline routing (PMP pass-through, v1_1 unchanged)

All 81 pre-existing tests continue to pass.

---

## Hard doctrine observed

- `qualification=None` for PMP outcomes is intentional and documented.
- `bird_image_pedagogical_review` and `bird_image_pedagogical_score` are never
  populated by the PMP path.
- No runtime session/scoring logic was introduced.
- No canonical identity fields were mutated.
- Default contract version was not changed.

---

## Residual risks

- Resources processed under PMP v1 will be rejected by existing qualification
  policies that require `qualification != None`. This is expected and documented.
  Downstream policy adaptation is out of scope for Sprint 5.
- No live pipeline run was performed in this sprint. The first live test with
  real Gemini calls is the next operational step.

---

## Next steps

1. Run `qualify-inat-snapshot --ai-review-contract-version pedagogical_media_profile_v1`
   against a small iNaturalist batch to validate end-to-end output.
2. Decide whether to introduce a PMP-specific qualification policy (separate sprint).
