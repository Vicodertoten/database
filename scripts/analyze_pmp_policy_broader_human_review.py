"""
Analyze the broader_400 PMP policy human review sheet.

Input:
    docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sheet.csv

Outputs:
    docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json
    docs/audits/pmp-policy-v1-broader-400-human-review-analysis.md
    docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INPUT_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_broader_400_20260504_human_review_sheet.csv"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "docs/audits/evidence"
    / "pmp_policy_v1_broader_400_20260504_human_review_analysis.json"
)
OUTPUT_MD = (
    REPO_ROOT
    / "docs/audits"
    / "pmp-policy-v1-broader-400-human-review-analysis.md"
)
OUTPUT_LABELED_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_broader_400_20260504_human_review_labeled.csv"
)

VALID_JUDGMENTS = {"accept", "too_strict", "too_permissive", "reject", "unclear", "blank"}

VALID_ISSUE_CATEGORIES = {
    "policy_accept",
    "schema_false_negative",
    "pre_ai_borderline",
    "target_taxon_visibility_issue",
    "multiple_species_target_unclear",
    "same_species_multiple_individuals_ok",
    "text_overlay_or_answer_visible",
    "habitat_too_permissive",
    "species_card_too_permissive",
    "field_observation_too_permissive",
    "score_too_high",
    "score_too_low",
    "evidence_type_wrong",
    "field_marks_wrong",
    "rare_model_subject_miss",
    "needs_second_review",
    "unclear",
    "other",
}

# Keywords for inference
_SAME_SPECIES_KW = [
    "meme espèce",
    "même espèce",
    "meme taxon",
    "même taxon",
    "same species",
    "same taxon",
    "pas un problème",
    "not a problem",
    "riche",
    "plusieurs individus mais pas",
    "deux individus de la meme",
    "deux individus de la même",
]
_MULTI_SPECIES_KW = [
    "espèces différentes",
    "especes differentes",
    "multi espèces",
    "multi-espèces",
    "multiple species",
    "different species",
    "plusieurs espèces",
    "differentes",
    "target unclear",
    "bordel",
    "on ne sait pas",
    "on doit préciser",
    "differents",
    "différents",
    "espèces diff",
    "especes diff",
]
_TEXT_OVERLAY_KW = [
    "screenshot",
    "écran",
    "ecran",
    "nom de l'espèce",
    "nom de l espèce",
    "identification par le son",
    "name visible",
    "species name",
    "nom de l'espece",
    "l'espèce en clair",
    "l espece en clair",
]
_HABITAT_GENERIC_KW = [
    "impossible de savoir",
    "impossible to know",
    "generic",
    "générique",
    "generique",
    "jardin",
    "mangeoire",
    "feeder",
    "garden",
    "on ne peut pas",
    "score horrible",
]
_MODEL_MISS_KW = [
    "very distant",
    "extremly",
    "hardly",
    "falcon",
    "hard but",
    "extremely",
    "peregrine",
    "far away",
]
_GOOD_IMAGE_KW = [
    "bonne image",
    "bonne photo",
    "bonne espèce",
    "très bonne",
    "tres bonne",
    "clairement ok",
    "clairement utilisable",
    "utilisable",
    "à garder",
    "a garder",
    "voir pourquoi",
    "clearly ok",
    "usable",
    "good image",
    "good photo",
    "ok",
]
_SPECIES_CARD_CONCERN_KW = [
    "bizzare",
    "bizarre",
    "species card",
    "species_card",
    "weird",
    "étrange",
    "etrange",
    "oui a species card",
    "dire oui a species",
]


def normalize_judgment(raw: str) -> str:
    """Normalize reviewer_overall_judgment to controlled enum."""
    if not raw or not raw.strip():
        return "blank"
    v = raw.strip().lower()
    # collapse multiple underscores, spaces → single underscore
    v = re.sub(r"[\s_]+", "_", v)
    mapping = {
        "accept": "accept",
        "too_strict": "too_strict",
        "too_permissive": "too_permissive",
        "too_permisive": "too_permissive",
        "reject": "reject",
        "unclear": "unclear",
        "blank": "blank",
    }
    return mapping.get(v, "unclear")


def clean_notes(raw: str) -> str:
    """Strip and normalize whitespace from reviewer notes."""
    if not raw:
        return ""
    return " ".join(raw.strip().split())


def _notes_contain(notes_lower: str, keywords: list[str]) -> bool:
    return any(kw in notes_lower for kw in keywords)


def infer_issue_category(row: dict) -> str:
    """Infer human_issue_category from row data."""
    review_focus = row.get("review_focus", "")
    policy_status = row.get("policy_status", "")
    evidence_type = row.get("evidence_type", "")
    judgment = row["reviewer_overall_judgment_normalized"]
    notes = row.get("reviewer_notes_cleaned", "").lower()
    recommended_uses = row.get("recommended_uses", "")

    # 1. schema_false_negative: profile_failed + human says image is good/usable
    if policy_status == "profile_failed":
        if judgment in ("too_strict",) or _notes_contain(notes, _GOOD_IMAGE_KW):
            return "schema_false_negative"
        if judgment == "blank" and review_focus == "schema_or_profile_failure":
            return "schema_false_negative"

    # 2. pre_ai_borderline
    if policy_status == "pre_ai_rejected" or review_focus == "pre_ai_rejected":
        return "pre_ai_borderline"

    # 3. text_overlay_or_answer_visible (check before others — high priority)
    if _notes_contain(notes, _TEXT_OVERLAY_KW):
        return "text_overlay_or_answer_visible"

    # 4. rare_model_subject_miss: AI saw no subject but human notes a bird
    if evidence_type == "unknown" and _notes_contain(notes, _MODEL_MISS_KW):
        return "rare_model_subject_miss"

    # 5. multiple_organisms cases
    if evidence_type == "multiple_organisms":
        has_same = _notes_contain(notes, _SAME_SPECIES_KW)
        has_diff = _notes_contain(notes, _MULTI_SPECIES_KW)
        if has_same and not has_diff:
            return "same_species_multiple_individuals_ok"
        if has_diff:
            return "multiple_species_target_unclear"
        # no note: default by judgment
        if judgment == "accept":
            return "same_species_multiple_individuals_ok"
        return "multiple_species_target_unclear"

    # 6. habitat_too_permissive
    if evidence_type == "habitat" and _notes_contain(notes, _HABITAT_GENERIC_KW):
        return "habitat_too_permissive"

    # 7. species_card_too_permissive
    if "species_card" in recommended_uses and _notes_contain(notes, _SPECIES_CARD_CONCERN_KW):
        return "species_card_too_permissive"

    # 8. field_observation_too_permissive or score_too_low
    if judgment == "too_strict" and review_focus == "field_observation_vs_identification":
        return "field_observation_too_permissive"

    # 9. accept with no concern
    if judgment == "accept":
        return "policy_accept"

    # 10. unclear judgment
    if judgment == "unclear":
        return "unclear"

    # 11. blank judgment
    if judgment == "blank":
        return "needs_second_review"

    # 12. too_permissive without category above
    if judgment == "too_permissive":
        return "score_too_high"

    # 13. too_strict without category above
    if judgment == "too_strict":
        return "score_too_high"

    return "other"


def assign_calibration_priority(row: dict) -> str:
    """Assign calibration priority based on issue category and context."""
    cat = row.get("human_issue_category", "")
    review_priority = row.get("review_priority", "")

    high_cats = {
        "schema_false_negative",
        "multiple_species_target_unclear",
        "text_overlay_or_answer_visible",
    }
    medium_cats = {
        "pre_ai_borderline",
        "habitat_too_permissive",
        "species_card_too_permissive",
        "field_observation_too_permissive",
        "same_species_multiple_individuals_ok",
        "rare_model_subject_miss",
        "needs_second_review",
        "unclear",
        "score_too_high",
        "score_too_low",
    }

    if cat in high_cats:
        return "high"
    if cat in medium_cats:
        return "medium"
    if review_priority == "high":
        return "medium"
    return "low"


def assign_calibration_action_hint(row: dict) -> str:
    """Return a short hint for follow-up action."""
    cat = row.get("human_issue_category", "")
    hints = {
        "policy_accept": "no action",
        "schema_false_negative": "investigate profile_failed root cause; potential schema fix",
        "pre_ai_borderline": "consider slight relaxation of image size/resolution threshold",
        "same_species_multiple_individuals_ok": (
            "formalize same-species multi-individual policy rule"
        ),
        "multiple_species_target_unclear": (
            "add target_taxon_visibility field to PMP or policy"
        ),
        "text_overlay_or_answer_visible": (
            "add detection rule or rejection criterion for text overlay"
        ),
        "habitat_too_permissive": "review habitat evidence thresholds; tighten scoring",
        "species_card_too_permissive": "tighten species_card threshold or add conditions",
        "field_observation_too_permissive": "review field_observation score thresholds",
        "score_too_high": "review score thresholds for this evidence_type",
        "score_too_low": "review score lower bounds",
        "evidence_type_wrong": "investigate AI evidence_type classification errors",
        "field_marks_wrong": "investigate visible_field_marks quality",
        "rare_model_subject_miss": "note for second review; low priority new category",
        "needs_second_review": "flag for second human review pass",
        "unclear": "flag for adjudication",
        "target_taxon_visibility_issue": "define target_taxon_visibility policy",
        "other": "manual triage",
    }
    return hints.get(cat, "manual triage")


PRIORITY_LIST_FIELDS = [
    "review_item_id",
    "local_image_path",
    "scientific_name",
    "common_name_en",
    "evidence_type",
    "policy_status",
    "recommended_uses",
    "borderline_uses",
    "blocked_uses",
    "reviewer_overall_judgment_normalized",
    "reviewer_notes",
    "human_issue_category",
    "calibration_action_hint",
]


def _extract_priority_list(rows: list[dict], category: str) -> list[dict]:
    return [
        {k: r.get(k, "") for k in PRIORITY_LIST_FIELDS}
        for r in rows
        if r.get("human_issue_category") == category
    ]


def _dist(rows: list[dict], key: str) -> dict[str, int]:
    return dict(Counter(r.get(key, "") for r in rows))


def _cross_dist(rows: list[dict], group_key: str, value_key: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        g = r.get(group_key, "")
        v = r.get(value_key, "")
        result[g][v] += 1
    return {g: dict(d) for g, d in result.items()}


def _top_taxa(rows: list[dict], n: int = 10) -> list[dict]:
    counts = Counter(r.get("scientific_name", "") for r in rows)
    return [{"scientific_name": name, "count": cnt} for name, cnt in counts.most_common(n)]


def _taxa_with_issues(rows: list[dict]) -> list[dict]:
    taxon_issues: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        cat = r.get("human_issue_category", "")
        if cat not in ("policy_accept", ""):
            taxon_issues[r.get("scientific_name", "")][cat] += 1
    result = []
    for taxon, counter in sorted(taxon_issues.items(), key=lambda x: -sum(x[1].values())):
        result.append({"scientific_name": taxon, "issues": dict(counter)})
    return result


def run(
    input_csv: Path = INPUT_CSV,
    output_json: Path = OUTPUT_JSON,
    output_md: Path = OUTPUT_MD,
    output_labeled_csv: Path = OUTPUT_LABELED_CSV,
) -> dict:
    """Run the full analysis. Returns the evidence dict."""
    rows = []
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))

    total_rows = len(rows)
    rows_with_review = 0
    rows_with_notes = 0

    for row in rows:
        raw_j = row.get("reviewer_overall_judgment", "")
        raw_n = row.get("reviewer_notes", "")
        row["reviewer_overall_judgment_normalized"] = normalize_judgment(raw_j)
        row["reviewer_notes_cleaned"] = clean_notes(raw_n)
        if row["reviewer_overall_judgment_normalized"] != "blank":
            rows_with_review += 1
        if row["reviewer_notes_cleaned"]:
            rows_with_notes += 1
        row["human_issue_category"] = infer_issue_category(row)
        row["calibration_priority"] = assign_calibration_priority(row)
        row["calibration_action_hint"] = assign_calibration_action_hint(row)

    # --- labeled CSV ---
    output_labeled_csv.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fieldnames = list(rows[0].keys())
        with open(output_labeled_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    # --- evidence JSON ---
    evidence = {
        "input_file": str(input_csv.relative_to(REPO_ROOT)),
        "generated_at": date.today().isoformat(),
        "total_rows": total_rows,
        "rows_with_review_judgment": rows_with_review,
        "rows_with_notes": rows_with_notes,
        "normalized_judgment_distribution": _dist(rows, "reviewer_overall_judgment_normalized"),
        "issue_category_distribution": _dist(rows, "human_issue_category"),
        "calibration_priority_distribution": _dist(rows, "calibration_priority"),
        "review_focus_distribution": _dist(rows, "review_focus"),
        "issue_category_by_review_focus": _cross_dist(
            rows, "review_focus", "human_issue_category"
        ),
        "normalized_judgment_by_review_focus": _cross_dist(
            rows, "review_focus", "reviewer_overall_judgment_normalized"
        ),
        "policy_status_distribution": _dist(rows, "policy_status"),
        "issue_category_by_policy_status": _cross_dist(
            rows, "policy_status", "human_issue_category"
        ),
        "normalized_judgment_by_policy_status": _cross_dist(
            rows, "policy_status", "reviewer_overall_judgment_normalized"
        ),
        "evidence_type_distribution": _dist(rows, "evidence_type"),
        "issue_category_by_evidence_type": _cross_dist(
            rows, "evidence_type", "human_issue_category"
        ),
        "normalized_judgment_by_evidence_type": _cross_dist(
            rows, "evidence_type", "reviewer_overall_judgment_normalized"
        ),
        "taxa_count": len({r.get("scientific_name", "") for r in rows}),
        "top_taxa_by_review_count": _top_taxa(rows),
        "issue_category_by_scientific_name": _cross_dist(
            rows, "scientific_name", "human_issue_category"
        ),
        "taxa_with_repeated_issues": _taxa_with_issues(rows),
        "schema_false_negative_items": _extract_priority_list(
            rows, "schema_false_negative"
        ),
        "pre_ai_borderline_items": _extract_priority_list(rows, "pre_ai_borderline"),
        "multiple_species_target_unclear_items": _extract_priority_list(
            rows, "multiple_species_target_unclear"
        ),
        "same_species_multiple_individuals_ok_items": _extract_priority_list(
            rows, "same_species_multiple_individuals_ok"
        ),
        "text_overlay_or_answer_visible_items": _extract_priority_list(
            rows, "text_overlay_or_answer_visible"
        ),
        "habitat_too_permissive_items": _extract_priority_list(
            rows, "habitat_too_permissive"
        ),
        "species_card_too_permissive_items": _extract_priority_list(
            rows, "species_card_too_permissive"
        ),
        "field_observation_too_permissive_items": _extract_priority_list(
            rows, "field_observation_too_permissive"
        ),
        "rare_model_subject_miss_items": _extract_priority_list(
            rows, "rare_model_subject_miss"
        ),
        "needs_second_review_items": _extract_priority_list(rows, "needs_second_review"),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)

    # --- Markdown report ---
    _write_markdown(evidence, output_md, rows)

    return evidence


def _write_markdown(ev: dict, path: Path, rows: list[dict]) -> None:
    j_dist = ev["normalized_judgment_distribution"]
    total = ev["total_rows"]
    accept_count = j_dist.get("accept", 0)
    accept_rate = accept_count / total if total else 0
    issue_dist = ev["issue_category_distribution"]

    schema_fn = ev["schema_false_negative_items"]
    pre_ai = ev["pre_ai_borderline_items"]
    multi_sp = ev["multiple_species_target_unclear_items"]
    same_sp = ev["same_species_multiple_individuals_ok_items"]
    text_ov = ev["text_overlay_or_answer_visible_items"]
    habitat = ev["habitat_too_permissive_items"]
    sp_card = ev["species_card_too_permissive_items"]
    fo_items = ev["field_observation_too_permissive_items"]
    model_miss = ev["rare_model_subject_miss_items"]

    decision = (
        "READY_FOR_PMP_POLICY_V1_1_PATCHES"
        if accept_rate >= 0.70
        and ev["rows_with_review_judgment"] >= total * 0.80
        else "NEEDS_MORE_REVIEW_NORMALIZATION"
    )

    def _item_list(items: list[dict]) -> str:
        if not items:
            return "_None._\n"
        lines = []
        for it in items:
            lines.append(
                f"- `{it['review_item_id']}` | {it['scientific_name']} | "
                f"`{it['evidence_type']}` | {it['reviewer_overall_judgment_normalized']} "
                f"| {it['reviewer_notes'][:80] if it['reviewer_notes'] else '—'}"
            )
        return "\n".join(lines) + "\n"

    def _j_table(dist: dict) -> str:
        lines = ["| Judgment | Count | % |", "|---|---|---|"]
        for k in ["accept", "too_strict", "too_permissive", "reject", "unclear", "blank"]:
            n = dist.get(k, 0)
            pct = f"{n / total * 100:.1f}%" if total else "—"
            lines.append(f"| {k} | {n} | {pct} |")
        return "\n".join(lines)

    def _issue_table(dist: dict) -> str:
        lines = ["| Issue category | Count |", "|---|---|"]
        for k, v in sorted(dist.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines)

    today = date.today().isoformat()

    md = f"""---
