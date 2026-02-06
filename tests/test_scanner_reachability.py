import unittest

import httpx

from pt_invite_watcher.scanner_reachability import probe_reachability


class ScannerReachabilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_probe_ok_and_engine_hint(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<!-- nexusphp -->", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            reach, hint = await probe_reachability(
                client,
                "https://example.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "up")
        self.assertEqual(reach.evidence.http_status, 200)
        self.assertEqual(reach.evidence.reason, "probe_ok")
        self.assertEqual(hint, "nexusphp")

    async def test_probe_http_503_marks_down_and_includes_retries(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="oops", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            reach, hint = await probe_reachability(
                client,
                "https://example.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "down")
        self.assertEqual(reach.evidence.http_status, 503)
        self.assertEqual(reach.evidence.reason, "probe_http_503")
        self.assertIn("retries=", str(reach.evidence.detail or ""))
        self.assertIsNone(hint)

    async def test_probe_redirect_to_unrelated_host_marks_down(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(302, headers={"Location": "https://evil.com/"}, request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            reach, hint = await probe_reachability(
                client,
                "https://example.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "down")
        self.assertEqual(reach.evidence.reason, "probe_redirect")
        self.assertIn("redirected_to:evil.com", str(reach.evidence.detail or ""))
        self.assertIsNone(hint)


if __name__ == "__main__":
    unittest.main()

