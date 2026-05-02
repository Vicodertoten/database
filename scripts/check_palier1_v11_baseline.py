from __future__ import annotations

import json
from pathlib import Path

BASELINE_EVIDENCE_DIR = Path("docs/audits/evidence/palier1_v11_baseline")
COMPILED_PATH = BASELINE_EVIDENCE_DIR / "pack_compiled_v2.json"
MATERIALIZED_PATH = BASELINE_EVIDENCE_DIR / "pack_materialization_v2.json"
AUDIT_PATH = BASELINE_EVIDENCE_DIR / "phase3_distractor_audit_report.json"

EXPECTED_QUESTION_COUNT = 50


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise ValueError(f"Missing baseline artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _as_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _validate_compiled(payload: dict[str, object]) -> tuple[str, set[str]]:
    if payload.get("pack_compiled_version") != "pack.compiled.v2":
        raise ValueError("pack_compiled_version must be pack.compiled.v2")

    requested = _as_int(payload, "question_count_requested")
    built = _as_int(payload, "question_count_built")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError("compiled questions must be a list")

    if requested != EXPECTED_QUESTION_COUNT:
        raise ValueError(f"question_count_requested must be {EXPECTED_QUESTION_COUNT}")
    if built != EXPECTED_QUESTION_COUNT:
        raise ValueError(f"question_count_built must be {EXPECTED_QUESTION_COUNT}")
    if len(questions) != EXPECTED_QUESTION_COUNT:
        raise ValueError(f"compiled questions length must be {EXPECTED_QUESTION_COUNT}")

    target_taxa = [
        str(question.get("target_canonical_taxon_id") or "").strip()
        for question in questions
    ]
    if any(not taxon_id for taxon_id in target_taxa):
        raise ValueError("compiled questions must define target_canonical_taxon_id")
    unique_targets = set(target_taxa)
    if len(unique_targets) != EXPECTED_QUESTION_COUNT:
        raise ValueError(
            "compiled questions must contain exactly "
            f"{EXPECTED_QUESTION_COUNT} unique target_canonical_taxon_id values"
        )

    build_id = str(payload.get("build_id") or "").strip()
    if not build_id:
        raise ValueError("compiled build_id must be non-empty")
    return build_id, unique_targets


def _validate_materialized(
    payload: dict[str, object],
    *,
    expected_build_id: str,
    compiled_target_taxa: set[str],
) -> None:
    if payload.get("pack_materialization_version") != "pack.materialization.v2":
        raise ValueError("pack_materialization_version must be pack.materialization.v2")

    question_count = _as_int(payload, "question_count")
    if question_count != EXPECTED_QUESTION_COUNT:
        raise ValueError(f"materialization question_count must be {EXPECTED_QUESTION_COUNT}")

    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError("materialization questions must be a list")
    if len(questions) != EXPECTED_QUESTION_COUNT:
        raise ValueError(
            "materialization questions length must be "
            f"{EXPECTED_QUESTION_COUNT}"
        )

    source_build_id = str(payload.get("source_build_id") or "").strip()
    if source_build_id != expected_build_id:
        raise ValueError("materialization source_build_id must match compiled build_id")

    materialized_target_taxa = {
        str(question.get("target_canonical_taxon_id") or "").strip()
        for question in questions
    }
    if "" in materialized_target_taxa:
        raise ValueError("materialization questions must define target_canonical_taxon_id")
    if materialized_target_taxa != compiled_target_taxa:
        raise ValueError("materialization target taxon set must match compiled target set")


def _validate_audit(payload: dict[str, object]) -> None:
    errors = payload.get("errors")
    if not isinstance(errors, dict):
        raise ValueError("audit errors must be an object")
    if errors:
        raise ValueError(f"audit report must not contain errors: {errors}")

    reports = payload.get("reports")
    if not isinstance(reports, list) or len(reports) < 2:
        raise ValueError("audit report must contain compiled and materialization reports")

    seen_contracts: set[str] = set()
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("audit report entries must be objects")
        summary = report.get("summary")
        invariants = report.get("invariants")
        if not isinstance(summary, dict) or not isinstance(invariants, dict):
            raise ValueError("audit report entries must include summary and invariants")

        contract_version = str(summary.get("contract_version") or "").strip()
        seen_contracts.add(contract_version)
        if int(summary.get("questions") or 0) != EXPECTED_QUESTION_COUNT:
            raise ValueError(
                "audit summary questions must be "
                f"{EXPECTED_QUESTION_COUNT} for each report"
            )

        unique_ids = ((invariants.get("questions_with_unique_canonical_ids") or {}).get("count"))
        if unique_ids != EXPECTED_QUESTION_COUNT:
            raise ValueError(
                "audit invariant questions_with_unique_canonical_ids must be "
                f"{EXPECTED_QUESTION_COUNT}"
            )

    required_contracts = {"pack.compiled.v2", "pack.materialization.v2"}
    if not required_contracts.issubset(seen_contracts):
        raise ValueError(
            "audit report must include both contracts: "
            f"missing={sorted(required_contracts - seen_contracts)}"
        )


def main() -> int:
    compiled = _load_json(COMPILED_PATH)
    materialized = _load_json(MATERIALIZED_PATH)
    audit = _load_json(AUDIT_PATH)

    build_id, target_taxa = _validate_compiled(compiled)
    _validate_materialized(
        materialized,
        expected_build_id=build_id,
        compiled_target_taxa=target_taxa,
    )
    _validate_audit(audit)

    print(
        "palier-1 v1.1 baseline gate: PASS "
        f"(questions={EXPECTED_QUESTION_COUNT}, unique_targets={len(target_taxa)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
