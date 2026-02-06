from __future__ import annotations

from typing import Any, Dict, Annotated

from fastapi import APIRouter, Depends

from pt_invite_watcher import __version__
from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.routes.common import get_ctx


router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True}


@router.get("/api/version")
async def api_version(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, str]:
    return {"version": __version__}

