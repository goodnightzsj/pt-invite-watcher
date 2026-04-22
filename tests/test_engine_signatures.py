from __future__ import annotations

import unittest
from types import SimpleNamespace

from pt_invite_watcher.engines.engine_selector import (
    default_paths_for_engine,
    engine_for_site,
    engine_fully_supported,
)
from pt_invite_watcher.engines.engine_signatures import (
    ENGINES_BY_NAME,
    detect_engine,
    score_cookies,
    score_headers,
    score_html,
)


class SignatureScoringTest(unittest.TestCase):
    def test_nexusphp_marker_wins_on_nexus_html(self) -> None:
        html = """
        <html><body>
            Powered by NexusPHP
            <a href="torrents.php">种子</a>
            <div id="info_block">…</div>
        </body></html>
        """
        detection = detect_engine(html=html)
        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.engine, "nexusphp")
        self.assertGreaterEqual(detection.score, 6)

    def test_unit3d_marker_wins_on_unit3d_html(self) -> None:
        html = """
        <html>
            <body class="unit3d">
                <div class="torrent-search--list__results"></div>
                <script src="/js/app.js"></script>
            </body>
        </html>
        """
        detection = detect_engine(html=html)
        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.engine, "unit3d")

    def test_gazelle_marker_wins_on_gazelle_html(self) -> None:
        html = """
        <html><body>
            <table class="torrent_table">
              <tr><td><a class="username" href="user.php?id=1">u</a></td></tr>
            </table>
            <script src="/static/functions/ajax.php"></script>
        </body></html>
        """
        detection = detect_engine(html=html)
        self.assertIsNotNone(detection)
        assert detection is not None
        self.assertEqual(detection.engine, "gazelle")

    def test_cookie_only_signal_promotes_unit3d(self) -> None:
        det = detect_engine(html="", cookies={"laravel_session": "abc", "XSRF-TOKEN": "xyz"})
        self.assertIsNotNone(det)
        assert det is not None
        self.assertEqual(det.engine, "unit3d")

    def test_header_only_signal_promotes_unit3d(self) -> None:
        det = detect_engine(html="", headers={"set-cookie": "laravel_session=abc; HttpOnly"})
        self.assertIsNotNone(det)
        assert det is not None
        self.assertEqual(det.engine, "unit3d")

    def test_domain_shortcut_wins_over_html(self) -> None:
        html = "<html><body>Powered by NexusPHP</body></html>"
        det = detect_engine(html=html, domain="kp.m-team.cc")
        self.assertIsNotNone(det)
        assert det is not None
        self.assertEqual(det.engine, "mteam")

    def test_empty_signals_return_none(self) -> None:
        self.assertIsNone(detect_engine())
        self.assertEqual(score_html(""), [])
        self.assertEqual(score_cookies({}), [])
        self.assertEqual(score_headers({}), [])


class EngineSelectorIntegrationTest(unittest.TestCase):
    def test_composite_detection_picks_up_unit3d(self) -> None:
        site = SimpleNamespace(domain="blu.example.com", template=None)
        html = '<div class="torrent-search--list__results"></div>'
        engine = engine_for_site(
            site,
            hint=None,
            html=html,
            cookies={"laravel_session": "abc"},
        )
        self.assertEqual(engine, "unit3d")

    def test_user_template_overrides_composite(self) -> None:
        site = SimpleNamespace(domain="blu.example.com", template="nexusphp")
        html = '<div class="torrent-search--list__results"></div>'
        # User explicitly set "nexusphp", even though HTML screams unit3d.
        # Honor the user; it's most often a deliberate override.
        engine = engine_for_site(site, hint=None, html=html)
        self.assertEqual(engine, "nexusphp")

    def test_mteam_domain_still_overrides_template(self) -> None:
        # Matches the contract tested in test_engine_selector.py — mteam is the
        # one hard-override for API-locked sites.
        site = SimpleNamespace(domain="kp.m-team.cc", template="nexusphp")
        self.assertEqual(engine_for_site(site), "mteam")

    def test_default_paths_for_unit3d(self) -> None:
        reg, inv = default_paths_for_engine("unit3d")
        self.assertEqual(reg, "register")
        self.assertEqual(inv, "invites")

    def test_default_paths_for_nexusphp_preserved(self) -> None:
        reg, inv = default_paths_for_engine("nexusphp")
        self.assertEqual(reg, "signup.php")
        self.assertEqual(inv, "invite.php")

    def test_default_paths_for_unknown_falls_back(self) -> None:
        reg, inv = default_paths_for_engine("definitely_not_an_engine")
        self.assertEqual((reg, inv), ("signup.php", "invite.php"))

    def test_fully_supported_matrix(self) -> None:
        self.assertTrue(engine_fully_supported("nexusphp"))
        self.assertTrue(engine_fully_supported("mteam"))
        self.assertFalse(engine_fully_supported("unit3d"))
        self.assertFalse(engine_fully_supported("gazelle"))
        self.assertFalse(engine_fully_supported("discuz"))
        self.assertFalse(engine_fully_supported("tnode"))


class SignatureTableStructureTest(unittest.TestCase):
    def test_every_engine_has_default_paths(self) -> None:
        for name, sig in ENGINES_BY_NAME.items():
            self.assertTrue(sig.default_registration_path, f"{name}: missing default reg path")
            self.assertTrue(sig.default_invite_path, f"{name}: missing default invite path")

    def test_expected_engines_are_present(self) -> None:
        expected = {"nexusphp", "mteam", "unit3d", "gazelle", "discuz", "tnode"}
        self.assertTrue(expected.issubset(set(ENGINES_BY_NAME.keys())))


if __name__ == "__main__":
    unittest.main()
