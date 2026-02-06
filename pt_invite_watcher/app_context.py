from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pt_invite_watcher.config import Settings
from pt_invite_watcher.effective_sites import EffectiveSitesService
from pt_invite_watcher.providers.cookiecloud_service import CookieCloudService
from pt_invite_watcher.providers.deps_service import DepsService
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.storage.sqlite import SqliteStore


if TYPE_CHECKING:
    from pt_invite_watcher.notify.manager import NotifierManager
    from pt_invite_watcher.scanner import Scanner


@dataclass
class AppContext:
    settings: Settings
    store: SqliteStore
    scanner: Scanner
    notifier: NotifierManager
    runtime_config: RuntimeConfigCache
    effective_sites: EffectiveSitesService
    deps: DepsService


async def build_context(settings: Settings) -> AppContext:
    from pt_invite_watcher.notify.manager import NotifierManager
    from pt_invite_watcher.scanner import Scanner

    store = SqliteStore(settings.db.path)
    await store.init()

    runtime_config = RuntimeConfigCache(settings, store)
    cookiecloud = CookieCloudService(settings, store, runtime_config=runtime_config)
    effective_sites = EffectiveSitesService(settings, store, runtime_config=runtime_config)
    deps = DepsService(settings, store, runtime_config=runtime_config, cookiecloud=cookiecloud)
    notifier = NotifierManager(store=store, settings=settings, runtime_config=runtime_config)
    scanner = Scanner(
        settings=settings,
        store=store,
        notifier=notifier,
        runtime_config=runtime_config,
        effective_sites=effective_sites,
        deps=deps,
        cookiecloud=cookiecloud,
    )

    return AppContext(
        settings=settings,
        store=store,
        scanner=scanner,
        notifier=notifier,
        runtime_config=runtime_config,
        effective_sites=effective_sites,
        deps=deps,
    )
