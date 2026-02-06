import unittest

from pt_invite_watcher.scanner_moviepilot import moviepilot_warning


class ScannerMoviePilotTest(unittest.TestCase):
    def test_warning_not_configured(self) -> None:
        self.assertEqual(moviepilot_warning(mp_configured=False, mp_fields={"moviepilot_error": "x"}), "")

    def test_warning_no_error(self) -> None:
        self.assertEqual(moviepilot_warning(mp_configured=True, mp_fields={"moviepilot_error": ""}), "")

    def test_warning_with_fallback_age(self) -> None:
        msg = moviepilot_warning(
            mp_configured=True,
            mp_fields={"moviepilot_error": "timeout", "moviepilot_source": "cache", "moviepilot_cache_age_seconds": 12},
        )
        self.assertEqual(msg, "moviepilot_failed: timeout (fallback=cache age=12s)")

    def test_warning_without_age(self) -> None:
        msg = moviepilot_warning(
            mp_configured=True,
            mp_fields={"moviepilot_error": "bad", "moviepilot_source": "none", "moviepilot_cache_age_seconds": None},
        )
        self.assertEqual(msg, "moviepilot_failed: bad")


if __name__ == "__main__":
    unittest.main()
