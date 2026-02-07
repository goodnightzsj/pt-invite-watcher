from __future__ import annotations

# NOTE: This module contains the concrete SqliteStore implementation.
# Keep `pt_invite_watcher/storage/sqlite.py` as a small compatibility wrapper.

import logging
import time
import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import aiosqlite

from pt_invite_watcher.kv_keys import APP_CONFIG_KEY, NOTIFICATIONS_KEY, SITES_KEY
from pt_invite_watcher.storage.event_log_store import (
    add_event as _add_event,
    clear_events as _clear_events,
    get_log_domains as _get_log_domains,
    list_events as _list_events,
)
from pt_invite_watcher.storage.kv_store import get_json as _get_json, set_json as _set_json
from pt_invite_watcher.storage.lease_store import release_lease as _release_lease, try_acquire_lease as _try_acquire_lease
from pt_invite_watcher.storage.scan_log_buffer import (
    enqueue_scan_log_event as _enqueue_scan_log_event_impl,
    ensure_scan_log_flusher as _ensure_scan_log_flusher_impl,
    flush_scan_logs as _flush_scan_logs_impl,
    scan_log_flush_loop as _scan_log_flush_loop_impl,
)
from pt_invite_watcher.storage.site_state_store import (
    get_reachability_states as _get_reachability_states,
    get_site_state as _get_site_state,
    get_sites_extras as _get_sites_extras,
    list_site_states as _list_site_states,
    load_sites_snapshot as _load_sites_snapshot,
    reset_site_states as _reset_site_states,
    save_site_result as _save_site_result,
)
from pt_invite_watcher.utils.asyncio_tasks import create_task_logged


logger = logging.getLogger("pt_invite_watcher.storage")


@dataclass(frozen=True)
class StoredSiteState:
    domain: str
    reachability_state: str
    registration_state: str
    invites_state: str
    invites_available: Optional[int]
    last_checked_at: str
    last_changed_at: Optional[str]



