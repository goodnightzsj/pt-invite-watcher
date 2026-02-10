# PT Invite Watcher - LLM Documentation Index

> PT 站点"开放注册 / 邀请名额 / 连通性"监控服务

## Quick Reference

| Aspect | Value |
|--------|-------|
| Language | Python 3.10+ (Backend), TypeScript (Frontend) |
| Framework | FastAPI + aiosqlite + Vue 3/Vite |
| Entry Point | `pt_invite_watcher/__main__.py` |
| Config | Environment vars + runtime DB config |
| Database | SQLite (WAL mode) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI (Vue/Vite)                     │
│                    webui/src/ → webui_dist/                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/WebSocket
┌─────────────────────────▼───────────────────────────────────┐
│                     FastAPI Application                      │
│  app.py → routes/ (sites, config_api, backup, ws)           │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
│   Scanner   │ │  Notify   │ │ Scheduler │
│ scanner_*.py│ │ notify/   │ │scheduler.py│
└──────┬──────┘ └───────────┘ └─────┬─────┘
       │                            │
┌──────▼────────────────────────────▼─────┐
│              Detection Engines           │
│  engines/nexusphp_detector.py (21KB)    │
│  engines/mteam_detector.py (10KB)       │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│           External Services              │
│  providers/moviepilot_*.py (MP站点)     │
│  providers/cookiecloud_*.py (Cookie)    │
└──────┬──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────┐
│            Storage Layer                 │
│  storage/sqlite_store.py (17KB)         │
│  Tables: site_state, kv, event_log      │
└─────────────────────────────────────────┘
```

## Document Map

### Overview
- [Project Overview](overview/project-overview.md) - 项目目的、功能、技术栈

### Architecture
- [Scanner Architecture](architecture/scanner-architecture.md) - 扫描系统核心架构
- [Detection Engines](architecture/detection-engines.md) - NexusPHP/M-Team 检测引擎
- [Storage Layer](architecture/storage-layer.md) - SQLite 存储与数据模型
- [External Services](architecture/external-services.md) - MoviePilot/CookieCloud 集成
- [Scheduler](architecture/scheduler.md) - 定时调度与 Leader 选举
- [WebUI Frontend](architecture/webui-frontend.md) - Vue/TypeScript 前端架构

### Guides
- [Adding a New Site](guides/adding-new-site.md) - 手动添加站点流程
- [Notification Setup](guides/notification-setup.md) - 配置 Telegram/企业微信通知

### Reference
- [Configuration Reference](reference/configuration.md) - 环境变量与运行时配置
- [Database Schema](reference/database-schema.md) - 数据库表结构
- [API Endpoints](reference/api-endpoints.md) - API 端点清单
- [Coding Conventions](reference/coding-conventions.md) - 编码规范
- [Git Conventions](reference/git-conventions.md) - Git 工作流与提交规范

## Key Entry Points

| Purpose | File | Key Function/Class |
|---------|------|-------------------|
| CLI Entry | `__main__.py:14` | `main()` |
| FastAPI App | `app.py:79` | `app = FastAPI(...)` |
| Scanner | `scanner_impl.py:65` | `class Scanner` |
| NexusPHP Detection | `engines/nexusphp_detector.py:100` | `class NexusPhpDetector` |
| Storage | `storage/sqlite_store.py:58` | `class SqliteStore` |
| Site Merge | `effective_sites.py:17` | `merge_sites()` |
| Notifications | `notify/manager.py:31` | `class NotifierManager` |

## Modification Hotspots

| Task | Primary Files |
|------|---------------|
| Add detection engine | `engines/` + `scanner_site_check.py` |
| Add notification channel | `notify/` + `notify/manager.py` |
| Modify scan logic | `scanner_impl.py`, `scanner_run.py` |
| Add API endpoint | `routes/` |
| Change DB schema | `storage/sqlite_store.py:162-203` |
| Modify site merge logic | `effective_sites.py:17-119` |
