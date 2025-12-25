from __future__ import annotations

import logging

from pt_invite_watcher.storage.sqlite import SqliteStore


logger = logging.getLogger("pt_invite_watcher.notify")


class NotifierManager:
    def __init__(self, store: SqliteStore):
        self._store = store

    async def test(self, channel: str) -> tuple[bool, str]:
        cfg = await self._store.get_json("notifications", default={})
        if channel == "telegram":
            telegram = cfg.get("telegram") or {}
            if not telegram.get("enabled"):
                return False, "telegram disabled"
            if not telegram.get("token") or not telegram.get("chat_id"):
                return False, "telegram not configured"
            from pt_invite_watcher.notify.telegram import TelegramNotifier

            ok = await TelegramNotifier(token=telegram["token"], chat_id=telegram["chat_id"]).send(
                "PT Invite Watcher test message"
            )
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
            ).send("PT Invite Watcher test message")
            return (True, "sent") if ok else (False, "send failed")

        return False, "unknown channel"

    async def send(self, title: str, text: str) -> None:
        cfg = await self._store.get_json("notifications", default={})

        telegram = cfg.get("telegram") or {}
        if telegram.get("enabled") and telegram.get("token") and telegram.get("chat_id"):
            try:
                from pt_invite_watcher.notify.telegram import TelegramNotifier

                await TelegramNotifier(token=telegram["token"], chat_id=telegram["chat_id"]).send(f"{title}\n{text}")
            except Exception:
                logger.exception("telegram notify failed")

        wecom = cfg.get("wecom") or {}
        if wecom.get("enabled") and wecom.get("corpid") and wecom.get("app_secret") and wecom.get("agent_id"):
            try:
                from pt_invite_watcher.notify.wecom import WeComNotifier

                await WeComNotifier(
                    corpid=wecom["corpid"],
                    app_secret=wecom["app_secret"],
                    agent_id=str(wecom["agent_id"]),
                    to_user=wecom.get("to_user") or "@all",
                    to_party=wecom.get("to_party") or "",
                    to_tag=wecom.get("to_tag") or "",
                ).send(f"{title}\n{text}")
            except Exception:
                logger.exception("wecom notify failed")

