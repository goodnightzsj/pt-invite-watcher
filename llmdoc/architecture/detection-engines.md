# Detection Engines Architecture

## Overview

检测引擎负责解析 PT 站点 HTML 页面，提取：
- **开放注册状态** (registration)
- **邀请名额** (invites)
- **连通性** (reachability，由 scanner 层处理)

## Engine Classes

### NexusPhpDetector

**Location:** `engines/nexusphp_detector.py:100`

通用 NexusPHP 架构站点检测器，支持大多数 PT 站点。

```
@dataclass(frozen=True)
class NexusPhpDetector:
    async def check_registration(client, site, user_agent, ...) -> AspectResult
    async def check_invites(client, site, user_agent, cookie_header, ...) -> AspectResult
```

### MTeamDetector

**Location:** `engines/mteam_detector.py`

M-Team 特定检测器，处理 M-Team 的特殊页面结构。

## AspectResult Data Model

**Location:** `models.py`

```python
@dataclass(frozen=True)
class AspectResult:
    state: str           # "open" | "closed" | "unknown"
    available: int = 0   # 可用数量（邀请）
    permanent: int = 0   # 永久邀请
    temporary: int = 0   # 临时邀请
    evidence: Evidence   # 证据

@dataclass(frozen=True)
class Evidence:
    url: str             # 检测 URL
    http_status: int     # HTTP 状态码
    reason: str          # 判定原因
    matched: str = ""    # 匹配的文本
    detail: str = ""     # 额外详情
```

## Registration Detection Flow

**Location:** `engines/nexusphp_detector.py:101-193`

```
check_registration():
1. 构造 signup.php URL（或自定义 registration_path）
2. HTTP GET 请求
3. 解析响应：
   ├─ 404 → 继续尝试其他路径
   ├─ 5xx → unknown (服务器错误)
   ├─ _is_registration_closed() → closed
   ├─ !_has_signup_form() → closed (无注册表单)
   ├─ _has_invite_field() → closed (需要邀请码)
   └─ 有注册表单 → open
```

## Invites Detection Flow

**Location:** `engines/nexusphp_detector.py:195-513`

```
check_invites():
1. 检查 cookie_header 是否存在
2. 请求首页 → 提取导航栏邀请数量
   └─ _parse_home_invite_quota() → quota_perm, quota_temp
3. 提取用户 ID
   ├─ _probe_user_id_from_usercp()
   └─ _extract_user_id_from_html()
4. 构造 invite.php URL
5. 请求邀请页面
6. 解析响应：
   ├─ _looks_like_login() → not_logged_in
   ├─ _is_invite_disabled() → invites_disabled
   ├─ _invite_permission_denied_any() → invite_permission_denied
   ├─ _invite_send_action_status() → 检查发送按钮
   └─ _parse_invite_count() → 解析邀请数量
7. 返回 AspectResult
```

## HTML Parsing Utilities

**Location:** `engines/nexusphp_parse.py`

| Function | Purpose |
|----------|---------|
| `_extract_text()` | 提取 HTML 纯文本 |
| `_has_signup_form()` | 检测注册表单 |
| `_has_invite_field()` | 检测邀请码输入框 |
| `_is_registration_closed()` | 检测"注册关闭"文本 |
| `_is_invite_disabled()` | 检测"邀请禁用"文本 |
| `_parse_invite_count()` | 解析邀请数量 |
| `_parse_home_invite_quota()` | 解析首页邀请名额 |
| `_extract_user_id_from_html()` | 提取用户 ID |
| `_invite_permission_denied_any()` | 检测权限不足 |
| `_invite_send_action_status()` | 检测发送邀请按钮状态 |

## Site Adapters

**Location:** `engines/nexusphp_sites.py`

针对特定站点的适配器，处理非标准页面结构：

```python
class NexusPhpSiteAdapter:
    def extract_uid(html: str) -> str | None
    def invite_permission_reason(text: str, html: str) -> str | None
```

通过 `get_nexusphp_site_adapter(site)` 获取适配器。

## Engine Selection

**Location:** `scanner_site_check.py`

根据站点模板选择引擎：

```python
if site.template == "mteam":
    result = await mteam_detector.check_...()
else:
    result = await detector.check_...()  # NexusPhpDetector
```

## Retry Logic

**Location:** `engines/nexusphp_detector.py:45-57`

```python
async def _get_with_retry(client, url, headers, *, attempts, delay_seconds):
    return await request_with_retry(
        lambda: client.get(url, headers=headers),
        attempts=attempts,
        delay_seconds=delay_seconds,
    )
```

HTTP 请求带重试，使用 `net.py` 的 `request_with_retry`。

## Adding New Engine

1. 创建 `engines/new_engine.py`
2. 实现 `check_registration()` 和 `check_invites()` 方法
3. 返回 `AspectResult` 数据结构
4. 在 `scanner_impl.py` 中注册新引擎
5. 在 `scanner_site_check.py` 中添加引擎选择逻辑
6. 添加站点模板到 `site_templates.py`
