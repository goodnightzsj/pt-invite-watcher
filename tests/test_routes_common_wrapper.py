import ast
import unittest
from pathlib import Path


class RoutesCommonWrapperTest(unittest.TestCase):
    def test_common_only_defines_wrapper_helpers(self) -> None:
        path = Path(__file__).resolve().parent.parent / "pt_invite_watcher" / "routes" / "common.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        func_names = {
            node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

        self.assertEqual(func_names, {"broadcast_dashboard_update", "broadcast_scan_progress"})
        self.assertEqual(class_names, set())


if __name__ == "__main__":
    unittest.main()

