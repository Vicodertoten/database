from database_core.qualification.classification import derive_minimal_classification


def test_classification_full_bird_high_visibility_maps_to_core_id() -> None:
    classification = derive_minimal_classification(
        {
            "qualification_status": "accepted",
            "media_role": "primary_id",
            "technical_quality": "high",
            "difficulty_level": "easy",
            "learning_suitability": "high",
            "diagnostic_feature_visibility": "high",
            "visible_parts": ["head", "wing", "tail"],
            "view_angle": "lateral",
            "qualification_flags": [],
            "qualification_notes": "",
            "uncertainty_reason": "none",
            "ai_confidence": 0.95,
        }
    )
    assert classification.observation_kind == "full_bird"
    assert classification.diagnostic_strength == "high"
    assert classification.pedagogical_role == "core_id"
    assert classification.difficulty_band == "starter"


def test_classification_weak_signals_map_to_context_or_advanced() -> None:
    classification = derive_minimal_classification(
        {
            "qualification_status": "accepted",
            "media_role": "context",
            "technical_quality": "medium",
            "difficulty_level": "medium",
            "learning_suitability": "medium",
            "diagnostic_feature_visibility": "unknown",
            "visible_parts": [],
            "qualification_flags": ["missing_visible_parts", "missing_view_angle"],
            "qualification_notes": "",
            "uncertainty_reason": "distance",
        }
    )
    assert classification.observation_kind in {"partial", "habitat_context"}
    assert classification.diagnostic_strength in {"low", "unknown"}
    assert classification.pedagogical_role in {"context", "advanced_id"}
    assert classification.difficulty_band == "intermediate"


def test_classification_low_technical_quality_is_not_core() -> None:
    classification = derive_minimal_classification(
        {
            "qualification_status": "accepted",
            "media_role": "primary_id",
            "technical_quality": "low",
            "difficulty_level": "hard",
            "learning_suitability": "high",
            "diagnostic_feature_visibility": "high",
            "visible_parts": ["head", "beak"],
            "qualification_flags": ["insufficient_technical_quality"],
            "qualification_notes": "",
            "uncertainty_reason": "none",
        }
    )
    assert classification.pedagogical_role in {"advanced_id", "context"}
    assert classification.pedagogical_role != "core_id"
    assert classification.difficulty_band == "expert"


def test_classification_trace_or_carcass_maps_to_forensics_or_excluded() -> None:
    trace = derive_minimal_classification(
        {
            "qualification_status": "accepted",
            "media_role": "primary_id",
            "technical_quality": "medium",
            "difficulty_level": "unknown",
            "learning_suitability": "low",
            "diagnostic_feature_visibility": "low",
            "visible_parts": ["feather"],
            "qualification_flags": [],
            "qualification_notes": "single feather on ground",
            "uncertainty_reason": "none",
        }
    )
    rejected = derive_minimal_classification(
        {
            "qualification_status": "rejected",
            "media_role": "primary_id",
            "technical_quality": "medium",
            "difficulty_level": "unknown",
            "learning_suitability": "low",
            "diagnostic_feature_visibility": "low",
            "visible_parts": ["carcass"],
            "qualification_flags": [],
            "qualification_notes": "carcass",
            "uncertainty_reason": "none",
        }
    )
    assert trace.pedagogical_role == "forensics"
    assert rejected.pedagogical_role == "excluded"
