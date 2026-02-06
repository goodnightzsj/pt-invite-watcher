from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Optional

from pt_invite_watcher.config import Settings
from pt_invite_watcher.kv_keys import NOTIFICATIONS_KEY
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.runtime_config_loader import get_runtime_config
from pt_invite_watcher.storage.sqlite import SqliteStore
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS
from pt_invite_watcher.utils.parse import safe_str


logger = logging.getLogger("pt_invite_watcher.notify")


def _hash_secret(secret: str) -> str:
    s = safe_str(secret)
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


if TYPE_CHECKING:
    from pt_invite_watcher.notify.wecom import WeComNotifier


class NotifierManager:
    def __init__(self, store: SqliteStore, settings: Settings, *, runtime_config: RuntimeConfigCache | None = None):
        self._store = store
        self._settings = settings
        self._runtime_config = runtime_config
        self._wecom: Optional[WeComNotifier] = None
        self._wecom_key: Optional[tuple[str, str, str, str, str, str, int]] = None
        self._wecom_lock = asyncio.Lock()

    async def _request_retry_delay_seconds(self) -> int:
        try:
            rc = await get_runtime_config(self._settings, self._store, runtime_config=self._runtime_config)
            return int(rc.connectivity.request_retry_delay_seconds or DEFAULT_REQUEST_RETRY_DELAY_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            return DEFAULT_REQUEST_RETRY_DELAY_SECONDS

    async def _get_wecom_notifier(self, wecom_cfg: dict[str, Any], *, retry_delay_seconds: int) -> WeComNotifier:
        from pt_invite_watcher.notify.wecom import WeComNotifier

        corpid = safe_str(wecom_cfg.get("corpid"))
        app_secret = safe_str(wecom_cfg.get("app_secret"))
        agent_id = safe_str(wecom_cfg.get("agent_id"))
        to_user = safe_str(wecom_cfg.get("to_user")) or "@all"
        to_party = safe_str(wecom_cfg.get("to_party"))
        to_tag = safe_str(wecom_cfg.get("to_tag"))

        key = (corpid, _hash_secret(app_secret), agent_id, to_user, to_party, to_tag, int(retry_delay_seconds or 0))

        async with self._wecom_lock:
            if self._wecom is None or self._wecom_key != key:
                self._wecom = WeComNotifier(
                    corpid=corpid,
                    app_secret=app_secret,
                    agent_id=agent_id,
                    to_user=to_user,
                    to_party=to_party,
                    to_tag=to_tag,
                    retry_attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
                    retry_delay_seconds=retry_delay_seconds,
                )
                self._wecom_key = key
            return self._wecom

    async def test(self, channel: str) -> tuple[bool, str]:
        retry_delay = await self._request_retry_delay_seconds()
        cfg = await self._store.get_json(NOTIFICATIONS_KEY, default={})
        if channel == "telegram":
            telegram = cfg.get("telegram") or {}
            if not telegram.get("enabled"):
                return False, "telegram disabled"
            if not telegram.get("token") or not telegram.get("chat_id"):
                return False, "telegram not configured"
            from pt_invite_watcher.notify.telegram import TelegramNotifier

            ok = await TelegramNotifier(
                token=telegram["token"],
                chat_id=telegram["chat_id"],
                retry_attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
                retry_delay_seconds=retry_delay,
            ).send(
                "PT Invite Watcher test message"
            )
            await self._store.add_event(
                category="notify",
                level="info" if ok else "error",
                action="telegram_test",
                message="telegram test sent" if ok else "telegram test failed",
            )
            return (True, "sent") if ok else (False, "send failed")

        if channel == "wecom":
            wecom = cfg.get("wecom") or {}
            if not wecom.get("enabled"):
                return False, "wecom disabled"
            if not wecom.get("corpid") or not wecom.get("app_secret") or not wecom.get("agent_id"):
                return False, "wecom not configured"
            notifier = await self._get_wecom_notifier(wecom, retry_delay_seconds=retry_delay)
            ok, msg, detail = await notifier.send_detail("PT Invite Watcher test message")
            await self._store.add_event(
                category="notify",
                level="info" if ok else "error",
                action="wecom_test",
                message="wecom test sent" if ok else "wecom test failed",
                detail={"ok": ok, "message": msg, "detail": detail},
            )
            return bool(ok), str(msg or "")

        return False, "unknown channel"

    async def send(self, title: str, text: str) -> None:
        cfg = await self._store.get_json(NOTIFICATIONS_KEY, default={})
        retry_delay = await self._request_retry_delay_seconds()

        telegram = cfg.get("telegram") or {}
        if telegram.get("enabled") and telegram.get("token") and telegram.get("chat_id"):
            try:
                from pt_invite_watcher.notify.telegram import TelegramNotifier

                ok = await TelegramNotifier(
                    token=telegram["token"],
                    chat_id=telegram["chat_id"],
                    retry_attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
                    retry_delay_seconds=retry_delay,
                ).send(f"{title}\n{text}")
                await self._store.add_event(
                    category="notify",
                    level="info" if ok else "error",
                    action="telegram_send",
                    message="telegram notify sent" if ok else "telegram notify failed",
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("telegram notify failed")
                await self._store.add_event(
                    category="notify",
                    level="error",
                    action="telegram_send",
                    message="telegram notify exception",
                )

        wecom = cfg.get("wecom") or {}
        if wecom.get("enabled") and wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id"):
            try:
                notifier = await self._get_wecom_notifier(wecom, retry_delay_seconds=retry_delay)
                ok, msg, detail = await notifier.send_detail(f"{title}\n{text}")
                await self._store.add_event(
                    category="notify",
                    level="info" if ok else "error",
                    action="wecom_send",
                    message="wecom notify sent" if ok else "wecom notify failed",
                    detail={"ok": ok, "message": msg, "detail": detail},
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("wecom notify failed")
                await self._store.add_event(
                    category="notify",
                    level="error",
                    action="wecom_send",
                    message="wecom notify exception",
                )
