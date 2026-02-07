import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
from pt_invite_watcher.providers.cookiecloud_service import CookieCloudService
from pt_invite_watcher.providers.deps_status import fingerprint_cookiecloud, load_deps_status
from pt_invite_watcher.runtime_config_cache import RuntimeConfigCache


class _FakeStore:
    def __init__(self):
        self.kv: dict[str, Any] = {}

    async def get_json(self, key: str, default: Any) -> Any:
        return self.kv.get(key, default)

    async def set_json(self, key: str, value: Any) -> None:
        self.kv[key] = value


def _settings(*, refresh_interval_seconds: int = 300, source: str = "auto") -> Settings:
    return Settings(
        moviepilot=MoviePilotSettings(base_url="", username="", password="", otp_password=None),
        cookie=CookieSettings(
            source=source,
            cookiecloud=CookieCloudSettings(
                base_url="http://cookiecloud",
                uuid="uuid",
                password="pass",
                refresh_interval_seconds=refresh_interval_seconds,
            ),
        ),
        scan=ScanSettings(interval_seconds=600, timeout_seconds=20, concurrency=8, user_agent="", trust_env=False),
        db=DatabaseSettings(path=Path("./data/ptiw.db")),
        web=WebSettings(host="0.0.0.0", port=8080, basic_auth=BasicAuthSettings(enabled=False, username="", password="")),
        log_level="INFO",
    )


class CookieCloudServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_does_not_cancel_single_flight_fetch(self) -> None:
        store = _FakeStore()
        settings = _settings(refresh_interval_seconds=300, source="auto")
        rc_cache = RuntimeConfigCache(settings, store)
        svc = CookieCloudService(settings, store, runtime_config=rc_cache)

        started = asyncio.Event()
        finish = asyncio.Event()

        cookies = [
            {
                "name": "sid",
                "value": "1",
                "domain": ".example.com",
                "expires": (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
            }
        ]

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def fetch_cookie_items(self):
                _FakeClient.calls += 1
                started.set()
                await finish.wait()
                return list(cookies)

        now = datetime.now(timezone.utc)
        deps_status = {"version": 1}

        with patch("pt_invite_watcher.providers.cookiecloud_service.CookieCloudClient", _FakeClient):
            t1 = asyncio.create_task(svc.access(now=now, deps_status=deps_status, require_enabled=False, force_fetch=True))
            t2 = asyncio.create_task(svc.access(now=now, deps_status=deps_status, require_enabled=False, force_fetch=True))

            await started.wait()

            t1.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await t1

            finish.set()
            res2 = await t2
            self.assertTrue(res2.cookies)

        self.assertEqual(_FakeClient.calls, 1)

    async def test_concurrent_access_is_single_flight(self) -> None:
        store = _FakeStore()
        settings = _settings(refresh_interval_seconds=300, source="auto")
        rc_cache = RuntimeConfigCache(settings, store)
        svc = CookieCloudService(settings, store, runtime_config=rc_cache)

        cookies = [
            {
                "name": "sid",
                "value": "1",
                "domain": ".example.com",
                "expires": (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
            }
        ]

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def fetch_cookie_items(self):
                _FakeClient.calls += 1
                await asyncio.sleep(0.05)
                return list(cookies)

        now = datetime.now(timezone.utc)
        deps_status = {"version": 1}

        with patch("pt_invite_watcher.providers.cookiecloud_service.CookieCloudClient", _FakeClient):
            a, b = await asyncio.gather(
                svc.access(now=now, deps_status=deps_status, require_enabled=False, force_fetch=True),
                svc.access(now=now, deps_status=deps_status, require_enabled=False, force_fetch=True),
            )
            self.assertTrue(a.cookies)
            self.assertTrue(b.cookies)

        self.assertEqual(_FakeClient.calls, 1)

    async def test_probe_then_scan_reuses_prefetch_cache(self) -> None:
        store = _FakeStore()
        settings = _settings(refresh_interval_seconds=300, source="auto")
        rc_cache = RuntimeConfigCache(settings, store)
        svc = CookieCloudService(settings, store, runtime_config=rc_cache)

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def fetch_cookie_items(self):
                _FakeClient.calls += 1
                return [
                    {
                        "name": "sid",
                        "value": "1",
                        "domain": ".example.com",
                        "expires": (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
                    }
                ]

        deps_status = {"version": 1}
        now = datetime.now(timezone.utc)

        with patch("pt_invite_watcher.providers.cookiecloud_service.CookieCloudClient", _FakeClient):
            probe = await svc.access(now=now, deps_status=deps_status, require_enabled=False, force_fetch=True)
            self.assertTrue(probe.attempted)
            self.assertTrue(probe.ok)

            mgr, _ = await svc.build_cookie_manager_for_scan(now=now, deps_status=probe.deps_status)
            hdr = await mgr.cookie_header_for("https://example.com", fallback_cookie=None)
            self.assertIn("sid=1", hdr or "")

        self.assertEqual(_FakeClient.calls, 1)

    async def test_fetch_failure_uses_cached_fallback(self) -> None:
        store = _FakeStore()
        settings = _settings(refresh_interval_seconds=1, source="auto")
        rc_cache = RuntimeConfigCache(settings, store)
        svc = CookieCloudService(settings, store, runtime_config=rc_cache)

        cookies = [
            {
                "name": "sid",
                "value": "1",
                "domain": ".example.com",
                "expires": (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
            }
        ]

        class _FakeClient:
            calls = 0
            should_fail = False

            def __init__(self, **kwargs: Any):
                pass

            async def fetch_cookie_items(self):
                _FakeClient.calls += 1
                if _FakeClient.should_fail:
                    raise RuntimeError("boom")
                return list(cookies)

        now0 = datetime.now(timezone.utc)
        deps_status = {"version": 1}

        with patch("pt_invite_watcher.providers.cookiecloud_service.CookieCloudClient", _FakeClient):
            first = await svc.access(now=now0, deps_status=deps_status, require_enabled=True, force_fetch=False)
            self.assertTrue(first.ok)
            self.assertEqual(_FakeClient.calls, 1)

            # Expire the in-process cache and force a failure; expect fallback cookies to still be used.
            svc._cache_at = now0 - timedelta(seconds=10)  # type: ignore[attr-defined]
            _FakeClient.should_fail = True

            now1 = now0 + timedelta(seconds=10)
            mgr, ds2 = await svc.build_cookie_manager_for_scan(now=now1, deps_status=first.deps_status)
            hdr = await mgr.cookie_header_for("https://example.com", fallback_cookie=None)
            self.assertIn("sid=1", hdr or "")
            self.assertFalse(bool((ds2.get("cookiecloud") or {}).get("ok", True)))

        self.assertEqual(_FakeClient.calls, 2)

    async def test_deps_backoff_blocks_network_but_allows_cached(self) -> None:
        store = _FakeStore()
        settings = _settings(refresh_interval_seconds=300, source="auto")
        rc_cache = RuntimeConfigCache(settings, store)
        svc = CookieCloudService(settings, store, runtime_config=rc_cache)

        now = datetime.now(timezone.utc)
        fp = fingerprint_cookiecloud("http://cookiecloud", "uuid")
        deps_status = load_deps_status(
            {
                "version": 1,
                "cookiecloud": {
                    "ok": False,
                    "checked_at": now.isoformat(),
                    "next_retry_at": (now + timedelta(hours=1)).isoformat(),
                    "error": "fail",
                    "fingerprint": fp,
                },
            }
        )

        # Prime cache so access can still return cookies even when backoff blocks network.
        svc._cache_fp = fp  # type: ignore[attr-defined]
        svc._cache_at = now  # type: ignore[attr-defined]
        svc._cache = [
            {
                "name": "sid",
                "value": "1",
                "domain": ".example.com",
                "expires": (datetime.now(timezone.utc) + timedelta(days=1)).timestamp(),
            }
        ]  # type: ignore[attr-defined]

        class _FakeClient:
            calls = 0

            def __init__(self, **kwargs: Any):
                pass

            async def fetch_cookie_items(self):
                _FakeClient.calls += 1
                return []

        with patch("pt_invite_watcher.providers.cookiecloud_service.CookieCloudClient", _FakeClient):
            res = await svc.access(now=now, deps_status=deps_status, require_enabled=True, force_fetch=True)
            self.assertFalse(res.attempted)
            self.assertEqual(_FakeClient.calls, 0)
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "fail")
            self.assertTrue(res.cookies)


if __name__ == "__main__":
    unittest.main()
