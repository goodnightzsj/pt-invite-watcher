# PT Invite Watcher

长期运行的 PT 站点“开放注册 / 可用邀请数”监控服务（默认 NexusPHP），站点列表来源于 MoviePilot，Cookie 优先从 CookieCloud 获取并支持回退。

## 功能

- 站点来源：MoviePilot API（登录拿 JWT，再拉取站点列表）
- Cookie：优先 CookieCloud，失败回退 MoviePilot 站点 cookie
- 监控项：
  - 开放注册（`signup.php`）
  - 已登录可发邀：从首页导航解析“邀请[发送]”名额，结合邀请页的等级/权限限制判断（名额 `> 0` 且无权限限制视为 `open`）
- 通知：Telegram / 企业微信（企业应用），通过 Web UI 手动配置与保存
- 部署：Docker 常驻

## 快速开始（本地）

1) 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) 构建 Web UI（Vue + Tailwind）

```bash
npm --prefix webui install
npm --prefix webui run build
```

3) 配置环境变量（示例）

```bash
export MP_BASE_URL="http://moviepilot:3001"  # MoviePilot: ${MP_BASE_URL}/docs
export MP_USERNAME="admin"
export MP_PASSWORD="***"

export COOKIE_SOURCE="auto"  # auto|cookiecloud|moviepilot
export COOKIECLOUD_BASE_URL="http://127.0.0.1:8088"
export COOKIECLOUD_UUID="***"
export COOKIECLOUD_PASSWORD="***"

export PTIW_DB_PATH="./data/ptiw.db"
export PTIW_SCAN_INTERVAL_SECONDS="600"
export PTIW_SCAN_TRUST_ENV="false"  # 是否使用系统代理环境变量（ALL_PROXY/HTTP_PROXY/HTTPS_PROXY）
```

如果你的系统设置了 `ALL_PROXY/HTTP_PROXY`（例如本地代理），建议给内网地址配置 `NO_PROXY`，否则访问 MoviePilot/CookieCloud 可能出现 `502`：

```bash
export NO_PROXY="localhost,127.0.0.1,192.168.31.122"
```

默认情况下，站点探测会忽略系统代理环境变量（`PTIW_SCAN_TRUST_ENV=false` / `scan.trust_env=false`），避免“部分站点通过代理无法访问”导致大量 `ConnectError`。

也可以使用 YAML 配置：复制 `config/config.example.yaml` 到 `config/config.yaml`，或设置 `PTIW_CONFIG` 指向你的配置文件。

4) 运行

```bash
python3 -m pt_invite_watcher run
```

打开 Web UI：`http://127.0.0.1:8080`，在“通知设置”里配置 Telegram / 企业微信并测试发送。

## Docker

### 方式 A：docker run（拉取镜像直接运行）

示例（将宿主机 `8003` 映射到容器 `8080`，并持久化 SQLite 到本地 `./data`）：

```bash
mkdir -p data

docker run -d \
  --name pt-invite-watcher \
  --restart always \
  -p 8003:8080 \
  -v "$(pwd)/data:/data" \
  -e PTIW_DB_PATH="/data/ptiw.db" \
  helloworldz1024/pt-invite-watcher:latest
```

Web UI：`http://<host>:8003`

如需在启动时直接配置 MoviePilot / CookieCloud（也可启动后在 Web UI 中配置并保存到 SQLite），追加环境变量即可：

```bash
docker run -d \
  --name pt-invite-watcher \
  --restart always \
  -p 8003:8080 \
  -v "$(pwd)/data:/data" \
  -e PTIW_DB_PATH="/data/ptiw.db" \
  -e MP_BASE_URL="http://moviepilot:3001" \
  -e MP_USERNAME="admin" \
  -e MP_PASSWORD="CHANGE_ME" \
  -e COOKIE_SOURCE="auto" \
  -e COOKIECLOUD_BASE_URL="http://cookiecloud:8088" \
  -e COOKIECLOUD_UUID="CHANGE_ME" \
  -e COOKIECLOUD_PASSWORD="CHANGE_ME" \
  helloworldz1024/pt-invite-watcher:latest
```

### 方式 B：docker compose

#### 直接拉取镜像运行

在任意目录创建 `docker-compose.yml`：

```yaml
services:
  pt-invite-watcher:
    image: helloworldz1024/pt-invite-watcher:latest
    container_name: pt-invite-watcher
    restart: unless-stopped
    ports:
      - "8003:8080"
    environment:
      PTIW_DB_PATH: "/data/ptiw.db"
      # 可选：启动时直接配置 MP / CookieCloud（也可启动后在 Web UI 中配置并保存到 SQLite）
      # MP_BASE_URL: "http://moviepilot:3001"
      # MP_USERNAME: "admin"
      # MP_PASSWORD: "CHANGE_ME"
      # COOKIE_SOURCE: "auto"
      # COOKIECLOUD_BASE_URL: "http://cookiecloud:8088"
      # COOKIECLOUD_UUID: "CHANGE_ME"
      # COOKIECLOUD_PASSWORD: "CHANGE_ME"
      # 可选：保护 Web UI（BasicAuth）
      # PTIW_WEB_AUTH_USERNAME: "admin"
      # PTIW_WEB_AUTH_PASSWORD: "CHANGE_ME"
    volumes:
      - ./data:/data
```

启动：

```bash
mkdir -p data
docker compose up -d
```

Web UI：`http://<host>:8003`

#### 从源码构建运行

参考 `docker/docker-compose.example.yml`：

```bash
# 按需修改 docker/docker-compose.example.yml 里的环境变量
docker compose -f docker/docker-compose.example.yml up -d --build
```

Web UI：`http://<host>:8080`

## 自动构建并推送到 DockerHub（GitHub Actions）

本项目已提供 GitHub Actions workflow：`.github/workflows/docker-publish.yml`。

1) 在 DockerHub 创建 Access Token（建议只给 push 权限）

2) 在 GitHub 仓库 Settings → Secrets and variables → Actions 添加 Secrets：

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

3) push 到 `main` 分支后，会自动构建并推送镜像（基于 `docker/Dockerfile`）：

- `${DOCKERHUB_USERNAME}/pt-invite-watcher:latest`
- `${DOCKERHUB_USERNAME}/pt-invite-watcher:${GITHUB_SHA}`

## 免责声明

本项目仅用于“状态监控与通知”，不包含任何绕过验证/突破安全机制/获取邀请码等功能。
