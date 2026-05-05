#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from database_core.qualification.pedagogical_media_profile_v1 import (
    is_valid_pedagogical_media_profile_v1,
    parse_pedagogical_media_profile_v1,
)

FIXTURE_SCHEMA_VERSION = "pedagogical_media_profile_fixture_dry_run.v1"

DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/pedagogical_media_profile_v1")
DEFAULT_RAW_FIXTURE_DIR = DEFAULT_FIXTURE_ROOT / "raw_model_outputs"
DEFAULT_REPORT_OUTPUT_PATH = (
    Path("docs/audits/evidence/pedagogical_media_profile_v1_fixture_dry_run.json")
)

REQUIRED_USAGE_SCORES = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

INTENDED_VALID_FIXTURES = {
    "clear_bird.json",
    "partial_occluded_bird.json",
    "distant_bird.json",
    "feather.json",
    "nest.json",
    "habitat.json",
    "multiple_organisms.json",
    "invalid_biological_basis.json",
}

INTENDED_INVALID_EXPECTATIONS = {
    "invalid_feedback_field.json": {
        "failure_reason": "schema_validation_failed",
        "schema_failure_cause": "additional_property",
    },
    "failed_media_uninspectable.json": {
        "failure_reason": "media_uninspectable",
    },
}

LOW_BASIC_IDENTIFICATION_THRESHOLD = 50
HIGH_INDIRECT_EVIDENCE_THRESHOLD = 80


class FixtureAuditError(RuntimeError):
    """Raised when the fixture corpus is malformed or incomplete."""


