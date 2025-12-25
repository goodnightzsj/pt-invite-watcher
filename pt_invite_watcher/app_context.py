from __future__ import annotations

from dataclasses import dataclass

from pt_invite_watcher.config import Settings
from pt_invite_watcher.storage.sqlite import SqliteStore


@dataclass
class AppContext:
    settings: Settings
    store: SqliteStore
    scanner: object
    notifier: object


async def build_context(settings: Settings) -> AppContext:
    from pt_invite_watcher.notify.manager import NotifierManager
    from pt_invite_watcher.scanner import Scanner

    store = SqliteStore(settings.db.path)
    await store.init()

    notifier = NotifierManager(store=store)
    scanner = Scanner(settings=settings, store=store, notifier=notifier)

    return AppContext(settings=settings, store=store, scanner=scanner, notifier=notifier)

