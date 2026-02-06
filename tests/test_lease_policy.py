import unittest

from pt_invite_watcher.lease_policy import scan_lease_ttl_seconds, scheduler_lease_ttl_seconds


class LeasePolicyTest(unittest.TestCase):
    def test_scheduler_lease_ttl_seconds(self) -> None:
        self.assertEqual(scheduler_lease_ttl_seconds(interval_seconds=600, timeout_seconds=20), 1800)
        self.assertEqual(scheduler_lease_ttl_seconds(interval_seconds=10, timeout_seconds=1), 300)
        self.assertEqual(scheduler_lease_ttl_seconds(interval_seconds=0, timeout_seconds=100), 3000)

    def test_scan_lease_ttl_seconds(self) -> None:
        self.assertEqual(scan_lease_ttl_seconds(timeout_seconds=20), 400)
        self.assertEqual(scan_lease_ttl_seconds(timeout_seconds=1), 60)
        self.assertEqual(scan_lease_ttl_seconds(timeout_seconds=0), 60)


if __name__ == "__main__":
    unittest.main()

