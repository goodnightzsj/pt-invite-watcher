# PT Invite Watcher — Plan

## Gate 0：任务说明（已对齐）

### 目标
- 长期运行的服务：对一批 PT 站点周期性检测并记录两类状态：
  - **开放注册**：站点无需邀请码即可注册（关心 `open`）
  - **已登录可发邀**：以“当前账号**可用邀请数 > 0**”作为 `open`
- 状态发生变化时推送通知：**Telegram**、**企业微信（企业应用）**
- Docker 部署运行：测试通过后以容器常驻
- 站点适配策略：**引擎识别 + 插件化**；优先覆盖 **NexusPHP**，少数站点逐个适配
- 站点来源：**接入 MoviePilot 的站点配置**

### 非目标（明确不做）
- 不获取/售卖/分享邀请码
- 不做绕过验证、破解反爬、突破登录或安全机制
- 不保证所有站点都能 100% 判定；允许输出 `unknown` 并给出证据

### 关键依赖与假设
- 你可提供可用登录态 cookie（通过 CookieCloud 或 MoviePilot 同步获得）
- MoviePilot API 可访问（同 Docker 网络或直连）
- 可提供 MoviePilot 的 API 访问凭据（管理员账号用于获取 JWT token；**凭据不写入仓库**，通过 env/挂载配置提供）

## 验收标准（成功判据）
- 给定站点列表，程序可输出每站两类状态：`open | closed | unknown`，并包含简短证据（URL、状态码、关键文本/匹配规则）
- Web UI 可展示单站最近一次探测异常（注册/邀请）及简要信息，便于排障
- 当 `开放注册` 状态变化或 `可用邀请数` 跨越 `0`（`0→>0` 或 `>0→0`）时，仅在变更时通知（不重复刷屏）
- 支持从 MoviePilot 读取站点清单（至少包含 `name/domain/url/is_active/ua/cookie`）
- 支持 CookieCloud 获取 cookie（作为 cookie 来源或刷新来源）
- 在 Docker 中可常驻运行并提供 health 日志/可观测输出（最少：启动、每轮扫描摘要、错误摘要）

## Gate C：实现方案（从宏到微）

### 总体思路与挂接点
- **SiteProvider（站点提供者）**：从 MoviePilot API 读取启用的站点列表（替代直连 SQLite）
- **CookieProvider（Cookie 提供者）**：
  - 优先：CookieCloud（POST `/get/:uuid` + `password`，由服务器端解密，返回 `{cookie_data, local_storage_data}`）
  - 备选：直接使用 MoviePilot 站点表中的 `cookie` 字段（当 CookieCloud 不可用时）
- **Engine & Detector（引擎与探测器）**：
  - 先对站点做轻量指纹识别（默认 NexusPHP，可配置强制引擎）
  - NexusPHP 统一实现：
    - 匿名探测 `signup.php` 判定注册状态
    - 登录态探测 `invite.php` 解析可用邀请数
- **StateStore（状态存储）**：SQLite（独立于 MP），保存上次结果与通知水位，保证“只在变化时通知”
- **Notifier（通知）**：Telegram Bot API + 企业微信应用 API
- **Runner（调度器）**：定时循环（可配置间隔、并发数、超时、重试策略）

### 目录结构（拟）
- `pt_invite_watcher/`：主包
  - `main.py`：入口（run/check-once）
  - `config.py`：配置读取与校验（YAML + env 覆盖）
  - `models.py`：状态/结果数据模型
  - `providers/`
    - `moviepilot_api.py`：通过 MP API 读取站点
    - `cookiecloud.py`：从 CookieCloud 拉取并按域名过滤 cookie
  - `engines/`
    - `base.py`
    - `nexusphp.py`
  - `storage/`
    - `sqlite.py`
  - `notify/`
    - `telegram.py`
    - `wecom.py`
  - `web/`
    - `app.py`：Web UI 与配置 API（通知配置）
- `config/`
  - `config.example.yaml`
- `docker/`
  - `Dockerfile`
  - `docker-compose.example.yml`
- `README.md`

### 配置设计（参考 MoviePilot 通知风格）
> 目标：你能复用/迁移现有 MoviePilot 的配置心智；但本项目仍以自己的 `config.yaml` 为准。

#### 配置来源与优先级（第一版）
- 启动参数（不可视化配置）：`db.path`、`web.host`、`web.port` 仍由 `config.yaml` / env 决定（因为影响服务监听与数据落盘位置）
- 运行时参数（可视化配置）：其余配置项（MoviePilot/Cookie/CookieCloud/Scan 等）通过 Web UI 保存到本服务的 SQLite，并在下一轮扫描时生效
- 优先级：SQLite 运行时配置（Web UI） > `config.yaml`/env 默认值
- 敏感信息（MP 密码、CookieCloud 密码等）会存入本服务的 SQLite；页面提供“留空不修改”，建议启用 BasicAuth 或仅在内网使用

关键配置项（草案）：
- `site_provider`：
  - `type: moviepilot_api`
  - `moviepilot_api.base_url`: 例如 `http://moviepilot:3001`（Swagger：`${base_url}/docs`）
  - `moviepilot_api.username`（建议用 env 注入）
  - `moviepilot_api.password`（建议用 env 注入，避免特殊字符转义问题）
  - `moviepilot_api.otp_password`（可选；若 MP 启用 MFA）
  - `only_active: true`
- `cookie`：
  - `source: cookiecloud | moviepilot | auto`
  - `cookiecloud.host`: `http://cookiecloud:8088`（支持 `API_ROOT`）
  - `cookiecloud.uuid`
  - `cookiecloud.password`
  - `refresh_interval_seconds`
- `scan`：
  - `interval_seconds`
  - `timeout_seconds`
  - `concurrency`
  - `user_agent`（默认使用 MP 的常见浏览器 UA）
