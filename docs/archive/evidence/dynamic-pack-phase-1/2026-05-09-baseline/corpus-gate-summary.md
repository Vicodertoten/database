---
owner: database
status: stable
last_reviewed: 2026-05-09
source_of_truth: docs/archive/evidence/dynamic-pack-phase-1/2026-05-09-baseline/corpus-gate-summary.md
scope: dynamic_pack_phase_1_baseline_evidence
---

# Dynamic Pack Phase 1 Baseline - 2026-05-09

## Decision

`NO_GO` for the dynamic pack pool readiness baseline.

The current database remains valid for the Golden Pack MVP smoke contract, but
the audited BE corpus is not deep or locale-ready enough to serve dynamic
20-question sessions cleanly.

After this baseline, the first dynamic pack scope was updated to birds of
Belgium + France. This report remains the BE-only baseline and should not be
treated as the final BE+FR corpus gate.

## Evidence

- `phase2_playable_corpus_report.v1.json`
- `docs/archive/evidence/smoke-reports/postgres.smoke_report.v1.json`

## Scope

- Repo: `database`
- DB source: `.env` `DATABASE_URL`
- Mode: audit-only
- New ingestion: no
- Gemini qualification: no
- Runtime changes: no
- Schema migrations: no

## Key Metrics

| Metric | Value |
|---|---:|
| canonical taxa | 50 |
| source observations | 817 |
| media assets | 816 |
| qualified resources | 816 |
| exportable resources | 408 |
| BE exportable/playable items | 408 |
| BE exportable/playable taxa | 49 |
| target species | 50 |
| target playable images | 1000 |
| taxa with >= 20 BE exportable/playable images | 0 |
| qualification rejection rate | 0.5 |
| estimated AI-qualified images | 526 |
| estimated AI cost | EUR 0.6312 |
| question generation success rate | 0.0 |
| attribution completeness | 1.0 |
| country completeness on BE audit set | 1.0 |

## Locale Readiness

Strict common-name readiness on BE exportable/playable items:

| Locale | Ready |
|---|---:|
| fr | 0 / 408 |
| en | 392 / 408 |
| nl | 0 / 408 |

The effective French fallback used by existing audit code reaches `1.0`, but
strict FR/NL readiness is not acceptable for a future dynamic runtime surface.
Phase 1 should treat target and option labels in `fr`, `en`, and `nl` as blocking.

## Distribution Risk

The corpus is sparse and uneven:

- only `408` BE exportable/playable items exist for a `1000` image target;
- only `49` target taxa have BE exportable/playable coverage;
- no target taxon reaches `20` BE exportable/playable images;
- one accepted canonical taxon has `0` BE exportable/playable images:
  `taxon:birds:000045` / `Alauda arvensis`;
- several taxa have only `1` to `5` BE exportable/playable images.

## Interpretation

This is not a reason to create a new repository. The current `database`
architecture remains useful: canonical taxa, governance, qualification,
exportability, pack history, smoke reports, and audit tooling are already in
place.

The clean next move is a targeted BE+FR birds corpus rebuild or repair plan in a
DB/schema clone, not opportunistic gap filling. The plan should define candidate
volume per taxon, pre-AI dedup, strict locale completion, cost budget, and
acceptance gates before any new Gemini spending.

## Recommendation

Classify the DB posture as `targeted_rebuild`.

Do not implement `pack_pool.v1` yet. Phase 2 should wait until Phase 1 can show
either `GO` or an explicit `GO_WITH_WARNINGS` on product-scoped corpus readiness.
