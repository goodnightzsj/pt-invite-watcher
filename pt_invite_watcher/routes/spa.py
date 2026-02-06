from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from pt_invite_watcher.routes.common import DIST_DIR, require_auth


router = APIRouter()


def _spa_file_response() -> HTMLResponse:
    index_path = DIST_DIR / "index.html"
    if not index_path.exists():
        detail = (
            "<h1>Web UI not built</h1>"
            "<p>Run:</p>"
            "<pre>npm --prefix webui install\nnpm --prefix webui run build</pre>"
        )
        return HTMLResponse(detail, status_code=503)
    return HTMLResponse(index_path.read_text(encoding="utf-8"), status_code=200)


@router.get("/favicon.svg", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(DIST_DIR / "favicon.svg")


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def spa_root() -> HTMLResponse:
    return _spa_file_response()


@router.get("/{path:path}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
async def spa_routes(path: str) -> HTMLResponse:
    if path.startswith("api") or path.startswith("assets") or path in {"docs", "openapi.json", "redoc", "health"}:
        raise HTTPException(status_code=404)
    return _spa_file_response()
