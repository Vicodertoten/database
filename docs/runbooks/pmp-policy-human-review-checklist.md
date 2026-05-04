---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/runbooks/pmp-policy-human-review-checklist.md
scope: runbook
---

# PMP policy human review checklist

## Purpose

Optional Sprint 7 checklist to calibrate `pmp_qualification_policy.v1` with a
human reviewer (naturalist/domain reviewer).

This checklist is recommended, not mandatory for Sprint 7 completion.

## Sample size

Review 10 to 20 media from policy audit outputs:
- include whole_organism,
- include indirect evidence (feather/nest/habitat/track/scat/burrow),
- include partial_organism or multiple_organisms,
- include failed and pre-AI examples.

## Per-item review steps

1. Verify evidence type
- Does policy evidence type match visible evidence in media?

2. Verify visible evidence quality context
- Do visible field marks and limitations support the interpreted usage statuses?

3. Check usage score consistency
- Are usage scores coherent with the visible evidence type?

4. Check policy eligible uses
- Are `eligible_database_uses` reasonable?
- Is any recommended usage clearly too strict or too permissive?

5. Record reviewer decision
- `accept`
- `adjust`
- `reject`

6. Record notes
- threshold too high/low,
- evidence-type rule mismatch,
- missing rule candidate,
- false positive or false negative usage recommendation.

## Calibration outcomes

After 10 to 20 items, summarize:
- acceptance rate,
- top mismatch patterns,
- suggested threshold changes,
- suggested evidence-type logic changes.

## Guardrails

Do not turn this checklist into runtime logic.
Do not add runtime fields to PMP or policy outputs.
Do not conflate review validity with final selection decisions.
