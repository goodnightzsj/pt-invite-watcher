from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from pt_invite_watcher.models import SiteCheckResult, to_jsonable


@dataclass(frozen=True)
class StoredSiteState:
    domain: str
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
        await self._conn.commit()

        await self._ensure_default_notifications()
        await self._ensure_default_app_config()

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

    async def get_site_state(self, domain: str) -> Optional[StoredSiteState]:
        conn = self._require_conn()
        cur = await conn.execute(
            """
            SELECT domain, registration_state, invites_state, invites_available, last_checked_at, last_changed_at
            FROM site_state
            WHERE domain = ?
            """,
            (domain,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return StoredSiteState(
            domain=row["domain"],
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
                changed_at,
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
                    item["reachability_note"] = f"HTTP {reach_status}"
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
