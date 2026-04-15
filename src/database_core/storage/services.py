from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from database_core.domain.models import (
	CanonicalTaxon,
	MediaAsset,
	PlayableItem,
	QualifiedResource,
	ReviewItem,
	SourceObservation,
)
from database_core.storage.confusion_store import PostgresConfusionStore
from database_core.storage.enrichment_store import PostgresEnrichmentStore
from database_core.storage.inspection_store import PostgresInspectionStore
from database_core.storage.pack_store import PostgresPackStore
from database_core.storage.playable_store import PostgresPlayableStore
from database_core.storage.postgres import PostgresRepository


class PostgresDatabase:
	"""Transitional DB lifecycle service extracted from PostgresRepository."""

	def __init__(self, repository: PostgresRepository) -> None:
		self._repository = repository

	@property
	def database_url(self) -> str:
		return self._repository.database_url

	def connect(self):
		return self._repository.connect()

	def initialize(self, *, allow_schema_reset: bool = False) -> None:
		self._repository.initialize(allow_schema_reset=allow_schema_reset)

	def migrate_to_latest(self) -> tuple[int, ...]:
		return self._repository.migrate_to_latest()

	def current_schema_version(self) -> int:
		return self._repository.current_schema_version()


class PostgresPipelineStore:
	"""Transitional pipeline persistence service extracted from PostgresRepository."""

	def __init__(self, repository: PostgresRepository) -> None:
		self._repository = repository

	def connect(self):
		return self._repository.connect()

	def fetch_latest_completed_canonical_taxa(self) -> list[CanonicalTaxon]:
		return self._repository.fetch_latest_completed_canonical_taxa()

	def reset_materialized_state(self, *, connection: psycopg.Connection | None = None) -> None:
		self._repository.reset_materialized_state(connection=connection)

	def save_canonical_taxa(
		self,
		taxa: Sequence[CanonicalTaxon],
		*,
		run_id: str | None = None,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_canonical_taxa(taxa, run_id=run_id, connection=connection)

	def save_source_observations(
		self,
		observations: Sequence[SourceObservation],
		*,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_source_observations(observations, connection=connection)

	def save_media_assets(
		self,
		media_assets: Sequence[MediaAsset],
		*,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_media_assets(media_assets, connection=connection)

	def save_qualified_resources(
		self,
		resources: Sequence[QualifiedResource],
		*,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_qualified_resources(resources, connection=connection)

	def save_review_items(
		self,
		review_items: Sequence[ReviewItem],
		*,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_review_items(review_items, connection=connection)

	def save_playable_items(
		self,
		playable_items: Sequence[PlayableItem],
		*,
		run_id: str | None = None,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.save_playable_items(
			playable_items,
			run_id=run_id,
			connection=connection,
		)

	def start_pipeline_run(
		self,
		*,
		run_id: str,
		source_mode: str,
		dataset_id: str,
		snapshot_id: str | None,
		started_at: datetime,
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.start_pipeline_run(
			run_id=run_id,
			source_mode=source_mode,
			dataset_id=dataset_id,
			snapshot_id=snapshot_id,
			started_at=started_at,
			connection=connection,
		)

	def complete_pipeline_run(
		self,
		*,
		run_id: str,
		completed_at: datetime,
		run_status: str = "completed",
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.complete_pipeline_run(
			run_id=run_id,
			completed_at=completed_at,
			run_status=run_status,
			connection=connection,
		)

	def append_run_history(
		self,
		*,
		run_id: str,
		governance_effective_at: datetime,
		canonical_taxa: Sequence[CanonicalTaxon],
		observations: Sequence[SourceObservation],
		media_assets: Sequence[MediaAsset],
		qualified_resources: Sequence[QualifiedResource],
		review_items: Sequence[ReviewItem],
		playable_items: Sequence[PlayableItem] = (),
		connection: psycopg.Connection | None = None,
	) -> None:
		self._repository.append_run_history(
			run_id=run_id,
			governance_effective_at=governance_effective_at,
			canonical_taxa=canonical_taxa,
			observations=observations,
			media_assets=media_assets,
			qualified_resources=qualified_resources,
			review_items=review_items,
			playable_items=playable_items,
			connection=connection,
		)

	def fetch_summary(self, *, run_id: str | None = None) -> dict[str, int]:
		return self._repository.fetch_summary(run_id=run_id)

	def fetch_run_level_metrics(self, *, run_id: str | None = None) -> dict[str, object]:
		return self._repository.fetch_run_level_metrics(run_id=run_id)


@dataclass(frozen=True)
class StorageServices:
	database: PostgresDatabase
	pipeline_store: PostgresPipelineStore
	pack_store: PostgresPackStore
	enrichment_store: PostgresEnrichmentStore
	confusion_store: PostgresConfusionStore
	inspection_store: PostgresInspectionStore
	playable_store: PostgresPlayableStore
	repository: PostgresRepository


def build_storage_services(database_url: str) -> StorageServices:
	repository = PostgresRepository(database_url)
	return StorageServices(
		database=PostgresDatabase(repository),
		pipeline_store=PostgresPipelineStore(repository),
		pack_store=repository.pack_store,
		enrichment_store=repository.enrichment_store,
		confusion_store=repository.confusion_store,
		inspection_store=repository.inspection_store,
		playable_store=repository.playable_store,
		repository=repository,
	)
