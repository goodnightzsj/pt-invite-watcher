# PT Invite Watcher

长期运行的 PT 站点“开放注册 / 可用邀请数 / 连通性”监控服务（默认 NexusPHP/M-Team），站点列表来源于 MoviePilot 或手动配置，Cookie 优先从 CookieCloud 获取并支持回退。

## ✨ 功能特性

- **多源站点管理**：
  - **MoviePilot**：自动拉取 MP 认证站点，无需重复配置。
  - **手动添加**：支持手动添加 MP 不支持的站点。
  - **CookieCloud**：自动同步 Cookie，失败回退到本地配置。
- **全方位监控**：
  - **开放注册**：检测 `signup.php` 或注册页关键字。
  - **邀请名额**：解析首页/用户中心/邀请页，智能判断等级权限与名额数量。
  - **连通性**：实时检测站点能否访问。
- **现代 Web UI**：
  - **响应式设计**：完美支持桌面端与移动端（Mobile Card View）。
  - **实时日志**：WebSocket 实时推送扫描日志，支持按分类/站点/关键字过滤。
  - **暗色模式**：自动跟随系统或手动切换。
  - **数据大屏**：直观展示各站点状态概览。
- **通知触达**：
  - Telegram Bot
  - 企业微信（应用消息）

## 🚀 快速开始

### 1. Docker 部署 (推荐)

**方式 A：Docker Compose (推荐)**

`docker-compose.yml`:
```yaml
services:
  pt-invite-watcher:
    image: helloworldz1024/pt-invite-watcher:latest
    container_name: pt-invite-watcher
    restart: unless-stopped
    ports:
      - "8003:8080"
    volumes:
      - ./data:/data
    environment:
      # 数据库路径（必填）
      PTIW_DB_PATH: "/data/ptiw.db"
      # 可选：初始化配置（也可启动后在 WebUI 配置）
      MP_BASE_URL: "http://moviepilot:3001"
      COOKIECLOUD_BASE_URL: "http://cookiecloud:8088"
```

启动：
```bash
docker compose up -d
```
访问：`http://localhost:8003`

**方式 B：Docker Run**

```bash
docker run -d \
  --name pt-invite-watcher \
  --restart always \
  -p 8003:8080 \
  -v "$(pwd)/data:/data" \
  -e PTIW_DB_PATH="/data/ptiw.db" \
  -e MP_BASE_URL="http://moviepilot:3001" \
  -e COOKIECLOUD_BASE_URL="http://cookiecloud:8088" \
  helloworldz1024/pt-invite-watcher:latest
```

### 2. 本地开发运行

依赖：Python 3.10+, Node.js 18+

1. **后端启动**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python3 -m pt_invite_watcher run
   ```

2. **前端构建**:
   ```bash
   cd webui
   npm install
   npm run build
   ```

## 🛠️ 配置说明

所有配置均可在 Web UI (`/config`) 中可视化管理，也可以通过环境变量预设。

### 核心环境变量

| 变量名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `PTIW_DB_PATH` | SQLite 数据库路径 | `./data/ptiw.db` |
| `PTIW_SCAN_INTERVAL_SECONDS` | 扫描间隔 (秒) | `600` |
| `PTIW_WEB_AUTH_USERNAME` | Web UI 认证用户名 | (无) |
| `PTIW_WEB_AUTH_PASSWORD` | Web UI 认证密码 | (无) |
| `MP_BASE_URL` | MoviePilot 地址 | - |
| `COOKIECLOUD_BASE_URL` | CookieCloud 地址 | - |

## 📱 移动端支持

- 项目对移动端进行了深度适配。
- **日志页面**自动切换为卡片视图，方便在手机上查看详细日志。
- **导航栏**自动切换为底部 Dock 栏。

## ⚠️ 免责声明

本项目仅用于“状态监控与通知”，不包含任何绕过验证、突破安全机制、自动抢注或获取邀请码的功能。请遵守各站点规则。
