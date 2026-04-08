from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from database_core.domain.enums import LicenseSafetyResult, QualificationStatus
from database_core.domain.models import QualifiedResource
from database_core.versioning import REVIEW_OVERRIDE_VERSION

DEFAULT_REVIEW_OVERRIDES_DIR = Path("data/review_overrides")


class ReviewOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    media_asset_id: str
    qualification_status: QualificationStatus
    note: str


class ReviewOverrideFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    override_version: str = REVIEW_OVERRIDE_VERSION
    snapshot_id: str
    overrides: list[ReviewOverride] = Field(default_factory=list)


def resolve_review_overrides_path(snapshot_id: str, path: Path | None = None) -> Path:
    return path or DEFAULT_REVIEW_OVERRIDES_DIR / f"{snapshot_id}.json"


def load_review_override_file(path: Path | None, *, snapshot_id: str) -> ReviewOverrideFile | None:
    if path is None or not path.exists():
        return None
    payload = ReviewOverrideFile.model_validate_json(path.read_text(encoding="utf-8"))
    if payload.snapshot_id != snapshot_id:
        raise ValueError(
            f"Review overrides snapshot mismatch: expected {snapshot_id}, got {payload.snapshot_id}"
        )
    return payload


def initialize_review_override_file(
    path: Path,
    *,
    snapshot_id: str,
    force: bool = False,
) -> ReviewOverrideFile:
    if path.exists() and not force:
        raise FileExistsError(f"Review overrides file already exists: {path}")
    override_file = ReviewOverrideFile(snapshot_id=snapshot_id)
    save_review_override_file(path, override_file)
    return override_file


def save_review_override_file(path: Path, override_file: ReviewOverrideFile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(override_file.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def upsert_review_override(
    path: Path,
    *,
    snapshot_id: str,
    media_asset_id: str,
    qualification_status: QualificationStatus,
    note: str,
) -> ReviewOverrideFile:
    override_file = load_review_override_file(path, snapshot_id=snapshot_id)
    if override_file is None:
        raise FileNotFoundError(f"Review overrides file not found: {path}")

    overrides_by_media_asset_id = {item.media_asset_id: item for item in override_file.overrides}
    overrides_by_media_asset_id[media_asset_id] = ReviewOverride(
        media_asset_id=media_asset_id,
        qualification_status=qualification_status,
        note=note,
    )
    updated = override_file.model_copy(
        update={
            "overrides": sorted(
                overrides_by_media_asset_id.values(),
                key=lambda item: item.media_asset_id,
            )
        }
    )
    save_review_override_file(path, updated)
    return updated


def apply_review_overrides(
    resources: list[QualifiedResource],
    *,
    override_file: ReviewOverrideFile | None,
) -> list[QualifiedResource]:
    if override_file is None:
        return resources

    overrides = {item.media_asset_id: item for item in override_file.overrides}
    updated: list[QualifiedResource] = []
    for resource in resources:
        override = overrides.get(resource.media_asset_id)
        if override is None:
            updated.append(resource)
            continue
        notes = [
            resource.qualification_notes.strip() if resource.qualification_notes else None,
            f"override:{override.note.strip()}",
        ]
        qualification_flags = list(dict.fromkeys([*resource.qualification_flags, "human_override"]))
        export_eligible = (
            override.qualification_status == QualificationStatus.ACCEPTED
            and resource.license_safety_result == LicenseSafetyResult.SAFE
        )
        updated.append(
            resource.model_copy(
                update={
                    "qualification_status": override.qualification_status,
                    "qualification_notes": " | ".join(item for item in notes if item),
                    "qualification_flags": qualification_flags,
                    "export_eligible": export_eligible,
                }
            )
        )
    return updated
