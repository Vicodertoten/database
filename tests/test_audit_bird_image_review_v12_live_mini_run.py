from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script_path = Path("scripts/audit_bird_image_review_v12_live_mini_run.py")
    spec = importlib.util.spec_from_file_location(
        "audit_bird_image_review_v12_live_mini_run",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load live mini-run audit script module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_mini_run_skips_safely_without_credentials(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "live-mini-report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-3.1-flash-lite-preview",
        gemini_concurrency=1,
        uncertain_policy="reject",
        qualification_policy="v1.1",
        output_path=output_path,
    )

    assert report["execution_status"] == "skipped_missing_credentials"
    assert report["decision"] == "INVESTIGATE_LIVE_FAILURES"
    assert report["sample_size"] == 0
    assert report["summary"]["skip_reason"] == "missing_live_credentials"
    assert module.validate_comparison_report_schema(report) is True


def test_v12_failure_reason_distribution_is_computed() -> None:
    module = _load_script_module()
    distribution = module.compute_v12_failure_reason_distribution(
        [
            {"status": "ok"},
            {
                "status": "bird_image_review_failed",
                "failure_reason": "schema_validation_failed",
            },
            {
                "status": "bird_image_review_failed",
                "failure_reason": "model_output_invalid",
            },
            {
                "status": "bird_image_review_failed",
                "failure_reason": "schema_validation_failed",
            },
        ]
    )

    assert distribution == {
        "model_output_invalid": 1,
        "schema_validation_failed": 2,
    }


def test_feedback_metrics_and_generic_feedback_are_deterministic() -> None:
    module = _load_script_module()
    complete_specific_review = {
        "post_answer_feedback": {
            "correct": {
                "short": "Sur cette image, le bec et la poitrine sont nets.",
                "long": "Ici, le bec, la poitrine et la queue sont bien visibles.",
            },
            "incorrect": {
                "short": "Sur cette image, revois le bec et la poitrine.",
                "long": "Ici, compare le bec, la queue et la silhouette avant de repondre.",
            },
            "identification_tips": [
                "Sur cette image, commence par le bec.",
                "Ici, verifie ensuite la poitrine et la queue.",
            ],
        }
    }
    generic_review = {
        "post_answer_feedback": {
            "correct": {
                "short": "Regarde la couleur et la forme generale.",
                "long": "Regarde la couleur et la forme generale de l oiseau.",
            },
            "incorrect": {
                "short": "Regarde la couleur et la forme.",
                "long": "Regarde la couleur et la forme generale.",
            },
            "identification_tips": [
                "Regarde la couleur.",
                "Regarde la forme.",
            ],
        }
    }

    metrics = module.compute_feedback_metrics(
        [complete_specific_review, generic_review]
    )
    assert metrics["feedback_completeness_rate"] == 1.0
    assert metrics["feedback_image_specificity_rate"] == 0.5
    assert metrics["generic_feedback_rate"] == 0.5
    assert module.is_generic_feedback(
        generic_review["post_answer_feedback"]
    ) is True
    assert module.is_generic_feedback(
        complete_specific_review["post_answer_feedback"]
    ) is False


def test_comparison_report_schema_validation() -> None:
    module = _load_script_module()
    per_image_results = [
        {
            "source_media_id": "810001",
            "v1_1": {
                "status": "ok",
                "profile_overall_score": 80,
                "profile_status": "profiled",
                "export_eligible": True,
                "mature_playable": True,
            },
            "v1_2": {
                "status": "ok",
                "failure_reason": None,
                "score_overall": 82,
                "score_payload": {
                    "overall": 82,
                    "subscores": {
                        "diagnostic_feature_visibility": 20,
                        "feedback_quality": 15,
                    },
                },
                "normalized_review": {
                    "status": "success",
                    "post_answer_feedback": {
                        "correct": {
                            "short": "Sur cette image, le bec est net.",
                            "long": "Ici, le bec et la poitrine sont visibles.",
                        },
                        "incorrect": {
                            "short": "Sur cette image, revois le bec.",
                            "long": "Ici, controle bec et poitrine avant de repondre.",
                        },
                        "identification_tips": [
                            "Sur cette image, observe le bec.",
                            "Ici, confirme avec la poitrine.",
                        ],
                    },
                },
                "post_answer_feedback": {
                    "correct": {
                        "short": "Sur cette image, le bec est net.",
                        "long": "Ici, le bec et la poitrine sont visibles.",
                    },
                    "incorrect": {
                        "short": "Sur cette image, revois le bec.",
                        "long": "Ici, controle bec et poitrine avant de repondre.",
                    },
                    "identification_tips": [
                        "Sur cette image, observe le bec.",
                        "Ici, confirme avec la poitrine.",
                    ],
                },
                "profile_status": "profiled",
                "profile_overall_score": 81,
                "export_eligible": True,
                "mature_playable": True,
            },
        }
    ]
    summary = module.compute_comparison_summary(per_image_results)
    report = {
        "schema_version": module.LIVE_AUDIT_SCHEMA_VERSION,
        "run_id": "audit:test",
        "generated_at": "2026-05-03T00:00:00Z",
        "execution_status": "completed",
        "ai_review_contract_version": "v1_2",
        "comparison_baseline_contract_version": "v1_1",
        "sample_size": 1,
        "summary": summary,
        "per_image_results": per_image_results,
        "decision": module.decide_v12_mini_run_outcome(summary),
    }

    assert module.validate_comparison_report_schema(report) is True
