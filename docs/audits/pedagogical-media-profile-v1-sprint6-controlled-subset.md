---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint6-controlled-subset.md
scope: audit
---

# Sprint 6 controlled subset documentation

## Purpose

Document how the controlled Sprint 6 subset was derived from the larger
baseline snapshot, so later audits can interpret representativeness and
reproducibility correctly.

## Snapshot identifiers

- Source snapshot id: `palier1-be-birds-50taxa-run003-v11-baseline`
- Controlled snapshot id:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`

## Counts

- Source media count: 1493
- Selected media count: 120
- Kept taxa count: 36 (taxon seeds with at least one retained observation)

## Why 120 media

Sprint 6 targeted a controlled real run that remained:
- affordable,
- auditable by hand,
- representative enough to test PMP generation behavior,
- fast enough to iterate on audit quality.

A full 1493-media run was considered too large for this controlled stabilization
stage.

## Sampling method used

The subset was generated deterministically from source `manifest.json`:

1. Start from `media_downloads` items where `download_status == downloaded`.
2. Sort by `source_media_id` (ascending lexical order).
3. Keep the first 120 media entries.
4. Keep only response results whose primary photo id is in selected media ids.
5. Keep only taxon seeds whose filtered response still has at least one result.
6. Reset `ai_outputs_path` to null before the controlled run.

This method is deterministic by ordering; no random seed was used.

## Selection characteristics

- Selection axis: media id ordering.
- No taxa balancing objective.
- No quality-based prefilter besides existing download and pre-AI checks.
- No explicit evidence_type stratification at subset creation time.

## Limitations

- Not statistically representative of the entire 1493-media baseline.
- Possible ordering bias due to media id sort.
- Coverage per evidence_type is emergent, not controlled.
- Cost/latency characterization from this subset should not be extrapolated
  directly to broad corpus runs.

## Artifact paths

- Controlled subset root:
  `data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`
- Manifest:
  `data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120/manifest.json`
- Run output:
  `data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120/ai_outputs.json`

## Versioning and reproducibility status

The subset artifact is currently available in repository local data paths used by
Sprint 6 audits. Treat it as a controlled audit artifact, not as a runtime
serving surface.

A dedicated reusable subset-construction script is recommended before any next
controlled subset run, to avoid ad hoc recreation drift.
