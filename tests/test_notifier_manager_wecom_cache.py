import tempfile
import unittest
from pathlib import Path

from pt_invite_watcher.config import (
    BasicAuthSettings,
    CookieCloudSettings,
    CookieSettings,
    DatabaseSettings,
    MoviePilotSettings,
    ScanSettings,
    Settings,
    WebSettings,
)
from pt_invite_watcher.kv_keys import NOTIFICATIONS_KEY
from pt_invite_watcher.notify.manager import NotifierManager
from pt_invite_watcher.storage.sqlite import SqliteStore


class NotifierManagerWeComCacheTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp.name) / "test.db"
        self._store = SqliteStore(self._db_path)
        await self._store.init()

        self._settings = Settings(
            moviepilot=MoviePilotSettings(base_url="", username="", password="", otp_password=None),
            cookie=CookieSettings(
                source="auto",
                cookiecloud=CookieCloudSettings(base_url="", uuid="", password="", refresh_interval_seconds=300),
            ),
            scan=ScanSettings(interval_seconds=600, timeout_seconds=20, concurrency=1, user_agent="", trust_env=False),
            db=DatabaseSettings(path=self._db_path),
            web=WebSettings(
                host="127.0.0.1",
                port=0,
                basic_auth=BasicAuthSettings(enabled=False, username="", password=""),
            ),
            log_level="INFO",
        )
        self._notifier = NotifierManager(store=self._store, settings=self._settings)

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_wecom_notifier_is_reused_until_config_changes(self) -> None:
        import pt_invite_watcher.notify.wecom as wecom_mod

        class FakeWeComNotifier:
            instances = 0

            def __init__(
                self,
                corpid: str,
                app_secret: str,
                agent_id: str,
                to_user: str = "@all",
                to_party: str = "",
                to_tag: str = "",
                base_url: str = "https://qyapi.weixin.qq.com",
                retry_attempts: int = 3,
                retry_delay_seconds: int = 30,
            ):
                type(self).instances += 1
                self._corpid = corpid
                self._app_secret = app_secret
                self._agent_id = agent_id
                self._to_user = to_user
                self._to_party = to_party
                self._to_tag = to_tag
                self._retry_delay_seconds = retry_delay_seconds

            async def send_detail(self, text: str):
                return True, "sent", {"to_user": self._to_user, "retry_delay_seconds": self._retry_delay_seconds}

        original = wecom_mod.WeComNotifier
        wecom_mod.WeComNotifier = FakeWeComNotifier
        try:
            await self._store.set_json(
                NOTIFICATIONS_KEY,
                {
                    "telegram": {"enabled": False, "token": "", "chat_id": ""},
                    "wecom": {
                        "enabled": True,
                        "corpid": "corp",
                        "app_secret": "secret-a",
                        "agent_id": "1000001",
                        "to_user": "@all",
                        "to_party": "",
                        "to_tag": "",
                    },
                },
            )

            await self._notifier.send("t", "m1")
            await self._notifier.send("t", "m2")
            self.assertEqual(FakeWeComNotifier.instances, 1)

            # Change recipients -> should rebuild notifier.
            await self._store.set_json(
                NOTIFICATIONS_KEY,
                {
                    "telegram": {"enabled": False, "token": "", "chat_id": ""},
                    "wecom": {
                        "enabled": True,
                        "corpid": "corp",
                        "app_secret": "secret-a",
                        "agent_id": "1000001",
                        "to_user": "user-a",
                        "to_party": "",
                        "to_tag": "",
                    },
                },
            )
            await self._notifier.send("t", "m3")
            self.assertEqual(FakeWeComNotifier.instances, 2)
        finally:
            wecom_mod.WeComNotifier = original


if __name__ == "__main__":
    unittest.main()

