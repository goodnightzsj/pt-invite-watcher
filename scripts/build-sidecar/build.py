"""Build a single-file PyInstaller binary for the Tauri desktop sidecar.

Produces one executable per host platform:

    src-tauri/binaries/pt-invite-watcher-server-<target-triple>[.exe]

Tauri's `externalBin` mechanism rebinds the binary name at bundle time based
on the current cargo target, so a CI matrix that builds on each OS ends up
with one binary per bundle. We don't cross-compile Python itself — each
Windows/macOS/Linux/ARM64 build happens on its native host.

Run:

    .venv/bin/python scripts/build-sidecar/build.py

Or through the npm script:

    npm run sidecar:build

Requirements:
    pip install pyinstaller          # inside the same venv as the project
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "src-tauri" / "binaries"
ENTRY = ROOT / "scripts" / "build-sidecar" / "entry.py"
SPEC_NAME = "pt-invite-watcher-server"


# Tauri's sidecar resolver looks up binaries by their Rust host triple, so a
# bundle produced on Apple Silicon must match `aarch64-apple-darwin` for the
# `.app` to pick it up. `rustc -vV` prints the host directly; falling back to
# a platform.machine()/system() mapping keeps the script running if rustc
# isn't on PATH at build time.
def rust_target_triple() -> str:
    try:
        out = subprocess.check_output(["rustc", "-vV"], text=True)
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    sys_name = platform.system()
    machine = platform.machine().lower()
    arch = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine, machine)
    vendor_os = {
        "Darwin": "apple-darwin",
        "Linux": "unknown-linux-gnu",
        "Windows": "pc-windows-msvc",
    }.get(sys_name, "unknown")
    return f"{arch}-{vendor_os}"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "PyInstaller not installed in this interpreter. Run:\n"
            f"    {sys.executable} -m pip install pyinstaller"
        )


def run_pyinstaller(spec_path: Path, workdir: Path) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--distpath", str(workdir / "dist"), "--workpath", str(workdir / "build"), "--noconfirm"]
    # ASCII-only prefix — Windows' default cp1252 console encoding doesn't
    # carry the `→` arrow and crashes the script with UnicodeEncodeError.
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triple", default=None, help="Override the Tauri target triple in the output filename")
    args = parser.parse_args()

    ensure_pyinstaller()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    workdir = ROOT / "scripts" / "build-sidecar" / ".work"
    workdir.mkdir(parents=True, exist_ok=True)

    spec_path = ROOT / "scripts" / "build-sidecar" / "sidecar.spec"
    run_pyinstaller(spec_path, workdir)

    built = workdir / "dist" / (SPEC_NAME + (".exe" if platform.system() == "Windows" else ""))
    if not built.exists():
        raise SystemExit(f"expected PyInstaller output at {built}, not found")

    triple = args.triple or rust_target_triple()
    suffix = ".exe" if platform.system() == "Windows" else ""
    target = OUT_DIR / f"{SPEC_NAME}-{triple}{suffix}"
    shutil.copy2(built, target)
    print(f"OK wrote {target} ({target.stat().st_size // (1024 * 1024)} MB)")


if __name__ == "__main__":
    main()
