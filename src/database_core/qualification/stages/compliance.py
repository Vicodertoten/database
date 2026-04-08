from __future__ import annotations

from dataclasses import dataclass

from database_core.domain.enums import LicenseSafetyResult, MediaType
from database_core.domain.models import MediaAsset, SourceObservation
from database_core.qualification.policy import evaluate_license_safety


@dataclass(frozen=True)
class ComplianceScreeningResult:
    license_safety_result: LicenseSafetyResult
    flags: list[str]


def run_compliance_screening(
    *,
    media_asset: MediaAsset,
    observation: SourceObservation,
) -> ComplianceScreeningResult:
    flags: list[str] = []
    if media_asset.media_type != MediaType.IMAGE:
        flags.append("unsupported_media_type")

    license_safety_result = evaluate_license_safety(
        media_license=media_asset.license,
        observation_license=observation.source_quality.observation_license,
    )
    if license_safety_result == LicenseSafetyResult.UNSAFE:
        flags.append("unsafe_license")

    return ComplianceScreeningResult(
        license_safety_result=license_safety_result,
        flags=flags,
    )
