"""Entry point used by PyInstaller to produce the sidecar binary.

Bypasses argparse — the Tauri shell always runs the binary with `run` and the
usual env-var overrides (`PTIW_WEB_HOST`, `PTIW_WEB_PORT`, `PTIW_DB_PATH`).
Keeping the binary single-purpose avoids a class of parsing errors where the
shell passes unexpected args into Python.
"""
from __future__ import annotations

import sys


def main() -> None:
    from pt_invite_watcher.__main__ import main as _app_main

    # Tauri's sidecar handle spawns the binary without any args; synthesize
    # the `run` subcommand so `__main__.main` takes the webui+scheduler path.
    argv = ["pt-invite-watcher-server"]
    if len(sys.argv) > 1:
        argv.extend(sys.argv[1:])
    else:
        argv.append("run")
    sys.argv = argv
    _app_main()


if __name__ == "__main__":
    main()
