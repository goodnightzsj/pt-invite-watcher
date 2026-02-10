# Project Overview

## Purpose

PT Invite Watcher 是一个长期运行的 PT（Private Tracker）站点监控服务，监控：
- **开放注册状态**：检测 `signup.php` 或注册页关键字
- **邀请名额**：解析首页/用户中心/邀请页，判断等级权限与名额数量
- **连通性**：实时检测站点能否访问

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.10+, FastAPI, aiosqlite |
| Frontend | Vue 3, TypeScript, Vite, Tailwind CSS |
| Database | SQLite (WAL mode) |
| HTTP Client | httpx (async) |
| HTML Parsing | BeautifulSoup4 |
| Notifications | Telegram Bot API, WeCom (企业微信) |

## External Integrations

| Service | Purpose | Module |
|---------|---------|--------|
| MoviePilot | 站点列表来源、Cookie 获取 | `providers/moviepilot_*.py` |
| CookieCloud | Cookie 自动同步 | `providers/cookiecloud_*.py` |

## Core Concepts

### 1. Effective Sites (有效站点)
站点列表的最终来源，合并了：
- MoviePilot 认证站点（自动拉取）
- 手动配置站点（本地 DB 存储）
- 站点模板（nexusphp, mteam, custom）

参考：`effective_sites.py:17` `merge_sites()`

### 2. Detection Engines (检测引擎)
负责解析站点 HTML 页面，提取状态信息：
- `NexusPhpDetector`：通用 NexusPHP 架构站点
- `MTeamDetector`：M-Team 特定适配

参考：`engines/nexusphp_detector.py:100`, `engines/mteam_detector.py`

### 3. Scanner (扫描器)
核心扫描编排，包括：
- 租约管理（多实例协调）
- 并发控制（Semaphore）
- 差异检测与通知触发

参考：`scanner_impl.py:65` `class Scanner`

### 4. Storage Layer (存储层)
SQLite 存储，包含：
- `site_state` 表：站点状态快照
- `kv` 表：配置、通知设置
- `event_log` 表：扫描日志

参考：`storage/sqlite_store.py:58` `class SqliteStore`

## Project Structure

```
pt_invite_watcher/
├── __main__.py          # CLI 入口
├── app.py               # FastAPI 应用
├── app_context.py       # 依赖注入上下文
├── scanner_impl.py      # 扫描器核心 (17KB)
├── scanner_run.py       # 扫描执行 (7.5KB)
├── effective_sites.py   # 站点合并 (8.7KB)
├── engines/             # 检测引擎
│   ├── nexusphp_detector.py  (21KB)
│   ├── nexusphp_parse.py     (12KB)
│   └── mteam_detector.py     (10.5KB)
├── storage/             # 存储层
│   ├── sqlite_store.py       (17KB)
│   ├── event_log_store.py    (9.5KB)
│   └── scan_log_buffer.py    (8.7KB)
├── providers/           # 外部服务
│   ├── cookiecloud_service.py (11.7KB)
│   ├── moviepilot_sites.py    (11.3KB)
│   └── moviepilot_api.py      (9.4KB)
├── routes/              # API 路由
│   ├── sites.py              (11.9KB)
│   ├── config_api.py         (7.8KB)
│   └── backup.py             (6.9KB)
├── notify/              # 通知系统
│   ├── manager.py            (7.5KB)
│   ├── telegram.py
│   └── wecom.py              (6.3KB)
└── web/                 # Web 服务辅助
```

## Deployment

### Docker (推荐)
```yaml
services:
  pt-invite-watcher:
    image: helloworldz1024/pt-invite-watcher:latest
    ports: ["8003:8080"]
    volumes: ["./data:/data"]
    environment:
      PTIW_DB_PATH: "/data/ptiw.db"
      MP_BASE_URL: "http://moviepilot:3001"
      COOKIECLOUD_BASE_URL: "http://cookiecloud:8088"
```

### 本地开发
```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m pt_invite_watcher run

# Frontend
cd webui && npm install && npm run build
```
