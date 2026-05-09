from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database_core.domain.models import DistractorRelationship
from database_core.dynamic_pack import validate_session_snapshot
from database_core.storage.services import build_storage_services
from database_core.versioning import (
    SCHEMA_VERSION_LABEL,
    SESSION_SNAPSHOT_V2_VERSION,
)

PHASE2B_SESSION_AUDIT_VERSION = "phase2b.session_snapshot_v2.audit.v1"
PHASE2B_LOCALES = ("fr", "en", "nl")
PHASE2B_FIXTURE_SEEDS = (
    "phase2b-v2-seed-a",
    "phase2b-v2-seed-b",
    "phase2b-v2-seed-c",
)
PHASE2B_QUESTION_COUNT = 20
PHASE2B_SELECTOR_VERSION = "phase2b.selector.v2"
PHASE2B_DISTRACTOR_POLICY_VERSION = "phase2b.distractors.palier_a.v1"
PHASE2B_FALLBACK_SOURCE = "taxonomic_fallback_db"
PHASE2B_SOURCE_SCORES = {
    "inaturalist_similar_species": 1.0,
    "taxonomic_neighbor_same_genus": 0.8,
    "taxonomic_neighbor_same_family": 0.6,
    "taxonomic_neighbor_same_order": 0.4,
    PHASE2B_FALLBACK_SOURCE: 0.2,
}


@dataclass(frozen=True)
class DistractorCandidate:
    canonical_taxon_id: str
    source: str
    score: float
    reason_codes: tuple[str, ...]
    relationship_id: str | None = None


def build_session_fixtures_v2(
    *,
    database_url: str,
    pool_id: str,
    output_dir: Path,
    seeds: tuple[str, ...] = PHASE2B_FIXTURE_SEEDS,
    locales: tuple[str, ...] = PHASE2B_LOCALES,
    question_count: int = PHASE2B_QUESTION_COUNT,
) -> list[dict[str, Any]]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")

    taxonomy_profiles = _fetch_taxonomy_profiles(database_url=database_url)
    relationships_by_target = (
        services.distractor_relationship_store.fetch_validated_distractors_by_target()
    )
    sessions: list[dict[str, Any]] = []
    for seed in seeds:
        for locale in locales:
            session = build_session_snapshot_v2(
                pool=pool,
                locale=locale,
                seed=seed,
                question_count=question_count,
                relationships_by_target=relationships_by_target,
                taxonomy_profiles=taxonomy_profiles,
            )
            validate_session_snapshot(session)
            services.dynamic_pack_store.save_session_snapshot(session)
            _write_json(
                output_dir / f"session_snapshot.{seed}.{locale}.v2.json",
                session,
            )
            sessions.append(session)

    index = {
        "schema_version": PHASE2B_SESSION_AUDIT_VERSION,
        "generated_at": _now_iso(),
        "pool_id": pool_id,
        "session_count": len(sessions),
        "sessions": sessions,
    }
    _write_json(output_dir / "session_fixture_index.json", index)
    return sessions


