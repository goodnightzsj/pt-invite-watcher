from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pt_invite_watcher.storage.types import SupportsConn, SupportsLeaseOperation


async def try_acquire_lease(store: SupportsLeaseOperation | SupportsConn, key: str, *, owner: str, ttl_seconds: int) -> bool:
    """
    Best-effort cross-process lease using the `kv` table.

    The lease is considered held if:
    - key is missing, or lease is expired, or owner matches (renew)
    - otherwise, another owner holds a non-expired lease
    """
    lease_op = getattr(store, "lease_operation", None)
    if callable(lease_op):
        async with lease_op() as conn:
            return await _try_acquire_lease_with_conn(conn, key, owner=owner, ttl_seconds=ttl_seconds)

    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    return await _try_acquire_lease_with_conn(conn, key, owner=owner, ttl_seconds=ttl_seconds)


async def _try_acquire_lease_with_conn(conn: Any, key: str, *, owner: str, ttl_seconds: int) -> bool:
    owner_id = str(owner or "").strip()
    if not owner_id:
        raise ValueError("owner is required")

    now = datetime.now(timezone.utc)
    ttl = max(1, int(ttl_seconds or 0))
    expires_at = now + timedelta(seconds=ttl)

    def _parse_dt(value: Any) -> Optional[datetime]:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    payload = {
        "owner": owner_id,
        "acquired_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    # Fast-path: avoid write locks if another owner holds an active lease.
    cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
    row = await cur.fetchone()
    await cur.close()
    if row is not None:
        try:
            existing = json.loads(row["value"])
        except json.JSONDecodeError:
            existing = None
        if isinstance(existing, dict):
            existing_owner = str(existing.get("owner") or "").strip()
            existing_expires = _parse_dt(existing.get("expires_at"))
            if existing_owner and existing_owner != owner_id and existing_expires is not None and existing_expires > now:
                return False

    cur = await conn.execute("BEGIN IMMEDIATE")
    await cur.close()
    try:
        cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
        row = await cur.fetchone()
        await cur.close()
        if row is not None:
            try:
                existing = json.loads(row["value"])
            except Exception:
                existing = None
            if isinstance(existing, dict):
                existing_owner = str(existing.get("owner") or "").strip()
                existing_expires = _parse_dt(existing.get("expires_at"))
                if (
                    existing_owner
                    and existing_owner != owner_id
                    and existing_expires is not None
                    and existing_expires > now
                ):
                    await conn.rollback()
                    return False

        cur = await conn.execute(
            """
            INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(payload, ensure_ascii=False), now.isoformat()),
        )
        await cur.close()
        await conn.commit()
        return True
    except Exception:
        await conn.rollback()
        raise


async def release_lease(store: SupportsLeaseOperation | SupportsConn, key: str, *, owner: str) -> None:
    """
    Release a lease if (and only if) current owner matches.
    """
    lease_op = getattr(store, "lease_operation", None)
    if callable(lease_op):
        async with lease_op() as conn:
            await _release_lease_with_conn(conn, key, owner=owner)
        return

    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    await _release_lease_with_conn(conn, key, owner=owner)


async def _release_lease_with_conn(conn: Any, key: str, *, owner: str) -> None:
    owner_id = str(owner or "").strip()
    if not owner_id:
        raise ValueError("owner is required")

    cur = await conn.execute("BEGIN IMMEDIATE")
    await cur.close()
    try:
        cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            await conn.rollback()
            return

        try:
            existing = json.loads(row["value"])
        except json.JSONDecodeError:
            existing = None

        if isinstance(existing, dict) and str(existing.get("owner") or "").strip() == owner_id:
            cur = await conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            await cur.close()
            await conn.commit()
            return

        await conn.rollback()
    except Exception:
        await conn.rollback()
        raise


__all__ = ["release_lease", "try_acquire_lease"]
