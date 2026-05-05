---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv
scope: pmp_policy_v1_1_optional_signal_annotation
---

# PMP Policy v1.1 — Optional Signal Annotations README

## Purpose

This file documents the optional signal annotation sheet
`pmp_policy_v1_1_optional_signal_annotations.csv`, which records human-annotated
optional signals for selected broader_400 review items.

These signals are **optional inputs** to policy v1.1. They do not override taxonomy
or PMP schema. They do not expand the PMP schema. They are used to evaluate whether
policy v1.1's optional signal support behaves correctly on known-sensitive cases.

---

## Why These Signals Are Optional

Policy v1.1 can consume the following optional signals when they are present in the
PMP profile or injected at evaluation time:

- `target_taxon_visibility` — describes how clearly the target taxon is visible
- `contains_visible_answer_text` — flags images where species name text is visible
- `contains_ui_screenshot` — flags UI screenshots (e.g., identification app screens)
- `habitat_specificity` — (informational only; not directly consumed by policy v1.1)

These signals are **not** routinely produced by the Gemini PMP review prompt in its
current v1 form. They require either:
1. A future prompt expansion (not yet implemented), or
2. Manual human annotation (as in this sheet).

The purpose of this annotation sheet is to:
- Record known cases where optional signals would change policy outcomes,
- Enable delta audit to compare policy behavior with/without optional signals,
- Inform the second broader review sheet by pre-filling expected signals for
  targeted cases.

---

## Controlled Values

### `target_taxon_visibility`

| Value | Meaning |
|---|---|
| `clear_primary` | Target taxon clearly visible as main subject |
| `clear_secondary` | Target taxon visible but not main subject |
| `multiple_individuals_same_taxon` | Multiple individuals of the same taxon |
| `multiple_species_target_clear` | Multiple species, target taxon is identifiable |
| `multiple_species_target_unclear` | Multiple species, target is ambiguous |
| `target_not_visible` | Target taxon not visible |
| `unknown` | Not annotated or not determinable |

### `contains_visible_answer_text`

| Value | Meaning |
|---|---|
| `true` | Image contains visible text naming the species |
| `false` | No visible answer text |
| `unknown` | Not annotated |

### `contains_ui_screenshot`

| Value | Meaning |
|---|---|
| `true` | Image is a screenshot of a UI (e.g., identification app) |
| `false` | Not a UI screenshot |
| `unknown` | Not annotated |

### `habitat_specificity`

| Value | Meaning |
|---|---|
| `generic` | Habitat is generic (e.g., bird feeder, generic forest) |
| `species_relevant` | Habitat is species-relevant (specific nest, foraging site) |
| `unknown` | Not annotated |

---

## How to Annotate

1. Open the CSV in any spreadsheet tool.
2. For each row, review the image (via `local_image_path` or the broader_400 snapshot).
3. Fill in the signal values using the controlled vocabulary above.
4. Leave `unknown` if you are not sure.
5. Add any notes in `annotation_notes`.

**Do not** change `review_item_id`, `media_key`, `scientific_name`, `evidence_type`,
`current_policy_status`, or `current_recommended_uses` — these are fixed from the
source review.

---

## What These Signals Do NOT Do

- They do not override taxonomy decisions.
- They do not expand the PMP schema (no new schema fields are added in Sprint 9/10).
- They do not change runtime behavior.
- They do not affect the broader 400-item snapshot outputs in place.

---

## How Signals Are Used

### In the delta audit

The delta audit script (`scripts/audit_pmp_policy_v1_1_delta.py`) can optionally
inject these signals into the policy evaluation for specific items. This allows the
audit to show the "with optional signals" policy behavior compared to the base
policy behavior.

### In the second broader review sheet

The second review sheet (`scripts/export_pmp_policy_v1_1_second_review.py`) reads
this annotation sheet and includes signal values as pre-filled columns for annotated
items. Reviewers can then validate whether the expected policy effect matches what
they observe.

### In future migration decisions

If second review confirms that optional signals are reliable and improve policy
accuracy, a future sprint may:
1. Add these signals as optional fields to the PMP schema, or
2. Add automated detection (e.g., OCR for visible text, screenshot detection).

These are out of scope for Sprint 10.

---

## Current Annotation Status

Rows annotated: 19 (selected from broader_400 human review; covers all non-trivial
issue categories).

Rows not annotated: rows in the broader_400 snapshot that were not included in the
60-item human review, and control rows with `policy_accept` category (annotated
`unknown` by default as they require no signal intervention).
