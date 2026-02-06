import tempfile
import unittest
from pathlib import Path

import pt_invite_watcher.runtime_config_cache as cache_mod
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
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache
from pt_invite_watcher.storage.sqlite import SqliteStore


class RuntimeConfigCacheTest(unittest.IsolatedAsyncioTestCase):
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

    async def asyncTearDown(self) -> None:
        await self._store.close()
        self._tmp.cleanup()

    async def test_cache_reuses_value_until_invalidated(self) -> None:
        call_count = 0

        original = cache_mod.load_runtime_config_from_store

        async def fake(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original(*args, **kwargs)

        cache_mod.load_runtime_config_from_store = fake
        try:
            cache = RuntimeConfigCache(self._settings, self._store, ttl_seconds=60)
            await cache.get()
            await cache.get()
            self.assertEqual(call_count, 1)

            cache.invalidate()
            await cache.get()
            self.assertEqual(call_count, 2)
        finally:
            cache_mod.load_runtime_config_from_store = original

    async def test_ttl_zero_disables_cache(self) -> None:
        call_count = 0

        original = cache_mod.load_runtime_config_from_store

        async def fake(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original(*args, **kwargs)

        cache_mod.load_runtime_config_from_store = fake
        try:
            cache = RuntimeConfigCache(self._settings, self._store, ttl_seconds=0)
            await cache.get()
            await cache.get()
            self.assertEqual(call_count, 2)
        finally:
            cache_mod.load_runtime_config_from_store = original


if __name__ == "__main__":
    unittest.main()

