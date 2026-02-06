import unittest
from datetime import datetime, timezone

from pt_invite_watcher.models import Evidence, ReachabilityResult, Site
from pt_invite_watcher.scanner_results import build_unreachable_result


class ScannerResultsTest(unittest.TestCase):
    def test_build_unreachable_result(self) -> None:
        site = Site(id=1, name="Example", domain="example.com", url="https://example.com")
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        reachability = ReachabilityResult(
            state="down",
            evidence=Evidence(url=site.url, http_status=None, reason="probe_error:Timeout", detail="timeout"),
        )

        result = build_unreachable_result(
            site=site,
            engine="nexusphp",
            reachability=reachability,
            checked_at=now,
            reg_path="signup.php",
            inv_path="invite.php?id=1",
        )
        self.assertEqual(result.engine, "nexusphp")
        self.assertEqual(result.reachability.state, "down")
        self.assertEqual(result.registration.state, "unknown")
        self.assertEqual(result.registration.evidence.reason, "site_unreachable")
        self.assertEqual(result.registration.evidence.url, "https://example.com/signup.php")
        self.assertEqual(result.registration.evidence.detail, "timeout")
        self.assertEqual(result.invites.evidence.url, "https://example.com/invite.php?id=1")


if __name__ == "__main__":
    unittest.main()

