---
owner: database
status: in_progress
last_reviewed: 2026-05-05
source_of_truth: docs/audits/pmp-policy-v1-open-questions.md
scope: audit
---

# PMP policy v1 open questions

## Purpose

Track unresolved questions for PMP policy calibration.
Updated after Sprint 9 Phase 1 (broader-400 human review analysis).

## Open questions — from Sprint 8

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

## Open questions — added from broader-400 human review (Sprint 9 Phase 1)

9. How should same-species multiple individuals in a single frame be formally
   treated in PMP policy? Current evidence: human reviewers consider it
   acceptable or even rich context. Candidate rule: same-species multi-individual
   = no penalty; target identity is clear.

10. How should mixed-species frames with an unclear target individual be handled?
    Current evidence: reviewers flag ambiguity and cannot determine which
    individual corresponds to the labeled taxon. Candidate: add
    `target_taxon_visibility` field to PMP or a policy downgrade rule.

11. Should `target_taxon_visibility` become an explicit PMP field or remain a
    policy-layer rule? Policy-layer rule is simpler; PMP field is more
    expressive but expands contract.

12. How should visible species name text or app screenshot images be detected
    and handled? Current evidence: at least one screenshot of an audio-ID app
    with species name visible passed qualification. Candidate: add a pre-AI or
    PMP-level rejection criterion for text overlay / answer visible.

13. How strict should habitat evidence be for `field_observation` eligibility?
    Current evidence: one image of a bird feeder (no organism) was flagged as
    impossible to link to a specific species. Candidate: require minimum
    ecological specificity for habitat images to qualify for `field_observation`.

14. Should `species_card` eligibility require minimum clarity / proximity
    conditions? Current evidence: at least one distant silhouette was flagged
    as odd for `species_card`. Candidate: add a minimum score threshold.

15. Is `field_observation` intentionally broad or too permissive? Current
    evidence: most cases are accepted. A few reviewers noted it could apply
    to more use cases (score_too_low direction). No over-permissiveness
    pattern found beyond one case.

16. Should pre-AI image size / resolution thresholds be slightly lowered?
    Current evidence: one pre-AI-rejected image was considered borderline-OK
    by reviewer. Candidate: minor threshold relaxation without new status
    classes. Low priority.

17. How should rare model-subject-miss cases be tracked without
    over-complexifying the pipeline? Current evidence: one image with
    `evidence_type=unknown` where a reviewer can see a very distant bird.
    Candidate: `needs_second_review` flag; no new policy category needed.

## Current position

Questions 1–8 are carry-overs from Sprint 8: calibration questions only.
Questions 9–17 are raised by broader-400 human review evidence.
None justify runtime coupling, distractor implementation, or PMP contract
expansion at this stage.
Sprint 9 Phase 2 will produce targeted patch proposals for questions 9, 10,
12, 13, 14.
