from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.providers.deps_service import DepsService
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.storage.sqlite import SqliteStore


async def probe_dependencies(
    store: SqliteStore,
    settings: Settings,
    *,
    now: Optional[datetime] = None,
    runtime_config: RuntimeConfigCache | None = None,
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    return await DepsService(settings, store, runtime_config=runtime_config).probe(now=checked_at)
