from __future__ import annotations

import unittest
from types import SimpleNamespace

from pt_invite_watcher.engines.engine_selector import engine_for_site


class TestEngineSelector(unittest.TestCase):
    def test_mteam_domain_overrides_template_and_hint(self) -> None:
        for template in ("", None, "nexusphp", "custom", "mteam"):
            with self.subTest(template=template):
                site = SimpleNamespace(domain="m-team.cc", template=template)
                self.assertEqual(engine_for_site(site, hint=None), "mteam")
                self.assertEqual(engine_for_site(site, hint="nexusphp"), "mteam")

    def test_template_wins_over_hint_for_non_mteam(self) -> None:
        site = SimpleNamespace(domain="example.com", template="custom")
        self.assertEqual(engine_for_site(site, hint="nexusphp"), "custom")

    def test_hint_used_when_no_template(self) -> None:
        site = SimpleNamespace(domain="example.com", template="")
        self.assertEqual(engine_for_site(site, hint="nexusphp"), "nexusphp")

    def test_default_is_nexusphp(self) -> None:
        site = SimpleNamespace(domain="example.com", template=None)
        self.assertEqual(engine_for_site(site, hint=None), "nexusphp")


if __name__ == "__main__":
    unittest.main()

