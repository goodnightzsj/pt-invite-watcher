from __future__ import annotations

import asyncio
import ast
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pt_invite_watcher.models import to_jsonable
from pt_invite_watcher.storage.event_hooks import dispatch_event_hooks as _dispatch_event_hooks
from pt_invite_watcher.storage.event_log_page import enrich_event_page


logger = logging.getLogger("pt_invite_watcher.storage")


async def add_event(
    store: Any,
    *,
    category: str,
    level: str,
    action: str,
    message: str,
    domain: Optional[str] = None,
    detail: Any = None,
    max_rows: int = 5000,
    conn: Any | None = None,
    commit: bool = True,
    dispatch_hooks: bool = True,
    best_effort: bool = True,
) -> Optional[dict[str, Any]]:
    """
    Append a structured event log row.
    Keep the latest `max_rows` rows to avoid unbounded growth.
    """
    if conn is None and not commit:
        raise ValueError("commit=False requires explicit conn")
    if not commit and dispatch_hooks:
        raise ValueError("dispatch_hooks=True requires commit=True")

    ts = datetime.now(timezone.utc).isoformat()
    cat = str(category or "misc").strip().lower() or "misc"
    lvl = str(level or "info").strip().lower() or "info"
    act = str(action or "").strip() or "-"
    dom = (str(domain).strip().lower() if domain is not None else None) or None
    msg = str(message or "").strip() or "-"
    det = None
    detail_payload: Any = None

    async def _run(c: Any, *, commit_now: bool, dispatch_hooks_now: bool) -> Optional[dict[str, Any]]:
        nonlocal det, detail_payload

        if detail is not None:
            try:
                detail_payload = to_jsonable(detail)
                det = json.dumps(detail_payload, ensure_ascii=False)
            except Exception:
                detail_payload = {"detail": str(detail)}
                det = json.dumps(detail_payload, ensure_ascii=False)

        cursor = await c.execute(
            """
            INSERT INTO event_log(ts, category, level, action, domain, message, detail)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, cat, lvl, act, dom, msg, det),
        )
        row_id = cursor.lastrowid
        await cursor.close()

        keep = max(100, int(max_rows or 0))
        cleanup_every = max(10, min(200, keep // 20))
        should_cleanup = True
        try:
            rid = int(row_id or 0)
            should_cleanup = rid <= 0 or (rid % cleanup_every == 0)
        except (ValueError, TypeError):
            should_cleanup = True

        if should_cleanup:
            cleanup_cur = await c.execute(
                """
                DELETE FROM event_log
                WHERE id <= (
                  SELECT id FROM event_log ORDER BY id DESC LIMIT 1 OFFSET ?
                )
                """,
                (keep,),
            )
            await cleanup_cur.close()

        evt: dict[str, Any] = {
            "id": row_id,
            "ts": ts,
            "category": cat,
            "level": lvl,
            "action": act,
            "domain": dom,
            "message": msg,
            "detail": detail_payload,
        }
        if detail_payload and isinstance(detail_payload, dict):
            enrich_event_page(evt)

        if commit_now:
            await c.commit()

        if dispatch_hooks_now:
            _dispatch_event_hooks(store, evt)

        if commit_now and dispatch_hooks_now:
            return None
        return evt

    try:
        if conn is not None:
            return await _run(conn, commit_now=commit, dispatch_hooks_now=dispatch_hooks)

        write_txn = getattr(store, "write_transaction", None)
        if callable(write_txn):
            async with write_txn() as c:
                evt = await _run(c, commit_now=False, dispatch_hooks_now=False)
            if evt is None:
                return None
            if dispatch_hooks:
                _dispatch_event_hooks(store, evt)
                return None
            return evt

        lock = getattr(store, "_write_lock", None)
        require_write = getattr(store, "require_write_conn", None)
        if not callable(require_write):
            require_write = getattr(store, "_require_write_conn", None)
        if callable(require_write):
            c = require_write()
        else:
            require_conn = getattr(store, "require_conn", None)
            if callable(require_conn):
                c = require_conn()
            else:
                c = store._require_conn()

        if lock is not None:
            async with lock:
                return await _run(c, commit_now=commit, dispatch_hooks_now=dispatch_hooks)
        return await _run(c, commit_now=commit, dispatch_hooks_now=dispatch_hooks)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if not best_effort:
            raise
        try:
            reporter = getattr(store, "log_event_write_failure", None)
            if not callable(reporter):
                reporter = getattr(store, "_log_event_write_failure", None)
            if callable(reporter):
                reporter(e, action=act, domain=dom)
            else:
                raise AttributeError("log_event_write_failure not available")
        except Exception:
            logger.exception("failed to write event log (action=%s domain=%s)", act, dom)
        return None


async def list_events(
    store: Any,
    *,
    category: Optional[str] = None,
    domain: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    cat = (str(category or "all").strip().lower() or "all")
    dom = (str(domain or "").strip().lower() or "").strip()
    kw = (str(keyword or "").strip() or "").strip()
    lim = int(limit or 0)  # 0 means unlimited
    if lim < 0:
        lim = 0

    clauses: list[str] = []
    params: list[Any] = []
    if cat and cat != "all":
        clauses.append("category = ?")
        params.append(cat)
    if dom:
        clauses.append("domain = ?")
        params.append(dom)
    if kw:
        pattern = f"%{kw}%"
        clauses.append("(message LIKE ? OR domain LIKE ? OR action LIKE ? OR category LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern])

    sql = "SELECT id, ts, category, level, action, domain, message, detail FROM event_log"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC"
    if lim > 0:
        sql += " LIMIT ?"
        params.append(lim)

    cur = await conn.execute(sql, tuple(params))
    rows = await cur.fetchall()
    await cur.close()
    items: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        detail_value = item.get("detail")
        if detail_value:
            try:
                item["detail"] = json.loads(detail_value)
            except json.JSONDecodeError:
                # Legacy/dirty rows may store non-JSON payloads (e.g. Python literal dicts).
                # Best-effort: parse via ast.literal_eval (safe) so WebUI can render structured details.
                raw = str(detail_value)
                stripped = raw.lstrip()
                parsed: Any | None = None
                if stripped[:1] in {"{", "["}:
                    try:
                        parsed = ast.literal_eval(stripped)
                    except (ValueError, SyntaxError):
                        parsed = None
                if isinstance(parsed, (dict, list)):
                    item["detail"] = parsed
                else:
                    item["detail"] = stripped
        else:
            item["detail"] = None

        try:
            enrich_event_page(item)
        except Exception:
            pass
        items.append(item)
    return items


async def clear_events(store: Any) -> None:
    write_txn = getattr(store, "write_transaction", None)
    if callable(write_txn):
        async with write_txn() as conn:
            cur = await conn.execute("DELETE FROM event_log")
            await cur.close()
        return

    lock = getattr(store, "_write_lock", None)
    require_write = getattr(store, "require_write_conn", None)
    if not callable(require_write):
        require_write = getattr(store, "_require_write_conn", None)
    if callable(require_write):
        conn = require_write()
    else:
        require_conn = getattr(store, "require_conn", None)
        if callable(require_conn):
            conn = require_conn()
        else:
            conn = store._require_conn()

    if lock is not None:
        async with lock:
            cur = await conn.execute("DELETE FROM event_log")
            await cur.close()
            await conn.commit()
        return

    cur = await conn.execute("DELETE FROM event_log")
    await cur.close()
    await conn.commit()


async def get_log_domains(store: Any) -> list[str]:
    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    cur = await conn.execute("SELECT DISTINCT domain FROM event_log WHERE domain IS NOT NULL AND domain != '' ORDER BY domain")
    rows = await cur.fetchall()
    await cur.close()
    return [str(r[0]) for r in rows if r[0]]


__all__ = ["add_event", "clear_events", "get_log_domains", "list_events"]