owner: database
status: ready_for_validation
generated_at: {today}
last_reviewed: {today}
source_of_truth: docs/audits/pmp-policy-v1-broader-400-human-review-analysis.md
scope: audit
---

# PMP policy v1 — Broader-400 human review analysis

## Purpose

Analyze the human review of the broader PMP policy qualification run
(`palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`) to identify
calibration issues, schema false negatives, and policy patch candidates
for Sprint 9 Phase 2.

## Input file

`{ev["input_file"]}`

## Scope

- 400 media qualified, 60 sampled for human review.
- Human reviewer: one reviewer, manual pass.
- This analysis normalizes judgments, infers issue categories, and surfaces
  calibration candidates.

## What this analysis does and does not decide

- **Does**: surface patch candidates, categorize issues, compute metrics.
- **Does not**: change PMP schema, change policy thresholds, run Gemini,
  touch runtime or materialization.

---

## Review completion summary

| Metric | Value |
|---|---|
| Total rows | {total} |
| Rows with judgment | {ev["rows_with_review_judgment"]} |
| Rows with notes | {ev["rows_with_notes"]} |
| Accept rate | {accept_rate * 100:.1f}% |

---

## Normalized judgment distribution

{_j_table(j_dist)}

---

## Issue category distribution

{_issue_table(issue_dist)}

