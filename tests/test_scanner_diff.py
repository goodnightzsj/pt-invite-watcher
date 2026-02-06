import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from pt_invite_watcher.models import (
    AspectResult,
    Evidence,
    ReachabilityResult,
    Site,
    SiteCheckResult,
)
from pt_invite_watcher.scanner import Scanner


class ScannerDiffTest(unittest.TestCase):
    def test_diff_reachability_registration_and_invites_count(self) -> None:
        prev = SimpleNamespace(
            reachability_state="up",
            registration_state="closed",
            invites_state="closed",
            invites_available=0,
        )

        site = Site(
            id=1,
            name="Example",
            domain="example.com",
            url="https://example.com",
        )
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cur = SiteCheckResult(
            site=site,
            engine="nexusphp",
            reachability=ReachabilityResult(
                state="down",
                evidence=Evidence(url=site.url, http_status=503, reason="probe_http_503"),
            ),
            registration=AspectResult(
                state="open",
                evidence=Evidence(url=f"{site.url}/signup.php", http_status=200, reason="registration_open"),
            ),
            invites=AspectResult(
                state="open",
                available=2,
                permanent=None,
                temporary=None,
                evidence=Evidence(url=f"{site.url}/invite.php", http_status=200, reason="invites_ok"),
            ),
            checked_at=now,
        )

        diff = Scanner._diff(prev, cur)
        self.assertEqual(
            diff,
            [
                "可访问：正常 -> 异常 (HTTP 503)",
                "开放注册：open",
                "可用邀请数：0 -> 2",
            ],
        )

    def test_diff_invites_unknown_to_closed(self) -> None:
        prev = SimpleNamespace(
            reachability_state="up",
            registration_state="unknown",
            invites_state="unknown",
            invites_available=None,
        )
        site = Site(id=1, name="Example", domain="example.com", url="https://example.com")
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cur = SiteCheckResult(
            site=site,
            engine="nexusphp",
            reachability=ReachabilityResult(
                state="up",
                evidence=Evidence(url=site.url, http_status=200, reason="probe_ok"),
            ),
            registration=AspectResult(
                state="unknown",
                evidence=Evidence(url=f"{site.url}/signup.php", http_status=None, reason="registration_unknown"),
            ),
            invites=AspectResult(
                state="closed",
                available=None,
                permanent=None,
                temporary=None,
                evidence=Evidence(url=f"{site.url}/invite.php", http_status=200, reason="invites_closed"),
            ),
            checked_at=now,
        )
        diff = Scanner._diff(prev, cur)
        self.assertEqual(diff, ["可用邀请：unknown -> closed"])


if __name__ == "__main__":
    unittest.main()

