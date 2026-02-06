import unittest
from datetime import datetime, timezone

from pt_invite_watcher.providers.cookiecloud import CookieManager


class CookieManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_cookiecloud_source_uses_prefetched_even_without_client(self) -> None:
        mgr = CookieManager(
            cookie_source="cookiecloud",
            cookiecloud=None,
            refresh_interval_seconds=300,
            prefetched_cookies=[{"name": "sid", "value": "1", "domain": ".example.com"}],
            prefetched_at=datetime.now(timezone.utc),
        )
        header = await mgr.cookie_header_for("https://example.com", fallback_cookie="a=b")
        self.assertEqual(header, "sid=1")

    async def test_auto_source_prefers_prefetched_then_falls_back(self) -> None:
        mgr = CookieManager(
            cookie_source="auto",
            cookiecloud=None,
            refresh_interval_seconds=300,
            prefetched_cookies=[{"name": "sid", "value": "1", "domain": ".example.com"}],
            prefetched_at=datetime.now(timezone.utc),
        )
        header = await mgr.cookie_header_for("https://example.com", fallback_cookie="a=b")
        self.assertEqual(header, "sid=1")

        header2 = await mgr.cookie_header_for("https://other.com", fallback_cookie="a=b")
        self.assertEqual(header2, "a=b")


if __name__ == "__main__":
    unittest.main()

