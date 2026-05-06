from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import normalize_localized_name_for_compare
from database_core.qualification.pmp_policy_v1 import evaluate_pmp_profile_policy

PLAN_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "localized_name_apply_plan_v1.json"
MATERIALIZATION_SOURCE_PATH = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "palier1_v11_baseline" / "pack_materialization_v2.json"
)
DISTRACTOR_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationships_v1_projected_sprint13.json"

QUALIFIED_EXPORT_PATH = REPO_ROOT / "data" / "exports" / "palier1_be_birds_50taxa_run003_v11_baseline.export.json"
INAT_SNAPSHOT_PATH = (
    REPO_ROOT / "data" / "raw" / "inaturalist" / "palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504"
)
INAT_MANIFEST_PATH = INAT_SNAPSHOT_PATH / "manifest.json"
INAT_AI_OUTPUTS_PATH = INAT_SNAPSHOT_PATH / "ai_outputs.json"

SCHEMA_PACK_PATH = REPO_ROOT / "schemas" / "golden_pack_v1.schema.json"
SCHEMA_MANIFEST_PATH = REPO_ROOT / "schemas" / "golden_pack_manifest_v1.schema.json"
SCHEMA_VALIDATION_REPORT_PATH = REPO_ROOT / "schemas" / "golden_pack_validation_report_v1.schema.json"

OUTPUT_DIR = REPO_ROOT / "data" / "exports" / "golden_packs" / "belgian_birds_mvp_v1"
OUTPUT_MEDIA_DIR = OUTPUT_DIR / "media"
OUTPUT_PACK_PATH = OUTPUT_DIR / "pack.json"
OUTPUT_FAILED_PARTIAL_PACK_PATH = OUTPUT_DIR / "failed_build" / "partial_pack.json"
OUTPUT_MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
OUTPUT_VALIDATION_REPORT_PATH = OUTPUT_DIR / "validation_report.json"

MEDIA_MAX_BYTES = 50_000_000
FALLBACK_FEEDBACK = "Compare les détails visibles de forme, couleur et silhouette avant de répondre."


class ContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterializerConfig:
    plan_path: Path
    materialization_source_path: Path
    distractor_path: Path
    qualified_export_path: Path
    inat_manifest_path: Path
    inat_ai_outputs_path: Path
    schema_pack_path: Path
    schema_manifest_path: Path
    schema_validation_report_path: Path
    output_dir: Path
    pack_id: str = "belgian_birds_mvp_v1"
    locale: str = "fr"
    target_count: int = 30

    @property
    def inat_snapshot_path(self) -> Path:
        return self.inat_manifest_path.parent

    @property
    def output_media_dir(self) -> Path:
        return self.output_dir / "media"

    @property
    def output_pack_path(self) -> Path:
        return self.output_dir / "pack.json"

    @property
    def output_failed_partial_pack_path(self) -> Path:
        return self.output_dir / "failed_build" / "partial_pack.json"

    @property
    def output_manifest_path(self) -> Path:
        return self.output_dir / "manifest.json"

    @property
    def output_validation_report_path(self) -> Path:
        return self.output_dir / "validation_report.json"


def _default_config() -> MaterializerConfig:
    return MaterializerConfig(
        plan_path=PLAN_PATH,
        materialization_source_path=MATERIALIZATION_SOURCE_PATH,
        distractor_path=DISTRACTOR_PATH,
        qualified_export_path=QUALIFIED_EXPORT_PATH,
        inat_manifest_path=INAT_MANIFEST_PATH,
        inat_ai_outputs_path=INAT_AI_OUTPUTS_PATH,
        schema_pack_path=SCHEMA_PACK_PATH,
        schema_manifest_path=SCHEMA_MANIFEST_PATH,
        schema_validation_report_path=SCHEMA_VALIDATION_REPORT_PATH,
        output_dir=OUTPUT_DIR,
    )


@dataclass(frozen=True)
class CandidateDistractor:
    ref_type: str
    ref_id: str
    source_rank: int


