# External Services Integration

## Overview

PT Invite Watcher 集成两个外部服务：
- **MoviePilot**：获取站点列表和 Cookie
- **CookieCloud**：自动同步浏览器 Cookie

## MoviePilot Integration

### MoviePilotSitesService

**Location:** `providers/moviepilot_sites.py`

负责从 MoviePilot 获取站点列表。

```python
class MoviePilotSitesService:
    async def load_sites(
        now, base_url, cache_ttl_seconds,
        username, password, otp_password,
        timeout_seconds, ...
    ) -> MoviePilotSitesResult
```

### MoviePilotSitesResult

```python
@dataclass(frozen=True)
class MoviePilotSitesResult:
    sites: list[Site]       # 站点列表
    source: str             # "live" | "cache" | "state" | "summary" | "none"
    ok: bool                # 是否成功
    error: str              # 错误信息
    cached_at: datetime     # 缓存时间
```

### MoviePilot API Client

**Location:** `providers/moviepilot_api.py`

```python
class MoviePilotClient:
    async def login() -> tuple[str, str]  # (token, error)
    async def get_sites(token) -> tuple[list[Site], str]  # (sites, error)
```

### Data Flow

```
MoviePilot API
    │
    ▼ /api/v1/site/
MoviePilotClient.get_sites()
    │
    ▼ 转换为 Site 对象
MoviePilotSitesService.load_sites()
    │ (带缓存/fallback 逻辑)
    ▼
EffectiveSitesService.load_for_scan()
    │
    ▼ merge_sites()
Scanner
```

### Caching & Fallback

MoviePilot 数据有多级 fallback：

1. **Live**：实时请求 MoviePilot API
2. **Cache**：内存缓存（TTL 可配置）
3. **State**：从 `site_state` 表恢复
4. **Summary**：从 `sites_summary` KV 恢复
5. **None**：无可用数据

## CookieCloud Integration

### CookieCloudService

**Location:** `providers/cookiecloud_service.py`

负责从 CookieCloud 获取 Cookie。

```python
class CookieCloudService:
    async def access(
        now, deps_status, require_enabled, force_fetch
    ) -> CookieCloudAccessResult

    async def build_cookie_manager_for_scan(
        now, deps_status
    ) -> tuple[CookieManager, dict]
```

### CookieCloudAccessResult

```python
@dataclass(frozen=True)
class CookieCloudAccessResult:
    attempted: bool          # 是否尝试请求
    ok: Optional[bool]       # 请求是否成功
    error: str               # 错误信息
    client: CookieCloudClient  # 客户端实例
    cookies: list[dict]      # Cookie 列表
    prefetched_at: datetime  # 预取时间
    deps_status: dict        # 依赖状态
```

### CookieCloudClient

**Location:** `providers/cookiecloud.py`

```python
class CookieCloudClient:
    async def fetch_cookie_items() -> list[dict]
```

### CookieManager

**Location:** `providers/cookiecloud.py`

管理 Cookie 的获取和匹配：

```python
class CookieManager:
    cookie_source: str       # "auto" | "cookiecloud" | "manual"
    cookiecloud: CookieCloudClient
    prefetched_cookies: list[dict]

    async def get_cookie_for_domain(domain) -> str
```

### Single-Flight Fetch

**Location:** `providers/cookiecloud_service.py:102-187`

CookieCloud 请求使用 single-flight 模式，避免重复请求：

```python
async def _fetch_cookie_items_single_flight(client, fp):
    async with self._lock:
        if self._fetch_task is None or self._fetch_fp != fp:
            self._fetch_task = asyncio.create_task(client.fetch_cookie_items())
        task = self._fetch_task
    cookies = await asyncio.shield(task)
    return cookies, fetched_at
```

## Dependency Status (deps_status)

**Location:** `providers/deps_status.py`

跟踪外部依赖的健康状态，实现退避重试：

```python
def can_attempt(dep, now, fingerprint) -> bool
def update_dep_ok(status, name, now, fp) -> dict
def update_dep_fail(status, name, now, fp, error, retry_interval) -> dict
```

### 状态结构

```python
{
    "moviepilot": {
        "ok": True,
        "error": "",
        "last_ok_at": "2024-01-01T00:00:00Z",
        "last_fail_at": None,
        "fingerprint": "http://moviepilot:3001",
        "retry_after": None
    },
    "cookiecloud": {
        "ok": False,
        "error": "connection refused",
        "last_fail_at": "2024-01-01T00:00:00Z",
        "retry_after": "2024-01-01T01:00:00Z"  # 退避 1 小时
    }
}
```

## Effective Sites Service

**Location:** `effective_sites.py`

合并 MoviePilot 站点和手动站点：

```python
def merge_sites(mp_sites: list[Site], site_entries: dict) -> list[Site]:
    # 1. 处理 MoviePilot 站点
    # 2. 应用本地覆盖 (mode=override)
    # 3. 添加手动站点 (mode=manual)
    # 4. 去重（按 domain）
```

### Site Entry Modes

| Mode | Description |
|------|-------------|
| `override` | 覆盖 MoviePilot 站点的部分字段 |
| `manual` | 完全手动配置的站点 |

### 可覆盖字段

- `name` - 站点名称
- `cookie` - Cookie 覆盖
- `authorization` - Authorization header
- `did` - Device ID
- `template` - 站点模板
- `registration_path` - 注册页路径
- `invite_path` - 邀请页路径

## Configuration

### MoviePilot

| Config | Env Var | Description |
|--------|---------|-------------|
| base_url | `MP_BASE_URL` | MoviePilot 地址 |
| username | `MP_USERNAME` | 用户名 |
| password | `MP_PASSWORD` | 密码 |
| otp_password | `MP_OTP_PASSWORD` | OTP 密码 |
| sites_cache_ttl | - | 缓存 TTL (秒) |

### CookieCloud

| Config | Env Var | Description |
|--------|---------|-------------|
| base_url | `COOKIECLOUD_BASE_URL` | CookieCloud 地址 |
| uuid | `COOKIECLOUD_UUID` | UUID |
| password | `COOKIECLOUD_PASSWORD` | 密码 |
| refresh_interval | - | 刷新间隔 (秒) |