---

## Key findings

1. **Schema false negatives** ({len(schema_fn)} cases): `profile_failed` images
   that the human reviewer considers good or usable. Root cause is likely
   over-strict schema validation on certain field combinations.

2. **Multiple-species / target-taxon ambiguity** ({len(multi_sp)} unclear +
   {len(same_sp)} same-species-ok): Policy needs a formal rule for
   `multiple_organisms` evidence distinguishing same-species groups (acceptable)
   from mixed-species frames where target identity is ambiguous (higher caution).

3. **Text overlay / answer visible** ({len(text_ov)} cases): Screenshots showing
   species name or identification app UI must be detected and rejected or
   heavily penalized. Currently not handled.

4. **Habitat evidence permissiveness** ({len(habitat)} cases): Habitat images
   classified as `field_observation`-eligible when species cannot be inferred
   from image content alone.

5. **Species card and field observation concerns** ({len(sp_card)} + {len(fo_items)} cases):
   Some `species_card` assignments appear too permissive for distant/silhouette
   shots; `field_observation` may be broad but is generally appropriate.

6. **Rare model-subject miss** ({len(model_miss)} cases): AI assigned
   `evidence_type=unknown` on at least one image where a reviewer can see a
   very distant bird. Low frequency; not a new category priority.

7. **Pre-AI borderline** ({len(pre_ai)} cases): Image rejected before AI
   qualification; reviewer considers it borderline but prefers not to
   over-complicate the pipeline.

