import unittest
from datetime import datetime, timezone

from pt_invite_watcher.models import AspectResult, Evidence, ReachabilityResult, Site, SiteCheckResult
from pt_invite_watcher.scanner_change import (
    build_state_changed_event_detail,
    build_state_changed_notification,
)


class ScannerChangeTest(unittest.TestCase):
    def _sample(self) -> tuple[Site, SiteCheckResult]:
        site = Site(id=1, name="Example", domain="example.com", url="https://example.com")
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = SiteCheckResult(
            site=site,
            engine="nexusphp",
            reachability=ReachabilityResult(
                state="up",
                evidence=Evidence(url=site.url, http_status=200, reason="probe_ok"),
            ),
            registration=AspectResult(
                state="closed",
                evidence=Evidence(url=f"{site.url}/signup.php", http_status=200, reason="registration_closed"),
            ),
            invites=AspectResult(
                state="open",
                available=2,
                permanent=None,
                temporary=None,
                evidence=Evidence(url=f"{site.url}/invite.php?id=42", http_status=200, reason="invites_ok"),
            ),
            checked_at=now,
        )
        return site, result

    def test_event_detail_primary_page_selection(self) -> None:
        site, result = self._sample()

        detail_inv = build_state_changed_event_detail(site, result, ["可用邀请数：0 -> 2"])
        self.assertEqual(detail_inv["page"], {"kind": "invite", "url": f"{site.url}/invite.php?id=42"})

        detail_reg = build_state_changed_event_detail(site, result, ["开放注册：open"])
        self.assertEqual(detail_reg["page"], {"kind": "signup", "url": f"{site.url}/signup.php"})

        detail_reach = build_state_changed_event_detail(site, result, ["可访问：正常 -> 异常 (HTTP 503)"])
        self.assertEqual(detail_reach["page"], {"kind": "home", "url": site.url})

    def test_notification_formatting(self) -> None:
        site, result = self._sample()
        title, text = build_state_changed_notification(site, result, ["可用邀请数：0 -> 2"])
        self.assertEqual(title, "PT Invite Watcher: 状态变化")
        self.assertIn(f"站点：{site.name} ({site.domain})", text)
        self.assertIn(f"URL：{site.url}", text)
        self.assertIn("可用邀请数：0 -> 2", text)
        self.assertIn("注册：closed (registration_closed)", text)
        self.assertIn("邀请：open 2", text)


if __name__ == "__main__":
    unittest.main()