class SqliteStore:
    def __init__(self, path: Path):
        self._path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._write_conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        self._lease_conn: Optional[aiosqlite.Connection] = None
        self._lease_lock = asyncio.Lock()
        self._event_hooks: list[Callable[[dict[str, Any]], Any]] = []
        self._logs_resync_hooks: list[Callable[[str], Any]] = []
        self._logs_resync_last_sent = 0.0
        self._logs_resync_throttle_seconds = 30.0
        self._event_write_failures_last_log = 0.0
        self._event_write_failures_suppressed = 0
        self._scan_log_buffer: list[dict[str, Any]] = []
        self._scan_log_buffer_lock = asyncio.Lock()
        self._scan_log_flush_lock = asyncio.Lock()
        self._scan_log_flush_task: Optional[asyncio.Task[None]] = None
        self._scan_log_flush_interval_seconds = 0.2
        self._scan_log_batch_max = 100
        self._scan_log_buffer_max = 2000
        self._scan_log_enqueue_max_wait_seconds = 2.0
        self._scan_log_enqueue_retry_sleep_seconds = 0.05
        self._scan_log_dropped_last_log = 0.0
        self._scan_log_dropped = 0
        self._scan_log_dropped_pending = 0
        self._scan_log_flush_failures_pending = 0
        self._scan_log_flush_failures_last_log = 0.0
        self._scan_log_flush_failures_suppressed = 0
        self._scan_log_flush_count = 0

    def on_event(self, hook: Callable[[dict[str, Any]], Any]) -> None:
        self._event_hooks.append(hook)

    def on_logs_resync(self, hook: Callable[[str], Any]) -> None:
        """
        Register a hook called when the store detects logs may be out-of-sync.

        This is used to request a WS `logs_update` without coupling storage to the WS layer.
        """
        self._logs_resync_hooks.append(hook)

    def _request_logs_resync(self, *, reason: str) -> None:
        hooks = list(self._logs_resync_hooks)
        if not hooks:
            return
        now = time.monotonic()
        if (now - self._logs_resync_last_sent) < self._logs_resync_throttle_seconds:
            return
        self._logs_resync_last_sent = now
        for hook in hooks:
            try:
                res = hook(reason)
                if asyncio.iscoroutine(res):
                    reason_key = str(reason or "-").strip() or "-"
                    task_name = f"sqlite_store_logs_resync_{reason_key}".replace(" ", "_")[:120]
                    label = f"logs resync hook (reason={reason_key})"
                    create_task_logged(res, logger=logger, name=task_name, label=label)
            except Exception:
                logger.exception("logs resync hook failed")

    def _log_event_write_failure(self, exc: BaseException, *, action: str, domain: Optional[str]) -> None:
        now = time.monotonic()
        if now - self._event_write_failures_last_log >= 60:
            suppressed = self._event_write_failures_suppressed
            self._event_write_failures_last_log = now
            self._event_write_failures_suppressed = 0
            logger.exception(
                "failed to write event log (action=%s domain=%s suppressed=%d)",
                str(action or "-"),
                str(domain or "-"),
                suppressed,
                exc_info=exc,
            )
        else:
            self._event_write_failures_suppressed += 1

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path.as_posix())
        self._conn.row_factory = aiosqlite.Row
        cur = await self._conn.execute("PRAGMA journal_mode=WAL;")
        await cur.close()
        cur = await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await cur.close()

        # Use a dedicated connection + lock for write transactions so we can batch
        # related writes without risking interleaving across coroutines.
        self._write_conn = await aiosqlite.connect(self._path.as_posix())
        self._write_conn.row_factory = aiosqlite.Row
        cur = await self._write_conn.execute("PRAGMA journal_mode=WAL;")
        await cur.close()
        cur = await self._write_conn.execute("PRAGMA synchronous=NORMAL;")
        await cur.close()

        # Use a dedicated connection for lease operations so cross-process locking
        # logic isn't affected by concurrent writes on the main connection.
        self._lease_conn = await aiosqlite.connect(self._path.as_posix())
        self._lease_conn.row_factory = aiosqlite.Row
        cur = await self._lease_conn.execute("PRAGMA journal_mode=WAL;")
        await cur.close()
        cur = await self._lease_conn.execute("PRAGMA synchronous=NORMAL;")
        await cur.close()

        cur = await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_state (
              domain TEXT PRIMARY KEY,
              name TEXT,
              url TEXT,
              engine TEXT,
              registration_state TEXT NOT NULL,
              invites_state TEXT NOT NULL,
              invites_available INTEGER,
              last_checked_at TEXT NOT NULL,
              last_changed_at TEXT,
              last_evidence TEXT NOT NULL
            );
            """
        )
        await cur.close()
        cur = await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        await cur.close()
        cur = await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              category TEXT NOT NULL,
              level TEXT NOT NULL,
              action TEXT NOT NULL,
              domain TEXT,
              message TEXT NOT NULL,
              detail TEXT
            );
            """
        )
        await cur.close()
        await self._conn.commit()

        await self._ensure_default_notifications()
        await self._ensure_default_app_config()
        await self._ensure_default_sites()
        self._ensure_scan_log_flusher()

    async def add_event(
        self,
        *,
        category: str,
        level: str,
        action: str,
        message: str,
        domain: Optional[str] = None,
        detail: Any = None,
        max_rows: int = 5000,
    ) -> None:
        cat = str(category or "").strip().lower() or "misc"
        lvl = str(level or "").strip().lower() or "info"
        if cat == "scan" and lvl == "info":
            await self._enqueue_scan_log_event(
                category=cat,
                level=lvl,
                action=action,
                message=message,
                domain=domain,
                detail=detail,
                max_rows=max_rows,
            )
            return None

        return await _add_event(
            self,
            category=cat,
            level=lvl,
            action=action,
            message=message,
            domain=domain,
            detail=detail,
            max_rows=max_rows,
        )

    async def list_events(
        self,
        *,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        await self.flush_scan_logs()
        return await _list_events(self, category=category, domain=domain, keyword=keyword, limit=limit)

    async def clear_events(self) -> None:
        async with self._scan_log_flush_lock:
            async with self._scan_log_buffer_lock:
                self._scan_log_buffer.clear()
        await _clear_events(self)

    async def get_log_domains(self) -> list[str]:
        await self.flush_scan_logs()
        return await _get_log_domains(self)



    async def close(self) -> None:
        flush_task = self._scan_log_flush_task
        if flush_task is not None and not flush_task.done():
            flush_task.cancel()
        if flush_task is not None:
            try:
                with suppress(asyncio.CancelledError):
                    await flush_task
            except Exception:
                logger.exception("scan log flush task failed on close")
            self._scan_log_flush_task = None

        if self._write_conn is not None:
            try:
                await asyncio.wait_for(self.flush_scan_logs(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("timed out flushing scan logs on close")
            except Exception:
                logger.exception("failed to flush scan logs on close")

        conns = [
            ("conn", self._conn),
            ("write_conn", self._write_conn),
            ("lease_conn", self._lease_conn),
        ]
        self._conn = None
        self._write_conn = None
        self._lease_conn = None
        for label, conn in conns:
            if conn is None:
                continue
            try:
                await conn.close()
            except Exception:
                logger.exception("failed to close sqlite connection (%s)", label)

    def _require_conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("SqliteStore not initialized")
        return self._conn

    def require_conn(self) -> aiosqlite.Connection:
        return self._require_conn()

    def _require_write_conn(self) -> aiosqlite.Connection:
        if not self._write_conn:
            raise RuntimeError("SqliteStore not initialized")
        return self._write_conn

    def require_write_conn(self) -> aiosqlite.Connection:
        return self._require_write_conn()

    def _require_lease_conn(self) -> aiosqlite.Connection:
        if not self._lease_conn:
            raise RuntimeError("SqliteStore not initialized")
        return self._lease_conn

    def require_lease_conn(self) -> aiosqlite.Connection:
        return self._require_lease_conn()

    @asynccontextmanager
    async def lease_operation(self) -> Any:
        async with self._lease_lock:
            yield self._require_lease_conn()

    def dispatch_event_hooks(self, evt: dict[str, Any]) -> None:
        hooks = list(self._event_hooks)
        action = str(evt.get("action") or "event").strip() or "event"
        domain = (str(evt.get("domain") or "").strip().lower() if evt.get("domain") is not None else "") or ""
        for hook in hooks:
            try:
                res = hook(evt)
                if asyncio.iscoroutine(res):
                    task_name = f"sqlite_store_event_hook_{action}"
                    if domain:
                        task_name = f"{task_name}_{domain}"
                    task_name = task_name.replace(" ", "_")[:120]
                    label = f"event hook (action={action} domain={domain or '-'})"
                    create_task_logged(res, logger=logger, name=task_name, label=label)
            except Exception:
                logger.exception("event hook failed")

    def log_event_write_failure(self, exc: BaseException, *, action: str, domain: Optional[str]) -> None:
        self._log_event_write_failure(exc, action=action, domain=domain)

    @asynccontextmanager
    async def write_transaction(self) -> Any:
        async with self._write_lock:
            conn = self._require_write_conn()
            cur = await conn.execute("BEGIN")
            await cur.close()
            try:
                yield conn
                await conn.commit()
            except BaseException:
                try:
                    await conn.rollback()
                except Exception:
                    pass
                raise

    def _ensure_scan_log_flusher(self) -> None:
        _ensure_scan_log_flusher_impl(self)

    async def _scan_log_flush_loop(self) -> None:
        return await _scan_log_flush_loop_impl(self)

    async def _enqueue_scan_log_event(
        self,
        *,
        category: str,
        level: str,
        action: str,
        message: str,
        domain: Optional[str],
        detail: Any,
        max_rows: int,
    ) -> None:
        return await _enqueue_scan_log_event_impl(
            self,
            category=category,
            level=level,
            action=action,
            message=message,
            domain=domain,
            detail=detail,
            max_rows=max_rows,
        )

    async def flush_scan_logs(self, *, max_items: int | None = None) -> None:
        return await _flush_scan_logs_impl(self, max_items=max_items)

    async def _ensure_default_notifications(self) -> None:
        existing = await self.get_json(NOTIFICATIONS_KEY, default=None)
        if existing is not None:
            return
        await self.set_json(
            NOTIFICATIONS_KEY,
            {
                "telegram": {"enabled": False, "token": "", "chat_id": ""},
                "wecom": {
                    "enabled": False,
                    "corpid": "",
                    "app_secret": "",
                    "agent_id": "",
                    "to_user": "@all",
                    "to_party": "",
                    "to_tag": "",
                },
            },
        )

    async def _ensure_default_app_config(self) -> None:
        existing = await self.get_json(APP_CONFIG_KEY, default=None)
        if existing is not None:
            return
        await self.set_json(APP_CONFIG_KEY, {})

    async def _ensure_default_sites(self) -> None:
        existing = await self.get_json(SITES_KEY, default=None)
        if existing is not None:
            return
        await self.set_json(SITES_KEY, {"version": 1, "entries": {}})

    async def get_site_state(self, domain: str) -> Optional[StoredSiteState]:
        return await _get_site_state(self, domain, state_cls=StoredSiteState)

    async def save_site_result(self, result: SiteCheckResult, changed_at: Optional[str]) -> None:
        await _save_site_result(self, result, changed_at)

    async def list_site_states(self) -> list[dict[str, Any]]:
        return await _list_site_states(self)

    async def reset_site_states(self) -> None:
        await _reset_site_states(self)

    async def get_reachability_states(self, domains: list[str]) -> dict[str, str]:
        return await _get_reachability_states(self, domains)

    async def get_sites_extras(self, domains: list[str]) -> dict[str, dict[str, Any]]:
        return await _get_sites_extras(self, domains)

    async def load_sites_snapshot(self) -> tuple[Optional[datetime], list[Site]]:
        return await _load_sites_snapshot(self)

    async def get_json(self, key: str, default: Any) -> Any:
        return await _get_json(self, key, default)

    async def set_json(self, key: str, value: Any) -> None:
        await _set_json(self, key, value)

    async def try_acquire_lease(self, key: str, *, owner: str, ttl_seconds: int) -> bool:
        return await _try_acquire_lease(self, key, owner=owner, ttl_seconds=ttl_seconds)

    async def release_lease(self, key: str, *, owner: str) -> None:
        await _release_lease(self, key, owner=owner)
