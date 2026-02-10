# Storage Layer Architecture

## Overview

存储层基于 SQLite，使用 WAL 模式和 aiosqlite 异步驱动。

**Location:** `storage/sqlite_store.py:58` `class SqliteStore`

## Database Schema

### site_state 表

存储站点状态快照。

```sql
CREATE TABLE site_state (
    domain TEXT PRIMARY KEY,
    name TEXT,
    url TEXT,
    engine TEXT,
    registration_state TEXT NOT NULL,  -- "open" | "closed" | "unknown"
    invites_state TEXT NOT NULL,        -- "open" | "closed" | "unknown"
    invites_available INTEGER,          -- 可用邀请数
    last_checked_at TEXT NOT NULL,      -- ISO8601 时间戳
    last_changed_at TEXT,               -- 状态变更时间
    last_evidence TEXT NOT NULL         -- JSON: Evidence 对象
);
```

### kv 表

通用键值存储，用于配置、通知设置等。

```sql
CREATE TABLE kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,    -- JSON 序列化
    updated_at TEXT NOT NULL
);
```

**常用 Keys:**
- `app_config` - 应用配置
- `notifications` - 通知设置
- `sites` - 站点配置（手动添加）
- `scan_status` - 最近扫描状态
- `deps_status` - 依赖健康状态

### event_log 表

扫描日志和事件记录。

```sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,           -- ISO8601 时间戳
    category TEXT NOT NULL,     -- "scan" | "notify" | "system"
    level TEXT NOT NULL,        -- "info" | "error" | "warning"
    action TEXT NOT NULL,       -- 动作标识
    domain TEXT,                -- 关联站点域名
    message TEXT NOT NULL,      -- 人类可读消息
    detail TEXT                 -- JSON 详情
);
```

## SqliteStore Class

```python
class SqliteStore:
    _conn: aiosqlite.Connection      # 读连接
    _write_conn: aiosqlite.Connection  # 写连接（事务隔离）
    _lease_conn: aiosqlite.Connection  # 租约专用连接
    _event_hooks: list[Callable]     # 事件钩子（WebSocket 推送）
    _scan_log_buffer: list[dict]     # 扫描日志缓冲
```

## Key Methods

| Method | Location | Description |
|--------|----------|-------------|
| `init()` | `:135` | 初始化连接、创建表 |
| `close()` | `:270` | 关闭连接、刷新缓冲 |
| `add_event()` | `:211` | 添加事件日志 |
| `list_events()` | `:247` | 查询事件日志 |
| `get_site_state()` | `:434` | 获取站点状态 |
| `save_site_result()` | `:437` | 保存站点结果 |
| `list_site_states()` | `:440` | 列出所有站点状态 |
| `get_json()` | `:455` | 读取 KV 值 |
| `set_json()` | `:458` | 写入 KV 值 |
| `try_acquire_lease()` | `:461` | 获取租约 |
| `release_lease()` | `:464` | 释放租约 |

## Connection Strategy

使用三个独立连接实现隔离：

```
_conn       → 读操作（并发安全）
_write_conn → 写事务（带锁）
_lease_conn → 租约操作（跨进程安全）
```

**WAL 模式配置:**
```python
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

## Event Hook System

**Location:** `storage/sqlite_store.py:89-117`

```python
def on_event(hook: Callable[[dict], Any]):
    """注册事件钩子，用于 WebSocket 实时推送"""

def dispatch_event_hooks(evt: dict):
    """分发事件到所有钩子"""
```

## Scan Log Buffering

高频扫描日志使用缓冲写入，减少 I/O：

**Location:** `storage/scan_log_buffer.py`

```
_scan_log_buffer: list[dict]
_scan_log_flush_interval_seconds = 0.2
_scan_log_batch_max = 100
_scan_log_buffer_max = 2000
```

流程：
1. `add_event()` 检测 `category=scan, level=info`
2. 入队到 `_scan_log_buffer`
3. 后台任务定期 flush 到数据库

## Sub-modules

| Module | File | Responsibility |
|--------|------|---------------|
| KV Store | `storage/kv_store.py` | get_json/set_json |
| Event Log | `storage/event_log_store.py` | add/list/clear events |
| Site State | `storage/site_state_store.py` | 站点状态 CRUD |
| Scan Log Buffer | `storage/scan_log_buffer.py` | 日志缓冲 |
| Lease Store | `storage/lease_store.py` | 租约管理 |

## Write Transaction

**Location:** `storage/sqlite_store.py:355-369`

```python
@asynccontextmanager
async def write_transaction():
    async with self._write_lock:
        conn = self._require_write_conn()
        await conn.execute("BEGIN")
        try:
            yield conn
            await conn.commit()
        except:
            await conn.rollback()
            raise
```

## Data Models

**StoredSiteState:**
```python
@dataclass(frozen=True)
class StoredSiteState:
    domain: str
    reachability_state: str
    registration_state: str
    invites_state: str
    invites_available: Optional[int]
    last_checked_at: str
    last_changed_at: Optional[str]
```
