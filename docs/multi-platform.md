# 多端客户端指南

PT Invite Watcher 支持三种部署形态，**同一份 Vue 代码**在三种形态下原样运行：

| 形态 | 平台 | 数据位置 | 扫描引擎 | 是否需要服务器 |
|---|---|---|---|---|
| **浏览器** | 任意现代浏览器 | 服务端 SQLite | 服务端 Python | 必须（自托管 FastAPI） |
| **桌面 – 本地模式** | Windows / macOS / Linux | 用户电脑本地 SQLite | 应用内嵌 Python sidecar | 不需要 |
| **桌面 – 远程模式** | Windows / macOS / Linux | 远程服务器 SQLite | 远程服务器 | 必须（任意自托管 FastAPI） |
| **移动 – 远程模式** | iOS / Android | 远程服务器 SQLite | 远程服务器 | 必须 |

移动端当前**仅支持远程模式**（见下文「为什么移动端不支持本地模式」）。

---

## 快速开始：构建桌面应用

### 前置依赖

**全平台**：

```bash
# Rust（Tauri 需要）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Node 依赖（Tauri CLI 从这里装）
npm install

# PyInstaller（打包 Python sidecar）
.venv/bin/pip install pyinstaller
```

**Linux 额外**：

```bash
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev pkg-config
```

**macOS**：无（Xcode Command Line Tools 即可，用 `xcode-select --install` 装）。

**Windows**：装 Microsoft Edge WebView2 Runtime（Win10+ 默认有；Win7/8 要手动装 Evergreen Bootstrapper）。

### 本地模式（含打包 Python sidecar）

```bash
# 1. 先构建前端 dist
npm run webui:build

# 2. 打包 Python 为单文件二进制（产出到 src-tauri/binaries/）
npm run sidecar:build

# 3. Tauri 打包（自动注入 sidecar）
npm run tauri:build
```

产物：

- macOS：`src-tauri/target/release/bundle/dmg/PT Invite Watcher_0.1.0_x64.dmg` 等
- Windows：`src-tauri/target/release/bundle/msi/PT Invite Watcher_0.1.0_x64_en-US.msi`
- Linux：`.deb` / `.AppImage` in `src-tauri/target/release/bundle/`

### 远程模式

不需要构建 sidecar；`tauri:build` 里如果 `src-tauri/binaries/` 为空会跳过 `externalBin` 并直接进入 Onboarding 流程。

```bash
npm run webui:build
npm run tauri:build
```

用户首启会看到 Onboarding 页，填入自托管 FastAPI 的 URL + BasicAuth 即可。

### 调试

```bash
npm run tauri:dev      # 热重载：改 webui/src 下任何文件自动刷新
```

---

## 移动端（iOS / Android）

### Android

前置：

- Android Studio + SDK（API 33+）
- JDK 17
- `ANDROID_HOME` / `NDK_HOME` 环境变量指向 SDK / NDK

初始化（**首次**）：

```bash
npm run tauri:android:init
# 产出 src-tauri/gen/android/   — 这是一个完整的 Gradle 项目，可用 Android Studio 打开
```

开发 / 构建：

```bash
npm run tauri:android:dev     # 连真机或跑模拟器
npm run tauri:android:build   # 产出 APK + AAB（on-device 装 APK，上 Play Store 传 AAB）
```

产物：`src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk`

### iOS

前置：

- macOS（iOS 构建只能在 macOS 上）
- Xcode 15+
- Apple Developer Account（$99/yr，上 TestFlight / App Store 必需；本地模拟器不需要）

初始化（**首次**）：

```bash
npm run tauri:ios:init
# 产出 src-tauri/gen/apple/   — Xcode 工程可直接打开
```

开发 / 构建：

```bash
npm run tauri:ios:dev         # 跑在 iOS 模拟器
npm run tauri:ios:build       # 构建 .ipa
```

### 为什么移动端不支持本地模式

Tauri 2 的 `externalBin` 机制在 iOS / Android 上无法启动外部进程（系统沙箱禁止）。要让 Python 扫描逻辑在移动端本地运行，只有两条路：

1. **捆绑 Python 解释器**（Chaquopy / BeeWare）。Android 可行，iOS 可行但复杂；二进制从 30MB 膨胀到 ~100MB，且移动后台无法长时运行扫描任务（iOS 的后台执行限制会杀掉 Python 进程），体验比云端模式差。
2. **把扫描核心 Rust 化**（`pt_invite_watcher/engines/*.py` → `src-tauri/engines-rs/`）。工作量大（~2-3k 行），但能做成真的离线扫描。

