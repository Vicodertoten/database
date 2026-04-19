from __future__ import annotations

from dataclasses import dataclass

from database_core.storage.pack_store import PostgresPackStore
from database_core.storage.playable_store import PostgresPlayableStore
from database_core.storage.services import build_storage_services


@dataclass(frozen=True)
class RuntimeReadOwnerService:
    """Owner-side read facade limited to official runtime surfaces."""

    playable_store: PostgresPlayableStore
    pack_store: PostgresPackStore
    default_playable_limit: int = 1000

    def read_playable_corpus(self, *, limit: int | None = None) -> dict[str, object]:
        resolved_limit = self.default_playable_limit if limit is None else limit
        if resolved_limit <= 0:
            raise ValueError("playable corpus limit must be > 0")
        return self.playable_store.fetch_playable_corpus_payload(limit=resolved_limit)

    def find_compiled_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
    ) -> dict[str, object] | None:
        payloads = self.pack_store.fetch_compiled_pack_builds(
            pack_id=pack_id,
            revision=revision,
            limit=1,
        )
        if not payloads:
            return None
        return payloads[0]

    def find_pack_materialization(
        self,
        *,
        materialization_id: str,
    ) -> dict[str, object] | None:
        return self.pack_store.fetch_pack_materialization_by_id(
            materialization_id=materialization_id
        )


def build_runtime_read_owner_service(
    database_url: str,
    *,
    default_playable_limit: int = 1000,
) -> RuntimeReadOwnerService:
    storage_services = build_storage_services(database_url)
    return RuntimeReadOwnerService(
        playable_store=storage_services.playable_store,
        pack_store=storage_services.pack_store,
        default_playable_limit=default_playable_limit,
    )
