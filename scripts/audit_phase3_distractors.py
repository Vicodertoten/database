from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _percent(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round((num / den) * 100, 2)


def _load_questions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    version = payload.get("pack_materialization_version") or payload.get("pack_compiled_version")
    if version not in {"pack.materialization.v2", "pack.compiled.v2"}:
        raise ValueError(f"unsupported contract version: {version}")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError("payload.questions must be a list")
    return questions


def _label_kind(label: str) -> str:
    tokens = [token for token in label.strip().split() if token]
    if len(tokens) >= 2 and tokens[0][0].isupper() and tokens[1][0].islower():
        return "scientific_or_mixed"
    return "vernacular_or_other"


def _question_has_inat_available_signal(question: dict[str, Any]) -> bool:
    # Best effort: contracts do not currently require an explicit availability field.
    value = question.get("inat_similar_available")
    if isinstance(value, bool):
        return value
    count_value = question.get("inat_similar_candidate_count")
    return isinstance(count_value, int) and count_value > 0


def _is_inat_source(source: str) -> bool:
    normalized = source.strip().lower()
    return normalized in {"inat_similar_species", "inaturalist.similar_species"}


def audit_payload(payload: dict[str, Any], *, source_name: str) -> dict[str, Any]:
    questions = _load_questions(payload)

    invariant = Counter()
    source_counts = Counter()
    reason_counts = Counter()
    distractor_taxon_counts = Counter()
    target_distractor_pair_counts = Counter()
    distractor_pairs_per_question = Counter()

    total_questions = len(questions)
    total_options = 0
    total_distractors = 0
    questions_with_inat = 0
    questions_with_out_of_pack = 0
    questions_with_three_out_of_pack = 0
    questions_with_referenced_only = 0
    questions_with_repeated_pair = 0

    referenced_only_without_label = 0
    referenced_only_scientific_or_mixed = 0
    referenced_only_low_conf_or_ambiguous = 0

    inat_available_questions = 0
    inat_available_but_unused = 0

    for question in questions:
        options = question.get("options") or []
        if not isinstance(options, list):
            options = []

        total_options += len(options)
        correct_count = sum(1 for opt in options if bool(opt.get("is_correct")))
        if len(options) == 4:
            invariant["questions_with_4_options"] += 1
        if correct_count == 1:
            invariant["questions_with_exactly_1_correct"] += 1

        target_taxon = question.get("target_canonical_taxon_id")
        canonical_ids = [opt.get("canonical_taxon_id") for opt in options]
        canonical_ids_no_null = [cid for cid in canonical_ids if isinstance(cid, str) and cid]
        if len(canonical_ids_no_null) == len(set(canonical_ids_no_null)):
            invariant["questions_with_unique_canonical_ids"] += 1

        distractors = [opt for opt in options if not bool(opt.get("is_correct"))]
        total_distractors += len(distractors)

        out_of_pack_count = 0
        has_inat = False
        has_referenced = False
        question_pair_set = set()

        for option in options:
            label = str(option.get("taxon_label") or "").strip()
            if label:
                invariant["options_with_non_empty_label"] += 1

            if bool(option.get("is_correct")):
                continue

            distractor_taxon = option.get("canonical_taxon_id")
            if target_taxon and distractor_taxon and distractor_taxon != target_taxon:
                invariant["distractors_not_equal_target"] += 1

            source = str(option.get("source") or "unknown")
            source_counts[source] += 1
            if _is_inat_source(source):
                has_inat = True

            reason_codes = option.get("reason_codes") or []
            if isinstance(reason_codes, list) and len(reason_codes) > 0:
                invariant["distractors_with_reason_codes"] += 1
                reason_counts.update(str(code) for code in reason_codes)
            else:
                reason_codes = []

            if "out_of_pack" in reason_codes:
                out_of_pack_count += 1

            referenced_only = bool(option.get("referenced_only"))
            if referenced_only:
                has_referenced = True
                if not label:
                    referenced_only_without_label += 1
                if _label_kind(label) == "scientific_or_mixed":
                    referenced_only_scientific_or_mixed += 1
                if "low_confidence" in reason_codes or "ambiguous" in reason_codes:
                    referenced_only_low_conf_or_ambiguous += 1

            if distractor_taxon:
                distractor_taxon_counts[str(distractor_taxon)] += 1
            if target_taxon and distractor_taxon:
                pair = (str(target_taxon), str(distractor_taxon))
                target_distractor_pair_counts[pair] += 1
                if pair in question_pair_set:
                    questions_with_repeated_pair += 1
                question_pair_set.add(pair)

        distractor_pairs_per_question[len(question_pair_set)] += 1

        if has_inat:
            questions_with_inat += 1
        if out_of_pack_count > 0:
            questions_with_out_of_pack += 1
        if out_of_pack_count == 3:
            questions_with_three_out_of_pack += 1
        if has_referenced:
            questions_with_referenced_only += 1

        if _question_has_inat_available_signal(question):
            inat_available_questions += 1
            if not has_inat:
                inat_available_but_unused += 1

    top_reason_codes = reason_counts.most_common(10)
    top_repeated_distractors = distractor_taxon_counts.most_common(20)

    diversity_only = 0
    taxonomic_only = 0
    inat_any = 0
    for question in questions:
        for option in question.get("options") or []:
            if bool(option.get("is_correct")):
                continue
            codes = option.get("reason_codes") or []
            if set(codes) == {"diversity_fallback"}:
                diversity_only += 1
            if set(codes) == {"taxonomic_fallback"}:
                taxonomic_only += 1
            if "inat_similar_species" in codes:
                inat_any += 1

    repeated_pair_count = sum(1 for _, count in target_distractor_pair_counts.items() if count > 1)

    report = {
        "source": source_name,
        "summary": {
            "questions": total_questions,
            "options": total_options,
            "distractors": total_distractors,
            "contract_version": payload.get("pack_materialization_version")
            or payload.get("pack_compiled_version"),
        },
        "invariants": {
            "questions_with_4_options": {
                "count": invariant["questions_with_4_options"],
                "percent": _percent(invariant["questions_with_4_options"], total_questions),
            },
            "questions_with_exactly_1_correct": {
                "count": invariant["questions_with_exactly_1_correct"],
                "percent": _percent(invariant["questions_with_exactly_1_correct"], total_questions),
            },
            "distractors_with_reason_codes": {
                "count": invariant["distractors_with_reason_codes"],
                "percent": _percent(invariant["distractors_with_reason_codes"], total_distractors),
            },
            "options_with_non_empty_label": {
                "count": invariant["options_with_non_empty_label"],
                "percent": _percent(invariant["options_with_non_empty_label"], total_options),
            },
            "distractors_not_equal_target": {
                "count": invariant["distractors_not_equal_target"],
                "percent": _percent(invariant["distractors_not_equal_target"], total_distractors),
            },
            "questions_with_unique_canonical_ids": {
                "count": invariant["questions_with_unique_canonical_ids"],
                "percent": _percent(
                    invariant["questions_with_unique_canonical_ids"],
                    total_questions,
                ),
            },
        },
        "inat_coverage": {
            "questions_with_inat_similar_species": {
                "count": questions_with_inat,
                "percent": _percent(questions_with_inat, total_questions),
            },
            "distractors_from_inat_similar_species": {
                "count": (
                    source_counts.get("inat_similar_species", 0)
                    + source_counts.get("inaturalist.similar_species", 0)
                ),
                "percent": _percent(
                    (
                        source_counts.get("inat_similar_species", 0)
                        + source_counts.get("inaturalist.similar_species", 0)
                    ),
                    total_distractors,
                ),
            },
            "inat_available_questions": inat_available_questions,
            "inat_available_but_unused": inat_available_but_unused,
            "inat_available_but_unused_percent": _percent(
                inat_available_but_unused, inat_available_questions
            ),
            "availability_note": (
                "Computed only when optional question-level fields "
                "inat_similar_available/inat_similar_candidate_count exist."
            ),
        },
        "out_of_pack": {
            "distractors_out_of_pack": {
                "count": reason_counts.get("out_of_pack", 0),
                "percent": _percent(reason_counts.get("out_of_pack", 0), total_distractors),
            },
            "questions_with_out_of_pack": {
                "count": questions_with_out_of_pack,
                "percent": _percent(questions_with_out_of_pack, total_questions),
            },
            "questions_with_3_out_of_pack": {
                "count": questions_with_three_out_of_pack,
                "percent": _percent(questions_with_three_out_of_pack, total_questions),
            },
        },
        "referenced_only": {
            "distractors_referenced_only": {
                "count": reason_counts.get("referenced_only", 0),
                "percent": _percent(reason_counts.get("referenced_only", 0), total_distractors),
            },
            "questions_with_referenced_only": {
                "count": questions_with_referenced_only,
                "percent": _percent(questions_with_referenced_only, total_questions),
            },
            "referenced_only_without_label": referenced_only_without_label,
            "referenced_only_scientific_or_mixed_label": referenced_only_scientific_or_mixed,
            "referenced_only_low_confidence_or_ambiguous": referenced_only_low_conf_or_ambiguous,
        },
        "reason_code_quality": {
            "top_reason_codes": [
                {"code": code, "count": count} for code, count in top_reason_codes
            ],
            "diversity_fallback_only": {
                "count": diversity_only,
                "percent": _percent(diversity_only, total_distractors),
            },
            "taxonomic_fallback_only": {
                "count": taxonomic_only,
                "percent": _percent(taxonomic_only, total_distractors),
            },
            "inat_similar_species_any": {
                "count": inat_any,
                "percent": _percent(inat_any, total_distractors),
            },
        },
        "repetition": {
            "top_20_repeated_distractor_taxa": [
                {"canonical_taxon_id": taxon_id, "count": count}
                for taxon_id, count in top_repeated_distractors
            ],
            "average_repetitions_per_distractor_taxon": round(
                (sum(distractor_taxon_counts.values()) / max(1, len(distractor_taxon_counts))), 2
            ),
            "target_distractor_pairs_reused": repeated_pair_count,
            "target_distractor_pairs_reused_percent": _percent(
                repeated_pair_count, len(target_distractor_pair_counts)
            ),
            "questions_with_repeated_pair_inside_question": questions_with_repeated_pair,
            "pair_cardinality_distribution": dict(sorted(distractor_pairs_per_question.items())),
        },
    }
    return report


def _print_human_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"=== {report['source']} ===")
    print(
        f"questions={summary['questions']} options={summary['options']} "
        f"distractors={summary['distractors']} "
        f"version={summary['contract_version']}"
    )

    print("\n[Invariants]")
    for key, value in report["invariants"].items():
        print(f"- {key}: {value['count']} ({value['percent']}%)")

    print("\n[iNat coverage]")
    inat = report["inat_coverage"]
    print(
        "- questions_with_inat_similar_species: "
        f"{inat['questions_with_inat_similar_species']['count']} "
        f"({inat['questions_with_inat_similar_species']['percent']}%)"
    )
    print(
        "- distractors_from_inat_similar_species: "
        f"{inat['distractors_from_inat_similar_species']['count']} "
        f"({inat['distractors_from_inat_similar_species']['percent']}%)"
    )
    print(
        "- inat_available_but_unused: "
        f"{inat['inat_available_but_unused']}/{inat['inat_available_questions']} "
        f"({inat['inat_available_but_unused_percent']}%)"
    )

    print("\n[Out of pack]")
    oop = report["out_of_pack"]
    print(
        f"- distractors_out_of_pack: {oop['distractors_out_of_pack']['count']} "
        f"({oop['distractors_out_of_pack']['percent']}%)"
    )
    print(
        f"- questions_with_out_of_pack: {oop['questions_with_out_of_pack']['count']} "
        f"({oop['questions_with_out_of_pack']['percent']}%)"
    )
    print(
        f"- questions_with_3_out_of_pack: {oop['questions_with_3_out_of_pack']['count']} "
        f"({oop['questions_with_3_out_of_pack']['percent']}%)"
    )

    print("\n[Referenced only]")
    ref = report["referenced_only"]
    print(
        f"- distractors_referenced_only: {ref['distractors_referenced_only']['count']} "
        f"({ref['distractors_referenced_only']['percent']}%)"
    )
    print(
        f"- questions_with_referenced_only: {ref['questions_with_referenced_only']['count']} "
        f"({ref['questions_with_referenced_only']['percent']}%)"
    )
    print(f"- referenced_only_without_label: {ref['referenced_only_without_label']}")
    print(
        "- referenced_only_low_confidence_or_ambiguous: "
        f"{ref['referenced_only_low_confidence_or_ambiguous']}"
    )

    print("\n[Reason code quality]")
    reason = report["reason_code_quality"]
    print(
        f"- diversity_fallback_only: {reason['diversity_fallback_only']['count']} "
        f"({reason['diversity_fallback_only']['percent']}%)"
    )
    print(
        f"- taxonomic_fallback_only: {reason['taxonomic_fallback_only']['count']} "
        f"({reason['taxonomic_fallback_only']['percent']}%)"
    )
    print(
        f"- inat_similar_species_any: {reason['inat_similar_species_any']['count']} "
        f"({reason['inat_similar_species_any']['percent']}%)"
    )
    print("- top_reason_codes:")
    for item in reason["top_reason_codes"]:
        print(f"  * {item['code']}: {item['count']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Phase 3 distractor quality metrics for "
            "pack.compiled.v2 / pack.materialization.v2 files."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more JSON files (pack.compiled.v2 or pack.materialization.v2)",
    )
    parser.add_argument(
        "--output-json",
        help="Optional output JSON file for aggregated report",
    )
    args = parser.parse_args()

    reports: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for path_str in args.paths:
        path = Path(path_str)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            report = audit_payload(payload, source_name=str(path))
            reports.append(report)
            _print_human_report(report)
            print()
        except Exception as exc:  # pragma: no cover - thin CLI guard
            errors[str(path)] = str(exc)

    aggregate: dict[str, Any] = {"reports": reports, "errors": errors}

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(aggregate, indent=2, ensure_ascii=True), encoding="utf-8")

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
