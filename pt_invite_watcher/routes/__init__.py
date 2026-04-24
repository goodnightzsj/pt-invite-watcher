from __future__ import annotations

from fastapi import APIRouter

from pt_invite_watcher.routes.common import ASSETS_DIR, ws_broadcaster
from pt_invite_watcher.routes.backup import router as backup_router
from pt_invite_watcher.routes.config_api import router as config_router
from pt_invite_watcher.routes.dashboard import router as dashboard_router
from pt_invite_watcher.routes.devices import router as devices_router
from pt_invite_watcher.routes.health import router as health_router
from pt_invite_watcher.routes.logs import router as logs_router
from pt_invite_watcher.routes.notifications import router as notifications_router
from pt_invite_watcher.routes.scan import router as scan_router
from pt_invite_watcher.routes.sites import router as sites_router
from pt_invite_watcher.routes.spa import router as spa_router
from pt_invite_watcher.routes.ws import router as ws_router

router = APIRouter()

router.include_router(health_router)
router.include_router(dashboard_router)
router.include_router(scan_router)
router.include_router(logs_router)
router.include_router(config_router)
router.include_router(backup_router)
router.include_router(notifications_router)
router.include_router(devices_router)
router.include_router(sites_router)
router.include_router(ws_router)
router.include_router(spa_router)

__all__ = ["ASSETS_DIR", "router", "ws_broadcaster"]
