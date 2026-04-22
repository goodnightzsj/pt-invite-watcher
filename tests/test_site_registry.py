from __future__ import annotations

import unittest
from types import SimpleNamespace

from pt_invite_watcher.engines.engine_selector import (
    default_paths_for_engine,
    default_paths_for_site,
    engine_for_site,
)
from pt_invite_watcher.engines.site_registry import (
    find_by_domain,
    find_by_id,
    list_all,
)


class RegistryLookupTest(unittest.TestCase):
    def test_exact_domain_hit(self) -> None:
        sd = find_by_domain("byr.pt")
        self.assertIsNotNone(sd)
        assert sd is not None
        self.assertEqual(sd.id, "byrbt")
        self.assertEqual(sd.schema, "nexusphp")

    def test_subdomain_resolves_to_parent(self) -> None:
        sd = find_by_domain("www.byr.pt")
        self.assertIsNotNone(sd)
        assert sd is not None
        self.assertEqual(sd.id, "byrbt")

    def test_mteam_suffix_matches(self) -> None:
        sd = find_by_domain("kp.m-team.cc")
        self.assertIsNotNone(sd)
        assert sd is not None
        self.assertEqual(sd.schema, "mteam")

    def test_unknown_domain_returns_none(self) -> None:
        self.assertIsNone(find_by_domain("definitely-not-a-pt-site.example"))
        self.assertIsNone(find_by_domain(""))

    def test_find_by_id(self) -> None:
        sd = find_by_id("blutopia")
        self.assertIsNotNone(sd)
        assert sd is not None
        self.assertEqual(sd.schema, "unit3d")

    def test_find_by_id_case_insensitive(self) -> None:
        sd = find_by_id("BYRBT")
        self.assertIsNotNone(sd)
        assert sd is not None
        self.assertEqual(sd.id, "byrbt")

    def test_registry_has_all_major_engine_examples(self) -> None:
        schemas = {sd.schema for sd in list_all()}
        # Every engine we advertise in the UI should have at least one real
        # example in the registry; otherwise the dropdown would list an engine
        # with no demo sites.
        self.assertIn("nexusphp", schemas)
        self.assertIn("mteam", schemas)
        self.assertIn("unit3d", schemas)
        self.assertIn("gazelle", schemas)


class RegistryIntegrationTest(unittest.TestCase):
    def test_engine_selector_uses_registry_for_known_domain(self) -> None:
        # No template, no HTML — just a known Unit3D domain.
        site = SimpleNamespace(domain="blutopia.cc", template=None)
        self.assertEqual(engine_for_site(site), "unit3d")

    def test_engine_selector_uses_registry_for_gazelle_domain(self) -> None:
        site = SimpleNamespace(domain="redacted.sh", template=None)
        self.assertEqual(engine_for_site(site), "gazelle")

    def test_user_template_still_wins_over_registry(self) -> None:
        # User deliberately sets nexusphp on a Unit3D-registered domain —
        # maybe they run a modified fork. Honor the user.
        site = SimpleNamespace(domain="blutopia.cc", template="nexusphp")
        self.assertEqual(engine_for_site(site), "nexusphp")

    def test_unknown_domain_falls_back_to_nexusphp_default(self) -> None:
        site = SimpleNamespace(domain="totally-unknown-pt.example", template=None)
        self.assertEqual(engine_for_site(site), "nexusphp")

    def test_default_paths_for_registered_unit3d_site(self) -> None:
        # Blutopia is registered with registration_path="register" and
        # invite_path="invites" — so the scanner uses those instead of
        # /signup.php even when no explicit engine is set on the Site.
        site = SimpleNamespace(domain="blutopia.cc", template=None)
        reg, inv = default_paths_for_site(site)
        self.assertEqual(reg, "register")
        self.assertEqual(inv, "invites")

    def test_default_paths_for_unknown_domain_uses_engine_default(self) -> None:
        site = SimpleNamespace(domain="totally-unknown-pt.example", template=None)
        reg, inv = default_paths_for_site(site)
        # No registry match → fall back to nexusphp defaults.
        self.assertEqual((reg, inv), default_paths_for_engine("nexusphp"))


if __name__ == "__main__":
    unittest.main()
