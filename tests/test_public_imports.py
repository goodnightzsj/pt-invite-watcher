import unittest


class PublicImportsTest(unittest.TestCase):
    def test_scanner_wrapper_exports(self) -> None:
        from pt_invite_watcher import scanner as wrapper
        from pt_invite_watcher import scanner_impl as impl

        self.assertIs(wrapper.Scanner, impl.Scanner)
        self.assertIs(wrapper.AlreadyScanningError, impl.AlreadyScanningError)
        self.assertEqual(set(getattr(wrapper, "__all__", [])), {"Scanner", "AlreadyScanningError"})

    def test_sqlite_wrapper_exports(self) -> None:
        from pt_invite_watcher.storage import sqlite as wrapper
        from pt_invite_watcher.storage import sqlite_store as impl

        self.assertIs(wrapper.SqliteStore, impl.SqliteStore)
        self.assertIs(wrapper.StoredSiteState, impl.StoredSiteState)
        self.assertEqual(set(getattr(wrapper, "__all__", [])), {"SqliteStore", "StoredSiteState"})


if __name__ == "__main__":
    unittest.main()

