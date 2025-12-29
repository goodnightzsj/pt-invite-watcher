from __future__ import annotations

import logging

from pt_invite_watcher.storage.sqlite import SqliteStore
from pt_invite_watcher.net import DEFAULT_REQUEST_RETRY_ATTEMPTS, DEFAULT_REQUEST_RETRY_DELAY_SECONDS


logger = logging.getLogger("pt_invite_watcher.notify")


class NotifierManager:
    def __init__(self, store: SqliteStore):
        self._store = store

    @staticmethod
    def _cfg_int(value, default: int, min_value: int, max_value: int) -> int:
        if value is None or value == "":
            return default
        try:
            parsed = int(str(value).strip())
        except Exception:
            return default
        return max(min_value, min(max_value, parsed))

    async def _request_retry_delay_seconds(self) -> int:
        try:
            cfg = await self._store.get_json("app_config", default={}) or {}
            connectivity = cfg.get("connectivity") if isinstance(cfg, dict) else None
            conn_dict = connectivity if isinstance(connectivity, dict) else {}
            return self._cfg_int(
                conn_dict.get("request_retry_delay_seconds"),
                DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
                5,
                24 * 3600,
            )
        except Exception:
            return DEFAULT_REQUEST_RETRY_DELAY_SECONDS

    async def test(self, channel: str) -> tuple[bool, str]:
        retry_delay = await self._request_retry_delay_seconds()
        cfg = await self._store.get_json("notifications", default={})
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
            try:
                await self._store.add_event(
                    category="notify",
                    level="info" if ok else "error",
                    action="telegram_test",
                    message="telegram test sent" if ok else "telegram test failed",
                )
            except Exception:
                pass
            return (True, "sent") if ok else (False, "send failed")

        if channel == "wecom":
            wecom = cfg.get("wecom") or {}
            if not wecom.get("enabled"):
                return False, "wecom disabled"
            if not wecom.get("corpid") or not wecom.get("app_secret") or not wecom.get("agent_id"):
                return False, "wecom not configured"
            from pt_invite_watcher.notify.wecom import WeComNotifier

            ok = await WeComNotifier(
                corpid=wecom["corpid"],
                app_secret=wecom["app_secret"],
                agent_id=str(wecom["agent_id"]),
                to_user=wecom.get("to_user") or "@all",
                to_party=wecom.get("to_party") or "",
                to_tag=wecom.get("to_tag") or "",
                retry_attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
                retry_delay_seconds=retry_delay,
            ).send("PT Invite Watcher test message")
            try:
                await self._store.add_event(
                    category="notify",
                    level="info" if ok else "error",
                    action="wecom_test",
                    message="wecom test sent" if ok else "wecom test failed",
                )
            except Exception:
                pass
            return (True, "sent") if ok else (False, "send failed")

        return False, "unknown channel"

    async def send(self, title: str, text: str) -> None:
        cfg = await self._store.get_json("notifications", default={})
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
                try:
                    await self._store.add_event(
                        category="notify",
                        level="info" if ok else "error",
                        action="telegram_send",
                        message="telegram notify sent" if ok else "telegram notify failed",
                    )
                except Exception:
                    pass
            except Exception:
                logger.exception("telegram notify failed")
                try:
                    await self._store.add_event(category="notify", level="error", action="telegram_send", message="telegram notify exception")
                except Exception:
                    pass

        wecom = cfg.get("wecom") or {}
        if wecom.get("enabled") and wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id"):
            try:
                from pt_invite_watcher.notify.wecom import WeComNotifier

                ok = await WeComNotifier(
                    corpid=wecom["corpid"],
                    app_secret=wecom["app_secret"],
                    agent_id=str(wecom["agent_id"]),
                    to_user=wecom.get("to_user") or "@all",
                    to_party=wecom.get("to_party") or "",
                    to_tag=wecom.get("to_tag") or "",
                    retry_attempts=DEFAULT_REQUEST_RETRY_ATTEMPTS,
                    retry_delay_seconds=retry_delay,
                ).send(f"{title}\n{text}")
                try:
                    await self._store.add_event(
                        category="notify",
                        level="info" if ok else "error",
                        action="wecom_send",
                        message="wecom notify sent" if ok else "wecom notify failed",
                    )
                except Exception:
                    pass
            except Exception:
                logger.exception("wecom notify failed")
                try:
                    await self._store.add_event(category="notify", level="error", action="wecom_send", message="wecom notify exception")
                except Exception:
                    pass
