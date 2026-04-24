"""Read/write layer for the `device_tokens` table.

Small CRUD surface — there are only ever a handful of device tokens per
operator (their own phones + maybe a housemate), so we don't bother with
batching or LRU eviction. Any "cleanup" (e.g. dropping tokens that APN/FCM
have marked `Unregistered`) is the delivery layer's job via
`remove_device_token()`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional


async def upsert_device_token(
    store: Any,
    *,
    token: str,
    platform: str,
    domain_filter: str = "",
) -> None:
    """Register (or refresh) a device token. `UNIQUE(token)` is the merge key.

    `domain_filter` is a comma-separated list of site domains the device
    wants alerts for; empty string = all sites. Kept as a flat text field
    because the typical operator has < 50 sites; indexing is unnecessary.
    """
    now = datetime.now(timezone.utc).isoformat()
    async with store.write_transaction() as conn:
        cur = await conn.execute(
            """
            INSERT INTO device_tokens(token, platform, domain_filter, registered_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
              platform = excluded.platform,
              domain_filter = excluded.domain_filter,
              last_seen_at = excluded.last_seen_at
            """,
            (token, platform, domain_filter, now, now),
        )
        await cur.close()


async def remove_device_token(store: Any, token: str) -> int:
    """Drop a token. Called on explicit user unregister + on APN/FCM
    `Unregistered` responses. Returns number of rows removed (0 or 1)."""
    async with store.write_transaction() as conn:
        cur = await conn.execute("DELETE FROM device_tokens WHERE token = ?", (token,))
        removed = cur.rowcount or 0
        await cur.close()
    return int(removed)


async def list_device_tokens(store: Any, *, domain: Optional[str] = None) -> List[dict]:
    """Enumerate tokens, optionally filtered to those subscribed to `domain`.

    A token with empty `domain_filter` is subscribed to every site.
    A token with a non-empty filter matches only when `domain` is in the
    comma-separated list.
    """
    conn = store._require_conn() if hasattr(store, "_require_conn") else None
    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()

    cur = await conn.execute(
        "SELECT id, token, platform, domain_filter, registered_at, last_seen_at FROM device_tokens"
    )
    rows = await cur.fetchall()
    await cur.close()

    out: List[dict] = []
    for r in rows:
        df = (r[3] or "").strip()
        if domain is not None and df:
            parts = {d.strip() for d in df.split(",") if d.strip()}
            if domain not in parts:
                continue
        out.append({
            "id": r[0],
            "token": r[1],
            "platform": r[2],
            "domain_filter": df,
            "registered_at": r[4],
            "last_seen_at": r[5],
        })
    return out


__all__ = ["list_device_tokens", "remove_device_token", "upsert_device_token"]
