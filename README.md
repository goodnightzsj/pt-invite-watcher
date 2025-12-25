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

2) 配置环境变量（示例）

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

3) 运行

```bash
python3 -m pt_invite_watcher run
```

打开 Web UI：`http://127.0.0.1:8080`，在“通知设置”里配置 Telegram / 企业微信并测试发送。

## Docker

参考 `docker/docker-compose.example.yml`：

```bash
# 按需修改 docker/docker-compose.example.yml 里的环境变量
docker compose -f docker/docker-compose.example.yml up -d --build
```

Web UI：`http://<host>:8080`

## 免责声明

本项目仅用于“状态监控与通知”，不包含任何绕过验证/突破安全机制/获取邀请码等功能。
