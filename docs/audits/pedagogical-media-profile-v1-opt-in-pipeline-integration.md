---
owner: database
status: stable
last_reviewed: 2025-07-01
source_of_truth: docs/audits/pedagogical-media-profile-v1-opt-in-pipeline-integration.md
scope: audit
---

# pedagogical_media_profile_v1 — opt-in pipeline integration

**Status:** active  
**Sprint:** 5  
**Date:** 2025-07  

---

## Purpose

This document describes how `pedagogical_media_profile_v1` (PMP v1) is wired into
the qualification pipeline as an explicit opt-in AI review contract version.

---

## Selector

Activate PMP v1 by passing `--ai-review-contract-version pedagogical_media_profile_v1`
to either:

- `run-pipeline`
- `qualify-inat-snapshot`

Accepted aliases (normalised at runtime): `pmp_v1`, `pmp1`,
`pedagogical_media_profile_1`.

Default contract version is unchanged: `v1_1`.

---

## Pipeline routing

```
GeminiVisionQualifier.qualify()
  └─ if review_contract_version == "pedagogical_media_profile_v1"
       └─ _qualify_pedagogical_media_profile_v1()
            ├─ build prompt via build_pedagogical_media_profile_prompt_v1()
            ├─ call Gemini (JSON mode, MEDIA_RESOLUTION_HIGH)
            └─ parse via parse_pedagogical_media_profile_v1()
```

The method returns an `AIQualificationOutcome` with:

| Field | Value |
|---|---|
| `qualification` | always `None` — PMP does not produce `AIQualification` |
| `pedagogical_media_profile` | parsed PMP dict |
| `pedagogical_media_profile_score` | scores dict (if `review_status == "valid"`) |
| `bird_image_pedagogical_review` | always `None` (no cross-contamination) |
| `bird_image_pedagogical_score` | always `None` |
| `review_contract_version` | `"pedagogical_media_profile_v1"` |
| `prompt_version` | `"pedagogical_media_profile_prompt.v1"` |

---

## qualification=None — known limitation

Because PMP v1 does not emit the `AIQualification` envelope expected by the
existing qualification policies, resources processed under PMP v1 will have
`qualification=None`. This may cause them to be rejected by policies that require
a populated qualification. This is intentional and documented — do not silently
patch policies to accept `qualification=None`.

Runtime consumers must not treat PMP outcomes with `qualification=None` as
unqualified failures; they should check `review_contract_version` and read
`pedagogical_media_profile` and `pedagogical_media_profile_score` instead.

---

## Serialization contract

Both fields are included in `to_snapshot_payload` / `from_snapshot_payload`.
Old snapshots without these keys deserialize with `None` (backward compatible).

---

## Cached mode

`_validate_cached_outcome` passes through `pedagogical_media_profile` and
`pedagogical_media_profile_score` on prompt-version-mismatch outcomes.

`_infer_review_contract_version` recognises `"pedagogical_media_profile_prompt.v1"`
and returns `AI_REVIEW_CONTRACT_PMP_V1`, so cached PMP outcomes are correctly
attributed even when `review_contract_version` is missing.

---

## Files changed

| File | Change |
|---|---|
| `src/database_core/qualification/ai.py` | constant, resolver, dataclass fields, qualify routing, Gemini method, normalization passthrough, cached passthrough, prompt-version inference |
| `src/database_core/cli.py` | `--ai-review-contract-version` choices for both subcommands |
| `schemas/pedagogical_media_profile_v1.schema.json` | `neck` added to `body_part` enum |
| `src/database_core/qualification/pedagogical_media_profile_v1.py` | `neck` added to normalizer set |
| `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py` | `neck` added to prompt guidance |
| `tests/test_sprint5_pmp_pipeline.py` | 19 new integration tests (phases 1–5) |
