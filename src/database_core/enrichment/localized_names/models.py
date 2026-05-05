from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Locale = Literal["fr", "en", "nl"]
Confidence = Literal["high", "medium_high", "medium", "low"]
Decision = Literal[
    "auto_accept", "same_value", "skip_optional_missing", "needs_review", "evidence_only"
]


@dataclass(frozen=True)
class RuntimeTaxon:
    taxon_kind: Literal["canonical_taxon", "referenced_taxon"]
    taxon_id: str
    scientific_name: str
    existing_names: dict[str, list[str]] = field(default_factory=dict)
    source_taxon_id: str | None = None
    is_active: bool | None = True
    rank: str | None = None
    wikipedia_url: str | None = None
    runtime_relevant: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NameEvidence:
    taxon_kind: str
    taxon_id: str
    scientific_name: str
    locale: str
    value: str
    source: str
    method: str
    confidence: Confidence
    source_url: str | None = None
    raw_ref: dict[str, Any] = field(default_factory=dict)

    @property
    def source_identity(self) -> str:
        return f"{self.source}:{self.method}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NameDecision:
    taxon_kind: str
    taxon_id: str
    scientific_name: str
    locale: str
    existing_value: str | None
    decision: Decision
    chosen_value: str | None
    reason: str
    source_identity: str | None
    source_value: str | None
    evidence: tuple[NameEvidence, ...] = ()
    alternatives: tuple[NameEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = [
            {
                "source": item.source,
                "method": item.method,
                "confidence": item.confidence,
                "value": item.value,
                "source_url": item.source_url,
            }
            for item in self.evidence
        ]
        data["alternatives"] = [item.to_dict() for item in self.alternatives]
        data.pop("evidence", None)
        return data


@dataclass(frozen=True)
class LocalizedNameReviewItem:
    taxon_kind: str
    taxon_id: str
    scientific_name: str
    locale: str
    reason: str
    existing_value: str | None
    candidates: tuple[NameEvidence, ...] = ()
    recommended_action: str = "manual_select_or_ignore"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return data


@dataclass(frozen=True)
class LocalizedNameApplyPlan:
    schema_version: str
    generated_at: str
    config: dict[str, Any]
    plan_hash: str
    items: tuple[NameDecision, ...]
    review_items_required: tuple[LocalizedNameReviewItem, ...]
    optional_coverage_gaps: tuple[LocalizedNameReviewItem, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "config": self.config,
            "plan_hash": self.plan_hash,
            "items": [item.to_dict() for item in self.items],
            "review_items_required": [item.to_dict() for item in self.review_items_required],
            "optional_coverage_gaps": [item.to_dict() for item in self.optional_coverage_gaps],
            "metrics": self.metrics,
        }
