from __future__ import annotations

from typing import Any, Dict, Annotated

from fastapi import APIRouter, Depends, HTTPException

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.routes.common import broadcast_dashboard_update, get_ctx, require_auth
from pt_invite_watcher.scanner import AlreadyScanningError


router = APIRouter()


@router.post("/api/scan/run", dependencies=[Depends(require_auth)])
async def api_scan_run(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    try:
        status = await ctx.scanner.run_once()
        await broadcast_dashboard_update()
        return status
    except AlreadyScanningError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/api/scan/manual", dependencies=[Depends(require_auth)])
async def api_scan_manual(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    """
    Backward-compatible alias of `/api/scan/run`.
    """
    return await api_scan_run(ctx)


@router.post("/api/scan/run/{domain}", dependencies=[Depends(require_auth)])
async def api_scan_run_one(domain: str, ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    try:
        status = await ctx.scanner.run_one(domain)
        await broadcast_dashboard_update()
        return status
    except AlreadyScanningError as e:
        raise HTTPException(status_code=409, detail=str(e))
