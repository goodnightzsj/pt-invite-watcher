import ast
import importlib
import unittest
from pathlib import Path


class PublicWrappersTest(unittest.TestCase):
    def _assert_wrapper_module(self, *, rel_path: str, module_name: str, expected_all: set[str]) -> None:
        path = Path(__file__).resolve().parent.parent / rel_path
        tree = ast.parse(path.read_text(encoding="utf-8"))

        func_names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

        self.assertEqual(func_names, set(), f"{rel_path} should not define functions")
        self.assertEqual(class_names, set(), f"{rel_path} should not define classes")

        mod = importlib.import_module(module_name)
        exported = set(getattr(mod, "__all__", []) or [])
        self.assertEqual(exported, expected_all)
        for name in expected_all:
            self.assertTrue(hasattr(mod, name), f"{module_name} missing export: {name}")

    def test_scanner_wrapper(self) -> None:
        self._assert_wrapper_module(
            rel_path="pt_invite_watcher/scanner.py",
            module_name="pt_invite_watcher.scanner",
            expected_all={"AlreadyScanningError", "Scanner"},
        )

    def test_storage_sqlite_wrapper(self) -> None:
        self._assert_wrapper_module(
            rel_path="pt_invite_watcher/storage/sqlite.py",
            module_name="pt_invite_watcher.storage.sqlite",
            expected_all={"SqliteStore", "StoredSiteState"},
        )

    def test_engines_nexusphp_wrapper(self) -> None:
        self._assert_wrapper_module(
            rel_path="pt_invite_watcher/engines/nexusphp.py",
            module_name="pt_invite_watcher.engines.nexusphp",
            expected_all={"NexusPhpDetector"},
        )

    def test_engines_mteam_wrapper(self) -> None:
        self._assert_wrapper_module(
            rel_path="pt_invite_watcher/engines/mteam.py",
            module_name="pt_invite_watcher.engines.mteam",
            expected_all={"MTeamDetector"},
        )


if __name__ == "__main__":
    unittest.main()
