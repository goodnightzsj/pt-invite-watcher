# Database Schema Reference

## Overview

PT Invite Watcher 使用 SQLite 数据库，启用 WAL 模式以提高并发性能。

**Location:** `storage/sqlite_store.py:162-203`

## Tables

### site_state

存储站点状态快照。

```sql
CREATE TABLE site_state (
    domain TEXT PRIMARY KEY,
    name TEXT,
    url TEXT,
    engine TEXT,
    registration_state TEXT NOT NULL,
    invites_state TEXT NOT NULL,
    invites_available INTEGER,
    last_checked_at TEXT NOT NULL,
    last_changed_at TEXT,
    last_evidence TEXT NOT NULL
);
```

| Column | Type | Description |
|--------|------|-------------|
| `domain` | TEXT PK | 站点域名（主键） |
| `name` | TEXT | 站点名称 |
| `url` | TEXT | 站点 URL |
| `engine` | TEXT | 检测引擎类型 |
| `registration_state` | TEXT | 注册状态: open/closed/unknown |
| `invites_state` | TEXT | 邀请状态: open/closed/unknown |
| `invites_available` | INTEGER | 可用邀请数量 |
| `last_checked_at` | TEXT | 最后检查时间 (ISO8601) |
| `last_changed_at` | TEXT | 最后状态变更时间 |
| `last_evidence` | TEXT | 最后检测证据 (JSON) |

### kv

通用键值存储。

```sql
CREATE TABLE kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT PK | 键名 |
| `value` | TEXT | 值 (JSON 序列化) |
| `updated_at` | TEXT | 更新时间 (ISO8601) |

**常用 Keys:**

| Key | Content |
|-----|---------|
| `app_config` | 运行时配置 |
| `notifications` | 通知设置 |
| `sites` | 手动站点配置 |
| `scan_status` | 最近扫描状态 |
| `scan_hint` | 扫描提示 |
| `deps_status` | 依赖健康状态 |
| `sites_summary` | 站点摘要快照 |
| `mp_sites_cache` | MoviePilot 站点缓存 |
| `mp_token` | MoviePilot Token 缓存 |

### event_log

事件日志。

```sql
CREATE TABLE event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,
    action TEXT NOT NULL,
    domain TEXT,
    message TEXT NOT NULL,
    detail TEXT
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | 自增 ID |
| `ts` | TEXT | 时间戳 (ISO8601) |
| `category` | TEXT | 分类: scan/notify/system |
| `level` | TEXT | 级别: info/error/warning |
| `action` | TEXT | 动作标识 |
| `domain` | TEXT | 关联站点域名（可选） |
| `message` | TEXT | 人类可读消息 |
| `detail` | TEXT | 详情 (JSON) |

**常用 Actions:**

| Action | Category | Description |
|--------|----------|-------------|
| `scan_start` | scan | 扫描开始 |
| `scan_done` | scan | 扫描完成 |
| `scan_failed` | scan | 扫描失败 |
| `scan_one_start` | scan | 单站点扫描开始 |
| `scan_one_done` | scan | 单站点扫描完成 |
| `site_state_changed` | scan | 站点状态变更 |
| `telegram_send` | notify | Telegram 发送 |
| `wecom_send` | notify | 企业微信发送 |

### lease (隐式)

租约通过 `storage/lease_store.py` 管理，数据存储在 KV 表中。

**Key 格式:** `lease:{name}`

**Value 结构:**
```json
{
    "owner": "hostname:pid",
    "expire_at": "2024-01-01T00:00:00Z"
}
```

## Computed Fields

### reachability_state

`reachability_state` 不是数据库列，而是从 `last_evidence` JSON 中动态计算：

```python
# storage/site_state_read.py
reachability_state = evidence.get("reachability", {}).get("state", "unknown")
```

`StoredSiteState` dataclass 包含此字段用于应用层使用。

## Data Models

### Evidence (JSON)

存储在 `site_state.last_evidence`：

```json
{
    "registration": {
        "url": "https://example.com/signup.php",
        "http_status": 200,
        "reason": "registration_closed",
        "matched": "暂停注册",
        "detail": ""
    },
    "invites": {
        "url": "https://example.com/invite.php",
        "http_status": 200,
        "reason": "invite_count_parsed",
        "matched": "邀请[发送]: 5(0)",
        "detail": "uid_source=usercp"
    },
    "reachability": {
        "state": "up",
        "evidence": {
            "url": "https://example.com/",
            "http_status": 200,
            "reason": "reachable"
        }
    }
}
```

**ReachabilityState:** `"up"` | `"down"` | `"unknown"`

### ScanStatus (JSON)

存储在 `kv.scan_status`：

```json
{
    "ok": true,
    "site_count": 10,
    "scanned_count": 10,
    "skipped_in_flight": 0,
    "task_errors_count": 0,
    "error": "",
    "warning": "",
    "moviepilot_configured": true,
    "moviepilot_ok": true,
    "moviepilot_source": "live",
    "moviepilot_error": "",
    "last_run_at": "2024-01-01T00:00:00Z"
}
```

### DepsStatus (JSON)

存储在 `kv.deps_status`：

```json
{
    "moviepilot": {
        "ok": true,
        "error": "",
        "last_ok_at": "2024-01-01T00:00:00Z",
        "last_fail_at": null,
        "fingerprint": "http://moviepilot:3001",
        "retry_after": null
    },
    "cookiecloud": {
        "ok": false,
        "error": "connection refused",
        "last_fail_at": "2024-01-01T00:00:00Z",
        "retry_after": "2024-01-01T01:00:00Z"
    }
}
```

## Indexes

当前没有额外索引，主键索引足够小规模使用。

## WAL Mode

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
```

WAL 模式优势：
- 读写并发
- 更快的写入
- 更好的崩溃恢复

## Migrations

当前没有自动迁移机制。表结构在 `SqliteStore.init()` 中使用 `CREATE TABLE IF NOT EXISTS` 创建。
