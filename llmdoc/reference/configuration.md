# Configuration Reference

## Environment Variables

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PTIW_DB_PATH` | SQLite 数据库路径 | `./data/ptiw.db` |
| `PTIW_SCAN_INTERVAL_SECONDS` | 扫描间隔 (秒) | `600` |
| `PTIW_DISABLE_SCHEDULER` | 禁用后台定时扫描 | `0` |
| `PTIW_DISABLE_LEADER_LOCK` | 禁用定时扫描 Leader 锁 | `0` |

### Web Authentication

| Variable | Description | Default |
|----------|-------------|---------|
| `PTIW_WEB_AUTH_USERNAME` | Web UI 认证用户名 | (无) |
| `PTIW_WEB_AUTH_PASSWORD` | Web UI 认证密码 | (无) |
| `PTIW_DISABLE_AUTH` | 强制禁用认证 | `0` |

### MoviePilot Integration

| Variable | Description | Default |
|----------|-------------|---------|
| `MP_BASE_URL` | MoviePilot 地址 | - |
| `MP_USERNAME` | MoviePilot 用户名 | - |
| `MP_PASSWORD` | MoviePilot 密码 | - |
| `MP_OTP_PASSWORD` | MoviePilot OTP 密码 | - |

### CookieCloud Integration

| Variable | Description | Default |
|----------|-------------|---------|
| `COOKIECLOUD_BASE_URL` | CookieCloud 地址 | - |
| `COOKIECLOUD_UUID` | CookieCloud UUID | - |
| `COOKIECLOUD_PASSWORD` | CookieCloud 密码 | - |

## Runtime Configuration

运行时配置存储在 SQLite `kv` 表中，可通过 Web UI 或 API 修改。

### 配置结构

**Location:** `runtime_config.py`

```python
@dataclass
class RuntimeConfig:
    moviepilot: MoviePilotConfig
    cookie: CookieConfig
    scan: ScanConfig
    connectivity: ConnectivityConfig
```

### MoviePilot Config

```python
@dataclass
class MoviePilotConfig:
    base_url: str
    username: str
    password: str
    otp_password: str
    sites_cache_ttl_seconds: int = 300
```

### Cookie Config

```python
@dataclass
class CookieConfig:
    source: str  # "auto" | "cookiecloud" | "manual"
    cookiecloud: CookieCloudConfig

@dataclass
class CookieCloudConfig:
    base_url: str
    uuid: str
    password: str
    refresh_interval_seconds: int = 300
```

### Scan Config

```python
@dataclass
class ScanConfig:
    timeout_seconds: int = 20
    concurrency: int = 5
    user_agent: str = ""
    trust_env: bool = False
```

### Connectivity Config

```python
@dataclass
class ConnectivityConfig:
    retry_interval_seconds: int = 3600  # 依赖失败重试间隔
    request_retry_delay_seconds: int = 30  # HTTP 请求重试延迟
```

## KV Keys

**Location:** `kv_keys.py`

| Key | Description |
|-----|-------------|
| `app_config` | 运行时配置 |
| `notifications` | 通知设置 |
| `sites` | 手动站点配置 |
| `scan_status` | 最近扫描状态 |
| `scan_hint` | 扫描提示 |
| `deps_status` | 依赖健康状态 |
| `sites_summary` | 站点摘要快照 |
| `mp_sites_cache` | MoviePilot 站点缓存 |

## Notification Settings

存储在 `kv.notifications`：

```json
{
    "telegram": {
        "enabled": false,
        "token": "",
        "chat_id": ""
    },
    "wecom": {
        "enabled": false,
        "corpid": "",
        "app_secret": "",
        "agent_id": "",
        "to_user": "@all",
        "to_party": "",
        "to_tag": ""
    }
}
```

## Sites Configuration

存储在 `kv.sites`：

```json
{
    "version": 1,
    "entries": {
        "example.com": {
            "mode": "manual",
            "name": "Example Site",
            "url": "https://example.com",
            "cookie": "session=xxx",
            "template": "nexusphp",
            "registration_path": "signup.php",
            "invite_path": "invite.php"
        },
        "mteam.com": {
            "mode": "override",
            "cookie": "override_cookie=xxx"
        }
    }
}
```

### Site Entry Fields

| Field | Required | Description |
|-------|----------|-------------|
| `mode` | Yes | `manual` 或 `override` |
| `name` | No | 站点名称 |
| `url` | manual 必填 | 站点 URL |
| `cookie` | No | Cookie 覆盖 |
| `authorization` | No | Authorization header |
| `did` | No | Device ID (M-Team) |
| `template` | No | 站点模板 |
| `registration_path` | No | 注册页路径 |
| `invite_path` | No | 邀请页路径 |

## Configuration Loading

**Location:** `runtime_config_loader.py`

配置加载优先级：
1. 环境变量
2. 数据库运行时配置
3. 默认值

```python
async def get_runtime_config(settings, store, runtime_config=None):
    # 从 DB 加载运行时配置
    # 合并环境变量覆盖
    # 返回 RuntimeConfig 对象
```

## Configuration Caching

**Location:** `runtime_config_cache.py`

运行时配置缓存，减少 DB 访问：

```python
class RuntimeConfigCache:
    _cache: RuntimeConfig | None
    _cache_at: float
    _ttl_seconds: float = 5.0

    async def get() -> RuntimeConfig
    def invalidate()
```
