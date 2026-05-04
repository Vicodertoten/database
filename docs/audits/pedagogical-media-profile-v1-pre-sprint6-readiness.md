---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-pre-sprint6-readiness.md
scope: audit
---

# Pre-Sprint-6 readiness — pedagogical_media_profile_v1

**Date:** 2026-05-04  
**Preceding sprint:** Sprint 5 (opt-in pipeline integration)  
**Next sprint:** Sprint 6 (controlled profiled snapshot run)

---

## Purpose

This readiness pass prepares the repository for Sprint 6.
It does **not** run the controlled snapshot. It ensures that:

- Sprint 5 documentation dates are correct.
- Qualification contract statuses are clearly documented.
- Bird-first scope is explicit.
- Neck body_part validation is fully tested at schema level.
- `qualification=None` doctrine is explicitly preserved in tests.
- CLI selector coverage is verified.
- Sprint 6 plan is actionable.

---

## Scope of changes

### 1. Sprint 5 documentation date corrections

Files corrected:

- `docs/audits/pedagogical-media-profile-v1-sprint5-closure.md`:
  `last_reviewed` and body date corrected from `2025-07` to `2026-05`.

- `docs/audits/pedagogical-media-profile-v1-opt-in-pipeline-integration.md`:
  `last_reviewed` and body date corrected from `2025-07` to `2026-05`.

### 2. Qualification contracts status document

Created: `docs/foundation/qualification-contracts-status.md`

Clarifies the role of each contract:

| Contract | Status | Role |
|---|---|---|
| `v1_1` | `legacy_default_baseline` | Current default; rollback; historical baseline |
| `v1_2` | `historical_experiment` | Bird image review experiment; not for new work |
| `pedagogical_media_profile_v1` | `canonical_new_path_opt_in` | Canonical new path; bird-first; not yet default |

Linked from `docs/README.md`.

### 3. Bird-first scope clarification

Added explicit note to
`docs/audits/pedagogical-media-profile-v1-opt-in-pipeline-integration.md`:

- PMP contract is multi-taxon generic by design.
- Current pipeline integration (`_qualify_pedagogical_media_profile_v1`) is
  bird-first: `organism_group="bird"` is hardcoded.
- Sprint 6 must use a bird-only controlled snapshot.
- Multi-taxon routing is explicitly out of scope.

### 4. Neck schema validation test

Added to `tests/test_sprint5_pmp_pipeline.py`:

`test_full_valid_pmp_profile_with_neck_field_mark_passes_validation`

This is a full contract-level test (not just normalizer). A complete valid PMP
payload with `identification_profile.visible_field_marks[].body_part = "neck"`
is passed through `parse_pedagogical_media_profile_v1` and must return
`review_status == "valid"`.

### 5. PMP qualification=None doctrine preservation test

Added to `tests/test_sprint5_pmp_pipeline.py`:

`test_pmp_valid_gemini_outcome_has_qualification_none`

Asserts that a valid PMP Gemini outcome returns `qualification=None`, and that
`pedagogical_media_profile` is populated and `bird_image_*` fields are `None`.

### 6. CLI selector coverage

Extracted `_build_argument_parser()` from `main()` in `src/database_core/cli.py`
to allow testable CLI parser access without invoking `main()`.

Added two tests to `tests/test_sprint5_pmp_pipeline.py`:

- `test_cli_qualify_inat_snapshot_accepts_pmp_selector`
- `test_cli_run_pipeline_accepts_pmp_selector`

Both verify that `--ai-review-contract-version pedagogical_media_profile_v1`
is accepted by the respective subcommand parser.

### 7. Sprint 6 plan

Created: `docs/audits/pedagogical-media-profile-v1-sprint6-plan.md`

Defines:
- Objective and scope
- Recommended command
- Metrics to collect (generation, scores, policy/legacy, operational)
- Critical distinction: PMP generation success vs. legacy policy effects
- Decision labels with thresholds
- Non-goals

---

## Validation

Validated on 2026-05-04 against commit `db50a13`.

### Tests

```bash
./.venv/bin/python -m pytest \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_sprint5_pmp_pipeline.py \
  tests/test_ai.py \
  tests/test_inat_qualification.py \
  tests/test_inat_snapshot.py \
  -q
```

Result: **127 passed** (23 tests in `test_sprint5_pmp_pipeline.py`).

### Ruff

```bash
./.venv/bin/python -m ruff check \
  src/database_core/qualification/pedagogical_media_profile_v1.py \
  src/database_core/qualification/pedagogical_media_profile_prompt_v1.py \
  src/database_core/qualification/ai.py \
  src/database_core/cli.py \
  src/database_core/adapters/inaturalist_qualification.py \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_sprint5_pmp_pipeline.py
```

Result: **no errors**.

### Docs hygiene and coherence

```bash
./.venv/bin/python scripts/check_docs_hygiene.py
./.venv/bin/python scripts/check_doc_code_coherence.py
```

Result: **both passed**.

### verify_repo

```bash
./.venv/bin/python scripts/verify_repo.py
```

Result: **"Repository verification complete" — all checks passed**.

---

## Residual risks

- `qualification=None` in PMP outcomes will be rejected by existing legacy
  qualification policies. This is expected and documented. Do not patch before
  Sprint 6 decision.
- No live Gemini call was made in this readiness pass. Sprint 6 is the first
  real-traffic validation.
- Multi-taxon routing is not implemented; bird-only scope enforced by prompt
  hardcoding.

---

## Final decision

**`READY_FOR_SPRINT_6_CONTROLLED_PROFILED_SNAPSHOT_RUN`**

All acceptance criteria are met:

- ✅ Sprint 5 documentation dates corrected
- ✅ Qualification contract statuses documented and linked
- ✅ PMP documented as canonical new path for new work, still opt-in
- ✅ v1_1/v1_2 documented as legacy/historical
- ✅ Bird-first scope explicit in pipeline integration doc
- ✅ Full PMP validation test with neck field mark passes
- ✅ PMP `qualification=None` doctrine explicitly preserved in test
- ✅ CLI selector coverage verified by tests
- ✅ Sprint 6 plan exists and is actionable
- ✅ No runtime changes
- ✅ No materialization
- ✅ No default behavior change
- ✅ No PMP-specific policy yet

---

## Next step

Execute Sprint 6: run the controlled profiled snapshot using the command in
`docs/audits/pedagogical-media-profile-v1-sprint6-plan.md`.
