from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from database_core.domain.enums import LicenseSafetyResult, QualificationStatus
from database_core.domain.models import (
    AIQualification,
    CanonicalTaxon,
    MediaAsset,
    ProvenanceSummary,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.qualification.ai import (
    AIQualificationOutcome,
    SourceExternalKey,
    serialize_source_external_key,
    source_external_key_for_media,
)
from database_core.qualification.policy import (
    build_notes,
    qualification_method,
    resolve_qualification_status,
)
from database_core.qualification.stages.compliance import run_compliance_screening
from database_core.qualification.stages.expert import run_expert_qualification
from database_core.qualification.stages.review import build_review_items
from database_core.qualification.stages.semantic import run_fast_semantic_screening
from database_core.versioning import QUALIFICATION_VERSION


def qualify_media_assets(
    *,
    canonical_taxa: Iterable[CanonicalTaxon] | None = None,
    observations: Iterable[SourceObservation],
    media_assets: Iterable[MediaAsset],
    ai_qualifications_by_source_media_key: dict[
        SourceExternalKey, AIQualification | AIQualificationOutcome
    ],
    created_at: datetime,
    run_id: str,
    uncertain_policy: str = "review",
) -> tuple[list[QualifiedResource], list[ReviewItem]]:
    observations_by_uid = {item.observation_uid: item for item in observations}
    taxon_status_by_id = {
        item.canonical_taxon_id: item.taxon_status for item in (canonical_taxa or [])
    }
    qualified_resources: list[QualifiedResource] = []

    for media_asset in sorted(media_assets, key=lambda item: item.media_id):
        observation = observations_by_uid[media_asset.source_observation_uid]
        ai_outcome = _coerce_ai_outcome(
            ai_qualifications_by_source_media_key.get(source_external_key_for_media(media_asset))
        )
        qualified_resources.append(
            _qualify_single_media(
                media_asset=media_asset,
                observation=observation,
                taxon_status_by_id=taxon_status_by_id,
                ai_outcome=ai_outcome,
                run_id=run_id,
                uncertain_policy=uncertain_policy,
            )
        )
    return qualified_resources, build_review_items(qualified_resources, created_at=created_at)


def _qualify_single_media(
    *,
    media_asset: MediaAsset,
    observation: SourceObservation,
    taxon_status_by_id: dict[str, str],
    ai_outcome: AIQualificationOutcome | None,
    run_id: str,
    uncertain_policy: str,
) -> QualifiedResource:
    ai_qualification = ai_outcome.qualification if ai_outcome else None
    compliance = run_compliance_screening(media_asset=media_asset, observation=observation)
    semantic = run_fast_semantic_screening(media_asset=media_asset)
    expert = run_expert_qualification(media_asset=media_asset, ai_qualification=ai_qualification)

    qualification_flags = list(ai_outcome.flags) if ai_outcome else []
    qualification_flags.extend(compliance.flags)
    qualification_flags.extend(semantic.flags)
    qualification_flags.extend(expert.flags)
    canonical_taxon_status = taxon_status_by_id.get(media_asset.canonical_taxon_id or "")
    if canonical_taxon_status == "deprecated":
        qualification_flags.append("deprecated_canonical_taxon")
    qualification_flags = list(dict.fromkeys(qualification_flags))
    status = resolve_qualification_status(qualification_flags, uncertain_policy=uncertain_policy)
    if canonical_taxon_status == "deprecated":
        status = QualificationStatus.REJECTED

    provenance_summary = ProvenanceSummary(
        source_name=media_asset.source_name,
        source_observation_key=serialize_source_external_key(
            (observation.source_name, observation.source_observation_id)
        ),
        source_media_key=serialize_source_external_key(source_external_key_for_media(media_asset)),
        source_observation_id=observation.source_observation_id,
        source_media_id=media_asset.source_media_id,
        raw_payload_ref=media_asset.raw_payload_ref,
        run_id=run_id,
        observation_license=observation.source_quality.observation_license,
        media_license=media_asset.license,
        qualification_method=qualification_method(
            ai_qualification=ai_qualification,
            ai_outcome=ai_outcome,
        ),
        ai_model=ai_qualification.model_name if ai_qualification else None,
        ai_prompt_version=ai_outcome.prompt_version if ai_outcome else None,
        ai_task_name="qualification",
        ai_status=ai_outcome.status if ai_outcome else "rules_only",
    )
    notes = build_notes(qualification_flags, ai_qualification, ai_outcome)
    export_eligible = (
        status == QualificationStatus.ACCEPTED
        and compliance.license_safety_result == LicenseSafetyResult.SAFE
        and canonical_taxon_status != "provisional"
    )

    return QualifiedResource(
        qualified_resource_id=f"qr:{media_asset.media_id}",
        canonical_taxon_id=media_asset.canonical_taxon_id or "unresolved",
        source_observation_uid=observation.observation_uid,
        source_observation_id=observation.source_observation_id,
        media_asset_id=media_asset.media_id,
        qualification_status=status,
        qualification_version=QUALIFICATION_VERSION,
        technical_quality=expert.technical_quality,
        pedagogical_quality=expert.pedagogical_quality,
        life_stage=expert.life_stage,
        sex=expert.sex,
        visible_parts=expert.visible_parts,
        view_angle=expert.view_angle,
        qualification_notes=notes,
        qualification_flags=qualification_flags,
        provenance_summary=provenance_summary,
        license_safety_result=compliance.license_safety_result,
        export_eligible=export_eligible,
    )


def _coerce_ai_outcome(
    value: AIQualification | AIQualificationOutcome | None,
) -> AIQualificationOutcome | None:
    if value is None:
        return None
    if isinstance(value, AIQualificationOutcome):
        return value
    return AIQualificationOutcome(qualification=value)
