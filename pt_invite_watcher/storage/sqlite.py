from __future__ import annotations

"""
Compatibility wrapper.

The concrete implementation lives in `pt_invite_watcher.storage.sqlite_store`.
Keep this module stable for existing imports:

    from pt_invite_watcher.storage.sqlite import SqliteStore
"""

from pt_invite_watcher.storage.sqlite_store import SqliteStore, StoredSiteState

__all__ = ["SqliteStore", "StoredSiteState"]

