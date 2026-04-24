# PyInstaller spec for the Tauri desktop sidecar.
#
# Invoke via:   python scripts/build-sidecar/build.py   (preferred)
# Or direct:    pyinstaller scripts/build-sidecar/sidecar.spec
#
# The spec file IS Python — PyInstaller evals it during build. Keep it side-effect-free;
# any logging here ends up in PyInstaller's build log, not the user's runtime log.
import os
from pathlib import Path

# Spec files don't receive __file__ in some PyInstaller versions; fall back to CWD
# which build.py sets to ROOT/scripts/build-sidecar before invoking us.
try:
    SPEC_DIR = Path(__file__).resolve().parent
except NameError:  # pragma: no cover — only trips on older PyInstaller
    SPEC_DIR = Path(os.getcwd())

ROOT = SPEC_DIR.parents[1]
ENTRY = str(SPEC_DIR / "entry.py")

# Bundle the built webui dist + the curated site registry YAML (if any) so the
# single-file binary is truly self-contained — users don't need the source
# tree alongside.
datas = []
webui_dist = ROOT / "pt_invite_watcher" / "webui_dist"
if webui_dist.exists():
    datas.append((str(webui_dist), "pt_invite_watcher/webui_dist"))

# PyInstaller's module tracer misses a handful of httpx + uvicorn runtime imports
# when the app loads them via get_running_loop / dynamic class resolution.
# Pin them explicitly so the output binary doesn't crash on first run with
# "ModuleNotFoundError".
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "h11",
    "h2",
    "httpx._transports.default",
    "httpx._transports.asgi",
    "aiosqlite",
    "pt_invite_watcher.app",
    "pt_invite_watcher.__main__",
]

a = Analysis(
    [ENTRY],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim Python's heavy stdlib + test shims we never use.
        "tkinter",
        "pydoc",
        "doctest",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pt-invite-watcher-server",
    debug=False,
    strip=False,
    upx=False,      # UPX-compressed binaries trip macOS Gatekeeper + anti-virus false positives.
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