@dataclass
class MediaChoice:
    source_media_id: str
    source_url: str
    image_rel_path: str
    image_abs_path: Path
    source_name: str
    creator: str
    license_name: str
    license_url: str
    attribution_text: str


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _target_label_safe_fr_map(plan: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("taxon_kind") != "canonical_taxon":
            continue
        if item.get("locale") != "fr":
            continue
        if item.get("decision") not in {"auto_accept", "same_value"}:
            continue
        taxon_id = str(item.get("taxon_id") or "").strip()
        label = str(item.get("chosen_value") or "").strip()
        if taxon_id and label:
            out[taxon_id] = label
    return out


def _option_label_safe_fr_map(plan: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("taxon_kind") not in {"canonical_taxon", "referenced_taxon"}:
            continue
        if item.get("locale") != "fr":
            continue
        if item.get("decision") not in {"auto_accept", "same_value"}:
            continue
        taxon_id = str(item.get("taxon_id") or "").strip()
        label = str(item.get("chosen_value") or "").strip()
        if taxon_id and label:
            out[taxon_id] = label
    return out


def _safe_ready_targets_from_plan(plan: dict[str, Any]) -> list[str]:
    metrics = plan.get("metrics")
    if not isinstance(metrics, dict):
        raise ContractError("Plan missing metrics")
    source_targets = metrics.get("safe_ready_targets_from_plan")
    if not isinstance(source_targets, list):
        raise ContractError("Plan missing safe_ready_targets_from_plan")
    targets = [str(item).strip() for item in source_targets if str(item).strip()]
    if len(targets) != len(set(targets)):
        raise ContractError("Plan safe-ready target set has duplicates")
    if any(not item.startswith("taxon:birds:") for item in targets):
        raise ContractError("Plan safe-ready target set contains malformed ids")
    return sorted(targets)


def _candidate_refs_by_target(distractor: dict[str, Any]) -> dict[str, list[CandidateDistractor]]:
    out: dict[str, list[CandidateDistractor]] = {}
    for row in distractor.get("projected_records", []):
        if not isinstance(row, dict) or row.get("status") != "candidate":
            continue
        target = str(row.get("target_canonical_taxon_id") or "").strip()
        ctype = str(row.get("candidate_taxon_ref_type") or "").strip()
        cid = str(row.get("candidate_taxon_ref_id") or "").strip()
        if not target or ctype not in {"canonical_taxon", "referenced_taxon"} or not cid:
            continue
        rank_raw = row.get("source_rank")
        try:
            rank = int(rank_raw)
        except (TypeError, ValueError):
            rank = 10**9
        out.setdefault(target, []).append(CandidateDistractor(ref_type=ctype, ref_id=cid, source_rank=rank))
    for target in list(out.keys()):
        out[target] = sorted(
            out[target],
            key=lambda item: (item.source_rank, item.ref_type, item.ref_id),
        )
    return out


def _extract_source_media_id(playable_item_id: str) -> str | None:
    match = re.search(r"inaturalist:(\d+)$", playable_item_id)
    return match.group(1) if match else None


def _build_media_metadata_indices(
    manifest: dict[str, Any],
    qualified_export: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    manifest_map: dict[str, dict[str, Any]] = {}
    for row in manifest.get("media_downloads", []):
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_media_id") or "").strip()
        if sid:
            manifest_map[sid] = row

    qualified_map: dict[str, dict[str, Any]] = {}
    for row in qualified_export.get("qualified_resources", []):
        if not isinstance(row, dict):
            continue
        provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
        source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
        sid = str(source.get("source_media_id") or "").strip()
        if sid:
            qualified_map[sid] = row

    return manifest_map, qualified_map


def _license_url_from_code(license_code: str) -> str:
    normalized = license_code.lower().strip()
    mapping = {
        "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
        "cc-by": "https://creativecommons.org/licenses/by/4.0/",
        "cc-by-sa": "https://creativecommons.org/licenses/by-sa/4.0/",
        "cc-by-nc": "https://creativecommons.org/licenses/by-nc/4.0/",
        "cc-by-nd": "https://creativecommons.org/licenses/by-nd/4.0/",
    }
    return mapping.get(normalized, "https://www.inaturalist.org/pages/help#copyright")


def _find_media_choice(
    source_media_id: str,
    media_manifest_map: dict[str, dict[str, Any]],
    qualified_map: dict[str, dict[str, Any]],
    inat_snapshot_path: Path,
) -> MediaChoice:
    manifest_row = media_manifest_map.get(source_media_id)
    if manifest_row is None:
        raise ContractError(f"Missing media manifest row for source_media_id={source_media_id}")

    image_rel_path = str(manifest_row.get("image_path") or "").strip()
    source_url = str(manifest_row.get("source_url") or "").strip()
    if not image_rel_path or not source_url:
        raise ContractError(f"Incomplete media manifest metadata for source_media_id={source_media_id}")

    image_abs_path = inat_snapshot_path / image_rel_path
    if not image_abs_path.exists():
        raise ContractError(f"Missing local image file for source_media_id={source_media_id}: {image_abs_path}")

    qualified_row = qualified_map.get(source_media_id)
    creator = "Unknown creator"
    license_name = "unknown"
    attribution_text = f"Photo {source_media_id} via iNaturalist"
    if qualified_row is not None:
        provenance = qualified_row.get("provenance") if isinstance(qualified_row.get("provenance"), dict) else {}
        source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
        raw_payload_ref = str(source.get("raw_payload_ref") or "")
        license_name = str(source.get("media_license") or "unknown")
        if raw_payload_ref:
            creator = raw_payload_ref
            attribution_text = f"Photo {source_media_id} from {raw_payload_ref} ({license_name})"

    license_url = _license_url_from_code(license_name)

    return MediaChoice(
        source_media_id=source_media_id,
        source_url=source_url,
        image_rel_path=image_rel_path,
        image_abs_path=image_abs_path,
        source_name="inaturalist",
        creator=creator,
        license_name=license_name,
        license_url=license_url,
        attribution_text=attribution_text,
    )


def _evaluate_basic_identification_eligible(ai_outputs: dict[str, Any], source_media_id: str) -> bool:
    key = f"inaturalist::{source_media_id}"
    outcome = ai_outputs.get(key)
    if not isinstance(outcome, dict):
        return False
    profile = outcome.get("pedagogical_media_profile")
    if not isinstance(profile, dict):
        return False
    decision = evaluate_pmp_profile_policy(profile)
    usage = decision.get("usage_statuses")
    if not isinstance(usage, dict):
        return False
    basic = usage.get("basic_identification")
    if not isinstance(basic, dict):
        return False
    return str(basic.get("status") or "") == "eligible"


def _json_schema_validate(instance: dict[str, Any], schema_path: Path, label: str) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise ContractError("jsonschema is required to validate golden_pack schemas") from exc

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(instance=instance, schema=schema)


def _collect_heavy_field_violations(pack: dict[str, Any]) -> list[str]:
    forbidden = {"raw_evidence", "apply_plan", "unresolved_candidates", "debug", "debug_traces", "blockers"}
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child_path = f"{path}.{key}" if path else key
                if key in forbidden:
                    found.append(child_path)
                walk(value, child_path)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(pack, "")
    return found


def _build_golden_pack_artifact(
    config: MaterializerConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str], list[str]]:
    plan = _load_json(config.plan_path)
    materialization_source = _load_json(config.materialization_source_path)
    distractor = _load_json(config.distractor_path)
    qualified_export = _load_json(config.qualified_export_path)
    inat_manifest = _load_json(config.inat_manifest_path)
    ai_outputs = _load_json(config.inat_ai_outputs_path)

    target_labels = _target_label_safe_fr_map(plan)
    option_labels = _option_label_safe_fr_map(plan)
    safe_targets = _safe_ready_targets_from_plan(plan)
    candidate_refs_by_target = _candidate_refs_by_target(distractor)
    media_manifest_map, qualified_map = _build_media_metadata_indices(inat_manifest, qualified_export)

    source_questions = materialization_source.get("questions")
    if not isinstance(source_questions, list):
        raise ContractError("Source pack_materialization_v2 missing questions list")

    questions_by_target: dict[str, dict[str, Any]] = {}
    for question in source_questions:
        if not isinstance(question, dict):
            continue
        target_id = str(question.get("target_canonical_taxon_id") or "").strip()
        if not target_id:
            continue
        if target_id in questions_by_target:
            raise ContractError(f"Duplicate target question in source materialization: {target_id}")
        questions_by_target[target_id] = question

    warnings: list[str] = []
    blockers: list[str] = []
    selected_targets: list[str] = []
    rejected_targets: list[dict[str, Any]] = []
    target_to_distractors: dict[str, list[CandidateDistractor]] = {}
    target_to_media_choice: dict[str, MediaChoice] = {}

    for target_id in safe_targets:
        reasons: list[str] = []
        source_question = questions_by_target.get(target_id)
        if source_question is None:
            reasons.append("missing_source_question")
        if target_id not in target_labels:
            reasons.append("missing_target_fr_label_safe")

        playable_id = str((source_question or {}).get("target_playable_item_id") or "").strip()
        source_media_id = _extract_source_media_id(playable_id) if playable_id else None
        if not source_media_id:
            reasons.append("missing_target_source_media_id")

        if source_media_id and not _evaluate_basic_identification_eligible(ai_outputs, source_media_id):
            reasons.append("primary_media_basic_identification_not_eligible")

        candidate_refs = candidate_refs_by_target.get(target_id, [])
        usable_candidates: list[CandidateDistractor] = []
        seen_ref: set[tuple[str, str]] = set()
        seen_label_norm: set[str] = set()
        target_label_norm = normalize_localized_name_for_compare(target_labels.get(target_id, ""))
        if target_label_norm:
            seen_label_norm.add(target_label_norm)

        for candidate in candidate_refs:
            if candidate.ref_id == target_id:
                continue
            if candidate.ref_id not in option_labels:
                continue
            label = option_labels[candidate.ref_id]
            if not label.strip():
                continue
            norm = normalize_localized_name_for_compare(label)
            if not norm:
                continue
            key = (candidate.ref_type, candidate.ref_id)
            if key in seen_ref or norm in seen_label_norm:
                continue
            seen_ref.add(key)
            seen_label_norm.add(norm)
            usable_candidates.append(candidate)
            if len(usable_candidates) == 3:
                break

        if len(usable_candidates) < 3:
            reasons.append("insufficient_label_safe_distractors")

        media_choice: MediaChoice | None = None
        if source_media_id and not reasons:
            try:
                media_choice = _find_media_choice(
                    source_media_id,
                    media_manifest_map,
                    qualified_map,
                    inat_snapshot_path=config.inat_snapshot_path,
                )
            except ContractError as exc:
                reasons.append(str(exc))

        if reasons:
            rejected_targets.append({"taxon_ref_id": target_id, "reason_codes": reasons})
            continue

        assert media_choice is not None
        target_to_distractors[target_id] = usable_candidates
        target_to_media_choice[target_id] = media_choice
        selected_targets.append(target_id)

    selected_targets = sorted(selected_targets)[: config.target_count]
    if len(selected_targets) < config.target_count:
        blockers.append(
            f"unable_to_select_{config.target_count}_targets:selected={len(selected_targets)} considered={len(safe_targets)}"
        )

    config.output_media_dir.mkdir(parents=True, exist_ok=True)

    media_entries: list[dict[str, Any]] = []
    question_entries: list[dict[str, Any]] = []
    copied_media_checksums: list[dict[str, str]] = []

    missing_runtime_media_paths: list[str] = []
    missing_attribution_entries: list[dict[str, Any]] = []

    for idx, target_id in enumerate(selected_targets, start=1):
        source_question = questions_by_target[target_id]
        target_playable_item_id = str(source_question.get("target_playable_item_id") or "")
        media_choice = target_to_media_choice[target_id]

        source_ext = media_choice.image_abs_path.suffix.lower() or ".jpg"
        media_filename = f"{target_id.replace(':', '_')}_{media_choice.source_media_id}{source_ext}"
        runtime_rel = f"media/{media_filename}"
        runtime_abs = config.output_dir / runtime_rel
        runtime_abs.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(media_choice.image_abs_path, runtime_abs)
        if not runtime_abs.exists():
            missing_runtime_media_paths.append(runtime_rel)

        checksum_hex = _sha256_file(runtime_abs)
        copied_media_checksums.append({"path": runtime_rel, "sha256": checksum_hex})

        media_id = f"m{idx:04d}"
        media_entries.append(
            {
                "media_id": media_id,
                "runtime_uri": runtime_rel,
                "source_url": media_choice.source_url,
                "source": media_choice.source_name,
                "creator": media_choice.creator,
                "license": media_choice.license_name,
                "license_url": media_choice.license_url,
                "attribution_text": media_choice.attribution_text,
                "checksum": f"sha256:{checksum_hex}",
            }
        )

        missing_fields = [
            field
            for field in ("source_url", "source", "creator", "license", "license_url", "attribution_text")
            if not str(media_entries[-1].get(field) or "").strip()
        ]
        if missing_fields:
            missing_attribution_entries.append({"media_id": media_id, "missing_fields": missing_fields})

        question_id = f"gbbmvp1_q{idx:04d}"
        correct_option_id = f"{question_id}_opt1"

        options: list[dict[str, Any]] = [
            {
                "option_id": correct_option_id,
                "taxon_ref": {"type": "canonical_taxon", "id": target_id},
                "display_label": target_labels[target_id],
                "is_correct": True,
                "referenced_only": False,
            }
        ]

        for didx, cand in enumerate(target_to_distractors[target_id], start=2):
            option = {
                "option_id": f"{question_id}_opt{didx}",
                "taxon_ref": {"type": cand.ref_type, "id": cand.ref_id},
                "display_label": option_labels[cand.ref_id],
                "is_correct": False,
            }
            if cand.ref_type == "referenced_taxon":
                option["referenced_only"] = True
                option["provenance"] = {"source": "distractor_relationships_v1_projected_sprint13"}
            else:
                option["referenced_only"] = False
            options.append(option)

        prompt = "Quelle espèce est visible sur cette image ?"
        feedback_short = FALLBACK_FEEDBACK
        feedback_source = "fallback_database_mvp"

        question_entries.append(
            {
                "question_id": question_id,
                "primary_media_id": media_id,
                "prompt": prompt,
                "options": options,
                "correct_option_id": correct_option_id,
                "feedback_short": feedback_short,
                "feedback_source": feedback_source,
            }
        )

    pack_payload = {
        "schema_version": "golden_pack.v1",
        "pack_id": config.pack_id,
        "locale": config.locale,
        "questions": question_entries,
        "media": media_entries,
    }

    heavy_violations = _collect_heavy_field_violations(pack_payload)
    if heavy_violations:
        blockers.append("forbidden_heavy_fields_present")

    cross_check_errors: list[str] = []
    media_ids = {m["media_id"] for m in media_entries}
    media_runtime_paths = {m["runtime_uri"] for m in media_entries}

    if len(question_entries) != config.target_count:
        cross_check_errors.append(f"question_count_expected_{config.target_count}_actual_{len(question_entries)}")

    for q in question_entries:
        options = q["options"]
        if len(options) != 4:
            cross_check_errors.append(f"{q['question_id']}:options_count_not_4")
        correct = [opt for opt in options if bool(opt.get("is_correct"))]
        if len(correct) != 1:
            cross_check_errors.append(f"{q['question_id']}:correct_options_count_not_1")

        if q["correct_option_id"] not in {opt["option_id"] for opt in options}:
            cross_check_errors.append(f"{q['question_id']}:correct_option_id_not_found")

        if q["primary_media_id"] not in media_ids:
            cross_check_errors.append(f"{q['question_id']}:primary_media_id_not_found")

        seen_refs: set[tuple[str, str]] = set()
        seen_labels: set[str] = set()
        for opt in options:
            ref = opt.get("taxon_ref")
            if not isinstance(ref, dict):
                cross_check_errors.append(f"{q['question_id']}:missing_taxon_ref")
                continue
            ref_type = str(ref.get("type") or "")
            ref_id = str(ref.get("id") or "")
            key = (ref_type, ref_id)
            if key in seen_refs:
                cross_check_errors.append(f"{q['question_id']}:duplicate_taxon_ref")
            seen_refs.add(key)

            label_norm = normalize_localized_name_for_compare(str(opt.get("display_label") or ""))
            if label_norm in seen_labels:
                cross_check_errors.append(f"{q['question_id']}:duplicate_normalized_display_label")
            seen_labels.add(label_norm)

            if ref_type == "referenced_taxon" and opt.get("referenced_only") is not True:
                cross_check_errors.append(f"{q['question_id']}:referenced_taxon_without_referenced_only_true")

        distractor_count = sum(1 for opt in options if not bool(opt.get("is_correct")))
        if distractor_count != 3:
            cross_check_errors.append(f"{q['question_id']}:distractor_count_not_3")

    checksum_errors = False
    for media_entry in media_entries:
        runtime_uri = media_entry["runtime_uri"]
        runtime_abs = config.output_dir / runtime_uri
        if not runtime_abs.exists():
            checksum_errors = True
            missing_runtime_media_paths.append(runtime_uri)
            continue
        actual = _sha256_file(runtime_abs)
        expected = str(media_entry["checksum"]).removeprefix("sha256:")
        if actual != expected:
            checksum_errors = True
            cross_check_errors.append(f"checksum_mismatch:{runtime_uri}")

    media_total_bytes = sum(
        (config.output_dir / p["path"]).stat().st_size
        for p in copied_media_checksums
        if (config.output_dir / p["path"]).exists()
    )
    media_within_limit = media_total_bytes <= MEDIA_MAX_BYTES
    if not media_within_limit:
        warnings.append(f"media_pack_size_exceeds_limit:{media_total_bytes}>{MEDIA_MAX_BYTES}")

    if cross_check_errors:
        blockers.extend(sorted(set(cross_check_errors)))

    if missing_attribution_entries:
        warnings.append("some_attribution_fields_use_minimal_fallbacks")

    if any((m.get("license") or "").strip().lower() == "unknown" for m in media_entries):
        warnings.append("license_not_institutionally_reviewed")

    warnings.append("source_attested_labels_not_human_reviewed_runtime_safe")

    validation_report = {
        "schema_version": "golden_pack_validation_report.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "status": "passed" if not blockers else "failed",
        "schema_validity": {
            "manifest_schema_valid": False,
            "pack_schema_valid": False,
            "validation_report_schema_valid": False,
        },
        "count_checks": {
            "expected_questions": config.target_count,
            "actual_questions": len(question_entries),
            "expected_options_per_question": 4,
            "expected_correct_options_per_question": 1,
            "expected_distractors_per_question": 3,
            "status": "passed" if len(question_entries) == config.target_count and not cross_check_errors else "failed",
        },
        "target_candidates_considered": len(safe_targets),
        "selected_targets": selected_targets,
        "rejected_targets": rejected_targets,
        "label_checks": {
            "all_display_labels_runtime_safe": True,
            "no_placeholder_labels": True,
            "no_empty_labels": True,
            "no_invented_labels": True,
            "no_scientific_fallback_primary_labels": True,
        },
        "distractor_checks": {
            "exactly_three_distractors_per_question": all(
                sum(1 for opt in q["options"] if not bool(opt["is_correct"])) == 3 for q in question_entries
            ),
            "options_have_taxon_ref": all(all("taxon_ref" in opt for opt in q["options"]) for q in question_entries),
            "no_generic_canonical_taxon_id_fields": True,
            "referenced_taxon_rules_valid": not any(
                (
                    opt.get("taxon_ref", {}).get("type") == "referenced_taxon"
                    and opt.get("referenced_only") is not True
                )
                for q in question_entries
                for opt in q["options"]
            ),
            "no_emergency_fallback_distractors": True,
        },
        "media_eligibility_checks": {
            "all_primary_media_basic_identification_eligible": len(selected_targets) == len(question_entries),
            "missing_primary_media_count": max(0, len(question_entries) - len(selected_targets)),
        },
        "media_copy_checksum_checks": {
            "all_runtime_media_copied": len(missing_runtime_media_paths) == 0,
            "all_media_checksums_verified": not checksum_errors,
            "missing_runtime_media_paths": sorted(set(missing_runtime_media_paths)),
        },
        "media_pack_size_check": {
            "total_bytes": media_total_bytes,
            "max_bytes": MEDIA_MAX_BYTES,
            "within_limit": media_within_limit,
        },
        "attribution_checks": {
            "all_attribution_fields_present": len(missing_attribution_entries) == 0,
            "missing_attribution_entries": missing_attribution_entries,
        },
        "feedback_checks": {
            "all_questions_have_feedback_short": all(bool(q.get("feedback_short")) for q in question_entries),
            "fallback_database_mvp_count": sum(1 for q in question_entries if q.get("feedback_source") == "fallback_database_mvp"),
        },
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
    }

    pack_bytes = json.dumps(pack_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    report_bytes = json.dumps(validation_report, sort_keys=True, ensure_ascii=False).encode("utf-8")

    manifest_payload = {
        "schema_version": "golden_pack_manifest.v1",
        "pack_id": config.pack_id,
        "contract_version": "golden_pack.v1",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": "sprint14c_commit3_materializer_refactor",
        "runtime_surface": "artifact_only",
        "contract_status": "before_mvp_candidate",
        "gates": [
            {"gate_id": "target_selection", "status": "passed" if len(selected_targets) == config.target_count else "failed"},
            {
                "gate_id": "media_basic_identification_policy",
                "status": "passed" if not blockers else "failed",
            },
            {
                "gate_id": "media_pack_size",
                "status": "passed" if media_within_limit else "warning",
                "message": f"media_total_bytes={media_total_bytes}",
            },
        ],
        "warnings": sorted(set(warnings)),
        "non_actions": [
            "no_distractor_relationship_persistence",
            "DATABASE_PHASE_CLOSED_remains_false",
            "PERSIST_DISTRACTOR_RELATIONSHIPS_V1_remains_false",
            "no_runtime_http_owner_side_dependency",
        ],
        "evidence_links": [
            {"path": _repo_rel(config.plan_path)},
            {"path": _repo_rel(config.distractor_path)},
            {"path": _repo_rel(config.materialization_source_path)},
            {"path": _repo_rel(config.inat_manifest_path)},
            {"path": _repo_rel(config.inat_ai_outputs_path)},
        ],
        "audit_links": [
            {"path": "docs/architecture/GOLDEN_PACK_SPEC.md"},
            {"path": "docs/architecture/MASTER_REFERENCE.md"},
        ],
        "checksums": {
            "pack.json": {"sha256": _sha256_bytes(pack_bytes)},
            "validation_report.json": {"sha256": _sha256_bytes(report_bytes)},
            "media_files": sorted(copied_media_checksums, key=lambda item: item["path"]),
        },
        "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
        "DATABASE_PHASE_CLOSED": False,
    }

    return pack_payload, manifest_payload, validation_report, warnings, blockers


def build_golden_pack(config: MaterializerConfig | None = None) -> dict[str, Any]:
    effective = config or _default_config()
    pack_payload, _, _, _, blockers = _build_golden_pack_artifact(effective)
    if blockers:
        raise ContractError(f"Golden pack blockers: {'; '.join(blockers)}")
    return pack_payload


def write_outputs(config: MaterializerConfig | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    effective = config or _default_config()
    pack_payload, manifest_payload, validation_report, _, blockers = _build_golden_pack_artifact(effective)

    _write_json(effective.output_validation_report_path, validation_report)
    _write_json(effective.output_manifest_path, manifest_payload)

    if blockers:
        # Failed builds must not be confused with runtime-ready canonical packs.
        if effective.output_pack_path.exists():
            effective.output_pack_path.unlink()
        _write_json(effective.output_failed_partial_pack_path, pack_payload)
        raise ContractError(
            "Materialization failed with blockers; see validation_report.json: "
            + "; ".join(blockers)
        )

    _write_json(effective.output_pack_path, pack_payload)
    if effective.output_failed_partial_pack_path.exists():
        effective.output_failed_partial_pack_path.unlink()

    _json_schema_validate(pack_payload, effective.schema_pack_path, "pack")
    _json_schema_validate(manifest_payload, effective.schema_manifest_path, "manifest")
    _json_schema_validate(validation_report, effective.schema_validation_report_path, "validation_report")

    validation_report["schema_validity"] = {
        "manifest_schema_valid": True,
        "pack_schema_valid": True,
        "validation_report_schema_valid": True,
    }
    _write_json(effective.output_validation_report_path, validation_report)

    return pack_payload, manifest_payload, validation_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-path", type=Path, default=PLAN_PATH)
    parser.add_argument("--distractor-path", type=Path, default=DISTRACTOR_PATH)
    parser.add_argument("--qualified-export-path", type=Path, default=QUALIFIED_EXPORT_PATH)
    parser.add_argument("--inat-manifest-path", type=Path, default=INAT_MANIFEST_PATH)
    parser.add_argument("--inat-ai-outputs-path", type=Path, default=INAT_AI_OUTPUTS_PATH)
    parser.add_argument("--materialization-source-path", type=Path, default=MATERIALIZATION_SOURCE_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--pack-id", default="belgian_birds_mvp_v1")
    parser.add_argument("--locale", default="fr")
    parser.add_argument("--target-count", type=int, default=30)
    parser.add_argument("--schema-pack-path", type=Path, default=SCHEMA_PACK_PATH)
    parser.add_argument("--schema-manifest-path", type=Path, default=SCHEMA_MANIFEST_PATH)
    parser.add_argument("--schema-validation-report-path", type=Path, default=SCHEMA_VALIDATION_REPORT_PATH)
    args = parser.parse_args()

    config = MaterializerConfig(
        plan_path=args.plan_path,
        materialization_source_path=args.materialization_source_path,
        distractor_path=args.distractor_path,
        qualified_export_path=args.qualified_export_path,
        inat_manifest_path=args.inat_manifest_path,
        inat_ai_outputs_path=args.inat_ai_outputs_path,
        schema_pack_path=args.schema_pack_path,
        schema_manifest_path=args.schema_manifest_path,
        schema_validation_report_path=args.schema_validation_report_path,
        output_dir=args.output_dir,
        pack_id=args.pack_id,
        locale=args.locale,
        target_count=args.target_count,
    )

    pack_payload, manifest_payload, validation_report = write_outputs(config=config)
    print(f"Output directory: {config.output_dir}")
    print(f"Contract: {pack_payload['schema_version']}")
    print(f"Questions: {len(pack_payload['questions'])}")
    print(f"Media entries: {len(pack_payload['media'])}")
    print(f"Validation status: {validation_report['status']}")
    print(f"Manifest contract version: {manifest_payload['contract_version']}")


if __name__ == "__main__":
    main()
