# Scanner Architecture

## Overview

Scanner 是扫描系统的核心编排器，负责：
- 获取有效站点列表
- 并发检查每个站点状态
- 差异检测与通知触发
- 结果持久化

## Core Class: Scanner

**Location:** `scanner_impl.py:65`

```
class Scanner:
    - _settings: Settings
    - _store: SqliteStore
    - _notifier: NotifierManager
    - _lease: ScanLeaseManager      # 租约管理
    - _sem: asyncio.Semaphore       # 并发控制
    - _detector: NexusPhpDetector   # NexusPHP 检测器
    - _mteam: MTeamDetector         # M-Team 检测器
    - _in_flight: dict[str, Task]   # 正在扫描的站点
    - _ctx_builder: ScanContextBuilder  # 上下文构建器
```

## Scan Lifecycle

```
1. run_once() / run_once_scheduled()
   └─► _run_once_locked()
       ├─► _prepare_run_with_lease()     # 获取租约
       │   ├─► _lease.acquire()
       │   └─► _prepare_run()            # 构建扫描上下文
       │       ├─► _ctx_builder.prepare()  # 获取站点列表
       │       └─► sync_site_list_summary() # 同步站点摘要
       │
       └─► run_once_locked() [scanner_run.py:39]
           ├─► 过滤 in_flight 站点
           ├─► 创建并发任务 asyncio.gather()
           │   └─► _check_one() per site
           │       └─► _check_one_site() [scanner_site_check.py]
           │           ├─► probe_reachability()
           │           ├─► detector.check_registration()
           │           ├─► detector.check_invites()
           │           └─► persist_and_notify()
           └─► 更新 scan status
```

## Key Modules

| Module | File | Responsibility |
|--------|------|---------------|
| Scanner | `scanner_impl.py` | 主扫描编排器 |
| Run Logic | `scanner_run.py` | 并发执行、任务管理 |
| Site Check | `scanner_site_check.py` | 单站点检查流程 |
| Reachability | `scanner_reachability.py` | 连通性探测 |
| Invites | `scanner_invites.py` | 邀请检查辅助 |
| Diff | `scanner_diff.py` | 状态差异检测 |
| Change | `scanner_change.py` | 变更记录 |
| Persist | `scanner_persist.py` | 结果持久化 |
| Lease | `scanner_lease.py` | 租约管理器 |

## Lease System

多实例部署时，使用租约机制防止重复扫描：

**Location:** `scanner_lease.py`, `storage/lease_store.py`

```
ScanLeaseManager:
    acquire(ttl_seconds) -> bool   # 尝试获取租约
    release()                       # 释放租约
    extend(ttl_seconds)            # 延长租约
    refresh_loop(...)              # 后台刷新任务
```

租约存储在 SQLite `lease` 表中，通过 `owner` + `expire_at` 实现分布式锁。

## Concurrency Control

**Location:** `scanner_impl.py:87`

```python
self._sem = asyncio.Semaphore(max(1, settings.scan.concurrency))
```

通过 Semaphore 控制并发扫描数量，避免过载。

## Data Flow

```
PreparedScanContext (scan_context_builder.py)
├─ sites: list[Site]           # 有效站点列表
├─ cookie_mgr: CookieManager   # Cookie 管理器
├─ scan_concurrency: int       # 并发数
└─ scan_timeout_seconds: int   # 超时时间

PreparedRun (scanner_run.py:19)
├─ sites, cookie_mgr
├─ mp_configured, mp_fields    # MoviePilot 状态
├─ scan_lease_ttl_seconds      # 租约 TTL
└─ scan_timeout, scan_user_agent
```

## Key Entry Points

| Entry | Location | Description |
|-------|----------|-------------|
| `run_once()` | `scanner_impl.py:184` | 手动触发全量扫描 |
| `run_once_scheduled()` | `scanner_impl.py:188` | 定时触发扫描 |
| `run_one(domain)` | `scanner_impl.py:258` | 单站点扫描 |

## Integration Points

- **Effective Sites:** `effective_sites.py` - 站点列表来源
- **Detection Engines:** `engines/` - 站点检测逻辑
- **Storage:** `storage/sqlite_store.py` - 状态持久化
- **Notifications:** `notify/manager.py` - 变更通知
