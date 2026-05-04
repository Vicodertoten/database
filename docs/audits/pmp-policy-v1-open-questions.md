---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-open-questions.md
scope: audit
---

# PMP policy v1 open questions

## Purpose

Track unresolved questions for PMP policy calibration after Sprint 8.

## Open questions

1. Should `species_card` require stricter thresholds than `basic_identification`
   for `whole_organism` evidence?
2. Is `field_observation` too broad as currently defined?
3. Should `confusion_learning` require future distractor availability before it
   is used in any quiz workflow?
4. Should `eligible` vs `borderline` thresholds differ by `evidence_type` and,
   later, by taxon group?
5. Should indirect evidence uses be promoted more explicitly for
   `feather` / `nest` / `habitat` media?
6. Should policy eventually produce separate corpus-readiness statuses?
7. What minimum taxon coverage is needed before selecting species-level learning
   packs?
8. How should human review disagreements be incorporated into threshold
   calibration?

## Current position

These are calibration questions only.
They do not justify runtime coupling, distractor implementation, or PMP contract
expansion in Sprint 8.