---

## Schema false negative summary

{_item_list(schema_fn)}
**Action:** investigate `profile_failed` root causes per item; candidate schema
patch if validation rules are over-strict on specific field combinations.

---

## Pre-AI borderline summary

{_item_list(pre_ai)}
**Action:** consider slight relaxation of image size/resolution thresholds only
if pattern is consistent. Do not introduce new status classes.

---

## Target taxon / multi-species summary

### Multiple species — target unclear

{_item_list(multi_sp)}

### Same species — multiple individuals OK

{_item_list(same_sp)}
**Action:** define `target_taxon_visibility` policy rule distinguishing
same-species multi-individual (acceptable, possibly rich) from mixed-species
frame where target is ambiguous (policy downgrade or flag).

---

## Text overlay summary

{_item_list(text_ov)}
**Action:** add detection criterion for visible species name / app screenshot.
Candidate: reject or heavy penalty at pre-AI or PMP schema validation stage.

---

## Habitat evidence summary

{_item_list(habitat)}
**Action:** tighten habitat evidence scoring; consider requiring minimum
ecological specificity to qualify for `field_observation`.

---

## Species card and field observation concerns

### Species card possibly too permissive

{_item_list(sp_card)}

### Field observation possibly too permissive / strict

{_item_list(fo_items)}
**Action:** review `species_card` threshold conditions; `field_observation` is
intentionally broad but should not be assigned to screenshots.

