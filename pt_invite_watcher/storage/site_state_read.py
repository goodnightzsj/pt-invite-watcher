from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from pt_invite_watcher.models import Site
from pt_invite_watcher.storage.types import SupportsConn
from pt_invite_watcher.utils.parse import safe_int, safe_str


def _require_conn(store: SupportsConn) -> Any:
    require_conn = getattr(store, "require_conn", None)
    if callable(require_conn):
        return require_conn()
    return store._require_conn()


async def get_site_state(store: SupportsConn, domain: str, *, state_cls: Any) -> Optional[Any]:
    conn = _require_conn(store)
    cur = await conn.execute(
        """
        SELECT domain, registration_state, invites_state, invites_available, last_checked_at, last_changed_at, last_evidence
        FROM site_state
        WHERE domain = ?
        """,
        (domain,),
    )
    row = await cur.fetchone()
    await cur.close()
    if not row:
        return None
    reachability_state = "unknown"
    try:
        payload = json.loads(row["last_evidence"] or "{}")
        if isinstance(payload, dict):
            reach = payload.get("reachability")
            if isinstance(reach, dict):
                reachability_state = str(reach.get("state") or "unknown")
    except Exception:
        reachability_state = "unknown"
    return state_cls(
        domain=row["domain"],
        reachability_state=reachability_state,
        registration_state=row["registration_state"],
        invites_state=row["invites_state"],
        invites_available=row["invites_available"],
        last_checked_at=row["last_checked_at"],
        last_changed_at=row["last_changed_at"],
    )


async def list_site_states(store: SupportsConn) -> list[dict[str, Any]]:
    conn = _require_conn(store)
    cur = await conn.execute(
        """
        SELECT domain, name, url, engine, registration_state, invites_state, invites_available,
               last_checked_at, last_changed_at, last_evidence
        FROM site_state
        ORDER BY domain
        """
    )
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


async def get_reachability_states(store: SupportsConn, domains: list[str]) -> dict[str, str]:
    conn = _require_conn(store)
    targets = [str(d or "").strip().lower() for d in (domains or []) if str(d or "").strip()]
    if not targets:
        return {}

    placeholders = ",".join(["?"] * len(targets))
    cur = await conn.execute(
        f"""
        SELECT domain, last_evidence
        FROM site_state
        WHERE domain IN ({placeholders})
        """,
        tuple(targets),
    )
    rows = await cur.fetchall()
    await cur.close()

    states: dict[str, str] = {}
    for r in rows:
        domain = str(r["domain"] or "").strip().lower()
        if not domain:
            continue
        state = "unknown"
        try:
            payload = json.loads(r["last_evidence"] or "{}")
            reach = payload.get("reachability") if isinstance(payload, dict) else None
            if isinstance(reach, dict):
                state = str(reach.get("state") or "unknown")
        except Exception:
            state = "unknown"
        states[domain] = state

    return states


def _extract_invite_uid(url: str) -> Optional[str]:
    raw = str(url or "").strip()
    if not raw:
        return None
    try:
        p = urlparse(raw)
        q = parse_qs(p.query or "")
        value = (q.get("id") or [None])[0]
        if value is None:
            return None
        s = str(value).strip()
        return s if s.isdigit() else None
    except Exception:
        return None


async def get_sites_extras(store: SupportsConn, domains: list[str]) -> dict[str, dict[str, Any]]:
    conn = _require_conn(store)
    targets = [str(d or "").strip().lower() for d in (domains or []) if str(d or "").strip()]
    if not targets:
        return {}

    placeholders = ",".join(["?"] * len(targets))
    cur = await conn.execute(
        f"""
        SELECT domain, last_evidence
        FROM site_state
        WHERE domain IN ({placeholders})
        """,
        tuple(targets),
    )
    rows = await cur.fetchall()
    await cur.close()

    extras: dict[str, dict[str, Any]] = {}
    for r in rows:
        domain = str(r["domain"] or "").strip().lower()
        if not domain:
            continue
        reachability_state = "unknown"
        invite_uid: Optional[str] = None
        try:
            payload = json.loads(r["last_evidence"] or "{}")
            reach = payload.get("reachability") if isinstance(payload, dict) else None
            if isinstance(reach, dict):
                reachability_state = str(reach.get("state") or "unknown")

            inv = payload.get("invites") if isinstance(payload, dict) else None
            if isinstance(inv, dict):
                ev = inv.get("evidence")
                if isinstance(ev, dict):
                    invite_uid = _extract_invite_uid(str(ev.get("url") or ""))
        except Exception:
            reachability_state = "unknown"
            invite_uid = None
        extras[domain] = {"reachability_state": reachability_state, "invite_uid": invite_uid}

    return extras


def _parse_dt(value: Any) -> Optional[datetime]:
    s = safe_str(value)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def load_sites_snapshot(store: SupportsConn) -> tuple[Optional[datetime], list[Site]]:
    conn = _require_conn(store)
    cur = await conn.execute(
        """
        SELECT domain, name, url, last_checked_at, last_evidence
        FROM site_state
        ORDER BY domain
        """
    )
    rows = await cur.fetchall()
    await cur.close()

    latest: Optional[datetime] = None
    sites: list[Site] = []

    for r in rows:
        domain = safe_str(r["domain"]).lower()
        url = safe_str(r["url"])
        if not domain or not url:
            continue
        name = safe_str(r["name"]) or domain

        checked_at = _parse_dt(r["last_checked_at"])
        if checked_at and (latest is None or checked_at > latest):
            latest = checked_at

        ua = None
        cookie = None
        is_active = True
        site_id: Optional[int] = 0
        try:
            payload = json.loads(r["last_evidence"] or "{}")
            if isinstance(payload, dict):
                site_payload = payload.get("site")
                if isinstance(site_payload, dict):
                    ua = safe_str(site_payload.get("ua")) or None
                    cookie = safe_str(site_payload.get("cookie")) or None
                    is_active = bool(site_payload.get("is_active", True))
                    parsed_id = safe_int(site_payload.get("id"))
                    if parsed_id is not None:
                        site_id = parsed_id
        except Exception:
            pass

        sites.append(
            Site(
                id=site_id,
                name=name,
                domain=domain,
                url=url,
                ua=ua,
                cookie=cookie,
                cookie_override=None,
                authorization=None,
                did=None,
                is_active=is_active,
                template=None,
                registration_path=None,
                invite_path=None,
            )
        )

    return latest, sites


__all__ = [
    "get_reachability_states",
    "get_site_state",
    "get_sites_extras",
    "list_site_states",
    "load_sites_snapshot",
]
