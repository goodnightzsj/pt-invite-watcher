import unittest

import httpx

from pt_invite_watcher.engines.redirect_guard import (
    detect_html_offsite_redirect,
    guarded_get,
    is_blacklisted_host,
    registrable_domain,
    same_registrable_domain,
)
from pt_invite_watcher.scanner_reachability import probe_reachability


class RegistrableDomainTest(unittest.TestCase):
    def test_two_label_domain_is_itself(self) -> None:
        self.assertEqual(registrable_domain("example.com"), "example.com")

    def test_strips_common_subdomains(self) -> None:
        self.assertEqual(registrable_domain("www.example.com"), "example.com")
        self.assertEqual(registrable_domain("m.example.com"), "example.com")
        self.assertEqual(registrable_domain("api.m-team.cc"), "m-team.cc")

    def test_handles_multi_part_tld(self) -> None:
        self.assertEqual(registrable_domain("foo.example.co.uk"), "example.co.uk")
        self.assertEqual(registrable_domain("shop.example.com.cn"), "example.com.cn")

    def test_empty_or_invalid(self) -> None:
        self.assertEqual(registrable_domain(""), "")
        self.assertEqual(registrable_domain("localhost"), "localhost")

    def test_same_registrable_domain(self) -> None:
        self.assertTrue(same_registrable_domain("www.example.com", "m.example.com"))
        self.assertTrue(same_registrable_domain("api.m-team.cc", "kp.m-team.cc"))
        self.assertFalse(same_registrable_domain("example.com", "baidu.com"))
        self.assertFalse(same_registrable_domain("example.co.uk", "evil.co.uk"))


class BlacklistTest(unittest.TestCase):
    def test_decoy_hosts_are_blocked(self) -> None:
        self.assertTrue(is_blacklisted_host("www.baidu.com"))
        self.assertTrue(is_blacklisted_host("baidu.com"))
        self.assertTrue(is_blacklisted_host("t.co"))
        self.assertTrue(is_blacklisted_host("bit.ly"))

    def test_pt_sites_pass(self) -> None:
        self.assertFalse(is_blacklisted_host("api.m-team.cc"))
        self.assertFalse(is_blacklisted_host("example.com"))


class HtmlRedirectTest(unittest.TestCase):
    def test_meta_refresh_to_baidu_detected(self) -> None:
        html = '<html><head><meta http-equiv="refresh" content="0; url=https://www.baidu.com/"></head></html>'
        self.assertEqual(detect_html_offsite_redirect(html, expected_host="site.com"), "www.baidu.com")

    def test_js_location_to_baidu_detected(self) -> None:
        html = '<html><body><script>window.location = "https://baidu.com/s?q=dead"</script></body></html>'
        self.assertEqual(detect_html_offsite_redirect(html, expected_host="site.com"), "baidu.com")

    def test_location_replace_detected(self) -> None:
        html = '<script>location.replace("https://qq.com/")</script>'
        self.assertEqual(detect_html_offsite_redirect(html, expected_host="site.com"), "qq.com")

    def test_relative_url_not_flagged(self) -> None:
        html = '<meta http-equiv="refresh" content="0; url=/login.php">'
        self.assertIsNone(detect_html_offsite_redirect(html, expected_host="site.com"))

    def test_same_domain_not_flagged(self) -> None:
        html = '<meta http-equiv="refresh" content="0; url=https://www.site.com/x">'
        self.assertIsNone(detect_html_offsite_redirect(html, expected_host="site.com"))

    def test_empty_html(self) -> None:
        self.assertIsNone(detect_html_offsite_redirect("", expected_host="site.com"))


class GuardedGetIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_301_chain_to_blacklist_is_caught(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(301, headers={"Location": "https://www.baidu.com/"}, request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            gr = await guarded_get(client, "https://example.com/", expected_host="example.com", attempts=1, delay_seconds=0)
        self.assertIsNone(gr.response)
        self.assertEqual(gr.off_site_reason, "blacklisted")
        self.assertEqual(gr.off_site_host, "www.baidu.com")
        self.assertEqual(len(gr.redirect_chain), 1)
        self.assertEqual(gr.redirect_chain[0]["status"], 301)

    async def test_subdomain_redirect_is_allowed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(301, headers={"Location": "https://www.example.com/"}, request=request)
            return httpx.Response(200, text="ok", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            gr = await guarded_get(client, "https://example.com/", expected_host="example.com", attempts=1, delay_seconds=0)
        self.assertIsNotNone(gr.response)
        self.assertIsNone(gr.off_site_reason)
        self.assertEqual(gr.response.status_code, 200)  # type: ignore[union-attr]

    async def test_html_meta_refresh_offsite_caught(self) -> None:
        hijacked = '<html><meta http-equiv="refresh" content="0; url=https://baidu.com/"></html>'

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=hijacked, headers={"Content-Type": "text/html"}, request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            gr = await guarded_get(client, "https://example.com/", expected_host="example.com", attempts=1, delay_seconds=0)
        self.assertIsNotNone(gr.response)
        self.assertEqual(gr.off_site_reason, "html_redirect")
        self.assertEqual(gr.off_site_host, "baidu.com")

    async def test_too_many_redirects(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # Keep bouncing between two in-domain paths — never terminates.
            target = "/a" if request.url.path != "/a" else "/b"
            return httpx.Response(302, headers={"Location": f"https://example.com{target}"}, request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            gr = await guarded_get(client, "https://example.com/", expected_host="example.com", attempts=1, delay_seconds=0, max_redirects=3)
        self.assertEqual(gr.off_site_reason, "too_many_redirects")
        self.assertGreaterEqual(len(gr.redirect_chain), 3)


class ReachabilityIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_redirect_to_baidu_marks_down_with_detail(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "deadsite.com":
                return httpx.Response(302, headers={"Location": "https://www.baidu.com/"}, request=request)
            return httpx.Response(200, text="baidu", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            reach, hint = await probe_reachability(
                client,
                "https://deadsite.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "down")
        self.assertEqual(reach.evidence.reason, "probe_redirect")
        self.assertIn("redirected_to:www.baidu.com", str(reach.evidence.detail or ""))
        self.assertIsNone(hint)

    async def test_html_redirect_marks_down(self) -> None:
        hijacked = '<html><meta http-equiv="refresh" content="0; url=https://baidu.com/"></html>'

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=hijacked, headers={"Content-Type": "text/html"}, request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            reach, _hint = await probe_reachability(
                client,
                "https://deadsite.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "down")
        self.assertEqual(reach.evidence.reason, "probe_html_redirect")
        self.assertIn("baidu.com", str(reach.evidence.detail or ""))

    async def test_legit_http_to_https_upgrade_passes(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.scheme == "http":
                return httpx.Response(301, headers={"Location": f"https://{request.url.host}/"}, request=request)
            return httpx.Response(200, text="<!-- nexusphp --> body", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            reach, hint = await probe_reachability(
                client,
                "http://pt.example.com/",
                user_agent=None,
                cookie_header=None,
                retry_delay_seconds=0,
            )
        self.assertEqual(reach.state, "up")
        self.assertEqual(hint, "nexusphp")


if __name__ == "__main__":
    unittest.main()
