---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/foundation/qualification-contracts-status.md
scope: foundation
---

# Qualification contracts status

This document clarifies the status and intended role of each AI qualification
contract so future work does not drift back toward legacy models.

---

## v1_1 — legacy default baseline

**Status:** `legacy_default_baseline`

**Selector:** `--ai-review-contract-version v1_1` (or omit the flag; this is the
current default)

**Role:**
- Current pipeline default until a PMP-specific qualification policy is ready.
- Rollback target if PMP integration regressions are detected.
- Historical baseline for palier-1 `50taxa` controlled snapshots.

**Not for new conceptual work.**
Do not design new qualification logic around v1_1.
Do not treat v1_1 output as the authoritative source of pedagogical signal.

---

## v1_2 — historical bird image review experiment

**Status:** `historical_experiment`

**Selector:** `--ai-review-contract-version v1_2`

**Role:**
- Historical experiment that surfaced why feedback and playability signals must
  not be mixed into media qualification.
- Retained as a legacy selectable contract for reference and backward compatibility.
- Not a design target for future work.

**Not for new work.**
Do not use v1_2 concepts (feedback fields, post_answer_feedback, selected_option_id)
as a reference when designing new qualification contracts.

---

## pedagogical_media_profile_v1 — canonical new path (opt-in)

**Status:** `canonical_new_path_opt_in`

**Selector:** `--ai-review-contract-version pedagogical_media_profile_v1`

**Prompt version:** `pedagogical_media_profile_prompt.v1`

**Role:**
- Canonical qualification contract for all new work.
- Designed from the start to be multi-taxon generic; current pipeline integration
  is bird-first (prompt hardcoded to `organism_group="bird"`).
- Not yet the default. Not yet production-validated at scale.
- Opt-in: must be explicitly selected via CLI flag.

**Current scope (Sprint 5):**
- Bird-only snapshots.
- Controlled sample runs using `palier1-be-birds-50taxa-run003-v11-baseline`.
- No materialization, no Supabase/Postgres writes by default.
- `qualification=None` in outcomes — this is intentional; legacy policies may
  reject resources. Do not silently patch this before Sprint 6 decision.

**Future scope:**
- Multi-taxon routing after controlled validation (separate sprint, out of scope
  until PMP valid_rate >= 90% sustained).
- PMP-specific qualification policy (not yet designed).

**Core doctrine:**
- database qualifies; downstream systems select.
- review validity is separate from media usefulness.
- weak usefulness is not failure.
- feather/nest/habitat/partial organism can be valid.
- AI provides qualitative signals; system computes deterministic scores.
- no feedback fields.
- no quiz/pack/runtime final selection fields.
- no taxonomic override or renaming.

---

## Decision tree for new work

```
Is this a new qualification concept?
  └─ YES → use pedagogical_media_profile_v1
       └─ Need a rollback baseline? → reference v1_1

Is this a historical palier-1 pipeline baseline audit?
  └─ YES → v1_1 baseline is fine for comparison

Is this referring to bird image review feedback/post-answer signal?
  └─ YES → this is v1_2 territory; do not replicate
```
