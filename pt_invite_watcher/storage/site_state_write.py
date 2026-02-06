from __future__ import annotations

import json
from typing import Any, Optional

from pt_invite_watcher.models import SiteCheckResult, to_jsonable
from pt_invite_watcher.storage.types import SupportsConn


async def save_site_result(
    store: SupportsConn,
    result: SiteCheckResult,
    changed_at: Optional[str],
    *,
    conn: Any | None = None,
    commit: bool = True,
) -> None:
    if conn is None and not commit:
        raise ValueError("commit=False requires explicit conn")

    evidence_json = json.dumps(to_jsonable(result), ensure_ascii=False)
    checked_at = result.checked_at.isoformat()
    changed_at_value = changed_at.strip() if isinstance(changed_at, str) else None
    if not changed_at_value:
        changed_at_value = None

    if conn is not None:
        await conn.execute(
            """
            INSERT INTO site_state (
              domain, name, url, engine,
              registration_state, invites_state, invites_available,
              last_checked_at, last_changed_at, last_evidence
            ) VALUES (
              ?, ?, ?, ?,
              ?, ?, ?,
              ?, ?, ?
            )
            ON CONFLICT(domain) DO UPDATE SET
              name=excluded.name,
              url=excluded.url,
              engine=excluded.engine,
              registration_state=excluded.registration_state,
              invites_state=excluded.invites_state,
              invites_available=excluded.invites_available,
              last_checked_at=excluded.last_checked_at,
              last_evidence=excluded.last_evidence,
              last_changed_at=COALESCE(excluded.last_changed_at, site_state.last_changed_at)
            """,
            (
                result.site.domain,
                result.site.name,
                result.site.url,
                result.engine,
                result.registration.state,
                result.invites.state,
                result.invites.available,
                checked_at,
                changed_at_value,
                evidence_json,
            ),
        )
        if commit:
            await conn.commit()
        return

    write_txn = getattr(store, "write_transaction", None)
    if callable(write_txn) and commit:
        async with write_txn() as c:
            await c.execute(
                """
                INSERT INTO site_state (
                  domain, name, url, engine,
                  registration_state, invites_state, invites_available,
                  last_checked_at, last_changed_at, last_evidence
                ) VALUES (
                  ?, ?, ?, ?,
                  ?, ?, ?,
                  ?, ?, ?
                )
                ON CONFLICT(domain) DO UPDATE SET
                  name=excluded.name,
                  url=excluded.url,
                  engine=excluded.engine,
                  registration_state=excluded.registration_state,
                  invites_state=excluded.invites_state,
                  invites_available=excluded.invites_available,
                  last_checked_at=excluded.last_checked_at,
                  last_evidence=excluded.last_evidence,
                  last_changed_at=COALESCE(excluded.last_changed_at, site_state.last_changed_at)
                """,
                (
                    result.site.domain,
                    result.site.name,
                    result.site.url,
                    result.engine,
                    result.registration.state,
                    result.invites.state,
                    result.invites.available,
                    checked_at,
                    changed_at_value,
                    evidence_json,
                ),
            )
        return

    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        c = require_conn()
    else:
        c = store._require_conn()
    await c.execute(
        """
        INSERT INTO site_state (
          domain, name, url, engine,
          registration_state, invites_state, invites_available,
          last_checked_at, last_changed_at, last_evidence
        ) VALUES (
          ?, ?, ?, ?,
          ?, ?, ?,
          ?, ?, ?
        )
        ON CONFLICT(domain) DO UPDATE SET
          name=excluded.name,
          url=excluded.url,
          engine=excluded.engine,
          registration_state=excluded.registration_state,
          invites_state=excluded.invites_state,
          invites_available=excluded.invites_available,
          last_checked_at=excluded.last_checked_at,
          last_evidence=excluded.last_evidence,
          last_changed_at=COALESCE(excluded.last_changed_at, site_state.last_changed_at)
        """,
        (
            result.site.domain,
            result.site.name,
            result.site.url,
            result.engine,
            result.registration.state,
            result.invites.state,
            result.invites.available,
            checked_at,
            changed_at_value,
            evidence_json,
        ),
    )
    if commit:
        await c.commit()


async def reset_site_states(store: SupportsConn) -> None:
    write_txn = getattr(store, "write_transaction", None)
    if callable(write_txn):
        async with write_txn() as conn:
            await conn.execute("DELETE FROM site_state")
        return

    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        conn = require_conn()
    else:
        conn = store._require_conn()
    await conn.execute("DELETE FROM site_state")
    await conn.commit()


__all__ = ["reset_site_states", "save_site_result"]
