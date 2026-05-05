"""
Export targeted second broader review sheet for PMP policy v1.1.

Inputs:
    docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv
    data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json
    docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json (optional)
    docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv (optional)

Outputs:
    docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.csv
    docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.jsonl
    docs/audits/human_review/pmp_policy_v1_1_second_broader_review_readme.md
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

INPUT_LABELED_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_broader_400_20260504_human_review_labeled.csv"
)
INPUT_AI_OUTPUTS = (
    REPO_ROOT
    / "data/raw/inaturalist"
    / "palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504"
    / "ai_outputs.json"
)
INPUT_DELTA_AUDIT = (
    REPO_ROOT
    / "docs/audits/evidence"
    / "pmp_policy_v1_1_broader_400_delta_audit.json"
)
INPUT_OPTIONAL_SIGNALS = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_optional_signal_annotations.csv"
)
INPUT_MANIFEST = (
    REPO_ROOT
    / "data/raw/inaturalist"
    / "palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504"
    / "manifest.json"
)

OUTPUT_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_second_broader_review_sheet.csv"
)
OUTPUT_JSONL = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_second_broader_review_sheet.jsonl"
)
OUTPUT_README = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_second_broader_review_readme.md"
)

# Target number of rows
MIN_REVIEW_ROWS = 80
MAX_REVIEW_ROWS = 120

# Category identifiers (ordered for deterministic sampling priority)
CATEGORIES = [
    "schema_false_negative",
    "profile_failed_current",
    "same_species_multiple_individuals_ok",
    "multiple_species_target_unclear",
    "habitat_generic",
    "habitat_species_relevant",
    "species_card_downgraded",
    "species_card_eligible",
    "text_or_screenshot",
    "field_observation_borderline",
    "stable_accepted_control",
]

# Per-category quotas (adjusted to hit 80-120 total)
CATEGORY_QUOTAS: dict[str, int] = {
    "schema_false_negative": 4,
    "profile_failed_current": 5,
    "same_species_multiple_individuals_ok": 5,
    "multiple_species_target_unclear": 4,
    "habitat_generic": 5,
    "habitat_species_relevant": 8,
    "species_card_downgraded": 10,
    "species_card_eligible": 12,
    "text_or_screenshot": 3,
    "field_observation_borderline": 8,
    "stable_accepted_control": 20,
}

OUTPUT_COLUMNS = [
    "review_item_id",
    "media_key",
    "image_url",
    "local_image_path",
    "scientific_name",
    "common_name_en",
    "evidence_type",
    "policy_status_before_if_available",
    "policy_status_current",
    "usage_statuses_before_if_available",
    "usage_statuses_current",
    "recommended_uses_current",
    "previous_human_issue_category",
    "target_taxon_visibility_if_available",
    "contains_visible_answer_text_if_available",
    "contains_ui_screenshot_if_available",
    "habitat_specificity_if_available",
    "why_selected_for_second_review",
    "expected_patch_effect",
    "visible_field_marks_summary",
    "limitations_summary",
    # Human fill fields
    "second_review_decision",
    "second_review_main_issue",
    "second_review_notes",
]

HUMAN_FIELDS = {
    "second_review_decision": "",
    "second_review_main_issue": "",
    "second_review_notes": "",
}


def _load_labeled_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_ai_outputs(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_delta_audit(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_optional_signals(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r.get("media_key", ""): r for r in rows if r.get("media_key")}


def _load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _media_key_from_local_path(local_image_path: str) -> str | None:
    p = Path(local_image_path)
    stem = p.stem
    if stem.isdigit():
        return f"inaturalist::{stem}"
    return None


def _parse_pipe_list(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split("|") if v.strip()]


def _usages_set(value: str) -> set[str]:
    return set(_parse_pipe_list(value))


def _field_marks_summary(pmp: dict) -> str:
    if not isinstance(pmp, dict):
        return ""
    id_profile = pmp.get("identification_profile", {})
    if not isinstance(id_profile, dict):
        return ""
    marks = id_profile.get("visible_field_marks", [])
    if not isinstance(marks, list):
        return ""
    parts = []
    for m in marks[:5]:
        if isinstance(m, dict):
            feat = m.get("feature") or m.get("description") or ""
            bp = m.get("body_part") or ""
            if feat:
                parts.append(f"{bp}:{feat}" if bp else feat)
    return " | ".join(parts)


def _limitations_summary(pmp: dict) -> str:
    if not isinstance(pmp, dict):
        return ""
    lims: list[str] = []
    main_lims = pmp.get("limitations", [])
    if isinstance(main_lims, list):
        lims.extend(str(l) for l in main_lims[:3])
    id_profile = pmp.get("identification_profile", {})
    if isinstance(id_profile, dict):
        id_lims = id_profile.get("identification_limitations", [])
        if isinstance(id_lims, list):
            lims.extend(str(l) for l in id_lims[:2])
    return " | ".join(lims[:4])


def _evaluate_current_policy(pmp: dict, optional_signals: dict | None = None) -> dict:
    from database_core.qualification.pmp_policy_v1 import evaluate_pmp_profile_policy

    merged = dict(pmp)
    if optional_signals:
        for field in ("target_taxon_visibility", "contains_visible_answer_text", "contains_ui_screenshot"):
            sig_val = optional_signals.get(field, "").strip()
            if sig_val and sig_val not in ("", "unknown") and field not in merged:
                if field in ("contains_visible_answer_text", "contains_ui_screenshot"):
                    merged[field] = sig_val.lower() == "true"
                else:
                    merged[field] = sig_val
    return evaluate_pmp_profile_policy(merged)


def _format_usage_statuses_brief(policy_result: dict) -> str:
    """Compact representation: usage:status pairs."""
    statuses = policy_result.get("usage_statuses", {})
    parts = []
    for usage, info in statuses.items():
        if isinstance(info, dict):
            s = info.get("status", "?")
            if s not in ("not_applicable",):
                parts.append(f"{usage}:{s}")
    return " | ".join(parts)


def _image_url_from_manifest(manifest: dict, media_key: str) -> str:
    """Try to get image URL from manifest."""
    entry = manifest.get(media_key, {})
    if isinstance(entry, dict):
        return entry.get("image_url") or entry.get("url") or ""
    return ""


def _build_delta_index(delta_audit: dict) -> dict[str, dict]:
    """Index delta audit row results by review_item_id."""
    result = {}
    for row in delta_audit.get("row_results", []):
        rid = row.get("review_item_id", "")
        if rid:
            result[rid] = row
    return result


def _expected_patch_effect(
    row: dict[str, str],
    delta_row: dict | None,
    optional_sig: dict | None,
) -> str:
    """Generate a human-readable expected effect for this item."""
    cat = row.get("human_issue_category", "")
    effects = []

    if cat == "schema_false_negative":
        effects.append("schema normalization fix: expect profile_valid")
    elif cat == "same_species_multiple_individuals_ok":
        effects.append("multiple_individuals_same_taxon note; no usage change")
    elif cat == "multiple_species_target_unclear":
        effects.append("if target_taxon_visibility=multiple_species_target_unclear: basic_id/confusion_learning→borderline; species_card→not_recommended")
    elif cat == "text_overlay_or_answer_visible":
        effects.append("if contains_ui_screenshot=true or contains_visible_answer_text=true: most uses→not_recommended")
    elif cat == "habitat_too_permissive":
        effects.append("generic habitat: indirect_evidence_learning→not_recommended")
    elif cat == "species_card_too_permissive":
        effects.append("severe limitation keywords: species_card→not_recommended")
    elif cat == "field_observation_too_permissive":
        effects.append("field_observation unchanged (broad by design)")
    else:
        effects.append("stable; no patch expected")

    if delta_row:
        sc_change = delta_row.get("species_card_change", "")
        hab_change = delta_row.get("habitat_change", "")
        if sc_change == "downgraded":
            effects.append("species_card was downgraded by v1.1")
        if hab_change == "indirect_evidence_downgraded":
            effects.append("habitat indirect_evidence_learning was downgraded by v1.1")
        if delta_row.get("status_change") == "improved_schema_fix":
            effects.append("policy_status changed from profile_failed to profile_valid")

    return "; ".join(effects) if effects else "no_specific_effect"


def _classify_item_categories(
    row: dict[str, str],
    delta_row: dict | None,
    pmp: dict,
    policy_result: dict,
) -> list[str]:
    """Return list of categories this item belongs to."""
    cats = []
    human_cat = row.get("human_issue_category", "")
    evidence_type = row.get("evidence_type", "")
    before_status = row.get("policy_status", "")

    if human_cat == "schema_false_negative":
        cats.append("schema_false_negative")

    current_status = policy_result.get("policy_status", "")
    if current_status == "profile_failed":
        cats.append("profile_failed_current")

    if human_cat == "same_species_multiple_individuals_ok":
        cats.append("same_species_multiple_individuals_ok")

    if human_cat == "multiple_species_target_unclear":
        cats.append("multiple_species_target_unclear")

    if evidence_type == "habitat":
        # Check if generic or species-relevant based on limitations/field_marks
        lims_text = _limitations_summary(pmp).lower()
        field_marks_text = _field_marks_summary(pmp).lower()
        combined = lims_text + " " + field_marks_text
        # Generic habitat has no organism-specific signals
        if "foraging" in combined or "nest" in combined or "typical of" in combined:
            cats.append("habitat_species_relevant")
        else:
            cats.append("habitat_generic")

    if delta_row and delta_row.get("species_card_change") == "downgraded":
        cats.append("species_card_downgraded")

    eligible_uses = set(policy_result.get("eligible_database_uses", []))
    if "species_card" in eligible_uses:
        cats.append("species_card_eligible")

    if human_cat == "text_overlay_or_answer_visible":
        cats.append("text_or_screenshot")

    if human_cat == "field_observation_too_permissive":
        cats.append("field_observation_borderline")

    # Field observation borderline: distant/silhouette with field_observation as only recommended
    if not cats or "field_observation_borderline" not in cats:
        if evidence_type == "whole_organism":
            recommended = set(row.get("recommended_uses", "").split("|")) if row.get("recommended_uses") else set()
            recommended = {r.strip() for r in recommended}
            if recommended and recommended <= {"field_observation", "species_card"}:
                lims = _limitations_summary(pmp).lower()
                if any(kw in lims for kw in ("distant", "silhouette", "far")):
                    cats.append("field_observation_borderline")

    if human_cat == "policy_accept" and not cats:
        cats.append("stable_accepted_control")

    return cats if cats else ["stable_accepted_control"]


def run_export(
    *,
    input_labeled_csv: Path = INPUT_LABELED_CSV,
    input_ai_outputs: Path = INPUT_AI_OUTPUTS,
    input_delta_audit: Path = INPUT_DELTA_AUDIT,
    input_optional_signals: Path = INPUT_OPTIONAL_SIGNALS,
    input_manifest: Path = INPUT_MANIFEST,
    output_csv: Path = OUTPUT_CSV,
    output_jsonl: Path = OUTPUT_JSONL,
    output_readme: Path = OUTPUT_README,
    seed: int = 42,
) -> dict[str, Any]:
    rows = _load_labeled_csv(input_labeled_csv)
    ai_outputs = _load_ai_outputs(input_ai_outputs)
    delta_audit = _load_delta_audit(input_delta_audit)
    optional_signals_map = _load_optional_signals(input_optional_signals)
    manifest = _load_manifest(input_manifest)

    delta_index = _build_delta_index(delta_audit)

    # Build candidate items per category
    # key: category -> list of review items (sorted deterministically by review_item_id)
    category_candidates: dict[str, list[dict]] = defaultdict(list)

    # Track which media_keys come from the labeled CSV
    labeled_media_keys: set[str] = set()

    for row in sorted(rows, key=lambda r: r.get("review_item_id", "")):
        local_path = row.get("local_image_path", "")
        media_key = _media_key_from_local_path(local_path)
        if not media_key:
            continue
        labeled_media_keys.add(media_key)

        entry = ai_outputs.get(media_key, {})
        pmp = entry.get("pedagogical_media_profile", {})
        optional_sig = optional_signals_map.get(media_key)

        # Evaluate current policy
        policy_result: dict = {}
        if isinstance(pmp, dict) and pmp.get("review_status") in ("valid", "failed"):
            try:
                policy_result = _evaluate_current_policy(pmp, optional_sig)
            except Exception:  # noqa: BLE001
                policy_result = {"policy_status": "policy_error", "eligible_database_uses": [], "usage_statuses": {}}
        elif row.get("policy_status") == "pre_ai_rejected":
            policy_result = {"policy_status": "pre_ai_rejected", "eligible_database_uses": [], "usage_statuses": {}}
        else:
            policy_result = {"policy_status": row.get("policy_status", ""), "eligible_database_uses": [], "usage_statuses": {}}

        delta_row = delta_index.get(row.get("review_item_id", ""))

        item_cats = _classify_item_categories(row, delta_row, pmp if isinstance(pmp, dict) else {}, policy_result)

        # Build the review item
        image_url = _image_url_from_manifest(manifest, media_key)
        eligible_uses = policy_result.get("eligible_database_uses", [])
        before_status = row.get("policy_status", "")
        before_recommended = row.get("recommended_uses", "")
        before_borderline = row.get("borderline_uses", "")
        before_usage_brief = f"recommended:{before_recommended}|borderline:{before_borderline}" if (before_recommended or before_borderline) else ""

        optional_sig_row = optional_signals_map.get(media_key, {})

        item = {
            "review_item_id": row.get("review_item_id", ""),
            "media_key": media_key,
            "image_url": image_url,
            "local_image_path": local_path,
            "scientific_name": row.get("scientific_name", ""),
            "common_name_en": row.get("common_name_en", ""),
            "evidence_type": row.get("evidence_type", ""),
            "policy_status_before_if_available": before_status,
            "policy_status_current": policy_result.get("policy_status", ""),
            "usage_statuses_before_if_available": before_usage_brief,
            "usage_statuses_current": _format_usage_statuses_brief(policy_result),
            "recommended_uses_current": "|".join(sorted(eligible_uses)),
            "previous_human_issue_category": row.get("human_issue_category", ""),
            "target_taxon_visibility_if_available": optional_sig_row.get("target_taxon_visibility", ""),
            "contains_visible_answer_text_if_available": optional_sig_row.get("contains_visible_answer_text", ""),
            "contains_ui_screenshot_if_available": optional_sig_row.get("contains_ui_screenshot", ""),
            "habitat_specificity_if_available": optional_sig_row.get("habitat_specificity", ""),
            "why_selected_for_second_review": ", ".join(item_cats),
            "expected_patch_effect": _expected_patch_effect(row, delta_row, optional_sig_row if optional_sig_row else None),
            "visible_field_marks_summary": _field_marks_summary(pmp if isinstance(pmp, dict) else {}),
            "limitations_summary": _limitations_summary(pmp if isinstance(pmp, dict) else {}),
            "second_review_decision": "",
            "second_review_main_issue": "",
            "second_review_notes": "",
            "_categories": item_cats,
            "_from_labeled": True,
        }

        for cat in item_cats:
            category_candidates[cat].append(item)

    # Supplement with items from ai_outputs.json that were NOT in the labeled CSV
    # Sort deterministically by media_key
    supplement_keys = sorted(k for k in ai_outputs if k not in labeled_media_keys)
    supplement_counter = 0
    for media_key in supplement_keys:
        entry = ai_outputs[media_key]
        pmp = entry.get("pedagogical_media_profile", {})
        if not isinstance(pmp, dict) or pmp.get("review_status") != "valid":
            continue

        evidence_type = pmp.get("evidence_type", "")
        try:
            policy_result = _evaluate_current_policy(pmp)
        except Exception:  # noqa: BLE001
            continue

        eligible_uses = policy_result.get("eligible_database_uses", [])
        policy_status = policy_result.get("policy_status", "")

        # Only supplement certain categories: species_card_eligible, habitat, field_obs, control
        eligible_set = set(eligible_uses)
        supplement_cats = []

        if evidence_type == "habitat":
            supplement_cats.append("habitat_species_relevant" if eligible_set else "habitat_generic")
        if "species_card" in eligible_set:
            supplement_cats.append("species_card_eligible")
        if evidence_type == "whole_organism" and eligible_set and eligible_set <= {"field_observation", "species_card"}:
            supplement_cats.append("field_observation_borderline")
        if policy_status == "profile_valid" and evidence_type == "whole_organism" and len(eligible_set) >= 3:
            supplement_cats.append("stable_accepted_control")

        if not supplement_cats:
            continue

        supplement_counter += 1
        review_item_id = f"supp-{media_key.replace('inaturalist::', '')}"
        image_url = _image_url_from_manifest(manifest, media_key)
        local_path = ""
        # Try to infer local path
        m_id = media_key.replace("inaturalist::", "")
        for ext in ("jpg", "jpeg", "png"):
            candidate = (
                REPO_ROOT
                / "data/raw/inaturalist"
                / "palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504"
                / "images"
                / f"{m_id}.{ext}"
            )
            if candidate.exists():
                local_path = str(candidate)
                break

        item = {
            "review_item_id": review_item_id,
            "media_key": media_key,
            "image_url": image_url,
            "local_image_path": local_path,
            "scientific_name": "",
            "common_name_en": "",
            "evidence_type": evidence_type,
            "policy_status_before_if_available": "",
            "policy_status_current": policy_status,
            "usage_statuses_before_if_available": "",
            "usage_statuses_current": _format_usage_statuses_brief(policy_result),
            "recommended_uses_current": "|".join(sorted(eligible_uses)),
            "previous_human_issue_category": "",
            "target_taxon_visibility_if_available": "",
            "contains_visible_answer_text_if_available": "",
            "contains_ui_screenshot_if_available": "",
            "habitat_specificity_if_available": "",
            "why_selected_for_second_review": ", ".join(supplement_cats),
            "expected_patch_effect": "supplemental item; validate current policy behavior",
            "visible_field_marks_summary": _field_marks_summary(pmp),
            "limitations_summary": _limitations_summary(pmp),
            "second_review_decision": "",
            "second_review_main_issue": "",
            "second_review_notes": "",
            "_categories": supplement_cats,
            "_from_labeled": False,
        }

        for cat in supplement_cats:
            category_candidates[cat].append(item)

    # Deterministic sampling:
    # 1. Include ALL labeled CSV items first (they are the primary review subjects)
    # 2. Supplement with non-labeled items until MIN_REVIEW_ROWS, per category quotas
    selected_ids: set[str] = set()
    selected_items: list[dict] = []

    # Pass 1: all labeled items (deduplicated, sorted by review_item_id)
    labeled_by_id: dict[str, dict] = {}
    for cat in CATEGORIES:
        for item in category_candidates.get(cat, []):
            if item.get("_from_labeled"):
                rid = item["review_item_id"]
                if rid not in labeled_by_id:
                    labeled_by_id[rid] = item
    for rid in sorted(labeled_by_id):
        selected_ids.add(rid)
        selected_items.append(labeled_by_id[rid])

    # Pass 2: supplement non-labeled items per category until MIN_REVIEW_ROWS
    for cat in CATEGORIES:
        if len(selected_items) >= MAX_REVIEW_ROWS:
            break
        quota = CATEGORY_QUOTAS.get(cat, 5)
        current_cat_count = sum(
            1 for item in selected_items
            if cat in item.get("why_selected_for_second_review", "")
        )
        remaining_quota = max(0, quota - current_cat_count)
        for item in category_candidates.get(cat, []):
            if remaining_quota <= 0:
                break
            if len(selected_items) >= MAX_REVIEW_ROWS:
                break
            rid = item["review_item_id"]
            if rid not in selected_ids and not item.get("_from_labeled"):
                selected_ids.add(rid)
                selected_items.append(item)
                remaining_quota -= 1

    # Pass 3: if still below minimum, fill with any valid supplement item
    if len(selected_items) < MIN_REVIEW_ROWS:
        for cat in ("stable_accepted_control", "species_card_eligible", "field_observation_borderline"):
            for item in category_candidates.get(cat, []):
                if len(selected_items) >= MIN_REVIEW_ROWS:
                    break
                rid = item["review_item_id"]
                if rid not in selected_ids and not item.get("_from_labeled"):
                    selected_ids.add(rid)
                    selected_items.append(item)

    # Sort final list by review_item_id for determinism
    selected_items.sort(key=lambda x: x["review_item_id"])

    # Remove internal fields from output
    output_items = [
        {k: v for k, v in item.items() if k not in ("_categories", "_from_labeled")}
        for item in selected_items
    ]

    # Write CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_items)

    # Write JSONL
    with output_jsonl.open("w", encoding="utf-8") as f:
        for item in output_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Write README
    _write_readme(output_readme, len(output_items), category_candidates, selected_ids)

    # Category coverage summary
    cat_coverage: dict[str, int] = {}
    for item in selected_items:
        for cat in item.get("_categories", item.get("why_selected_for_second_review", "").split(", ")):
            cat_coverage[cat] = cat_coverage.get(cat, 0) + 1

    return {
        "total_rows": len(output_items),
        "categories_covered": list(CATEGORIES),
        "output_csv": str(output_csv),
        "output_jsonl": str(output_jsonl),
        "output_readme": str(output_readme),
    }


def _write_readme(path: Path, row_count: int, category_candidates: dict, selected_ids: set) -> None:
    cat_counts = {cat: sum(1 for item in items if item["review_item_id"] in selected_ids)
                  for cat, items in category_candidates.items()}

    lines = [
        "# PMP Policy v1.1 — Second Broader Review Sheet README",
        "",
        "## Purpose",
        "",
        "This is a targeted human review sheet for Sprint 10, validating the effect of "
        "Sprint 9 Phase 2 calibration patches (policy v1.1) on the broader_400 snapshot.",
        "",
        "**Do not use this sheet to evaluate media usefulness in general.**",
        "This review is specifically about whether policy v1.1 behavior is correct "
        "compared to what a human would expect.",
        "",
        f"Total items: **{row_count}**",
        "",
        "## What Changed Since the Previous Review",
        "",
        "Sprint 9 Phase 2 applied the following patches:",
        "",
        "1. **Schema normalization**: `body→whole_body`, `sitting→resting`, "
        "biological basis null downgrade. Fixes 4 schema false negatives.",
        "2. **Species card calibration**: stricter thresholds + severe limitation "
        "keyword detection (distant, silhouette, obscured).",
        "3. **Habitat calibration**: generic habitat now downgrades `indirect_evidence_learning`.",
        "4. **Optional signals**: `target_taxon_visibility`, `contains_visible_answer_text`, "
        "`contains_ui_screenshot` consumed by policy when present.",
        "",
        "## What to Check",
        "",
        "For each item, review the image and the current policy outcome. Ask:",
        "",
        "- Does the `policy_status_current` make sense for this image?",
        "- Does the `recommended_uses_current` accurately reflect what this image can teach?",
        "- If the item was previously a human-flagged issue, has the issue been resolved?",
        "- Is there an unexpected regression (previously acceptable, now too strict)?",
        "- Is there still a policy permissiveness problem?",
        "",
        "## How to Fill Fields",
        "",
        "### `second_review_decision`",
        "**Required.** One of:",
        "- `accept` — policy outcome is appropriate",
        "- `too_strict` — policy is stricter than warranted",
        "- `too_permissive` — policy is more permissive than warranted",
        "- `reject` — item should not be used for any learning purpose",
        "- `unclear` — uncertain; leave a note",
        "",
        "### `second_review_main_issue`",
        "**Optional but recommended.** One of:",
        "- `none` — no issue",
        "- `still_too_strict` — patch did not fix a too_strict case",
        "- `still_too_permissive` — patch did not fix a too_permissive case",
        "- `fixed` — patch resolved the previous issue",
        "- `regression` — patch introduced a new problem",
        "- `target_taxon_issue` — problem with target visibility",
        "- `habitat_issue` — problem with habitat classification",
        "- `species_card_issue` — problem with species_card eligibility",
        "- `visible_text_issue` — problem with visible answer text detection",
        "- `schema_failure` — still failing at schema level",
        "- `other` — other issue (explain in notes)",
        "",
        "### `second_review_notes`",
        "**Optional.** Free text notes about the decision.",
        "",
        "## What NOT to Judge",
        "",
        "- Do not judge media aesthetic quality beyond what affects learning utility.",
        "- Do not re-assess taxonomy (species name is fixed).",
        "- Do not assess whether runtime should select this item (out of scope).",
        "- Do not assess pack composition (out of scope).",
        "",
        "## How Optional Signals Are Evaluated",
        "",
        "Some items include pre-filled optional signals in the columns:",
        "- `target_taxon_visibility_if_available`",
        "- `contains_visible_answer_text_if_available`",
        "- `contains_ui_screenshot_if_available`",
        "- `habitat_specificity_if_available`",
        "",
        "These signals are annotated from the optional signal sheet and, where present, "
        "are injected into policy v1.1 evaluation. The `usage_statuses_current` already "
        "reflects these injected signals.",
        "",
        "If you disagree with a signal value, note it in `second_review_notes`.",
        "",
        "## Decision Criteria After Review",
        "",
        "After this review is filled, the analysis script "
        "(`scripts/analyze_pmp_policy_v1_1_second_review.py`) will compute:",
        "",
        "- Overall accept/too_strict/too_permissive/reject distribution",
        "- Fixed count (previous issues now resolved)",
        "- Regression count (new issues introduced by patch)",
        "- Category-specific outcomes",
        "",
        "Decision labels that the analysis will produce:",
        "- `READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE` — patches validated, no critical regressions",
        "- `NEEDS_POLICY_V1_2_CALIBRATION` — significant issues remain",
        "- `NEEDS_MORE_TARGET_SIGNAL_WORK` — optional signals need more work",
        "- `INVESTIGATE_REGRESSIONS` — unexpected regressions detected",
        "",
        "## Category Coverage",
        "",
        "| Category | Count |",
        "|---|---|",
    ]

    for cat in CATEGORIES:
        count = cat_counts.get(cat, 0)
        lines.append(f"| {cat} | {count} |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    result = run_export()
    print(f"Total rows: {result['total_rows']}")
    print(f"Output CSV: {result['output_csv']}")
    print(f"Output JSONL: {result['output_jsonl']}")


if __name__ == "__main__":
    main()