两条路都属于 Phase 4 的长期规划。现阶段移动端走远程模式（连接用户自托管的桌面 / 服务器实例）是最务实的选择。

---

## 签名、公证与分发

### macOS：Developer ID + Notarization

```bash
# 首先 Apple Dev Portal 下载 Developer ID Application 证书，导入钥匙串
# 设置环境变量（可放到 ~/.zshrc）：
export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export APPLE_ID="you@example.com"
export APPLE_PASSWORD="app-specific-password"        # appleid.apple.com 生成的 app-specific
export APPLE_TEAM_ID="TEAMID"

npm run tauri:build
# Tauri 自动调用 codesign + notarytool
# 产物会在 bundle/dmg/ 下生成已签名+公证的 .dmg
```

**不签名时**：用户下载 .dmg 双击会触发 Gatekeeper 阻止，需右键 → 打开 → 确认。可以用，但不专业。

### Windows：EV Code Signing

```bash
# .pfx 证书 + 密码
export TAURI_SIGNING_PRIVATE_KEY="C:\path\to\cert.pfx"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="****"
npm run tauri:build
```

**不签名时**：SmartScreen 首次运行会警告（"已阻止不识别的应用"），用户点"更多信息 → 仍要运行"可以过。EV 证书 ~$200/yr 可以让新应用也立即过 SmartScreen。

### Linux：AppImage / .deb

Linux 没有平台级签名要求，直接分发即可：

```bash
npm run tauri:build
ls src-tauri/target/release/bundle/appimage/*.AppImage
ls src-tauri/target/release/bundle/deb/*.deb
```

### Android：Play Store

Play Console（$25 一次性）→ 创建应用 → 上传 AAB → 走内部测试轨 → 生产。

> 首次上架需要用自己的签名 key：
>
> ```bash
> keytool -genkey -v -keystore ~/.android/pt-invite-watcher.keystore \
>   -alias upload -keyalg RSA -keysize 4096 -validity 9125
> ```
>
> 把 keystore 路径和密码在 `src-tauri/gen/android/key.properties` 中配置（Tauri init 会留好模板）。

### iOS：TestFlight / App Store

Xcode 打开 `src-tauri/gen/apple/PT Invite Watcher.xcodeproj` → Product → Archive → Distribute App → App Store Connect → 上传。TestFlight 内测最多 90 天，要公开要提交 App Review（1-3 天）。

---

## 数据迁移 / 切换模式

**本地模式的 SQLite 位置**：

- macOS：`~/Library/Application Support/com.pt-invite-watcher.app/ptiw.sqlite`
- Windows：`%APPDATA%\com.pt-invite-watcher.app\ptiw.sqlite`
- Linux：`~/.local/share/com.pt-invite-watcher.app/ptiw.sqlite`

**从本地模式迁到云端**：

1. 在本地模式下 Config → "完整导出" 拿到 JSON
2. 部署 FastAPI 到服务器
3. 新客户端连服务器，Config → "导入"

**反向**：同理，Config → 导出 → 本地模式客户端导入。

---

## 架构参考

```
┌─────────────────────────────────────────┐
│ webui/  (Vue 3 + Tailwind + TS)         │  一份代码，三种宿主
└──────┬──────────────────────────────────┘
       │
       ▼
┌──────────────────┐   ┌─────────────────┐
│ Browser (原同源)  │   │ Tauri Shell     │
│  → FastAPI        │   │  src-tauri/     │
└──────────────────┘   │                 │
                       │  ┌───────────┐  │   桌面（本地模式）
                       │  │ Rust main │─▶│  Python sidecar
                       │  │  + sidecar│  │     ↓ localhost
                       │  │   runtime │  │   SQLite 在用户磁盘
                       │  └───────────┘  │
                       │       │         │   桌面（远程模式）/ 移动
                       │       └─────────┼──▶ 用户自托管 FastAPI
                       └─────────────────┘
```

`runtime_config.ts` 是所有三种形态的共同入口：读 `window.__PTIW_RUNTIME__`（Tauri 注入）→ localStorage → 空默认（浏览器同源）。`api.ts` / `ws.ts` 都从它拿 base URL，调用点不用关心当前在哪个形态下跑。
