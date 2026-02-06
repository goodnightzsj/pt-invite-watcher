import re
import unittest
from pathlib import Path

from pt_invite_watcher import ws_events as py_ws


class WSEventsSyncTest(unittest.TestCase):
    def test_webui_ws_events_matches_backend_constants(self) -> None:
        root = Path(__file__).resolve().parent.parent
        ts_path = root / "webui" / "src" / "ws_events.ts"
        self.assertTrue(ts_path.exists(), f"missing {ts_path}")

        text = ts_path.read_text(encoding="utf-8")
        pattern = re.compile(r'^export const (?P<name>WS_[A-Z0-9_]+) = "(?P<value>[^"]+)" as const;', re.M)
        ts_consts = {m.group("name"): m.group("value") for m in pattern.finditer(text)}

        py_names = list(getattr(py_ws, "__all__", []) or [])
        self.assertTrue(py_names, "backend ws_events.__all__ is empty")

        self.assertEqual(set(ts_consts.keys()), set(py_names))
        for name in py_names:
            self.assertEqual(ts_consts.get(name), getattr(py_ws, name))


if __name__ == "__main__":
    unittest.main()

