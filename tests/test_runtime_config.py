import unittest
from pathlib import Path

from pt_invite_watcher.config import (
    BasicAuthSettings,
    CookieCloudSettings,
    CookieSettings,
    DatabaseSettings,
    MoviePilotSettings,
    ScanSettings,
    Settings,
    WebSettings,
)
from pt_invite_watcher.providers.deps_status import MAX_RETRY_INTERVAL_SECONDS, MIN_RETRY_INTERVAL_SECONDS
from pt_invite_watcher.providers.moviepilot_sites_cache import MP_SITES_CACHE_MIN_TTL_SECONDS
from pt_invite_watcher.runtime_config import load_runtime_config


def _settings(*, cookie_source: str = "auto") -> Settings:
    return Settings(
        moviepilot=MoviePilotSettings(
            base_url="http://moviepilot",
            username="u",
            password="p",
            otp_password=None,
        ),
        cookie=CookieSettings(
            source=cookie_source,
            cookiecloud=CookieCloudSettings(
                base_url="http://cookiecloud",
                uuid="uuid",
                password="ccp",
                refresh_interval_seconds=300,
            ),
        ),
        scan=ScanSettings(
            interval_seconds=600,
            timeout_seconds=20,
            concurrency=8,
            user_agent="",
            trust_env=False,
        ),
        db=DatabaseSettings(path=Path("./data/ptiw.db")),
        web=WebSettings(
            host="0.0.0.0",
            port=8080,
            basic_auth=BasicAuthSettings(enabled=False, username="", password=""),
        ),
        log_level="INFO",
    )


class RuntimeConfigTest(unittest.TestCase):
    def test_clamps_and_defaults(self) -> None:
        cfg = {
            "moviepilot": {"sites_cache_ttl_seconds": 1},
            "connectivity": {"retry_interval_seconds": 1, "request_retry_delay_seconds": 1},
            "cookie": {"cookiecloud": {"refresh_interval_seconds": 1}},
            "scan": {"interval_seconds": 10, "timeout_seconds": 1, "concurrency": 999},
            "ui": {"allow_state_reset": False},
        }
        rc = load_runtime_config(_settings(), cfg)
        self.assertEqual(rc.moviepilot.sites_cache_ttl_seconds, MP_SITES_CACHE_MIN_TTL_SECONDS)
        self.assertEqual(rc.connectivity.retry_interval_seconds, MIN_RETRY_INTERVAL_SECONDS)
        self.assertEqual(rc.connectivity.request_retry_delay_seconds, 5)
        self.assertEqual(rc.cookie.cookiecloud.refresh_interval_seconds, 30)
        self.assertEqual(rc.scan.interval_seconds, 30)
        self.assertEqual(rc.scan.timeout_seconds, 5)
        self.assertEqual(rc.scan.concurrency, 64)
        self.assertFalse(rc.ui.allow_state_reset)

    def test_cookie_source_invalid_falls_back_to_settings(self) -> None:
        rc = load_runtime_config(_settings(cookie_source="moviepilot"), {"cookie": {"source": "bad"}})
        self.assertEqual(rc.cookie.source, "moviepilot")

    def test_connectivity_retry_interval_max(self) -> None:
        rc = load_runtime_config(_settings(), {"connectivity": {"retry_interval_seconds": 999999}})
        self.assertEqual(rc.connectivity.retry_interval_seconds, MAX_RETRY_INTERVAL_SECONDS)


if __name__ == "__main__":
    unittest.main()

