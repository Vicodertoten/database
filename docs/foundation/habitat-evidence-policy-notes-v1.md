---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/habitat-evidence-policy-notes-v1.md
scope: foundation
---

# Habitat evidence policy notes v1

## Purpose

Clarify how `habitat` evidence should be interpreted in PMP policy calibration.

## Core position

`habitat` is valid evidence, but it is stricter than `feather`, `nest`, or
`dead_organism` for species-level pedagogical use.

Reason:
- generic habitat often says little about the exact taxon;
- species-relevant signs can still be useful when the ecological trace is strong.

## Generic habitat: weak species-level evidence

Examples:
- generic garden context,
- feeder only,
- environmental scene only,
- no organism present,
- no species-relevant sign.

Policy implication:
- do not over-promote generic habitat into `indirect_evidence_learning`;
- `field_observation` can remain broad context in some cases,
  but species-level learning should stay cautious.

## Species-relevant habitat signs: acceptable when strong

Examples:
- woodpecker foraging damage,
- burrow or cavity evidence,
- nest site with clear ecological trace,
- distinctive species-relevant environmental sign.

Policy implication:
- `indirect_evidence_learning` may remain eligible when the signal is explicit
  and the score is high enough.

## v1.1 calibration rule

Sprint 9 Phase 2 uses a conservative rule:
- `habitat` indirect evidence requires a higher bar for eligibility;
- generic habitat is downgraded;
- species-relevant habitat signs can remain eligible when strongly supported.

This note does not change runtime behavior and does not materialize packs.