def build_session_snapshot_v2(
    *,
    pool: dict[str, Any],
    locale: str,
    seed: str,
    question_count: int,
    relationships_by_target: dict[str, list[DistractorRelationship]],
    taxonomy_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if locale not in PHASE2B_LOCALES:
        raise ValueError(f"Unsupported locale: {locale}")
    if question_count != PHASE2B_QUESTION_COUNT:
        raise ValueError(f"question_count must be {PHASE2B_QUESTION_COUNT}")

    items = _as_pool_items(pool)
    by_taxon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_taxon[str(item["canonical_taxon_id"])].append(item)
    if len(by_taxon) < question_count:
        raise ValueError(
            "Pool does not contain enough distinct taxa for max-one-per-taxon fixtures "
            f"(requested={question_count}, available_taxa={len(by_taxon)})"
        )

    taxon_labels = _taxon_labels_from_pool(items)
    rng = random.Random(_stable_seed(f"v2:{seed}:{locale}:{pool['pool_id']}"))
    taxon_ids = sorted(by_taxon)
    rng.shuffle(taxon_ids)
    selected_taxa = taxon_ids[:question_count]
    used_media_asset_ids: set[str] = set()
    questions: list[dict[str, Any]] = []

    for index, taxon_id in enumerate(selected_taxa, start=1):
        item = _select_target_item(
            rows=by_taxon[taxon_id],
            rng=rng,
            used_media_asset_ids=used_media_asset_ids,
        )
        used_media_asset_ids.add(str(item["media_asset_id"]))
        question_id = _stable_id(
            "question",
            "v2",
            str(pool["pool_id"]),
            seed,
            locale,
            str(index),
            str(item["playable_item_id"]),
        )
        options = _build_options(
            question_id=question_id,
            target_item=item,
            locale=locale,
            taxon_labels=taxon_labels,
            relationships=relationships_by_target.get(taxon_id, []),
            taxonomy_profiles=taxonomy_profiles,
            rng=rng,
        )
        correct_option_id = next(
            str(option["option_id"]) for option in options if bool(option["is_correct"])
        )
        labels = item["labels"]
        label_sources = item["label_sources"]
        questions.append(
            {
                "question_id": question_id,
                "question_index": index,
                "playable_item_id": item["playable_item_id"],
                "canonical_taxon_id": item["canonical_taxon_id"],
                "media_asset_id": item["media_asset_id"],
                "common_name": labels[locale],
                "scientific_name": item["scientific_name"],
                "label_source": label_sources[locale],
                "feedback_short": item["feedback_short"],
                "media": item["media"],
                "country_code": item["country_code"],
                "correct_option_id": correct_option_id,
                "options": options,
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION_LABEL,
        "session_snapshot_version": SESSION_SNAPSHOT_V2_VERSION,
        "session_snapshot_id": _stable_id("session", "v2", str(pool["pool_id"]), seed, locale),
        "pool_id": pool["pool_id"],
        "source_run_id": pool["source_run_id"],
        "generated_at": _now_iso(),
        "locale": locale,
        "seed": seed,
        "question_count": question_count,
        "selector_policy": {
            "version": PHASE2B_SELECTOR_VERSION,
            "max_questions_per_taxon": 1,
            "unique_media_per_session": True,
        },
        "distractor_policy": {
            "version": PHASE2B_DISTRACTOR_POLICY_VERSION,
            "referenced_only_allowed": False,
            "max_referenced_only_per_question": 0,
            "fallback_source": PHASE2B_FALLBACK_SOURCE,
        },
        "questions": questions,
    }
    validate_session_snapshot(payload)
    validate_session_snapshot_v2_invariants(payload)
    return payload


def audit_session_snapshots_v2(
    *,
    database_url: str,
    pool_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    index_path = output_dir / "session_fixture_index.json"
    blockers: list[str] = []
    warnings: list[str] = []
    session_reports: list[dict[str, Any]] = []
    fallback_count = 0

    if not index_path.exists():
        blockers.append("missing_session_fixture_index")
        sessions: list[dict[str, Any]] = []
    else:
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        raw_sessions = index_payload.get("sessions", [])
        sessions = [item for item in raw_sessions if isinstance(item, dict)]

    if len(sessions) != len(PHASE2B_FIXTURE_SEEDS) * len(PHASE2B_LOCALES):
        blockers.append("unexpected_fixture_count")

    seen_seed_locales: set[tuple[str, str]] = set()
    for session in sessions:
        session_id = str(session.get("session_snapshot_id") or "")
        try:
            validate_session_snapshot(session)
            validate_session_snapshot_v2_invariants(session)
        except ValueError as exc:
            blockers.append("invalid_session_snapshot")
            session_reports.append(
                {"session_snapshot_id": session_id, "valid": False, "error": str(exc)}
            )
            continue

        db_payload = services.dynamic_pack_store.fetch_session_snapshot(
            session_snapshot_id=session_id
        )
        if db_payload != session:
            blockers.append("db_payload_mismatch")

        seed_locale = (str(session["seed"]), str(session["locale"]))
        seen_seed_locales.add(seed_locale)
        session_fallback_count = _count_fallback_options(session)
        fallback_count += session_fallback_count
        session_reports.append(
            {
                "session_snapshot_id": session_id,
                "seed": session["seed"],
                "locale": session["locale"],
                "question_count": session["question_count"],
                "fallback_option_count": session_fallback_count,
                "valid": True,
            }
        )

    expected_seed_locales = {
        (seed, locale) for seed in PHASE2B_FIXTURE_SEEDS for locale in PHASE2B_LOCALES
    }
    if seen_seed_locales != expected_seed_locales:
        blockers.append("missing_expected_seed_locale_fixture")
    if any(session.get("pool_id") != pool_id for session in sessions):
        blockers.append("fixture_pool_id_mismatch")
    if fallback_count:
        warnings.append("taxonomic_fallback_db_used")

    status = "GO"
    if blockers:
        status = "NO_GO"
    elif warnings:
        status = "GO_WITH_WARNINGS"

    report = {
        "schema_version": PHASE2B_SESSION_AUDIT_VERSION,
        "report_type": "session_snapshot_v2_audit",
        "generated_at": _now_iso(),
        "pool_id": pool_id,
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "fixture_count": len(sessions),
        "fallback_option_count": fallback_count,
        "sessions": session_reports,
    }
    _write_json(output_dir / "session_snapshot_v2_audit.json", report)
    _write_markdown_report(output_dir / "session_snapshot_v2_audit.md", report)
    return report


def validate_session_snapshot_v2_invariants(session: dict[str, Any]) -> None:
    if session.get("session_snapshot_version") != SESSION_SNAPSHOT_V2_VERSION:
        raise ValueError("session_snapshot_version must be session_snapshot.v2")
    questions = session.get("questions")
    if not isinstance(questions, list) or len(questions) != PHASE2B_QUESTION_COUNT:
        raise ValueError("session_snapshot.v2 must contain exactly 20 questions")

    media_asset_ids: list[str] = []
    target_taxa: list[str] = []
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("question must be an object")
        media_asset_ids.append(str(question["media_asset_id"]))
        target_taxon_id = str(question["canonical_taxon_id"])
        target_taxa.append(target_taxon_id)
        options = question["options"]
        option_taxa = [str(option["canonical_taxon_id"]) for option in options]
        if len(set(option_taxa)) != len(option_taxa):
            raise ValueError("option canonical_taxon_id values must be unique per question")
        correct_options = [option for option in options if option["is_correct"]]
        if len(correct_options) != 1:
            raise ValueError("question must include exactly one correct option")
        if str(correct_options[0]["option_id"]) != str(question["correct_option_id"]):
            raise ValueError("correct_option_id must point to the correct option")
        if str(correct_options[0]["canonical_taxon_id"]) != target_taxon_id:
            raise ValueError("correct option must match target canonical taxon")
        for option in options:
            if option["referenced_only"]:
                raise ValueError("Palier A snapshots must not include referenced_only options")
            if not option["is_correct"] and str(option["canonical_taxon_id"]) == target_taxon_id:
                raise ValueError("distractor option must not use target taxon")
            if not option["display_label"] or not option["scientific_name"]:
                raise ValueError("option display_label and scientific_name must be non-empty")
            if not option["reason_codes"]:
                raise ValueError("option reason_codes must be non-empty")

    if len(set(media_asset_ids)) != len(media_asset_ids):
        raise ValueError("media_asset_id values must be unique per session")
    if len(set(target_taxa)) != len(target_taxa):
        raise ValueError("Phase 2B fixtures must use max one question per taxon")


def _build_options(
    *,
    question_id: str,
    target_item: dict[str, Any],
    locale: str,
    taxon_labels: dict[str, dict[str, Any]],
    relationships: list[DistractorRelationship],
    taxonomy_profiles: dict[str, dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    target_taxon_id = str(target_item["canonical_taxon_id"])
    selected_candidates = _select_distractors(
        target_taxon_id=target_taxon_id,
        relationships=relationships,
        taxon_labels=taxon_labels,
        taxonomy_profiles=taxonomy_profiles,
        rng=rng,
    )
    options = [
        _option_payload(
            option_id=f"{question_id}:opt:correct",
            taxon_id=target_taxon_id,
            locale=locale,
            labels=taxon_labels,
            is_correct=True,
            source="target_taxon",
            score=1.0,
            reason_codes=("correct_taxon",),
            relationship_id=None,
        )
    ]
    for index, candidate in enumerate(selected_candidates, start=1):
        options.append(
            _option_payload(
                option_id=f"{question_id}:opt:d{index}",
                taxon_id=candidate.canonical_taxon_id,
                locale=locale,
                labels=taxon_labels,
                is_correct=False,
                source=candidate.source,
                score=candidate.score,
                reason_codes=candidate.reason_codes,
                relationship_id=candidate.relationship_id,
            )
        )
    rng.shuffle(options)
    return options


def _select_distractors(
    *,
    target_taxon_id: str,
    relationships: list[DistractorRelationship],
    taxon_labels: dict[str, dict[str, Any]],
    taxonomy_profiles: dict[str, dict[str, Any]],
    rng: random.Random,
) -> list[DistractorCandidate]:
    candidates: list[DistractorCandidate] = []
    seen_taxa = {target_taxon_id}
    for relationship in sorted(
        relationships,
        key=lambda item: (
            -PHASE2B_SOURCE_SCORES.get(str(item.source), 0.0),
            item.source_rank,
            item.relationship_id,
        ),
    ):
        candidate_taxon_id = str(relationship.candidate_taxon_ref_id or "")
        if (
            not candidate_taxon_id
            or candidate_taxon_id in seen_taxa
            or candidate_taxon_id not in taxon_labels
        ):
            continue
        candidates.append(
            DistractorCandidate(
                canonical_taxon_id=candidate_taxon_id,
                source=str(relationship.source),
                score=PHASE2B_SOURCE_SCORES.get(str(relationship.source), 0.0),
                reason_codes=(str(relationship.source),),
                relationship_id=relationship.relationship_id,
            )
        )
        seen_taxa.add(candidate_taxon_id)

    selected = _weighted_sample_without_replacement(
        candidates,
        count=min(3, len(candidates)),
        rng=rng,
    )
    selected_taxa = {candidate.canonical_taxon_id for candidate in selected}
    if len(selected) < 3:
        fallback_candidates = _fallback_candidates(
            target_taxon_id=target_taxon_id,
            excluded_taxa={target_taxon_id, *selected_taxa},
            taxon_labels=taxon_labels,
            taxonomy_profiles=taxonomy_profiles,
        )
        selected.extend(fallback_candidates[: 3 - len(selected)])
    if len(selected) != 3:
        raise ValueError(f"Could not select 3 distractors for {target_taxon_id}")
    return selected


def _fallback_candidates(
    *,
    target_taxon_id: str,
    excluded_taxa: set[str],
    taxon_labels: dict[str, dict[str, Any]],
    taxonomy_profiles: dict[str, dict[str, Any]],
) -> list[DistractorCandidate]:
    target_profile = taxonomy_profiles.get(target_taxon_id, {})
    target_parent = str(target_profile.get("parent_id") or "")
    target_ancestors = _ancestor_ids(target_profile)
    ranked: list[tuple[tuple[int, int, str], DistractorCandidate]] = []
    for candidate_taxon_id in sorted(taxon_labels):
        if candidate_taxon_id in excluded_taxa:
            continue
        candidate_profile = taxonomy_profiles.get(candidate_taxon_id, {})
        candidate_parent = str(candidate_profile.get("parent_id") or "")
        candidate_ancestors = _ancestor_ids(candidate_profile)
        shared_ancestors = target_ancestors.intersection(candidate_ancestors)
        if target_parent and target_parent == candidate_parent:
            reason_codes = ("shared_parent", "palier_a_fallback")
            sort_key = (0, -len(shared_ancestors), candidate_taxon_id)
        elif shared_ancestors:
            reason_codes = ("shared_ancestor", "palier_a_fallback")
            sort_key = (1, -len(shared_ancestors), candidate_taxon_id)
        else:
            reason_codes = ("taxonomic_diversity", "palier_a_fallback")
            sort_key = (2, 0, candidate_taxon_id)
        ranked.append(
            (
                sort_key,
                DistractorCandidate(
                    canonical_taxon_id=candidate_taxon_id,
                    source=PHASE2B_FALLBACK_SOURCE,
                    score=PHASE2B_SOURCE_SCORES[PHASE2B_FALLBACK_SOURCE],
                    reason_codes=reason_codes,
                    relationship_id=None,
                ),
            )
        )
    return [candidate for _, candidate in sorted(ranked, key=lambda item: item[0])]


def _option_payload(
    *,
    option_id: str,
    taxon_id: str,
    locale: str,
    labels: dict[str, dict[str, Any]],
    is_correct: bool,
    source: str,
    score: float,
    reason_codes: tuple[str, ...],
    relationship_id: str | None,
) -> dict[str, Any]:
    label_payload = labels[taxon_id]
    common_name = str(label_payload["labels"][locale])
    scientific_name = str(label_payload["scientific_name"])
    option = {
        "option_id": option_id,
        "canonical_taxon_id": taxon_id,
        "common_name": common_name,
        "scientific_name": scientific_name,
        "display_label": common_name,
        "label_source": label_payload["label_sources"][locale],
        "is_correct": is_correct,
        "referenced_only": False,
        "source": source,
        "score": score,
        "reason_codes": list(reason_codes),
    }
    if relationship_id is not None:
        option["relationship_id"] = relationship_id
    return option


def _select_target_item(
    *,
    rows: list[dict[str, Any]],
    rng: random.Random,
    used_media_asset_ids: set[str],
) -> dict[str, Any]:
    candidates = [
        item for item in sorted(rows, key=lambda item: str(item["playable_item_id"]))
        if str(item["media_asset_id"]) not in used_media_asset_ids
    ]
    if not candidates:
        raise ValueError("No unused media candidate available for selected taxon")
    return candidates[rng.randrange(len(candidates))]


def _weighted_sample_without_replacement(
    candidates: list[DistractorCandidate],
    *,
    count: int,
    rng: random.Random,
) -> list[DistractorCandidate]:
    remaining = list(candidates)
    selected: list[DistractorCandidate] = []
    while remaining and len(selected) < count:
        total_weight = sum(max(candidate.score, 0.0001) for candidate in remaining)
        threshold = rng.random() * total_weight
        running = 0.0
        selected_index = len(remaining) - 1
        for index, candidate in enumerate(remaining):
            running += max(candidate.score, 0.0001)
            if running >= threshold:
                selected_index = index
                break
        selected.append(remaining.pop(selected_index))
    return selected


def _taxon_labels_from_pool(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    labels: dict[str, dict[str, Any]] = {}
    for item in sorted(items, key=lambda value: str(value["playable_item_id"])):
        taxon_id = str(item["canonical_taxon_id"])
        labels.setdefault(
            taxon_id,
            {
                "scientific_name": item["scientific_name"],
                "labels": item["labels"],
                "label_sources": item["label_sources"],
            },
        )
    return labels


def _fetch_taxonomy_profiles(*, database_url: str) -> dict[str, dict[str, Any]]:
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT canonical_taxon_id, authority_taxonomy_profile_json
            FROM canonical_taxa
            ORDER BY canonical_taxon_id
            """
        ).fetchall()
    profiles: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            profile = json.loads(str(row["authority_taxonomy_profile_json"]))
        except json.JSONDecodeError:
            profile = {}
        profiles[str(row["canonical_taxon_id"])] = profile if isinstance(profile, dict) else {}
    return profiles


def _ancestor_ids(profile: dict[str, Any]) -> set[str]:
    raw_value = profile.get("ancestor_ids")
    if not isinstance(raw_value, list):
        return set()
    return {str(value) for value in raw_value if str(value).strip()}


def _as_pool_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    items = pool.get("items")
    if not isinstance(items, list):
        raise ValueError("pack_pool items must be a list")
    return [item for item in items if isinstance(item, dict)]


def _count_fallback_options(session: dict[str, Any]) -> int:
    return sum(
        1
        for question in session["questions"]
        for option in question["options"]
        if option["source"] == PHASE2B_FALLBACK_SOURCE
    )


def _stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {str(report['generated_at'])[:10]}",
        "source_of_truth: docs/archive/evidence/dynamic-pack-phase-2b/"
        "session-snapshot-v2-palier-a/session_snapshot_v2_audit.md",
        "scope: dynamic_pack_phase_2b_session_snapshot_v2",
        "---",
        "",
        "# Phase 2B Session Snapshot V2 Audit",
        "",
        f"- status: `{report['status']}`",
        f"- pool_id: `{report['pool_id']}`",
        f"- fixture_count: `{report['fixture_count']}`",
        f"- fallback_option_count: `{report['fallback_option_count']}`",
        f"- blockers: `{len(report['blockers'])}`",
        f"- warnings: `{len(report['warnings'])}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["blockers"] or ["none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in report["warnings"] or ["none"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
