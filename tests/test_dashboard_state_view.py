import json
import unittest

from pt_invite_watcher.dashboard_state_view import derive_state_view


class DashboardStateViewTest(unittest.TestCase):
    def test_reachability_down_sets_error_and_note(self) -> None:
        row = {
            "registration_state": "unknown",
            "invites_state": "unknown",
            "invites_available": None,
            "last_evidence": json.dumps(
                {
                    "reachability": {"state": "down", "evidence": {"detail": "timeout", "reason": "connect_timeout"}},
                    "registration": {"state": "unknown", "evidence": {}},
                    "invites": {"state": "unknown", "evidence": {}},
                },
                ensure_ascii=False,
            ),
        }

        derived = derive_state_view(row)
        self.assertEqual(derived["reachability_state"], "down")
        self.assertEqual(derived["reachability_note"], "timeout")
        self.assertIn("站点不可访问：timeout", derived["errors"])

    def test_registration_and_invites_error_aggregated(self) -> None:
        row = {
            "registration_state": "unknown",
            "invites_state": "unknown",
            "invites_available": None,
            "last_evidence": json.dumps(
                {
                    "reachability": {"state": "up", "evidence": {"http_status": 200}},
                    "registration": {"state": "unknown", "evidence": {"reason": "registration_error:TimeoutError", "detail": "boom"}},
                    "invites": {"state": "unknown", "evidence": {"reason": "invites_error:ValueError", "detail": "bad"}},
                },
                ensure_ascii=False,
            ),
        }

        derived = derive_state_view(row)
        self.assertIn("注册：TimeoutError · boom", derived["errors"])
        self.assertIn("邀请：ValueError · bad", derived["errors"])


if __name__ == "__main__":
    unittest.main()