---

## Rare model-subject miss note

{_item_list(model_miss)}
**Action:** mark for second review. Do not create a major new policy category
unless this pattern recurs at scale.

---

## Recommended Sprint 9 Phase 2 patches

1. **Schema fix**: investigate 4 `schema_false_negative` items for
   over-strict validation rules.
2. **Target taxon visibility**: define and document
   `target_taxon_visibility_v1` policy distinguishing same-species vs
   mixed-species `multiple_organisms`.
3. **Text overlay rejection**: add detection rule for visible species name /
   app screenshot at pre-AI or PMP stage.
4. **Habitat scoring**: tighten `habitat` evidence score thresholds.
5. **Pre-AI threshold**: evaluate whether image size/resolution limits can
   be slightly lowered without pipeline complexity.
6. **Species card conditions**: add minimum clarity condition for
   `species_card` eligibility.

---

## Open questions

- How should same-species multiple individuals be formally treated in PMP?
- How should mixed-species frames with unclear target be penalized?
- Should `target_taxon_visibility` be a new PMP field or a policy rule?
- How should visible answer text / app screenshots be detected?
- Should habitat evidence require ecological specificity for `field_observation`?
- Should `species_card` require stricter conditions (distance, clarity)?
- Is `field_observation` intentionally broad? Current behavior seems correct.
- Should pre-AI resolution thresholds be slightly lowered?
- How should rare model-subject-miss cases be tracked without over-complexifying?

---

## Final decision

**{decision}**

Rationale: accept rate is {accept_rate * 100:.1f}% ({accept_count}/{total}),
judgments are normalized, issue categories populated, high-priority patch
candidates identified. Proceeding to Sprint 9 Phase 2 patches is appropriate.
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)


def main() -> None:
    ev = run()
    j = ev["normalized_judgment_distribution"]
    total = ev["total_rows"]
    accept = j.get("accept", 0)
    print(
        f"Analysis complete | rows={total} | accept={accept} ({accept/total*100:.1f}%)"
        f" | issues={len(ev['issue_category_distribution'])} categories"
    )
    print(f"  JSON  -> {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"  MD    -> {OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"  CSV   -> {OUTPUT_LABELED_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
