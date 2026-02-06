from __future__ import annotations

from typing import Any, Dict, Annotated

from fastapi import APIRouter, Depends

from pt_invite_watcher.app_context import AppContext
from pt_invite_watcher.routes.common import get_ctx, require_auth


router = APIRouter()


@router.get("/api/logs", dependencies=[Depends(require_auth)])
async def api_logs(
    ctx: Annotated[AppContext, Depends(get_ctx)],
    category: str = "all",
    domain: str = "",
    keyword: str = "",
    limit: int = 200,
) -> Dict[str, Any]:
    items = await ctx.store.list_events(category=category, domain=domain, keyword=keyword, limit=limit)
    return {"items": items}


@router.get("/api/logs/domains", dependencies=[Depends(require_auth)])
async def api_logs_domains(ctx: Annotated[AppContext, Depends(get_ctx)]) -> Dict[str, Any]:
    domains = await ctx.store.get_log_domains()
    return {"domains": domains}