- `engine`：
  - `default: nexusphp`
  - `overrides`: 按 `domain` 指定 `engine`、自定义路径（如非标准 `invite.php`）
- `web`：
  - `enabled: true`
  - `listen: 0.0.0.0`
  - `port: 8080`
  - `auth`（可选）：用于保护 Web UI 的简单口令/BasicAuth
- 通知参数不在 `config.yaml` 写死：通过 Web UI 进行配置与保存（Telegram、企业微信应用）。

### 关键接口/失败模式/降级策略
- MP API 读取：
  - 通过 `POST /api/v1/login/access-token` 获取 JWT（Bearer），再调用 `GET /api/v1/site/` 拉取站点
  - Token 过期自动刷新；认证失败（401）→ 标记本轮 `unknown` 并给出清晰错误
- CookieCloud：
  - 失败/超时 → 自动回退到 MP `site.cookie`（当 `cookie.source=auto`）
  - 返回结构缺失/解密失败 → 标记 `unknown` 并记录原因（不打印敏感值）
- 探测请求：
  - 网络异常/站点 5xx/Cloudflare 52x：单次请求最多重试 3 次（短退避），仍失败才判定为异常并记录到证据（含 `retries=3`）
  - 401/重定向到登录/出现“未登录”提示 → 视为 cookie 失效，`invite` 状态 `unknown`
  - 403/挑战页/反爬 → `unknown`（后续可扩展 headless）

### NexusPHP 探测规则（第一版：可解释、可调）
- `开放注册`：访问 `signup.php`
  - 明确匹配“注册关闭/仅邀请”等关键词 → `closed`
  - 页面存在 `<form>` 注册表单且未要求邀请码 → `open`
  - 页面不存在 `<form>` 注册表单 → `closed`（可确认未开放注册）
  - 无法判定 → `unknown`
- `可用邀请数`（需 cookie）
  - 先访问首页（`/`）解析顶部导航中的邀请名额：`邀请[发送]: 9(3)` / `邀請[發送]: 9(3)`（外层=永久邀请，括号内=临时邀请；用于判定时按总数相加）
  - 再跟随导航中的邀请链接（常见 `invite.php?id=<uid>`，少数为 `/invite`）校验是否具备“发送邀请”权限
    - 以“发送/创建邀请”的动作控件是否存在且可用为准（例如 `type=new`、`takeinvite.php`、按钮/链接“邀请(他人/其他人)”）
    - 若动作存在但被禁用（disabled）或提示无权限 → `closed`
    - 若名额 > 0 但未找到可用的发送动作 → 按 `closed` 处理（避免误报为 open）
  - 否则以名额 `count > 0` → `open`，否则 `closed`
  - 无法判定 → `unknown`

### 站点特例（第一版）
- M-Team（馒头）：默认不开放注册（直接按 `closed` 处理；后续若有更可靠规则再单独适配）

## Gate A：步骤拆分（小步可验收）

### Step 1：定义数据模型 + 最小输出
- 产出：状态模型（两类状态 + 证据字段）与 `check-once` 输出 JSON
- 验证：对 2~3 个站点手工对照页面与输出一致

### Step 2：接入 MoviePilot 站点配置（SQLite）
### Step 2：接入 MoviePilot 站点配置（API）
- 产出：通过 MP API 获取站点列表（过滤 `is_active=true`），并拉到 `name/domain/url/ua/cookie`
- 验证：输出站点数量/域名清单与 MP 后台一致；MP token 过期后可自动续期

### Step 3：接入 CookieCloud（按域名过滤 cookie）
- 产出：CookieCloud 拉取/刷新逻辑；可给某站生成可用 Cookie Header
- 验证：用其中 1 个站点访问需要登录的页面返回 200（或至少不跳登录）

### Step 4：实现 NexusPHP 探测器
- 产出：`signup.php` 探测；邀请探测支持从首页解析名额 + 识别 `invite.php?id=<uid>` / `/invite` 权限限制
- 验证：对 NexusPHP 站点跑通（含邀请数解析为整数）

### Step 5：状态存储 + 变更通知
### Step 5：通知配置（Web UI）+ 变更通知
- 产出：Web UI 可配置 Telegram/企业微信应用参数（启用/禁用、测试发送）；配置持久化到 SQLite
- 验证：Web UI 保存后立即生效；可测试发送成功；未配置通知时不影响检测主流程

### Step 5.1：运行时配置（Web UI）
- 产出：Web UI 可配置 MoviePilot/Cookie/CookieCloud/Scan 等运行时参数（除 `db.path`、`web.host`、`web.port` 外）；配置持久化到 SQLite
- 验证：保存后下一轮扫描生效；后台定时任务的间隔可随配置动态调整

### Step 6：状态存储 + 变更通知
- 产出：SQLite state store；仅在变化时触发已启用的通知渠道
- 验证：连续跑两轮不重复通知；模拟状态变化能触发一次通知

### Step 7：Docker 化与运行文档
- 产出：Dockerfile、compose 示例、README（含与 MP/CookieCloud 同网络的部署示例）
- 验证：`docker compose up -d` 可常驻，容器重启后仍能保持状态与不重复通知

## 静态检查与自检命令（拟）
- `python -m compileall .`
- `python -m pt_invite_watcher check-once --domain <domain>`
- （若加入测试）`pytest -q`

## 风险点与备选方案
- 站点改版/模板差异导致解析失效：通过 `engine.overrides` 增加单站正则/路径覆盖
- 反爬/JS challenge：第一版标记 `unknown`；二期可选 Playwright headless
- MP API 认证与权限：需要可用管理员凭据；若后续 MP 增加只读站点接口（API_TOKEN 认证），可替换为更低权限方案
