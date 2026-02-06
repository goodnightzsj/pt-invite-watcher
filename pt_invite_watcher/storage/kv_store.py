from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pt_invite_watcher.storage.types import SupportsConn


async def get_json(store: SupportsConn, key: str, default: Any) -> Any:
    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return default


async def set_json(store: SupportsConn, key: str, value: Any, *, conn: Any | None = None, commit: bool = True) -> None:
    if conn is None and not commit:
        raise ValueError("commit=False requires explicit conn")

    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(value, ensure_ascii=False)

    if conn is not None:
        await conn.execute(
            """
            INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, payload, now),
        )
        if commit:
            await conn.commit()
        return

    write_txn = getattr(store, "write_transaction", None)
    if callable(write_txn) and commit:
        async with write_txn() as c:
            await c.execute(
                """
                INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, payload, now),
            )
        return

    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        c = require_conn()
    else:
        c = store._require_conn()
    await c.execute(
        """
        INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, payload, now),
    )
    if commit:
        await c.commit()


__all__ = ["get_json", "set_json"]
