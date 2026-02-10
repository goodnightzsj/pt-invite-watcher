# API Endpoints Reference

## Base URL

```
http://localhost:8003/api
```

## Authentication

当配置 `PTIW_WEB_AUTH_USERNAME` 和 `PTIW_WEB_AUTH_PASSWORD` 时，API 使用 HTTP Basic Auth。

## Sites API

**Location:** `routes/sites.py`

### GET /api/sites

获取站点列表和状态。

**Response:**
```json
{
    "sites": [
        {
            "domain": "example.com",
            "name": "Example Site",
            "url": "https://example.com",
            "is_active": true,
            "registration_state": "closed",
            "invites_state": "open",
            "invites_available": 5,
            "reachability_state": "ok",
            "last_checked_at": "2024-01-01T00:00:00Z",
            "last_changed_at": "2024-01-01T00:00:00Z"
        }
    ],
    "moviepilot_source": "live",
    "moviepilot_ok": true,
    "moviepilot_error": ""
}
```

### POST /api/sites/{domain}/scan

触发单站点扫描。

**Response:**
```json
{
    "ok": true,
    "domain": "example.com",
    "site_count": 1,
    "error": ""
}
```

### POST /api/scan

触发全量扫描。

**Response:**
```json
{
    "ok": true,
    "site_count": 10,
    "scanned_count": 10,
    "error": ""
}
```

### GET /api/sites/{domain}

获取单站点详情。

### PUT /api/sites/{domain}

更新站点配置。

**Request Body:**
```json
{
    "mode": "manual",
    "name": "New Name",
    "url": "https://example.com",
    "cookie": "session=xxx",
    "template": "nexusphp"
}
```

### DELETE /api/sites/{domain}

删除手动站点。

## Config API

**Location:** `routes/config_api.py`

### GET /api/config

获取运行时配置。

**Response:**
```json
{
    "moviepilot": {
        "base_url": "http://moviepilot:3001",
        "username": "admin",
        "password": "****"
    },
    "cookie": {
        "source": "auto",
        "cookiecloud": {
            "base_url": "http://cookiecloud:8088",
            "uuid": "xxx",
            "refresh_interval_seconds": 300
        }
    },
    "scan": {
        "timeout_seconds": 20,
        "concurrency": 5
    }
}
```

### PUT /api/config

更新运行时配置。

### GET /api/config/notifications

获取通知设置。

### PUT /api/config/notifications

更新通知设置。

### POST /api/config/notifications/test/{channel}

测试通知渠道。

**Parameters:**
- `channel`: `telegram` 或 `wecom`

**Response:**
```json
{
    "ok": true,
    "message": "sent"
}
```

## Logs API

### GET /api/logs

获取事件日志。

**Query Parameters:**
- `category`: 过滤分类 (scan, notify, system)
- `domain`: 过滤站点域名
- `keyword`: 关键字搜索
- `limit`: 返回条数 (默认 200)

**Response:**
```json
{
    "logs": [
        {
            "id": 1,
            "ts": "2024-01-01T00:00:00Z",
            "category": "scan",
            "level": "info",
            "action": "scan_done",
            "domain": "example.com",
            "message": "扫描完成",
            "detail": {}
        }
    ]
}
```

### DELETE /api/logs

清空事件日志。

### GET /api/logs/domains

获取日志中的站点域名列表。

## Backup API

**Location:** `routes/backup.py`

### GET /api/backup/export

导出配置和状态。

**Response:** JSON 文件下载

### POST /api/backup/import

导入配置和状态。

**Request:** multipart/form-data with JSON file

## Status API

### GET /api/status

获取系统状态。

**Response:**
```json
{
    "version": "1.0.0",
    "scan_status": {
        "ok": true,
        "site_count": 10,
        "last_run_at": "2024-01-01T00:00:00Z"
    }
}
```

### GET /api/deps

探测依赖状态。

**Response:**
```json
{
    "moviepilot": {
        "ok": true,
        "error": ""
    },
    "cookiecloud": {
        "ok": true,
        "error": ""
    }
}
```

## WebSocket

**Location:** `routes/ws.py`

### WS /api/ws

实时事件推送。

**Messages:**

```json
// 日志追加
{"type": "logs_append", "data": {...}}

// 日志更新（需重新获取）
{"type": "logs_update", "data": {"reason": "flush"}}

// 仪表板更新
{"type": "dashboard_update", "data": {...}}
```

## Dashboard API

### GET /api/dashboard

获取仪表板数据。

**Response:**
```json
{
    "sites": [...],
    "scan_status": {...},
    "summary": {
        "total": 10,
        "reachable": 9,
        "registration_open": 2,
        "invites_open": 5
    }
}
```

## Error Response

所有 API 在错误时返回：

```json
{
    "detail": "Error message"
}
```

HTTP 状态码：
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Internal Server Error
