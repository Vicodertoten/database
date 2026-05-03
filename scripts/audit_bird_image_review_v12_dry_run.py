#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from database_core.qualification.bird_image_review_v12 import (
    build_failed_bird_image_review_v12,
    compute_bird_image_pedagogical_score_v12,
    is_playable_bird_image_review_v12,
    parse_bird_image_pedagogical_review_v12,
)


@dataclass(frozen=True)
class _CandidateReview:
    media_id: str
    raw_response: str


def _build_success_payload() -> dict[str, object]:
    return {
        "schema_version": "bird_image_pedagogical_review.v1.2",
        "prompt_version": "bird_image_review_prompt.v1.2",
        "status": "success",
        "failure_reason": None,
        "consistency_warning": None,
        "image_assessment": {
            "technical_quality": "high",
            "subject_visibility": "high",
            "sharpness": "high",
            "lighting": "medium",
            "background_clutter": "low",
            "occlusion": "none",
            "view_angle": "lateral",
            "visible_parts": ["head", "beak", "breast", "tail"],
            "confidence": 0.9,
        },
        "pedagogical_assessment": {
            "pedagogical_quality": "high",
            "difficulty_level": "easy",
            "media_role": "primary_identification",
            "diagnostic_feature_visibility": "high",
            "representativeness": "high",
            "learning_suitability": "high",
            "confusion_relevance": "medium",
            "confidence": 0.88,
        },
        "identification_features_visible_in_this_image": [
            {
                "feature": "beak shape",
                "body_part": "beak",
                "visibility": "high",
                "importance_for_identification": "high",
                "explanation": "Sur cette image, le bec est bien visible.",
            }
        ],
        "post_answer_feedback": {
            "correct": {
                "short": "Oui. Sur cette image, le bec et la poitrine sont nets.",
                "long": (
                    "Sur cette image, commence par le bec puis la poitrine; "
                    "ici la silhouette et la queue confirment l'identification."
                ),
            },
            "incorrect": {
                "short": "Pas encore. Sur cette image, verifie d'abord le bec et la poitrine.",
                "long": "Ici, controle le bec, la poitrine et la queue avant de repondre.",
            },
            "identification_tips": [
                "Sur cette image, repere le bec puis la poitrine.",
                "Ici, compare la silhouette et la queue.",
                "Observe aussi l'oeil pour confirmer.",
            ],
            "confidence": 0.84,
        },
        "limitations": {
            "why_not_ideal": [],
            "uncertainty_reason": None,
            "requires_human_review": False,
        },
        "overall_confidence": 0.87,
    }


def _fixture_candidates() -> list[_CandidateReview]:
    success_payload = _build_success_payload()
    schema_invalid_payload = {
        "status": "success",
    }
    failed_payload = build_failed_bird_image_review_v12(failure_reason="image_too_blurry")
    return [
        _CandidateReview(media_id="fixture-1", raw_response=json.dumps(success_payload)),
        _CandidateReview(media_id="fixture-2", raw_response=json.dumps(schema_invalid_payload)),
        _CandidateReview(media_id="fixture-3", raw_response="{not-valid-json"),
        _CandidateReview(media_id="fixture-4", raw_response=json.dumps(failed_payload)),
    ]


def run_dry_run_audit() -> dict[str, object]:
    candidates = _fixture_candidates()
    parsed_reviews = [
        parse_bird_image_pedagogical_review_v12(item.raw_response)
        for item in candidates
    ]

    success_reviews = [item for item in parsed_reviews if item.get("status") == "success"]
    failed_reviews = [item for item in parsed_reviews if item.get("status") != "success"]

    success_scores = [
        int(compute_bird_image_pedagogical_score_v12(item)["overall"])
        for item in success_reviews
    ]
    avg_score = round(sum(success_scores) / len(success_scores), 2) if success_scores else 0.0

    complete_feedback_count = sum(
        1
        for item in success_reviews
        if is_playable_bird_image_review_v12(item)
    )

    failure_reasons = Counter(
        str(item.get("failure_reason") or "unknown")
        for item in failed_reviews
    )

    return {
        "schema_version": "bird_image_review_v12_dry_run_audit.v1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "candidate_images_reviewed": len(candidates),
        "successful_v12_reviews": len(success_reviews),
        "failed_v12_reviews": len(failed_reviews),
        "average_pedagogical_score": avg_score,
        "feedback_completeness_rate": (
            round(complete_feedback_count / len(success_reviews), 4) if success_reviews else 0.0
        ),
        "failure_reasons": dict(sorted(failure_reasons.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic fixture-based dry-run audit for bird image review contract v1.2."
        )
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        help="Optional path for writing JSON report.",
    )
    args = parser.parse_args()

    report = run_dry_run_audit()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
