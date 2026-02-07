#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI gate: compile + unit tests + refactor audit.")
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref for refactor audit compare base (default: HEAD). Example: <base_commit> or origin/main",
    )
    parser.add_argument("--root", default="pt_invite_watcher", help="Package root (default: pt_invite_watcher)")
    parser.add_argument(
        "--all-classes",
        action="store_true",
        help="Audit methods for all classes under root (refactor audit only)",
    )
    parser.add_argument(
        "--class",
        dest="classes",
        action="append",
        default=[],
        help="Audit methods of this class name (repeatable). Example: --class Scanner --class SqliteStore",
    )
    args = parser.parse_args(argv)

    py = sys.executable
    root = str(args.root).strip().rstrip("/")
    ref = str(args.ref).strip()
    classes = [str(c).strip() for c in (args.classes or []) if str(c).strip()]
    all_classes = bool(getattr(args, "all_classes", False))

    _run([py, "-m", "compileall", "-q", root])
    _run([py, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-q"])

    audit_cmd = [py, "tools/refactor_audit.py", "--ref", ref, "--root", root]
    if all_classes:
        audit_cmd.append("--all-classes")
    for c in classes:
        audit_cmd += ["--class", c]
    _run(audit_cmd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
