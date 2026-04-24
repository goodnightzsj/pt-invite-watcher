from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch

from fastapi import HTTPException

from pt_invite_watcher.routes import sites as sites_module


@dataclass
class _FakeResponse:
    status_code: int
    content: bytes
    content_type: str

    @property
    def headers(self) -> dict:
        return {"Content-Type": self.content_type} if self.content_type else {}

    async def aclose(self) -> None:
        return None


@dataclass
class _FakeGuardResult:
    response: Optional[_FakeResponse] = None
    off_site_reason: Optional[str] = None
    off_site_host: Optional[str] = None
    redirect_chain: tuple = ()
    retries: int = 1
    error: Optional[Exception] = None


class FaviconProxyTest(unittest.TestCase):
    """Coverage for `GET /api/sites/icon?domain=…`.

    The endpoint is a hot path (one hit per site per dashboard render per 12h);
    tests pin the happy path, every 204 fallback reason, and the shared in-
    memory cache so we don't regress the dedup behavior that keeps upstream PT
    sites from getting hammered when many users share one server.
    """

    def setUp(self) -> None:
        # Each test starts with an empty server-side icon cache so assertions
        # about upstream call counts are not polluted by earlier tests.
        sites_module._icon_cache.clear()

    async def _call(self, domain: str):
        return await sites_module.api_site_icon(domain=domain)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)

    def test_empty_domain_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self._run(self._call(""))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_successful_image_returned_with_cache_headers(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

        async def fake_guarded_get(client, url, **kwargs):
            return _FakeGuardResult(response=_FakeResponse(200, png, "image/png"))

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            resp = self._run(self._call("example.com"))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.body, png)
        self.assertEqual(resp.media_type, "image/png")
        self.assertIn("public", resp.headers.get("cache-control", ""))

    def test_offsite_redirect_returns_204_and_negative_caches(self) -> None:
        calls = {"n": 0}

        async def fake_guarded_get(client, url, **kwargs):
            calls["n"] += 1
            # Simulate `guarded_get` flagging an off-site hop away from the
            # requested domain — classic hijack / parked-domain situation.
            return _FakeGuardResult(off_site_reason="hop_offsite", off_site_host="decoy.example")

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            first = self._run(self._call("hijacked.example"))
            second = self._run(self._call("hijacked.example"))

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)
        # Negative cache hit on the second call — upstream is probed exactly once.
        self.assertEqual(calls["n"], 1)

    def test_non_image_content_type_returns_204(self) -> None:
        async def fake_guarded_get(client, url, **kwargs):
            # Some sites 200-OK their 404 page with an HTML body; must not serve that.
            return _FakeGuardResult(response=_FakeResponse(200, b"<html>Not Found</html>", "text/html"))

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            resp = self._run(self._call("html-404.example"))
        self.assertEqual(resp.status_code, 204)

    def test_tiny_body_returns_204(self) -> None:
        async def fake_guarded_get(client, url, **kwargs):
            # A 1x1 transparent pixel served with `image/gif` is technically a
            # valid image but worthless; treat <32 B as "no real icon".
            return _FakeGuardResult(response=_FakeResponse(200, b"GIF89a", "image/gif"))

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            resp = self._run(self._call("tiny.example"))
        self.assertEqual(resp.status_code, 204)

    def test_oversized_body_returns_204(self) -> None:
        async def fake_guarded_get(client, url, **kwargs):
            return _FakeGuardResult(response=_FakeResponse(200, b"\xff" * (sites_module._FAVICON_MAX_BYTES + 1), "image/png"))

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            resp = self._run(self._call("huge.example"))
        self.assertEqual(resp.status_code, 204)

    def test_upstream_exception_returns_204_and_negative_caches(self) -> None:
        calls = {"n": 0}

        async def fake_guarded_get(client, url, **kwargs):
            calls["n"] += 1
            raise RuntimeError("connection reset")

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            first = self._run(self._call("broken.example"))
            second = self._run(self._call("broken.example"))

        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 204)
        # Negative cache also catches exceptions — we don't keep hammering a
        # consistently-failing origin every time the dashboard re-renders.
        self.assertEqual(calls["n"], 1)

    def test_successful_image_served_from_cache_on_second_request(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        calls = {"n": 0}

        async def fake_guarded_get(client, url, **kwargs):
            calls["n"] += 1
            return _FakeGuardResult(response=_FakeResponse(200, png, "image/png"))

        with patch.object(sites_module, "guarded_get", fake_guarded_get):
            first = self._run(self._call("cached.example"))
            second = self._run(self._call("cached.example"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.body, second.body)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
