from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from urllib.parse import parse_qs, urlparse

from pt_invite_watcher.models import Site, SiteCheckResult, to_jsonable


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

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path.as_posix())
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")

        await self._conn.execute(
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
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        await self._conn.execute(
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
        await self._conn.commit()

        await self._ensure_default_notifications()
        await self._ensure_default_app_config()
        await self._ensure_default_sites()

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
        """
        Append a structured event log row.
        Keep the latest `max_rows` rows to avoid unbounded growth.
        """
        conn = self._require_conn()
        ts = datetime.now(timezone.utc).isoformat()
        cat = str(category or "misc").strip().lower() or "misc"
        lvl = str(level or "info").strip().lower() or "info"
        act = str(action or "").strip() or "-"
        dom = (str(domain).strip().lower() if domain is not None else None) or None
        msg = str(message or "").strip() or "-"
        det = None
        if detail is not None:
            try:
                det = json.dumps(detail, ensure_ascii=False)
            except Exception:
                det = json.dumps({"detail": str(detail)}, ensure_ascii=False)

        await conn.execute(
            """
            INSERT INTO event_log(ts, category, level, action, domain, message, detail)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, cat, lvl, act, dom, msg, det),
        )

        keep = max(100, int(max_rows or 0))
        # Keep only the latest `keep` rows (delete oldest if needed).
        await conn.execute(
            """
            DELETE FROM event_log
            WHERE id <= (
              SELECT id FROM event_log ORDER BY id DESC LIMIT 1 OFFSET ?
            )
            """,
            (keep,),
        )
        await conn.commit()

    async def list_events(
        self,
        *,
        category: Optional[str] = None,
        domain: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        cat = (str(category or "").strip().lower() or "").strip()
        dom = (str(domain or "").strip().lower() or "").strip()
        kw = (str(keyword or "").strip() or "").strip()
        lim = max(1, min(1000, int(limit or 0)))

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
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(lim)

        cur = await conn.execute(sql, tuple(params))
        rows = await cur.fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            detail = item.get("detail")
            if detail:
                try:
                    item["detail"] = json.loads(detail)
                except Exception:
                    item["detail"] = str(detail)
            else:
                item["detail"] = None
            items.append(item)
        return items

    async def clear_events(self) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM event_log")
        await conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _require_conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("SqliteStore not initialized")
        return self._conn

    async def _ensure_default_notifications(self) -> None:
        existing = await self.get_json("notifications", default=None)
        if existing is not None:
            return
        await self.set_json(
            "notifications",
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
        existing = await self.get_json("app_config", default=None)
        if existing is not None:
            return
        await self.set_json("app_config", {})

    async def _ensure_default_sites(self) -> None:
        existing = await self.get_json("sites", default=None)
        if existing is not None:
            return
        await self.set_json("sites", {"version": 1, "entries": {}})

    async def get_site_state(self, domain: str) -> Optional[StoredSiteState]:
        conn = self._require_conn()
        cur = await conn.execute(
            """
            SELECT domain, registration_state, invites_state, invites_available, last_checked_at, last_changed_at, last_evidence
            FROM site_state
            WHERE domain = ?
            """,
            (domain,),
        )
        row = await cur.fetchone()
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
        return StoredSiteState(
            domain=row["domain"],
            reachability_state=reachability_state,
            registration_state=row["registration_state"],
            invites_state=row["invites_state"],
            invites_available=row["invites_available"],
            last_checked_at=row["last_checked_at"],
            last_changed_at=row["last_changed_at"],
        )

    async def save_site_result(self, result: SiteCheckResult, changed_at: Optional[str]) -> None:
        conn = self._require_conn()
        evidence_json = json.dumps(to_jsonable(result), ensure_ascii=False)
        checked_at = result.checked_at.isoformat()
        changed_at_value = changed_at.strip() if isinstance(changed_at, str) else None
        if not changed_at_value:
            changed_at_value = None

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
        await conn.commit()

    async def list_site_states(self) -> list[dict[str, Any]]:
        conn = self._require_conn()
        cur = await conn.execute(
            """
            SELECT domain, name, url, engine, registration_state, invites_state, invites_available,
                   last_checked_at, last_changed_at, last_evidence
            FROM site_state
            ORDER BY domain
            """
        )
        rows = await cur.fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            errors: list[str] = []
            try:
                payload = json.loads(item.get("last_evidence") or "{}")
                reach = (payload.get("reachability") or {}) if isinstance(payload, dict) else {}
                reach_ev = (reach.get("evidence") or {}) if isinstance(reach, dict) else {}

                reach_state = str(reach.get("state") or "unknown")
                item["reachability_state"] = reach_state
                reach_status = reach_ev.get("http_status")
                reach_reason = str(reach_ev.get("reason") or "")
                reach_detail = str(reach_ev.get("detail") or "").strip()
                if reach_state == "down":
                    if reach_detail:
                        item["reachability_note"] = reach_detail
                    elif reach_status is not None:
                        item["reachability_note"] = f"HTTP {reach_status}"
                    else:
                        item["reachability_note"] = reach_reason or "down"
                    errors.append(f"站点不可访问：{item['reachability_note']}")
                elif reach_status is not None:
                    try:
                        status_value = int(reach_status)
                    except Exception:
                        status_value = None
                    item["reachability_note"] = "" if status_value == 200 else f"HTTP {reach_status}"
                else:
                    item["reachability_note"] = ""

                reg_ev = ((payload.get("registration") or {}).get("evidence") or {}) if isinstance(payload, dict) else {}
                inv_ev = ((payload.get("invites") or {}).get("evidence") or {}) if isinstance(payload, dict) else {}
                inv_payload = (payload.get("invites") or {}) if isinstance(payload, dict) else {}

                reg_reason = str(reg_ev.get("reason") or "")
                inv_reason = str(inv_ev.get("reason") or "")
                reg_detail = str(reg_ev.get("detail") or reg_ev.get("matched") or "").strip()
                inv_detail = str(inv_ev.get("detail") or inv_ev.get("matched") or "").strip()

                reg_status = reg_ev.get("http_status")
                if item.get("registration_state") == "unknown":
                    if reg_detail:
                        item["registration_note"] = reg_detail
                    elif reg_status is not None and reg_reason:
                        item["registration_note"] = f"HTTP {reg_status} {reg_reason}"
                    elif reg_status is not None:
                        item["registration_note"] = f"HTTP {reg_status}"
                    else:
                        item["registration_note"] = reg_reason
                else:
                    item["registration_note"] = ""

                inv_perm = inv_payload.get("permanent") if isinstance(inv_payload, dict) else None
                inv_temp = inv_payload.get("temporary") if isinstance(inv_payload, dict) else None
                if item.get("invites_state") == "open":
                    if inv_perm is not None:
                        item["invites_display"] = f"{int(inv_perm)}({int(inv_temp or 0)})"
                    elif item.get("invites_available") is not None:
                        item["invites_display"] = f"{int(item['invites_available'])}(0)"
                    else:
                        item["invites_display"] = ""
                else:
                    item["invites_display"] = ""

                if reg_reason.startswith("registration_error:"):
                    err_type = reg_reason.split(":", 1)[1] or "Error"
                    errors.append(f"注册：{err_type} · {reg_detail or 'no details'}")
                if inv_reason.startswith("invites_error:"):
                    err_type = inv_reason.split(":", 1)[1] or "Error"
                    errors.append(f"邀请：{err_type} · {inv_detail or 'no details'}")
            except Exception:
                item["reachability_state"] = "unknown"
                item["reachability_note"] = ""
                item["registration_note"] = ""
                item["invites_display"] = ""
                errors.append("解析异常信息失败：请查看日志")

            item.pop("last_evidence", None)
            item["errors"] = errors
            items.append(item)

        return items

    async def reset_site_states(self) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM site_state")
        await conn.commit()

    async def get_reachability_states(self, domains: list[str]) -> dict[str, str]:
        conn = self._require_conn()
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

    async def get_sites_extras(self, domains: list[str]) -> dict[str, dict[str, Any]]:
        conn = self._require_conn()
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

    async def load_sites_snapshot(self) -> tuple[Optional[datetime], list[Site]]:
        conn = self._require_conn()
        cur = await conn.execute(
            """
            SELECT domain, name, url, last_checked_at, last_evidence
            FROM site_state
            ORDER BY domain
            """
        )
        rows = await cur.fetchall()

        latest: Optional[datetime] = None
        sites: list[Site] = []

        def _safe_str(value: Any) -> str:
            if value is None:
                return ""
            return str(value).strip()

        def _safe_int(value: Any) -> Optional[int]:
            if value is None or value == "":
                return None
            try:
                return int(value)
            except Exception:
                return None

        def _parse_dt(value: Any) -> Optional[datetime]:
            s = _safe_str(value)
            if not s:
                return None
            try:
                dt = datetime.fromisoformat(s)
            except Exception:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        for r in rows:
            domain = _safe_str(r["domain"]).lower()
            url = _safe_str(r["url"])
            if not domain or not url:
                continue
            name = _safe_str(r["name"]) or domain

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
                        ua = _safe_str(site_payload.get("ua")) or None
                        cookie = _safe_str(site_payload.get("cookie")) or None
                        is_active = bool(site_payload.get("is_active", True))
                        parsed_id = _safe_int(site_payload.get("id"))
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

    async def get_json(self, key: str, default: Any) -> Any:
        conn = self._require_conn()
        cur = await conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
        row = await cur.fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    async def set_json(self, key: str, value: Any) -> None:
        conn = self._require_conn()
        now = datetime.utcnow().isoformat()
        payload = json.dumps(value, ensure_ascii=False)
        await conn.execute(
            """
            INSERT INTO kv(key, value, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, payload, now),
        )
        await conn.commit()