def _load_fixture_manifest(fixture_root: Path) -> dict[str, Any]:
    manifest_path = fixture_root / "fixture_manifest.json"
    if not manifest_path.exists():
        raise FixtureAuditError(f"Missing fixture manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _fixture_names_from_manifest(manifest: dict[str, Any]) -> list[str]:
    raw_files = manifest.get("raw_model_outputs")
    if not isinstance(raw_files, list) or not all(isinstance(item, str) for item in raw_files):
        raise FixtureAuditError(
            "fixture_manifest.json must define raw_model_outputs as a string list"
        )
    return sorted(raw_files)


def _load_raw_fixture_payloads(
    raw_fixture_dir: Path,
    fixture_names: list[str],
) -> list[tuple[str, str]]:
    fixtures: list[tuple[str, str]] = []
    for fixture_name in fixture_names:
        fixture_path = raw_fixture_dir / fixture_name
        if not fixture_path.exists():
            raise FixtureAuditError(f"Missing fixture file: {fixture_path}")
        fixtures.append((fixture_name, fixture_path.read_text(encoding="utf-8")))
    return fixtures


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _to_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _usage_score(payload: dict[str, Any], key: str) -> int:
    usage_scores = ((payload.get("scores") or {}).get("usage_scores") or {})
    if not isinstance(usage_scores, dict):
        return 0
    return _to_int(usage_scores.get(key))


def run_fixture_dry_run_audit(
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    raw_fixture_dir: Path = DEFAULT_RAW_FIXTURE_DIR,
) -> dict[str, Any]:
    manifest = _load_fixture_manifest(fixture_root)
    fixture_names = _fixture_names_from_manifest(manifest)
    raw_fixtures = _load_raw_fixture_payloads(raw_fixture_dir, fixture_names)

    parsed_by_fixture: dict[str, dict[str, Any]] = {}
    parser_output_invalid_count = 0

    for fixture_name, raw_output in raw_fixtures:
        parsed = parse_pedagogical_media_profile_v1(raw_output, media_id=fixture_name)
        parsed_by_fixture[fixture_name] = parsed
        if not is_valid_pedagogical_media_profile_v1(parsed):
            parser_output_invalid_count += 1

    valid_names = [
        name
        for name, payload in parsed_by_fixture.items()
        if str(payload.get("review_status") or "") == "valid"
    ]
    failed_names = [name for name in fixture_names if name not in valid_names]

    valid_payloads = [parsed_by_fixture[name] for name in valid_names]
    failed_payloads = [parsed_by_fixture[name] for name in failed_names]

    failure_reason_distribution = Counter(
        str(payload.get("failure_reason") or "unknown_failure") for payload in failed_payloads
    )

    schema_failure_cause_distribution = Counter()
    feedback_rejection_count = 0
    biological_basis_rejection_count = 0
    selection_rejection_count = 0

    for payload in failed_payloads:
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            continue

        cause = str(diagnostics.get("schema_failure_cause") or "")
        if cause:
            schema_failure_cause_distribution[cause] += 1

        schema_errors = diagnostics.get("schema_errors")
        if not isinstance(schema_errors, list):
            continue

        for error in schema_errors:
            if not isinstance(error, dict):
                continue
            path = str(error.get("path") or "")
            message = str(error.get("message") or "").lower()
            if "post_answer_feedback" in path or "post_answer_feedback" in message:
                feedback_rejection_count += 1
            if "invalid_biological_basis" == str(error.get("cause") or ""):
                biological_basis_rejection_count += 1
            if "selectedoptionid" in path.lower() or "selected option" in message:
                selection_rejection_count += 1

    evidence_type_distribution = Counter(
        str(payload.get("evidence_type") or "unknown") for payload in valid_payloads
    )
    organism_group_distribution = Counter(
        str(payload.get("organism_group") or "unknown") for payload in valid_payloads
    )

    global_scores = [
        _to_int((payload.get("scores") or {}).get("global_quality_score"))
        for payload in valid_payloads
        if isinstance(payload.get("scores"), dict)
    ]

    usage_score_values: dict[str, list[int]] = {key: [] for key in REQUIRED_USAGE_SCORES}
    for payload in valid_payloads:
        scores = payload.get("scores")
        if not isinstance(scores, dict):
            continue
        usage_scores = scores.get("usage_scores")
        if not isinstance(usage_scores, dict):
            continue
        for key in REQUIRED_USAGE_SCORES:
            usage_score_values[key].append(_to_int(usage_scores.get(key)))

    average_usage_scores = {
        key: _average([float(item) for item in values])
        for key, values in usage_score_values.items()
    }

    low_basic_identification_valid_count = sum(
        1
        for payload in valid_payloads
        if _usage_score(payload, "basic_identification")
        < LOW_BASIC_IDENTIFICATION_THRESHOLD
    )

    high_indirect_evidence_valid_count = sum(
        1
        for payload in valid_payloads
        if _usage_score(payload, "indirect_evidence_learning")
        >= HIGH_INDIRECT_EVIDENCE_THRESHOLD
    )

    schema_validation_failed_count = int(
        failure_reason_distribution.get("schema_validation_failed", 0)
    )
    model_output_invalid_count = int(failure_reason_distribution.get("model_output_invalid", 0))

    valid_expectation_ok = all(
        str(parsed_by_fixture.get(name, {}).get("review_status") or "") == "valid"
        for name in sorted(INTENDED_VALID_FIXTURES)
    )

    invalid_expectation_ok = True
    for name, expected in INTENDED_INVALID_EXPECTATIONS.items():
        payload = parsed_by_fixture.get(name, {})
        observed_reason = str(payload.get("failure_reason") or "")
        if observed_reason != expected["failure_reason"]:
            invalid_expectation_ok = False
            continue
        expected_cause = expected.get("schema_failure_cause")
        if expected_cause is None:
            continue
        diagnostics = payload.get("diagnostics")
        observed_cause = ""
        if isinstance(diagnostics, dict):
            observed_cause = str(diagnostics.get("schema_failure_cause") or "")
        if observed_cause != expected_cause:
            invalid_expectation_ok = False

    low_basic_identification_valid_ok = low_basic_identification_valid_count >= 1
    high_indirect_evidence_valid_ok = high_indirect_evidence_valid_count >= 1
    feedback_rejection_ok = feedback_rejection_count >= 1
    selection_rejection_ok = selection_rejection_count == 0

    if parser_output_invalid_count > 0:
        decision = "INVESTIGATE_FIXTURE_FAILURES"
    elif (
        valid_expectation_ok
        and invalid_expectation_ok
        and low_basic_identification_valid_ok
        and high_indirect_evidence_valid_ok
        and feedback_rejection_ok
        and selection_rejection_ok
    ):
        decision = "READY_FOR_LIVE_MINI_RUN"
    elif not (valid_expectation_ok and invalid_expectation_ok):
        decision = "INVESTIGATE_FIXTURE_FAILURES"
    else:
        decision = "ADJUST_PROMPT_OR_SCHEMA"

    report: dict[str, Any] = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "execution_status": "ok" if parser_output_invalid_count == 0 else "parser_output_invalid",
        "fixture_count": len(fixture_names),
        "valid_count": len(valid_names),
        "failed_count": len(failed_names),
        "failure_reason_distribution": dict(sorted(failure_reason_distribution.items())),
        "schema_validation_failed_count": schema_validation_failed_count,
        "model_output_invalid_count": model_output_invalid_count,
        "schema_failure_cause_distribution": dict(
            sorted(schema_failure_cause_distribution.items())
        ),
        "evidence_type_distribution": dict(sorted(evidence_type_distribution.items())),
        "organism_group_distribution": dict(sorted(organism_group_distribution.items())),
        "average_global_quality_score": _average([float(item) for item in global_scores]),
        "average_usage_scores": average_usage_scores,
        "low_basic_identification_valid_count": low_basic_identification_valid_count,
        "high_indirect_evidence_valid_count": high_indirect_evidence_valid_count,
        "feedback_rejection_count": feedback_rejection_count,
        "biological_basis_rejection_count": biological_basis_rejection_count,
        "qualitative_examples": {
            "low_basic_identification_valid_fixtures": [
                name
                for name in valid_names
                if _usage_score(parsed_by_fixture[name], "basic_identification")
                < LOW_BASIC_IDENTIFICATION_THRESHOLD
            ],
            "high_indirect_evidence_valid_fixtures": [
                name
                for name in valid_names
                if _usage_score(parsed_by_fixture[name], "indirect_evidence_learning")
                >= HIGH_INDIRECT_EVIDENCE_THRESHOLD
            ],
            "failed_fixture_reasons": {
                name: str(parsed_by_fixture[name].get("failure_reason") or "unknown_failure")
                for name in failed_names
            },
        },
        "decision": decision,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic fixture dry-run audit for pedagogical_media_profile.v1 "
            "without live model calls."
        )
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="Root directory containing fixture_manifest.json and fixture subfolders.",
    )
    parser.add_argument(
        "--raw-fixture-dir",
        type=Path,
        default=DEFAULT_RAW_FIXTURE_DIR,
        help="Directory containing raw model output JSON fixtures.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_REPORT_OUTPUT_PATH,
        help="JSON report output path.",
    )
    args = parser.parse_args()

    report = run_fixture_dry_run_audit(
        fixture_root=args.fixture_root,
        raw_fixture_dir=args.raw_fixture_dir,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
