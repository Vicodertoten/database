from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat

RUN_PREFIX = "golden_pack_v1_clean_room"
RUNS_ROOT = REPO_ROOT / "data" / "runs"
SEED_PATH = REPO_ROOT / "data" / "fixtures" / "golden_pack_v1_50_taxa_clean_room.json"
LABEL_OVERRIDES_PATH = REPO_ROOT / "data" / "fixtures" / "golden_pack_v1_label_overrides.json"
FLAGS = {
    "DATABASE_PHASE_CLOSED": False,
    "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
}
LOCALIZED_NAME_LANGUAGES = ("fr", "en", "nl")
INAT_SIMILAR_SPECIES_API = "https://api.inaturalist.org/v1/identifications/similar_species"

EXTERNAL_STAGES = {
    "source_inat_refresh",
    "normalization",
    "pmp_gemini",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _redact_for_artifact(payload)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _redact_database_url(value: str) -> str:
    if not value.startswith(("postgresql://", "postgres://")):
        return re.sub(
            r"(postgres(?:ql)?://[^\s'\",]+)",
            lambda match: _redact_database_url(match.group(1)),
            value,
        )
    parsed = urlparse(value)
    if not parsed.hostname:
        return "***REDACTED_DATABASE_URL***"
    username = parsed.username or ""
    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    auth = f"{username}:***@" if username else ""
    return urlunparse(
        (
            parsed.scheme,
            f"{auth}{host}{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _database_url_metadata(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {}
    parsed = urlparse(database_url)
    return {
        "database_url_redacted": _redact_database_url(database_url),
        "database_host": parsed.hostname,
        "database_port": parsed.port,
    }


def _redact_for_artifact(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_database_url(value)
    if isinstance(value, list):
        return [_redact_for_artifact(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key == "database_url":
                redacted["database_url_redacted"] = _redact_for_artifact(item)
                continue
            redacted[key] = _redact_for_artifact(item)
        return redacted
    return value


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _new_run_dir(output_root: Path | None = None) -> tuple[str, Path]:
    root = output_root or RUNS_ROOT
    run_id = f"{RUN_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for rel in (
        "seed",
        "source_fetch",
        "raw",
        "normalized",
        "qualified",
        "pmp",
        "media_prefilter",
        "localized_names",
        "distractors",
        "candidate_pool",
        "selection",
        "golden_pack",
        "reports",
    ):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def _stage_records() -> list[dict[str, Any]]:
    return [
        {"step": "seed_validation", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "source_inat_refresh", "status": "planned", "executable_local": False, "next_command": "python scripts/fetch_inat_snapshot.py"},
        {"step": "pmp_gemini", "status": "planned", "executable_local": False, "next_command": "python scripts/qualify_inat_snapshot.py"},
        {"step": "normalization", "status": "planned", "executable_local": False, "next_command": "python scripts/run_pipeline.py"},
        {"step": "media_prefilter_report", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "fr_labels", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "distractors", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "candidate_pool", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "select_30", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "materialization", "status": "planned", "executable_local": True, "next_command": "python scripts/materialize_golden_pack_belgian_birds_mvp_v1.py"},
        {"step": "validation", "status": "planned", "executable_local": True, "next_command": "internal"},
        {"step": "promotion_check", "status": "planned", "executable_local": True, "next_command": "internal"},
    ]


def _first_incomplete_stage_index(stages: list[dict[str, Any]]) -> int:
    for idx, row in enumerate(stages):
        if row.get("status") != "completed":
            return idx
    return len(stages)


def _persist(run_dir: Path, manifest: dict[str, Any], stages: list[dict[str, Any]]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(run_dir / "run_manifest.json", manifest)
    _write_json(run_dir / "pipeline_plan.json", {"steps": stages})


def _source_context(run_id: str, *, max_observations_per_taxon: int) -> dict[str, Any]:
    snapshot_id = f"{run_id}_inat"
    snapshot_root = REPO_ROOT / "data" / "raw" / "inaturalist"
    return {
        "snapshot_id": snapshot_id,
        "snapshot_root": str(snapshot_root),
        "snapshot_dir": str(snapshot_root / snapshot_id),
        "pilot_taxa_path": str(SEED_PATH),
        "max_observations_per_taxon": max_observations_per_taxon,
        "timeout_seconds": 30,
        "country_code": "BE",
    }


def _fetch_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/fetch_inat_snapshot.py",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--pilot-taxa-path",
        str(context["pilot_taxa_path"]),
        "--max-observations-per-taxon",
        str(context["max_observations_per_taxon"]),
        "--timeout-seconds",
        str(context["timeout_seconds"]),
        "--country-code",
        str(context["country_code"]),
    ]


def _normalization_context(run_dir: Path, source_context: dict[str, Any], *, database_url: str | None) -> dict[str, Any]:
    return {
        "snapshot_id": source_context["snapshot_id"],
        "snapshot_root": source_context["snapshot_root"],
        "normalized_path": str(run_dir / "normalized" / "normalized_snapshot.json"),
        "qualified_path": str(run_dir / "qualified" / "qualified_snapshot.json"),
        "export_path": str(run_dir / "qualified" / "export_bundle.json"),
        "database_url": database_url,
        **_database_url_metadata(database_url),
    }


def _normalization_command(context: dict[str, Any]) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_pipeline.py",
        "--source-mode",
        "inat_snapshot",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--normalized-path",
        str(context["normalized_path"]),
        "--qualified-path",
        str(context["qualified_path"]),
        "--export-path",
        str(context["export_path"]),
        "--qualifier-mode",
        "cached",
        "--qualification-policy",
        "v1",
        "--ai-review-contract-version",
        "pedagogical_media_profile_v1",
    ]
    if context.get("database_url"):
        command.extend(["--database-url", str(context["database_url"])])
    return command


def _pmp_context(source_context: dict[str, Any]) -> dict[str, Any]:
    snapshot_dir = Path(str(source_context["snapshot_dir"]))
    return {
        "snapshot_id": source_context["snapshot_id"],
        "snapshot_root": source_context["snapshot_root"],
        "snapshot_dir": str(snapshot_dir),
        "ai_outputs_path": str(snapshot_dir / "ai_outputs.json"),
        "gemini_concurrency": 4,
        "max_retries": 2,
        "request_interval_seconds": 0.0,
        "ai_review_contract_version": "pedagogical_media_profile_v1",
        "ai_role": "signal_only",
    }


def _pmp_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/qualify_inat_snapshot.py",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--gemini-concurrency",
        str(context["gemini_concurrency"]),
        "--max-retries",
        str(context["max_retries"]),
        "--request-interval-seconds",
        str(context["request_interval_seconds"]),
        "--ai-review-contract-version",
        str(context["ai_review_contract_version"]),
    ]


def _ai_outputs_summary(ai_outputs_path: Path) -> dict[str, int]:
    if not ai_outputs_path.exists():
        return {
            "processed_media_count": 0,
            "ai_valid_output_count": 0,
            "ai_failed_output_count": 0,
        }
    payload = _load_json(ai_outputs_path)
    rows = [value for key, value in payload.items() if isinstance(key, str) and "::" in key and isinstance(value, dict)]
    return {
        "processed_media_count": len(rows),
        "ai_valid_output_count": sum(1 for row in rows if row.get("status") == "ok" or isinstance(row.get("pedagogical_media_profile"), dict)),
        "ai_failed_output_count": sum(1 for row in rows if row.get("status") not in {None, "ok"} and not isinstance(row.get("pedagogical_media_profile"), dict)),
    }


def _ai_outputs_match_pmp_contract(ai_outputs_path: Path) -> bool:
    if not ai_outputs_path.exists():
        return False
    payload = _load_json(ai_outputs_path)
    rows = [value for key, value in payload.items() if isinstance(key, str) and "::" in key and isinstance(value, dict)]
    if not rows:
        return False
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    return bool(ok_rows) and all(
        row.get("review_contract_version") == "pedagogical_media_profile_v1"
        and isinstance(row.get("pedagogical_media_profile"), dict)
        for row in ok_rows
    )


def _clear_snapshot_ai_outputs_pointer(snapshot_dir: Path) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = _load_json(manifest_path)
    if manifest.get("ai_outputs_path") is not None:
        manifest["ai_outputs_path"] = None
        _write_json(manifest_path, manifest)


def _materialization_context(run_dir: Path, source_context: dict[str, Any], pmp_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_path": str(run_dir / "selection" / "golden_pack_selection.json"),
        "inat_manifest_path": str(Path(source_context["snapshot_dir"]) / "manifest.json"),
        "inat_ai_outputs_path": str(pmp_context["ai_outputs_path"]),
        "output_dir": str(run_dir / "golden_pack"),
    }


def _materialization_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/materialize_golden_pack_belgian_birds_mvp_v1.py",
        "--selection-path",
        str(context["selection_path"]),
        "--inat-manifest-path",
        str(context["inat_manifest_path"]),
        "--inat-ai-outputs-path",
        str(context["inat_ai_outputs_path"]),
        "--output-dir",
        str(context["output_dir"]),
    ]


def _set_stage_command(stages: list[dict[str, Any]], name: str, command: list[str]) -> None:
    command_str = " ".join(shlex.quote(part) for part in command)
    for row in stages:
        if row["step"] == name:
            row["next_command"] = command_str
            return


def _validate_seed(run_dir: Path) -> dict[str, Any]:
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    if not isinstance(seed, list):
        raise RuntimeError("seed_must_be_json_array")
    canonical_ids = [str(row.get("canonical_taxon_id") or "").strip() for row in seed if isinstance(row, dict)]
    source_ids = [str(row.get("source_taxon_id") or "").strip() for row in seed if isinstance(row, dict)]
    blockers: list[str] = []
    if len(seed) != 50:
        blockers.append(f"seed_count_expected_50_actual_{len(seed)}")
    if len(canonical_ids) != len(set(canonical_ids)):
        blockers.append("duplicate_canonical_taxon_id")
    if len(source_ids) != len(set(source_ids)):
        blockers.append("duplicate_source_taxon_id")
    if any(not item for item in canonical_ids):
        blockers.append("blank_canonical_taxon_id")
    if any(not item for item in source_ids):
        blockers.append("blank_source_taxon_id")

    report = {
        "schema_version": "golden_pack_clean_room_seed_validation.v1",
        "seed_path": str(SEED_PATH.relative_to(REPO_ROOT)),
        "seed_sha256": _sha256(SEED_PATH),
        "taxa_count": len(seed),
        "blockers": blockers,
    }
    _write_json(run_dir / "seed" / "seed_validation.json", report)
    if blockers:
        raise RuntimeError("seed_validation_failed:" + ",".join(blockers))
    return report


def _run_subprocess_stage(
    run_dir: Path,
    report_rel: str,
    command: list[str],
    *,
    extra: dict[str, Any] | None = None,
    stream_log_rel: str | None = None,
) -> tuple[bool, str]:
    if stream_log_rel is None:
        result = subprocess.run(command, cwd=REPO_ROOT, check=False, capture_output=True, text=True)
        stdout = result.stdout
        stderr = result.stderr
        returncode = int(result.returncode)
    else:
        log_path = run_dir / stream_log_rel
        log_path.parent.mkdir(parents=True, exist_ok=True)
        tail_parts: list[str] = []
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                tail_parts.append(line)
                while sum(len(part) for part in tail_parts) > 4000 and len(tail_parts) > 1:
                    tail_parts.pop(0)
            returncode = int(process.wait())
        stdout = "".join(tail_parts)
        stderr = ""
    report = {
        "schema_version": "golden_pack_clean_room_subprocess_stage.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "returncode": returncode,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        **(extra or {}),
    }
    if stream_log_rel is not None:
        report["stream_log_path"] = stream_log_rel
    _write_json(run_dir / report_rel, report)
    if returncode != 0:
        return False, f"command_failed_exit_{returncode}"
    return True, "completed"


def _media_to_taxon_map(snapshot_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for seed in manifest.get("taxon_seeds", []):
        if not isinstance(seed, dict):
            continue
        taxon_id = str(seed.get("canonical_taxon_id") or "").strip()
        response_path = str(seed.get("response_path") or "").strip()
        if not taxon_id or not response_path:
            continue
        payload_path = snapshot_dir / response_path
        if not payload_path.exists():
            continue
        payload = _load_json(payload_path)
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            photos = result.get("photos") if isinstance(result.get("photos"), list) else []
            for photo in photos:
                if not isinstance(photo, dict):
                    continue
                media_id = str(photo.get("id") or "").strip()
                if media_id:
                    out.setdefault(media_id, taxon_id)
    return out


def _ai_basic_score(ai_outputs: dict[str, Any], source_media_id: str) -> float:
    profile = (ai_outputs.get(f"inaturalist::{source_media_id}") or {}).get("pedagogical_media_profile")
    if not isinstance(profile, dict):
        return 0.0
    scores = profile.get("scores") if isinstance(profile.get("scores"), dict) else {}
    usage_scores = scores.get("usage_scores") if isinstance(scores.get("usage_scores"), dict) else {}
    raw = usage_scores.get("basic_identification", scores.get("global_quality_score", 0))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _reference_labels() -> tuple[dict[str, str], dict[str, str]]:
    plan = _load_json(mat.PLAN_PATH)
    return mat._target_label_safe_fr_map(plan), mat._option_label_safe_fr_map(plan)


def _reference_distractors() -> dict[str, list[Any]]:
    return mat._candidate_refs_by_target(_load_json(mat.DISTRACTOR_PATH))


def _seed_rows() -> list[dict[str, Any]]:
    return [row for row in json.loads(SEED_PATH.read_text(encoding="utf-8")) if isinstance(row, dict)]


def _safe_label(value: object) -> str:
    label = str(value or "").strip()
    norm = mat.normalize_localized_name_for_compare(label)
    if not label or not norm:
        return ""
    if norm in {"unknown", "inconnu", "non renseigne", "non renseigné", "n/a", "na"}:
        return ""
    return label


def _label_overrides() -> dict[str, dict[str, str]]:
    if not LABEL_OVERRIDES_PATH.exists():
        return {}
    payload = json.loads(LABEL_OVERRIDES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("labels") if isinstance(payload.get("labels"), dict) else payload
    overrides: dict[str, dict[str, str]] = {}
    if not isinstance(rows, dict):
        return overrides
    for taxon_id, value in rows.items():
        if isinstance(value, str):
            label = _safe_label(value)
            if label:
                overrides[str(taxon_id)] = {"fr": label}
            continue
        if isinstance(value, dict):
            labels = {
                str(language).lower(): label
                for language, raw_label in value.items()
                if (label := _safe_label(raw_label))
            }
            if labels:
                overrides[str(taxon_id)] = labels
    return overrides


def _first_taxon_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    return payload if isinstance(payload, dict) else {}


def _taxon_payload_for_seed(snapshot_dir: Path, seed: dict[str, Any]) -> dict[str, Any]:
    rel = str(seed.get("taxon_payload_path") or "").strip()
    if not rel:
        return {}
    path = snapshot_dir / rel
    if not path.exists():
        return {}
    payload = _load_json(path)
    record = dict(_first_taxon_result(payload))
    if isinstance(payload.get("localized_taxa"), dict):
        record["localized_taxa"] = payload["localized_taxa"]
    return record


def _valid_common_names(record: dict[str, Any], *, language: str) -> list[tuple[int, str]]:
    wanted = language.lower()
    candidates: list[tuple[int, str]] = []
    for key in ("common_names", "names", "taxon_names", "all_names"):
        names = record.get(key)
        if not isinstance(names, list):
            continue
        for fallback_position, item in enumerate(names):
            if not isinstance(item, dict):
                label = _safe_label(item)
                if label:
                    candidates.append((10_000 + fallback_position, label))
                continue
            if item.get("is_valid") is False:
                continue
            lang = str(item.get("locale") or item.get("language") or "").lower()
            lexicon = str(item.get("lexicon") or "").lower()
            if not _matches_language(lang=lang, lexicon=lexicon, wanted=wanted):
                continue
            label = _safe_label(item.get("name"))
            if not label:
                continue
            try:
                position = int(item.get("position"))
            except (TypeError, ValueError):
                position = 10_000 + fallback_position
            candidates.append((position, label))
    return sorted(candidates, key=lambda item: (item[0], item[1].lower()))


def _available_common_names_by_language(record: dict[str, Any]) -> dict[str, list[str]]:
    names_by_language: dict[str, list[tuple[int, str]]] = {}
    for key in ("common_names", "names", "taxon_names", "all_names"):
        names = record.get(key)
        if not isinstance(names, list):
            continue
        for fallback_position, item in enumerate(names):
            if not isinstance(item, dict) or item.get("is_valid") is False:
                continue
            lang = str(item.get("locale") or item.get("language") or "").lower()
            label = _safe_label(item.get("name"))
            if not lang or not label:
                continue
            try:
                position = int(item.get("position"))
            except (TypeError, ValueError):
                position = 10_000 + fallback_position
            names_by_language.setdefault(lang, []).append((position, label))
    return {
        language: [
            label
            for _, label in sorted(values, key=lambda item: (item[0], item[1].lower()))
        ]
        for language, values in sorted(names_by_language.items())
    }


def _label_from_taxon_record(record: dict[str, Any], *, language: str = "fr") -> str:
    wanted = language.lower()
    common_names = _valid_common_names(record, language=wanted)
    if common_names:
        return common_names[0][1]
    for key in ("preferred_common_name", "english_common_name", "common_name"):
        label = _safe_label(record.get(key))
        if label:
            return label
    return ""


def _matches_language(*, lang: str, lexicon: str, wanted: str) -> bool:
    aliases = {
        "fr": {"fr", "fra", "fre", "french", "français", "francais"},
        "en": {"en", "eng", "english", "anglais"},
        "nl": {"nl", "nld", "dut", "dutch", "nederlands", "neerlandais"},
    }
    accepted = aliases.get(wanted, {wanted})
    return lang in accepted or lexicon in accepted


def _localized_record_from_payload(payload: dict[str, Any], language: str) -> dict[str, Any]:
    localized = payload.get("localized_taxa")
    if isinstance(localized, dict):
        value = localized.get(language)
        if isinstance(value, dict) and "error" not in value:
            return _first_taxon_result(value)
    return _first_taxon_result(payload)


def _localized_labels_from_taxon_record(record: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for language in LOCALIZED_NAME_LANGUAGES:
        candidate = _localized_record_from_payload(record, language)
        label = _label_from_taxon_record(candidate, language=language)
        if label:
            labels[language] = label
    return labels


def _all_available_common_names_from_taxon_record(record: dict[str, Any]) -> dict[str, list[str]]:
    names: dict[str, list[str]] = {}
    records = [_first_taxon_result(record)]
    localized = record.get("localized_taxa")
    if isinstance(localized, dict):
        for value in localized.values():
            if isinstance(value, dict) and "error" not in value:
                records.append(_first_taxon_result(value))
    for candidate in records:
        for language, values in _available_common_names_by_language(candidate).items():
            existing = names.setdefault(language, [])
            for label in values:
                if label not in existing:
                    existing.append(label)
    return names


def _fetch_inat_taxon_record(
    source_taxon_id: str,
    *,
    language: str = "fr",
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    from database_core.adapters.inaturalist_harvest import INAT_TAXA_API, _fetch_json

    payload = _fetch_json(
        INAT_TAXA_API,
        params={
            "taxon_id": source_taxon_id,
            "per_page": "1",
            "locale": language,
            "all_names": "true",
            "preferred_place_id": "7008",
        },
        timeout_seconds=int(timeout_seconds),
    )
    return _first_taxon_result(payload if isinstance(payload, dict) else {})


def _fetch_inat_taxon_fr_record(source_taxon_id: str, *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    return _fetch_inat_taxon_record(source_taxon_id, language="fr", timeout_seconds=timeout_seconds)


def _fetch_localized_taxon_labels(
    source_taxon_id: str,
    *,
    timeout_seconds: float = 20.0,
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for language in LOCALIZED_NAME_LANGUAGES:
        try:
            record = _fetch_inat_taxon_record(
                source_taxon_id,
                language=language,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            continue
        label = _label_from_taxon_record(record, language=language)
        if label:
            labels[language] = label
    return labels


def _legacy_labels() -> tuple[dict[str, str], dict[str, str]]:
    try:
        return _reference_labels()
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return {}, {}


def _legacy_distractors() -> dict[str, list[Any]]:
    try:
        return _reference_distractors()
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return {}


def _build_fr_label_artifact(run_dir: Path, source_context: dict[str, Any]) -> dict[str, Any]:
    snapshot_dir = Path(str(source_context["snapshot_dir"]))
    manifest = _load_json(snapshot_dir / "manifest.json")
    seed_by_target = {
        str(seed.get("canonical_taxon_id") or ""): seed
        for seed in _seed_rows()
        if isinstance(seed, dict)
    }
    seed_by_target.update(
        {
            str(seed.get("canonical_taxon_id") or ""): seed
            for seed in manifest.get("taxon_seeds", [])
            if isinstance(seed, dict)
        }
    )
    label_overrides = _label_overrides()
    target_labels: dict[str, str] = {}
    option_labels: dict[str, str] = {}
    target_labels_by_language: dict[str, dict[str, str]] = {
        language: {} for language in LOCALIZED_NAME_LANGUAGES
    }
    option_labels_by_language: dict[str, dict[str, str]] = {
        language: {} for language in LOCALIZED_NAME_LANGUAGES
    }
    option_labels_by_language["fr"].update(option_labels)
    provenance: dict[str, dict[str, Any]] = {}
    fetched_records: dict[str, dict[str, Any]] = {}
    available_names_by_taxon: dict[str, dict[str, list[str]]] = {}
    preferred_labels_by_taxon: dict[str, dict[str, str]] = {}
    missing: list[str] = []

    for target_id in sorted(tid for tid in seed_by_target if tid):
        override = label_overrides.get(target_id, {})
        if override:
            for language, label in override.items():
                target_labels_by_language.setdefault(language, {})[target_id] = label
                option_labels_by_language.setdefault(language, {})[target_id] = label
            label = override.get("fr", "")
            if label:
                target_labels[target_id] = label
                option_labels[target_id] = label
                provenance[target_id] = {"source": "curated_label_override"}
                preferred_labels_by_taxon[target_id] = dict(override)
                continue

        seed = seed_by_target[target_id]
        source_taxon_id = str(seed.get("source_taxon_id") or "").strip()
        record = _taxon_payload_for_seed(snapshot_dir, seed)
        localized_labels = _localized_labels_from_taxon_record(record) if record else {}
        available_names = _all_available_common_names_from_taxon_record(record) if record else {}
        fetch_error = None
        if source_taxon_id and "fr" not in localized_labels:
            try:
                record = _fetch_inat_taxon_fr_record(source_taxon_id)
                fetched_records[source_taxon_id] = record
            except Exception as exc:  # pragma: no cover - network behavior is integration-only.
                fetch_error = f"{type(exc).__name__}: {exc}"
            else:
                localized_labels.update(_localized_labels_from_taxon_record(record))
                for language, values in _all_available_common_names_from_taxon_record(record).items():
                    existing = available_names.setdefault(language, [])
                    for value in values:
                        if value not in existing:
                            existing.append(value)

        if available_names:
            available_names_by_taxon[target_id] = available_names

        for language, localized_label in localized_labels.items():
            target_labels_by_language.setdefault(language, {})[target_id] = localized_label
            option_labels_by_language.setdefault(language, {})[target_id] = localized_label
        if localized_labels:
            preferred_labels_by_taxon[target_id] = dict(localized_labels)

        label = localized_labels.get("fr", "")
        if label:
            target_labels[target_id] = label
            option_labels[target_id] = label
            provenance[target_id] = {
                "source": "inat_locale_fr",
                "source_taxon_id": source_taxon_id,
            }
        else:
            missing.append(target_id)
            provenance[target_id] = {
                "source": "missing",
                "source_taxon_id": source_taxon_id,
                "fetch_error": fetch_error,
            }

    payload = {
        "schema_version": "golden_pack_clean_room_fr_labels.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_labels": target_labels,
        "option_labels": option_labels,
        "target_labels_by_language": target_labels_by_language,
        "option_labels_by_language": option_labels_by_language,
        "available_names_by_taxon": available_names_by_taxon,
        "preferred_labels_by_taxon": preferred_labels_by_taxon,
        "provenance": provenance,
        "missing_target_labels": missing,
        "fetched_inat_taxa_locale_fr": fetched_records,
        "fetched_inat_taxa": fetched_records,
        "summary": {
            "target_count": len(seed_by_target),
            "target_label_count": len(target_labels),
            "missing_target_label_count": len(missing),
            "option_label_count": len(option_labels),
            "target_label_counts_by_language": {
                language: len(target_labels_by_language.get(language, {}))
                for language in LOCALIZED_NAME_LANGUAGES
            },
            "option_label_counts_by_language": {
                language: len(option_labels_by_language.get(language, {}))
                for language in LOCALIZED_NAME_LANGUAGES
            },
        },
    }
    _write_json(run_dir / "localized_names" / "fr_labels.json", payload)
    return payload


def _taxonomy_info_from_record(record: dict[str, Any], seed: dict[str, Any]) -> dict[str, str]:
    info: dict[str, str] = {}
    ancestors = record.get("ancestors")
    if isinstance(ancestors, list):
        for ancestor in ancestors:
            if not isinstance(ancestor, dict):
                continue
            rank = str(ancestor.get("rank") or "").strip()
            name = str(ancestor.get("name") or "").strip()
            if rank and name:
                info[rank] = name
    rank = str(record.get("rank") or seed.get("canonical_rank") or "").strip()
    name = str(record.get("name") or seed.get("accepted_scientific_name") or "").strip()
    if rank and name:
        info[rank] = name
    if "genus" not in info:
        scientific = str(seed.get("accepted_scientific_name") or "").strip()
        if scientific:
            info["genus"] = scientific.split()[0]
    return info


def _taxonomy_id_info_from_record(record: dict[str, Any], seed: dict[str, Any]) -> dict[str, str]:
    del seed
    info: dict[str, str] = {}
    ancestors = record.get("ancestors")
    if isinstance(ancestors, list):
        for ancestor in ancestors:
            if not isinstance(ancestor, dict):
                continue
            rank = str(ancestor.get("rank") or "").strip()
            taxon_id = str(ancestor.get("id") or "").strip()
            if rank and taxon_id:
                info[rank] = taxon_id
    rank = str(record.get("rank") or "").strip()
    taxon_id = str(record.get("id") or "").strip()
    if rank and taxon_id:
        info[rank] = taxon_id
    return info


def _fetch_inat_similar_species(
    source_taxon_id: str,
    *,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    from database_core.adapters.inaturalist_harvest import _fetch_json

    return _fetch_json(
        INAT_SIMILAR_SPECIES_API,
        params={"taxon_id": source_taxon_id},
        timeout_seconds=timeout_seconds,
    )


def _similar_species_cache_path(run_dir: Path, target_id: str) -> Path:
    return run_dir / "distractors" / "similar_species_raw" / f"{target_id.replace(':', '_')}.json"


def _load_or_fetch_similar_species(
    run_dir: Path,
    *,
    target_id: str,
    source_taxon_id: str,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    cache_path = _similar_species_cache_path(run_dir, target_id)
    if cache_path.exists():
        return _load_json(cache_path)
    try:
        raw_payload = _fetch_inat_similar_species(
            source_taxon_id,
            timeout_seconds=timeout_seconds,
        )
        payload = {
            "status": "ok",
            "endpoint": INAT_SIMILAR_SPECIES_API,
            "params": {"taxon_id": source_taxon_id},
            "target_canonical_taxon_id": target_id,
            "source_taxon_id": source_taxon_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "raw_payload": raw_payload,
        }
    except Exception as exc:  # pragma: no cover - network behavior is integration-only.
        payload = {
            "status": "error",
            "endpoint": INAT_SIMILAR_SPECIES_API,
            "params": {"taxon_id": source_taxon_id},
            "target_canonical_taxon_id": target_id,
            "source_taxon_id": source_taxon_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
            "raw_payload": {},
        }
    _write_json(cache_path, payload)
    return payload


def _parse_similar_species_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else payload
    results = raw.get("results") if isinstance(raw, dict) else []
    candidates: list[dict[str, Any]] = []
    if not isinstance(results, list):
        return candidates
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            continue
        taxon = result.get("taxon") if isinstance(result.get("taxon"), dict) else result
        source_taxon_id = str(taxon.get("id") or "").strip()
        if not source_taxon_id:
            continue
        candidates.append(
            {
                "source_taxon_id": source_taxon_id,
                "scientific_name": str(taxon.get("name") or "").strip(),
                "rank": str(taxon.get("rank") or "").strip(),
                "preferred_common_name": _safe_label(taxon.get("preferred_common_name")),
                "count": result.get("count"),
                "source_rank_order": index,
            }
        )
    return candidates


def _fetch_inat_observed_taxa_for_parent(
    parent_taxon_id: str,
    *,
    timeout_seconds: int = 20,
) -> list[dict[str, Any]]:
    from database_core.adapters.inaturalist_harvest import INAT_OBSERVATION_TAXA_API, _fetch_json

    payload = _fetch_json(
        INAT_OBSERVATION_TAXA_API,
        params={
            "taxon_id": parent_taxon_id,
            "place_id": "7008",
            "preferred_place_id": "7008",
            "locale": "fr",
            "rank": "species",
            "quality_grade": "research",
            "photos": "true",
            "per_page": "30",
        },
        timeout_seconds=timeout_seconds,
    )
    results = payload.get("results") if isinstance(payload, dict) else []
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def _build_distractor_artifact(run_dir: Path, source_context: dict[str, Any]) -> dict[str, Any]:
    labels_payload = _load_json(run_dir / "localized_names" / "fr_labels.json")
    target_labels = {
        str(k): str(v)
        for k, v in (labels_payload.get("target_labels") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    target_labels_by_language = {
        language: {
            str(k): str(v)
            for k, v in (
                (labels_payload.get("target_labels_by_language") or {}).get(language, {})
            ).items()
            if str(k).strip() and str(v).strip()
        }
        for language in LOCALIZED_NAME_LANGUAGES
    }
    option_labels_by_language = {
        language: {
            str(k): str(v)
            for k, v in (
                (labels_payload.get("option_labels_by_language") or {}).get(language, {})
            ).items()
            if str(k).strip() and str(v).strip()
        }
        for language in LOCALIZED_NAME_LANGUAGES
    }
    fetched_records = labels_payload.get("fetched_inat_taxa_locale_fr")
    fetched_records = fetched_records if isinstance(fetched_records, dict) else {}
    snapshot_dir = Path(str(source_context["snapshot_dir"]))
    manifest = _load_json(snapshot_dir / "manifest.json")
    manifest_seed = {
        str(seed.get("canonical_taxon_id") or ""): seed
        for seed in manifest.get("taxon_seeds", [])
        if isinstance(seed, dict)
    }
    seed_by_target = {
        str(seed.get("canonical_taxon_id") or ""): seed
        for seed in _seed_rows()
        if isinstance(seed, dict)
    }
    seed_by_target.update(manifest_seed)
    records_by_target = {
        target_id: _taxon_payload_for_seed(snapshot_dir, seed)
        for target_id, seed in seed_by_target.items()
        if target_id
    }
    taxonomy = {
        target_id: _taxonomy_info_from_record(records_by_target.get(target_id, {}), seed)
        for target_id, seed in seed_by_target.items()
        if target_id
    }
    taxonomy_ids = {
        target_id: _taxonomy_id_info_from_record(records_by_target.get(target_id, {}), seed)
        for target_id, seed in seed_by_target.items()
        if target_id
    }
    source_taxon_to_canonical = {
        str(seed.get("source_taxon_id") or "").strip(): target_id
        for target_id, seed in seed_by_target.items()
        if target_id and str(seed.get("source_taxon_id") or "").strip()
    }
    projected_records: list[dict[str, Any]] = []
    by_target: dict[str, list[dict[str, Any]]] = {}
    localized_label_cache: dict[str, dict[str, str]] = {}

    def add_candidate(
        *,
        target_id: str,
        ref_type: str,
        ref_id: str,
        label: str,
        source: str,
        rank: int,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        target_label = target_labels.get(target_id, "")
        label = _safe_label(label)
        if not target_id or not ref_id or not label:
            return False
        if ref_type == "canonical_taxon" and ref_id == target_id:
            return False
        existing = by_target.setdefault(target_id, [])
        seen = {
            mat.normalize_localized_name_for_compare(target_label),
            *[
                mat.normalize_localized_name_for_compare(str(row.get("display_label") or ""))
                for row in existing
            ],
        }
        label_norm = mat.normalize_localized_name_for_compare(label)
        if not label_norm or label_norm in seen:
            return False
        row = {
            "status": "candidate",
            "target_canonical_taxon_id": target_id,
            "candidate_taxon_ref_type": ref_type,
            "candidate_taxon_ref_id": ref_id,
            "display_label": label,
            "localized_labels": {
                language: option_labels_by_language.get(language, {}).get(ref_id, "")
                for language in LOCALIZED_NAME_LANGUAGES
                if option_labels_by_language.get(language, {}).get(ref_id, "")
            },
            "target_localized_labels": {
                language: target_labels_by_language.get(language, {}).get(target_id, "")
                for language in LOCALIZED_NAME_LANGUAGES
                if target_labels_by_language.get(language, {}).get(target_id, "")
            },
            "source_rank": rank,
            "source": source,
        }
        if extra:
            row.update(extra)
        existing.append(row)
        projected_records.append(row)
        return True

    for target_id in sorted(seed_by_target):
        if target_id not in target_labels:
            by_target[target_id] = []
            continue
        target_source_taxon_id = str(seed_by_target[target_id].get("source_taxon_id") or "").strip()
        if target_source_taxon_id:
            similar_payload = _load_or_fetch_similar_species(
                run_dir,
                target_id=target_id,
                source_taxon_id=target_source_taxon_id,
            )
        else:
            similar_payload = {"status": "missing_source_taxon_id", "raw_payload": {}}
        for similar in _parse_similar_species_candidates(similar_payload):
            if len(by_target.get(target_id, [])) >= 3:
                break
            source_taxon_id = str(similar.get("source_taxon_id") or "").strip()
            if (
                not source_taxon_id
                or source_taxon_id == target_source_taxon_id
                or str(similar.get("rank") or "").strip().lower() != "species"
            ):
                continue
            canonical_ref = source_taxon_to_canonical.get(source_taxon_id)
            if canonical_ref == target_id:
                continue
            ref_type = "canonical_taxon" if canonical_ref else "referenced_taxon"
            ref_id = canonical_ref or f"inat:{source_taxon_id}"
            if canonical_ref:
                localized = {
                    language: target_labels_by_language.get(language, {}).get(canonical_ref, "")
                    for language in LOCALIZED_NAME_LANGUAGES
                }
            else:
                if source_taxon_id not in localized_label_cache:
                    localized_label_cache[source_taxon_id] = _fetch_localized_taxon_labels(
                        source_taxon_id
                    )
                localized = localized_label_cache[source_taxon_id]
                if "fr" not in localized and similar.get("preferred_common_name"):
                    localized["fr"] = str(similar["preferred_common_name"])
            for language, localized_label in localized.items():
                if localized_label:
                    option_labels_by_language.setdefault(language, {})[ref_id] = localized_label
            label = target_labels.get(canonical_ref or "", "") or localized.get("fr", "")
            add_candidate(
                target_id=target_id,
                ref_type=ref_type,
                ref_id=ref_id,
                label=label,
                source="inaturalist_similar_species",
                rank=10 + int(similar.get("source_rank_order") or 0),
                extra={
                    "candidate_source_taxon_id": source_taxon_id,
                    "candidate_scientific_name": similar.get("scientific_name", ""),
                    "similar_species_count": similar.get("count"),
                },
            )

        for source, rank_key, rank in (
            ("taxonomic_neighbor_same_genus", "genus", 200),
            ("taxonomic_neighbor_same_family", "family", 300),
            ("taxonomic_neighbor_same_order", "order", 400),
        ):
            if len(by_target.get(target_id, [])) >= 3:
                break
            target_rank_value = taxonomy.get(target_id, {}).get(rank_key)
            if not target_rank_value:
                continue
            for other_id in sorted(seed_by_target):
                if len(by_target.get(target_id, [])) >= 3:
                    break
                if other_id == target_id:
                    continue
                if taxonomy.get(other_id, {}).get(rank_key) != target_rank_value:
                    continue
                add_candidate(
                    target_id=target_id,
                    ref_type="canonical_taxon",
                    ref_id=other_id,
                    label=target_labels.get(other_id, ""),
                    source=source,
                    rank=rank,
                )

        for source, rank_key, rank in (
            ("inat_observed_same_family", "family", 500),
            ("inat_observed_same_order", "order", 600),
        ):
            if len(by_target.get(target_id, [])) >= 3:
                break
            parent_taxon_id = taxonomy_ids.get(target_id, {}).get(rank_key)
            if not parent_taxon_id:
                continue
            try:
                observed_taxa = _fetch_inat_observed_taxa_for_parent(parent_taxon_id)
            except Exception:
                observed_taxa = []
            for observed in observed_taxa:
                if len(by_target.get(target_id, [])) >= 3:
                    break
                source_taxon_id = str(observed.get("id") or "").strip()
                if not source_taxon_id or source_taxon_id == target_source_taxon_id:
                    continue
                canonical_ref = source_taxon_to_canonical.get(source_taxon_id)
                if canonical_ref == target_id:
                    continue
                ref_type = "canonical_taxon" if canonical_ref else "referenced_taxon"
                ref_id = canonical_ref or f"inat:{source_taxon_id}"
                localized = (
                    {
                        language: target_labels_by_language.get(language, {}).get(
                            canonical_ref or "", ""
                        )
                        for language in LOCALIZED_NAME_LANGUAGES
                    }
                    if canonical_ref
                    else _localized_labels_from_taxon_record(observed)
                )
                for language, localized_label in localized.items():
                    if localized_label:
                        option_labels_by_language.setdefault(language, {})[ref_id] = localized_label
                label = target_labels.get(canonical_ref or "", "") or localized.get("fr", "")
                add_candidate(
                    target_id=target_id,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    label=label,
                    source=source,
                    rank=rank,
                )

    payload = {
        "schema_version": "golden_pack_clean_room_distractors.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projected_records": sorted(
            projected_records,
            key=lambda row: (
                str(row.get("target_canonical_taxon_id") or ""),
                int(row.get("source_rank") or 0),
                str(row.get("candidate_taxon_ref_type") or ""),
                str(row.get("candidate_taxon_ref_id") or ""),
            ),
        ),
        "summary": {
            "target_count": len(seed_by_target),
            "targets_with_three_label_safe_distractors": sum(
                1 for rows in by_target.values() if len(rows) >= 3
            ),
            "candidate_count": len(projected_records),
            "source_counts": {
                source: sum(1 for row in projected_records if row.get("source") == source)
                for source in sorted({str(row.get("source") or "") for row in projected_records})
                if source
            },
            "similar_species_cache_count": len(
                list((run_dir / "distractors" / "similar_species_raw").glob("*.json"))
            ),
        },
        "non_actions": ["no_distractor_relationship_persistence"],
    }
    _write_json(run_dir / "distractors" / "distractors.json", payload)
    return payload


def _distractor_rows_by_target(distractor_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_by_target: dict[str, list[dict[str, Any]]] = {}
    for row in distractor_payload.get("projected_records", []):
        if not isinstance(row, dict) or row.get("status") != "candidate":
            continue
        target_id = str(row.get("target_canonical_taxon_id") or "").strip()
        ref_type = str(row.get("candidate_taxon_ref_type") or "").strip()
        ref_id = str(row.get("candidate_taxon_ref_id") or "").strip()
        if not target_id or ref_type not in {"canonical_taxon", "referenced_taxon"} or not ref_id:
            continue
        rows_by_target.setdefault(target_id, []).append(row)
    for target_id in list(rows_by_target):
        rows_by_target[target_id] = sorted(
            rows_by_target[target_id],
            key=lambda row: (
                int(row.get("source_rank") or 10**9),
                str(row.get("candidate_taxon_ref_type") or ""),
                str(row.get("candidate_taxon_ref_id") or ""),
            ),
        )
    return rows_by_target


def _qualified_media_map(export_path: Path) -> dict[str, dict[str, Any]]:
    if not export_path.exists():
        return {}
    _, qualified = mat._build_media_metadata_indices({"media_downloads": []}, _load_json(export_path))
    return qualified


def _raw_inat_media_index(snapshot_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for seed in manifest.get("taxon_seeds", []):
        if not isinstance(seed, dict):
            continue
        response_path = str(seed.get("response_path") or "").strip()
        if not response_path:
            continue
        payload_path = snapshot_dir / response_path
        if not payload_path.exists():
            continue
        payload = _load_json(payload_path)
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        for result_index, observation in enumerate(results):
            if not isinstance(observation, dict):
                continue
            photos = observation.get("photos") if isinstance(observation.get("photos"), list) else []
            observation_photos = observation.get("observation_photos") if isinstance(observation.get("observation_photos"), list) else []
            obs_photo_by_photo_id: dict[str, dict[str, Any]] = {}
            for item in observation_photos:
                if not isinstance(item, dict):
                    continue
                photo = item.get("photo") if isinstance(item.get("photo"), dict) else {}
                photo_id = str(photo.get("id") or item.get("photo_id") or "").strip()
                if photo_id:
                    obs_photo_by_photo_id[photo_id] = item
            for photo_index, photo in enumerate(photos):
                if not isinstance(photo, dict):
                    continue
                source_media_id = str(photo.get("id") or "").strip()
                if not source_media_id:
                    continue
                index.setdefault(
                    source_media_id,
                    {
                        "photo": photo,
                        "observation": observation,
                        "observation_photo": obs_photo_by_photo_id.get(source_media_id, {}),
                        "raw_payload_ref": f"{response_path}#/results/{result_index}/photos/{photo_index}",
                    },
                )
    return index


def _creator_from_raw_inat(raw: dict[str, Any]) -> str:
    photo = raw.get("photo") if isinstance(raw.get("photo"), dict) else {}
    observation = raw.get("observation") if isinstance(raw.get("observation"), dict) else {}
    user = observation.get("user") if isinstance(observation.get("user"), dict) else {}
    for value in (
        photo.get("attribution_name"),
        user.get("name"),
        user.get("login"),
        photo.get("attribution"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _attribution_from_raw_inat(
    *,
    source_media_id: str,
    manifest_row: dict[str, Any],
    qualified_row: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    photo = raw.get("photo") if isinstance(raw.get("photo"), dict) else {}
    observation = raw.get("observation") if isinstance(raw.get("observation"), dict) else {}
    provenance = qualified_row.get("provenance") if isinstance(qualified_row.get("provenance"), dict) else {}
    source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
    license_name = str(
        source.get("media_license")
        or photo.get("license_code")
        or observation.get("license_code")
        or manifest_row.get("license_code")
        or ""
    ).strip()
    source_url = str(manifest_row.get("source_url") or observation.get("uri") or "").strip()
    raw_payload_ref = str(source.get("raw_payload_ref") or raw.get("raw_payload_ref") or "").strip()
    creator = str(source.get("creator") or _creator_from_raw_inat(raw)).strip()
    attribution_text = str(photo.get("attribution") or "").strip()
    if not attribution_text and creator:
        attribution_text = f"Photo {source_media_id} by {creator} via iNaturalist ({license_name})"
    elif not attribution_text:
        attribution_text = f"Photo {source_media_id} via iNaturalist ({license_name or 'unknown license'})"
    return {
        "source_url": source_url,
        "creator": creator,
        "license": license_name or "unknown",
        "license_url": mat._license_url_from_code(license_name),
        "attribution_text": attribution_text,
        "raw_payload_ref": raw_payload_ref,
        "attribution_complete": bool(source_url and raw_payload_ref and creator and license_name),
        "observation_license": str(observation.get("license_code") or "").strip(),
        "media_license": str(photo.get("license_code") or "").strip(),
    }


def _build_candidate_pool(run_dir: Path, source_context: dict[str, Any], norm_context: dict[str, Any], pmp_context: dict[str, Any]) -> dict[str, Any]:
    snapshot_dir = Path(str(source_context["snapshot_dir"]))
    manifest = _load_json(snapshot_dir / "manifest.json")
    ai_outputs = _load_json(Path(str(pmp_context["ai_outputs_path"])))
    labels_payload = _load_json(run_dir / "localized_names" / "fr_labels.json")
    target_labels = {
        str(k): str(v)
        for k, v in (labels_payload.get("target_labels") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    distractors_payload = _load_json(run_dir / "distractors" / "distractors.json")
    distractors_by_target = _distractor_rows_by_target(distractors_payload)
    manifest_map, _ = mat._build_media_metadata_indices(manifest, {"qualified_resources": []})
    qualified_map = _qualified_media_map(Path(str(norm_context["export_path"])))
    media_to_taxon = _media_to_taxon_map(snapshot_dir, manifest)
    raw_media_index = _raw_inat_media_index(snapshot_dir, manifest)

    rows: list[dict[str, Any]] = []
    option_labels = {
        str(k): str(v)
        for k, v in (labels_payload.get("option_labels") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    for row in distractors_payload.get("projected_records", []):
        if not isinstance(row, dict):
            continue
        ref_id = str(row.get("candidate_taxon_ref_id") or "").strip()
        label = str(row.get("display_label") or "").strip()
        if ref_id and label:
            option_labels[ref_id] = label
    for target_id in sorted({str(row.get("canonical_taxon_id") or "") for row in _seed_rows()}):
        label = target_labels.get(target_id, "")
        media_candidates: list[dict[str, Any]] = []
        for source_media_id, owner_taxon_id in sorted(media_to_taxon.items()):
            if owner_taxon_id != target_id:
                continue
            manifest_row = manifest_map.get(source_media_id)
            if not manifest_row:
                continue
            if not mat._evaluate_basic_identification_eligible(ai_outputs, source_media_id):
                continue
            qualified_row = qualified_map.get(source_media_id, {})
            attribution = _attribution_from_raw_inat(
                source_media_id=source_media_id,
                manifest_row=manifest_row,
                qualified_row=qualified_row,
                raw=raw_media_index.get(source_media_id, {}),
            )
            media_candidates.append(
                {
                    "source_media_id": source_media_id,
                    "image_path": str(manifest_row.get("image_path") or ""),
                    "source_url": attribution["source_url"],
                    "source": "inaturalist",
                    "creator": attribution["creator"],
                    "license": attribution["license"],
                    "license_url": attribution["license_url"],
                    "attribution_text": attribution["attribution_text"],
                    "raw_payload_ref": attribution["raw_payload_ref"],
                    "media_license": attribution["media_license"],
                    "observation_license": attribution["observation_license"],
                    "basic_identification_status": "eligible",
                    "basic_identification_score": _ai_basic_score(ai_outputs, source_media_id),
                    "attribution_complete": attribution["attribution_complete"],
                }
            )
        media_candidates.sort(key=lambda item: (-float(item.get("basic_identification_score") or 0), str(item.get("source_media_id") or "")))

        distractors: list[dict[str, Any]] = []
        seen_labels = {mat.normalize_localized_name_for_compare(label)} if label else set()
        for cand in distractors_by_target.get(target_id, []):
            ref_id = str(cand.get("candidate_taxon_ref_id") or "").strip()
            ref_type = str(cand.get("candidate_taxon_ref_type") or "").strip()
            option_label = str(cand.get("display_label") or option_labels.get(ref_id, "")).strip()
            norm = mat.normalize_localized_name_for_compare(option_label)
            if not option_label or not norm or norm in seen_labels:
                continue
            seen_labels.add(norm)
            distractors.append(
                {
                    "taxon_ref": {"type": ref_type, "id": ref_id},
                    "display_label": option_label,
                    "localized_labels": cand.get("localized_labels") or {},
                    "referenced_only": ref_type == "referenced_taxon",
                    "provenance": {
                        "source": cand.get("source") or "clean_room_distractor_projection"
                    },
                }
            )
            if len(distractors) == 3:
                break

        reasons: list[str] = []
        if not label:
            reasons.append("missing_fr_runtime_safe_label")
        if not media_candidates:
            reasons.append("no_basic_identification_eligible_media")
        elif not media_candidates[0].get("attribution_complete"):
            reasons.append("media_attribution_incomplete")
        if len(distractors) < 3:
            reasons.append("insufficient_label_safe_distractors")

        rows.append(
            {
                "target_canonical_taxon_id": target_id,
                "target_label_fr": label,
                "eligible_media": media_candidates,
                "distractors": distractors,
                "ready": not reasons,
                "rejection_reasons": sorted(set(reasons)),
                "best_score": float(media_candidates[0].get("basic_identification_score") or 0) if media_candidates else 0.0,
            }
        )

    payload = {
        "schema_version": "golden_pack_clean_room_candidate_pool.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "summary": {
            "targets": len(rows),
            "ready_targets": sum(1 for row in rows if row["ready"]),
        },
    }
    _write_json(run_dir / "candidate_pool" / "candidate_pool.json", payload)
    return payload


def _select_30(run_dir: Path, candidate_pool: dict[str, Any], source_context: dict[str, Any], pmp_context: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in candidate_pool.get("rows", []) if isinstance(row, dict)]
    ready = [row for row in rows if row.get("ready") is True]
    ready.sort(key=lambda row: (-float(row.get("best_score") or 0), str(row.get("target_canonical_taxon_id") or "")))
    selected = ready[:30]
    rejected = [
        {
            "taxon_ref_id": str(row.get("target_canonical_taxon_id") or ""),
            "reason_codes": row.get("rejection_reasons") or ["not_selected_top_30"],
        }
        for row in rows
        if row not in selected
    ]
    entries = []
    for row in selected:
        entries.append(
            {
                "target_canonical_taxon_id": row["target_canonical_taxon_id"],
                "target_label_fr": row["target_label_fr"],
                "primary_media": row["eligible_media"][0],
                "distractors": row["distractors"][:3],
            }
        )
    selection = {
        "schema_version": "golden_pack_selection.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_count": 30,
        "target_candidates_considered": len(rows),
        "snapshot_id": source_context["snapshot_id"],
        "ai_outputs_path": pmp_context["ai_outputs_path"],
        "entries": entries,
        "rejected_targets": rejected,
        "lineage": {
            "seed_path": str(SEED_PATH.relative_to(REPO_ROOT)),
            "snapshot_dir": source_context["snapshot_dir"],
            "candidate_pool_path": "candidate_pool/candidate_pool.json",
        },
    }
    _write_json(run_dir / "selection" / "golden_pack_selection.json", selection)
    return selection


def _write_prefilter_report(run_dir: Path, source_context: dict[str, Any]) -> None:
    snapshot_dir = Path(str(source_context["snapshot_dir"]))
    manifest = _load_json(snapshot_dir / "manifest.json")
    downloads = [row for row in manifest.get("media_downloads", []) if isinstance(row, dict)]
    prefiltered = [
        row for row in downloads
        if str(row.get("download_status") or "") == "downloaded"
        and not row.get("pre_ai_rejection_reason")
    ]
    _write_json(run_dir / "media_prefilter" / "media_prefilter_report.json", {
        "schema_version": "golden_pack_clean_room_media_prefilter_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "downloaded_media_count": sum(1 for row in downloads if row.get("download_status") == "downloaded"),
        "prefilter_pass_count": len(prefiltered),
        "total_media_download_rows": len(downloads),
    })


def run_pipeline(
    *,
    mode: str,
    output_root: Path | None = None,
    resume_run_id: str | None = None,
    reset_from_stage: str | None = None,
    skip_external: bool = False,
    allow_full_gemini_run: bool = False,
    max_observations_per_taxon: int = 20,
    database_url: str | None = None,
) -> Path:
    if mode not in {"dry-run", "apply"}:
        raise ValueError("mode must be dry-run or apply")

    if resume_run_id:
        run_dir = (output_root or RUNS_ROOT) / resume_run_id
        manifest = _load_json(run_dir / "run_manifest.json")
        stages = _load_json(run_dir / "pipeline_plan.json")["steps"]
        run_id = resume_run_id
        if reset_from_stage:
            stage_names = [str(row.get("step") or "") for row in stages]
            if reset_from_stage not in stage_names:
                raise ValueError(f"Unknown reset stage: {reset_from_stage}")
            reset_index = stage_names.index(reset_from_stage)
            for row in stages[reset_index:]:
                row["status"] = "planned"
                row.pop("message", None)
            manifest["status"] = "in_progress"
    else:
        if reset_from_stage:
            raise ValueError("--reset-from-stage requires --resume")
        run_id, run_dir = _new_run_dir(output_root=output_root)
        stages = _stage_records()
        manifest = {
            "schema_version": "golden_pack_v1_clean_room_run_manifest.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "run_dir": str(run_dir),
            "mode": mode,
            "status": "planned_only" if mode == "dry-run" else "in_progress",
            "flags": FLAGS,
            "non_actions": [
                "no legacy snapshot media ids as selection source",
                "no pack_materialization_v2 selection source",
                "no automatic canonical promotion",
                "no distractor relationship persistence",
            ],
        }

    source_ctx = _source_context(run_id, max_observations_per_taxon=max_observations_per_taxon)
    norm_ctx = _normalization_context(run_dir, source_ctx, database_url=database_url)
    pmp_ctx = _pmp_context(source_ctx)
    mat_ctx = _materialization_context(run_dir, source_ctx, pmp_ctx)
    manifest["source_inat_refresh"] = source_ctx
    manifest["normalization"] = norm_ctx
    manifest["pmp_gemini"] = pmp_ctx
    manifest["materialization"] = mat_ctx
    _set_stage_command(stages, "source_inat_refresh", _fetch_command(source_ctx))
    _set_stage_command(stages, "normalization", _normalization_command(norm_ctx))
    _set_stage_command(stages, "pmp_gemini", _pmp_command(pmp_ctx))
    _set_stage_command(stages, "materialization", _materialization_command(mat_ctx))
    _persist(run_dir, manifest, stages)

    if mode == "dry-run":
        _write_json(run_dir / "reports" / "final_report.json", {
            "status": "planned_only",
            "blocked_step": "source_inat_refresh",
            "golden_pack_generated": False,
            "next_command": "python scripts/run_golden_pack_v1_clean_room_pipeline.py --apply --allow-full-gemini-run",
        })
        return run_dir

    for row in stages[_first_incomplete_stage_index(stages):]:
        stage = str(row["step"])
        if stage in EXTERNAL_STAGES and skip_external:
            row["status"] = "skipped"
            row["message"] = "skipped_external_by_flag"
            manifest["status"] = "applied_with_skips"
            _write_json(run_dir / "reports" / "final_report.json", {
                "status": "applied_with_skips",
                "blocked_step": stage,
                "golden_pack_generated": False,
                "next_command": f"python scripts/run_golden_pack_v1_clean_room_pipeline.py --apply --resume {run_id} --allow-full-gemini-run",
            })
            _persist(run_dir, manifest, stages)
            return run_dir

        try:
            if stage == "seed_validation":
                _validate_seed(run_dir)
                ok, message = True, "completed"
            elif stage == "source_inat_refresh":
                ok, message = _run_subprocess_stage(run_dir, "source_fetch/source_inat_refresh.json", _fetch_command(source_ctx), extra={"context": source_ctx})
            elif stage == "normalization":
                ok, message = _run_subprocess_stage(run_dir, "normalized/normalization_stage_report.json", _normalization_command(norm_ctx), extra={"context": norm_ctx})
            elif stage == "pmp_gemini":
                ai_outputs_path = Path(str(pmp_ctx["ai_outputs_path"]))
                if _ai_outputs_match_pmp_contract(ai_outputs_path):
                    summary = _ai_outputs_summary(ai_outputs_path)
                    _write_json(run_dir / "pmp" / "ai_outputs.json", _load_json(ai_outputs_path))
                    _write_json(run_dir / "pmp" / "gemini_run_report.json", {
                        "schema_version": "golden_pack_clean_room_gemini_run_report.v1",
                        "status": "cache_hit",
                        "context": pmp_ctx,
                        "sent_to_gemini_count": 0,
                        **summary,
                    })
                    ok, message = True, "completed_from_existing_ai_outputs"
                elif not allow_full_gemini_run:
                    ok, message = False, "requires_allow_full_gemini_run"
                    _write_json(run_dir / "pmp" / "gemini_run_report.json", {
                        "schema_version": "golden_pack_clean_room_gemini_run_report.v1",
                        "status": "blocked_requires_allow_full_gemini_run",
                        "context": pmp_ctx,
                        "existing_ai_outputs_contract_usable": False,
                    })
                else:
                    _clear_snapshot_ai_outputs_pointer(Path(str(pmp_ctx["snapshot_dir"])))
                    ok, message = _run_subprocess_stage(
                        run_dir,
                        "pmp/gemini_run_report.json",
                        _pmp_command(pmp_ctx),
                        extra={"context": pmp_ctx, "allow_full_gemini_run": True},
                        stream_log_rel="pmp/gemini_progress.log",
                    )
                    if ok and ai_outputs_path.exists():
                        summary = _ai_outputs_summary(ai_outputs_path)
                        _write_json(run_dir / "pmp" / "ai_outputs.json", _load_json(ai_outputs_path))
                        _write_json(run_dir / "pmp" / "gemini_run_report.json", {
                            "schema_version": "golden_pack_clean_room_gemini_run_report.v1",
                            "status": "completed",
                            "context": pmp_ctx,
                            "allow_full_gemini_run": True,
                            "sent_to_gemini_count": summary["processed_media_count"],
                            **summary,
                        })
            elif stage == "media_prefilter_report":
                _write_prefilter_report(run_dir, source_ctx)
                ok, message = True, "completed"
            elif stage == "fr_labels":
                manifest["fr_labels"] = {
                    "path": "localized_names/fr_labels.json",
                    "summary": _build_fr_label_artifact(run_dir, source_ctx)["summary"],
                }
                ok, message = True, "completed"
            elif stage == "distractors":
                manifest["distractors"] = {
                    "path": "distractors/distractors.json",
                    "summary": _build_distractor_artifact(run_dir, source_ctx)["summary"],
                }
                ok, message = True, "completed"
            elif stage == "candidate_pool":
                manifest["candidate_pool"] = {
                    "path": "candidate_pool/candidate_pool.json",
                    "summary": _build_candidate_pool(run_dir, source_ctx, norm_ctx, pmp_ctx)["summary"],
                }
                ok, message = True, "completed"
            elif stage == "select_30":
                pool = _load_json(run_dir / "candidate_pool" / "candidate_pool.json")
                selection = _select_30(run_dir, pool, source_ctx, pmp_ctx)
                manifest["selection"] = {
                    "path": "selection/golden_pack_selection.json",
                    "selected_count": len(selection["entries"]),
                }
                ok, message = True, "completed"
            elif stage == "materialization":
                ok, message = _run_subprocess_stage(run_dir, "golden_pack/materialization_stage_report.json", _materialization_command(mat_ctx), extra={"context": mat_ctx})
                validation_path = run_dir / "golden_pack" / "validation_report.json"
                if validation_path.exists():
                    status = str(_load_json(validation_path).get("status") or "")
                    ok = ok and status == "passed"
                    message = "completed" if ok else f"materialization_status_{status or 'missing'}"
            elif stage == "validation":
                validation_path = run_dir / "golden_pack" / "validation_report.json"
                validation = _load_json(validation_path) if validation_path.exists() else {}
                schema_validity = validation.get("schema_validity") if isinstance(validation.get("schema_validity"), dict) else {}
                ok = validation.get("status") == "passed" and all(schema_validity.get(k) is True for k in ("manifest_schema_valid", "pack_schema_valid", "validation_report_schema_valid"))
                message = "completed" if ok else "validation_not_passed"
            elif stage == "promotion_check":
                validation_path = run_dir / "golden_pack" / "validation_report.json"
                validation = _load_json(validation_path) if validation_path.exists() else {}
                schema_validity = validation.get("schema_validity") if isinstance(validation.get("schema_validity"), dict) else {}
                promotable = (
                    validation.get("status") == "passed"
                    and all(schema_validity.get(k) is True for k in ("manifest_schema_valid", "pack_schema_valid", "validation_report_schema_valid"))
                    and (run_dir / "golden_pack" / "pack.json").exists()
                    and (run_dir / "golden_pack" / "media").is_dir()
                )
                _write_json(run_dir / "reports" / "final_report.json", {
                    "status": "promotable" if promotable else "not_promotable",
                    "golden_pack_generated": promotable,
                    "validation_report_status": validation.get("status", "missing"),
                    "next_command": f"python scripts/promote_golden_pack_v1_run_output.py --run-output-dir {run_dir / 'golden_pack'}" if promotable else "inspect golden_pack/validation_report.json",
                })
                ok, message = True, "completed"
            else:
                raise RuntimeError(f"unknown_stage:{stage}")
        except Exception as exc:
            ok, message = False, str(exc)

        row["status"] = "completed" if ok else "blocked"
        row["message"] = message
        if not ok:
            manifest["status"] = "blocked"
            _persist(run_dir, manifest, stages)
            return run_dir
        _persist(run_dir, manifest, stages)

    manifest["status"] = "completed"
    _persist(run_dir, manifest, stages)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", type=str)
    parser.add_argument("--reset-from-stage", type=str)
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--allow-full-gemini-run", action="store_true")
    parser.add_argument("--max-observations-per-taxon", type=int, default=20)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("Use exactly one mode: --dry-run or --apply")
    run_dir = run_pipeline(
        mode="dry-run" if args.dry_run else "apply",
        resume_run_id=args.resume,
        reset_from_stage=args.reset_from_stage,
        skip_external=args.skip_external,
        allow_full_gemini_run=args.allow_full_gemini_run,
        max_observations_per_taxon=args.max_observations_per_taxon,
        database_url=args.database_url,
    )
    manifest = _load_json(run_dir / "run_manifest.json")
    print(f"run_dir={run_dir}")
    print(f"status={manifest.get('status')}")


if __name__ == "__main__":
    main()
