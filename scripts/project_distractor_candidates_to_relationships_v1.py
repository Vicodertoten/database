"""Project Sprint 12 distractor candidates into schema-compliant relationships.

Sprint 13A scope:
- Read candidate artifact (analysis-rich records).
- Project to strict DistractorRelationship V1 records.
- Validate every projected record against schema.
- Report rejected records with explicit reasons.

This script does not persist to Postgres and does not modify runtime behavior.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

DEFAULT_INPUT_PATH = Path(
    "docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json"
)
DEFAULT_SCHEMA_PATH = Path("schemas/distractor_relationship_v1.schema.json")
DEFAULT_OUTPUT_JSON = Path(
    "docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json"
)
DEFAULT_OUTPUT_MD = Path("docs/audits/distractor-relationships-v1-projection-sprint13.md")
DEFAULT_REFERENCED_SNAPSHOT_PATH = Path("data/review_overrides/referenced_taxa_snapshot.json")

DECISION_READY = "READY_FOR_REFERENCED_TAXON_SHELL_APPLY_PATH"
DECISION_NEEDS_FIXES = "NEEDS_PROJECTION_FIXES"
DECISION_BLOCKED_SCHEMA = "BLOCKED_BY_SCHEMA_VALIDATION_ERRORS"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_stable_referenced_taxon_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    payload = _load_json(path)
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        referenced = payload.get("referenced_taxa")
        if isinstance(referenced, list):
            items = [item for item in referenced if isinstance(item, dict)]
        elif isinstance(payload.get("items"), list):
            items = [item for item in payload["items"] if isinstance(item, dict)]

    stable_ids: set[str] = set()
    for item in items:
        rid = str(item.get("referenced_taxon_id", "")).strip()
        if rid:
            stable_ids.add(rid)
    return stable_ids


def _validator_for_schema(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _non_blank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_source_rank(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_candidate_ref(
    raw_ref_type: Any,
    raw_ref_id: Any,
    raw_status: Any,
    stable_referenced_ids: set[str],
) -> tuple[str | None, str | None, str, list[str]]:
    reasons: list[str] = []
    ref_type = str(raw_ref_type or "").strip()
    ref_id = str(raw_ref_id).strip() if raw_ref_id is not None else None
    status = str(raw_status or "candidate").strip() or "candidate"

    if ref_type not in {"canonical_taxon", "referenced_taxon", "unresolved_taxon"}:
        reasons.append("invalid_candidate_taxon_ref_type")
        return None, None, status, reasons

    if ref_type == "canonical_taxon":
        if not _non_blank(ref_id):
            reasons.append("missing_candidate_taxon_ref_id_for_canonical")
        return ref_type, ref_id, status, reasons

    if ref_type == "referenced_taxon":
        if ref_id and ref_id in stable_referenced_ids:
            return ref_type, ref_id, status, reasons

        # Virtual/unapplied referenced IDs are downgraded to unresolved_taxon.
        ref_type = "unresolved_taxon"
        ref_id = None
        if status not in {"needs_review", "unavailable_missing_taxon"}:
            status = "needs_review"
        reasons.append("referenced_taxon_id_not_stable_downgraded_to_unresolved")
        return ref_type, ref_id, status, reasons

    # unresolved_taxon
    ref_id = None
    if status not in {"needs_review", "unavailable_missing_taxon"}:
        status = "needs_review"
        reasons.append("unresolved_taxon_status_normalized_to_needs_review")
    return ref_type, ref_id, status, reasons


def _project_one_record(
    candidate: dict[str, Any],
    validator: Draft202012Validator,
    stable_referenced_ids: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    relationship: dict[str, Any] = {}
    reasons: list[str] = []

    relationship_id = candidate.get("relationship_id")
    target_id = candidate.get("target_canonical_taxon_id")
    target_name = candidate.get("target_scientific_name")
    candidate_name = candidate.get("candidate_scientific_name")
    source = candidate.get("source")
    source_rank = _normalize_source_rank(candidate.get("source_rank"))
    created_at = candidate.get("created_at")

    if not _non_blank(relationship_id):
        reasons.append("missing_relationship_id")
    if not _non_blank(target_id):
        reasons.append("missing_target_canonical_taxon_id")
    if not _non_blank(target_name):
        reasons.append("missing_target_scientific_name")
    if not _non_blank(candidate_name):
        reasons.append("missing_candidate_scientific_name")
    if not _non_blank(source):
        reasons.append("missing_source")
    if source_rank is None:
        reasons.append("invalid_source_rank")
    if not _non_blank(created_at):
        reasons.append("missing_created_at")

    ref_type, ref_id, normalized_status, ref_reasons = _normalize_candidate_ref(
        candidate.get("candidate_taxon_ref_type"),
        candidate.get("candidate_taxon_ref_id"),
        candidate.get("status"),
        stable_referenced_ids,
    )
    reasons.extend(ref_reasons)

    has_fatal = any(
        reason.startswith("missing_") or reason.startswith("invalid_")
        for reason in reasons
    )
    if reasons and has_fatal:
        return None, {
            "relationship_id": relationship_id,
            "candidate_scientific_name": candidate_name,
            "reasons": reasons,
            "source_record": candidate,
        }

    relationship["relationship_id"] = str(relationship_id)
    relationship["target_canonical_taxon_id"] = str(target_id)
    relationship["target_scientific_name"] = str(target_name)
    relationship["candidate_taxon_ref_type"] = ref_type
    relationship["candidate_taxon_ref_id"] = ref_id
    relationship["candidate_scientific_name"] = str(candidate_name)
    relationship["source"] = str(source)
    relationship["source_rank"] = int(source_rank)
    relationship["status"] = normalized_status
    relationship["created_at"] = str(created_at)

    if "confusion_types" in candidate:
        relationship["confusion_types"] = candidate.get("confusion_types")
    if "pedagogical_value" in candidate:
        relationship["pedagogical_value"] = candidate.get("pedagogical_value")
    if "difficulty_level" in candidate:
        relationship["difficulty_level"] = candidate.get("difficulty_level")
    if "learner_level" in candidate:
        relationship["learner_level"] = candidate.get("learner_level")
    if "reason" in candidate:
        relationship["reason"] = candidate.get("reason")
    if "constraints" in candidate:
        relationship["constraints"] = candidate.get("constraints")
    if "updated_at" in candidate:
        relationship["updated_at"] = candidate.get("updated_at")

    schema_errors = [err.message for err in validator.iter_errors(relationship)]
    if schema_errors:
        return None, {
            "relationship_id": relationship_id,
            "candidate_scientific_name": candidate_name,
            "reasons": ["schema_validation_failed"],
            "schema_errors": schema_errors,
            "source_record": candidate,
            "projected_record": relationship,
        }

    return relationship, None


def project_candidates(
    candidates_payload: dict[str, Any],
    schema: dict[str, Any],
    stable_referenced_ids: set[str],
) -> dict[str, Any]:
    relationships = candidates_payload.get("relationships", [])
    if not isinstance(relationships, list):
        relationships = []

    validator = _validator_for_schema(schema)
    projected_records: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []

    for candidate in relationships:
        if not isinstance(candidate, dict):
            rejected_records.append(
                {
                    "relationship_id": None,
                    "candidate_scientific_name": None,
                    "reasons": ["non_object_candidate_record"],
                    "source_record": candidate,
                }
            )
            continue
        projected, rejected = _project_one_record(candidate, validator, stable_referenced_ids)
        if projected is not None:
            projected_records.append(projected)
        elif rejected is not None:
            rejected_records.append(rejected)

    rejection_reason_distribution = Counter()
    schema_validation_error_count = 0
    for rejected in rejected_records:
        for reason in rejected.get("reasons", []):
            rejection_reason_distribution[reason] += 1
        schema_validation_error_count += len(rejected.get("schema_errors", []))

    if schema_validation_error_count > 0:
        decision = DECISION_BLOCKED_SCHEMA
    elif rejected_records:
        decision = DECISION_NEEDS_FIXES
    else:
        decision = DECISION_READY

    return {
        "execution_status": "complete",
        "run_date": datetime.now(UTC).isoformat(),
        "decision": decision,
        "input_records_count": len(relationships),
        "projected_records_count": len(projected_records),
        "rejected_records_count": len(rejected_records),
        "schema_validation_error_count": schema_validation_error_count,
        "rejection_reason_distribution": dict(rejection_reason_distribution),
        "projected_records": projected_records,
        "rejected_records": rejected_records,
    }


def write_markdown_report(
    output_path: Path,
    projection_result: dict[str, Any],
    input_artifact_path: Path,
    schema_path: Path,
) -> None:
    run_date = projection_result["run_date"][:10]
    decision = projection_result["decision"]
    projected = projection_result["projected_records_count"]
    rejected = projection_result["rejected_records_count"]
    schema_errors = projection_result["schema_validation_error_count"]

    if decision == DECISION_READY:
        next_phase = (
            "Proceed to reviewed referenced taxon shell apply path "
            "before persistence writes."
        )
    elif decision == DECISION_NEEDS_FIXES:
        next_phase = (
            "Fix projection rejections, rerun projection, and require "
            "zero rejected records for clean handoff."
        )
    else:
        next_phase = "Fix schema validation failures first; persistence remains blocked."

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/distractor-relationships-v1-projection-sprint13.md",
        "scope: audit",
        "---",
        "",
        "# Distractor Relationships V1 Projection — Sprint 13A",
        "",
        "## Purpose",
        "",
        (
            "Project Sprint 12 candidate artifacts into strict "
            "DistractorRelationship V1 records that validate against schema "
            "without changing schema permissiveness."
        ),
        "",
        "## Input Artifact",
        "",
        f"- Candidates: {input_artifact_path}",
        f"- Schema: {schema_path}",
        "",
        "## Projection Rules",
        "",
        "- Remove audit-only fields and keep only schema-defined DistractorRelationship fields.",
        (
            "- Preserve source, source_rank, target taxon, candidate "
            "scientific name, status, reason, confusion_types, "
            "difficulty_level, learner_level, pedagogical_value."
        ),
        "- Preserve canonical_taxon and unresolved_taxon typing as-is when valid.",
        (
            "- Preserve referenced_taxon only when referenced_taxon_id is "
            "stable in referenced storage snapshot."
        ),
        (
            "- Downgrade virtual/unapplied referenced_taxon to unresolved_taxon "
            "with status normalized to needs_review when required by model rules."
        ),
        "- Reject invalid records explicitly with reasons; never silently drop.",
        "",
        "## Records Projected",
        "",
        f"- Input records: {projection_result['input_records_count']}",
        f"- Projected records: {projected}",
        f"- Rejected records: {rejected}",
        "",
        "## Records Rejected",
        "",
        f"- Rejection distribution: {projection_result['rejection_reason_distribution']}",
        "",
        "## Schema Validation Result",
        "",
        f"- schema_validation_error_count: {schema_errors}",
        "- Requirement target: 0",
        "",
        "## Blockers for Persistence",
        "",
        (
            "- Projection now isolates schema-compliant records, but referenced "
            "taxon shell apply path remains required before persisting "
            "unresolved/referenced edges safely."
        ),
        "- Any rejected records must be triaged before persistence batch planning.",
        "",
        "## Recommended Next Phase",
        "",
        f"- Decision: {decision}",
        f"- Next: {next_phase}",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run_projection(
    input_path: Path,
    schema_path: Path,
    output_json_path: Path,
    output_md_path: Path,
    referenced_snapshot_path: Path | None,
) -> dict[str, Any]:
    candidates_payload = _load_json(input_path)
    schema = _load_json(schema_path)
    stable_referenced_ids = _load_stable_referenced_taxon_ids(referenced_snapshot_path)

    projection_result = project_candidates(candidates_payload, schema, stable_referenced_ids)
    projection_result["input_artifact"] = str(input_path)
    projection_result["schema"] = str(schema_path)
    projection_result["stable_referenced_taxon_id_count"] = len(stable_referenced_ids)

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(projection_result, indent=2), encoding="utf-8")

    write_markdown_report(output_md_path, projection_result, input_path, schema_path)
    return projection_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Project distractor candidate records to schema-compliant "
            "distractor relationships"
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--referenced-snapshot",
        type=Path,
        default=DEFAULT_REFERENCED_SNAPSHOT_PATH,
        help=(
            "Optional referenced taxa snapshot used to determine stable "
            "referenced_taxon_id values"
        ),
    )
    args = parser.parse_args()

    result = run_projection(
        input_path=args.input,
        schema_path=args.schema,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
        referenced_snapshot_path=args.referenced_snapshot,
    )

    print(f"Decision: {result['decision']}")
    print(f"Input: {result['input_records_count']}")
    print(f"Projected: {result['projected_records_count']}")
    print(f"Rejected: {result['rejected_records_count']}")
    print(f"Schema validation errors: {result['schema_validation_error_count']}")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_md}")


if __name__ == "__main__":
    main()
