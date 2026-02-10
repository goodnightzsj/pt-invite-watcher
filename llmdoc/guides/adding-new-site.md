# Adding a New Site Guide

## Overview

PT Invite Watcher 支持两种方式添加站点：
1. **MoviePilot 自动拉取**：无需手动配置
2. **手动添加**：支持 MoviePilot 不支持的站点

## 方式一：MoviePilot 站点（自动）

如果站点已在 MoviePilot 中配置：

1. 确保 MoviePilot 集成已配置（Web UI → 配置 → MoviePilot）
2. 站点会在下次扫描时自动出现
3. 可选：添加本地覆盖以自定义部分字段

## 方式二：手动添加站点

### 通过 Web UI

1. 访问 Web UI → 站点管理
2. 点击「添加站点」
3. 填写必填字段：
   - **域名**：站点域名（如 `example.com`）
   - **URL**：站点完整 URL（如 `https://example.com`）
4. 填写可选字段：
   - **名称**：站点显示名称
   - **Cookie**：登录 Cookie
   - **模板**：站点类型（nexusphp/mteam/custom）

### 通过 API

```bash
curl -X PUT "http://localhost:8003/api/sites/example.com" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "manual",
    "name": "Example Site",
    "url": "https://example.com",
    "cookie": "session=xxx",
    "template": "nexusphp"
  }'
```

### 数据结构

站点配置存储在 `kv.sites`：

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
        }
    }
}
```

## 站点模板

| Template | Description | 默认引擎 |
|----------|-------------|---------|
| `nexusphp` | 标准 NexusPHP 站点 | NexusPhpDetector |
| `mteam` | M-Team 站点 | MTeamDetector |
| `custom` | 自定义站点 | NexusPhpDetector |

### M-Team 特殊配置

M-Team 站点需要额外配置：

```json
{
    "mode": "manual",
    "url": "https://kp.m-team.cc",
    "template": "mteam",
    "authorization": "Bearer xxx",  // API Token
    "did": "device_id"              // 设备 ID
}
```

## Cookie 获取

### 方式一：CookieCloud 自动同步

1. 配置 CookieCloud（Web UI → 配置 → CookieCloud）
2. Cookie 会自动从浏览器同步

### 方式二：手动获取

1. 登录站点
2. 打开浏览器开发者工具 → Application → Cookies
3. 复制所有 Cookie 值
4. 格式：`key1=value1; key2=value2`

### Cookie 优先级

```
1. site_entry.cookie_override  # 本地覆盖
2. CookieCloud cookies         # 自动同步
3. MoviePilot site.cookie      # MP 提供
```

## 验证站点配置

添加站点后：

1. 在站点列表中找到新站点
2. 点击「扫描」按钮触发单站点扫描
3. 查看日志确认检测结果
4. 检查状态显示是否正确

## 常见问题

### 站点显示 "unknown" 状态

可能原因：
- Cookie 无效或过期
- 站点 URL 错误
- 站点模板选择错误
- 网络连接问题

解决方案：
1. 检查日志获取详细错误
2. 验证 Cookie 是否有效
3. 确认站点 URL 可访问
4. 尝试更换站点模板

### 邀请检测不准确

某些站点需要自定义邀请页路径：

```json
{
    "invite_path": "invite.php?id=12345"
}
```

### 连通性检测失败

确保：
- 站点 URL 正确
- 网络可达（考虑代理配置）
- 站点没有 IP 封禁

## 删除站点

### 手动站点

```bash
curl -X DELETE "http://localhost:8003/api/sites/example.com"
```

### MoviePilot 站点

MoviePilot 站点无法直接删除，需要在 MoviePilot 中移除。
