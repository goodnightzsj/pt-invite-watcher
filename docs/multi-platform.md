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

## 移动端（iOS / Android，Capacitor）

移动端用 **Capacitor**，不是 Tauri。原因：

- 移动端本来就跑不了 Python sidecar（沙箱禁止外部进程），Tauri 的 `externalBin` 机制在 iOS/Android 上是摆设。
- 用 Tauri 做移动就要付出 NDK + Rust cross-compile 的代价换零功能收益。
- Capacitor 就是「把 Web 打成原生 WebView 壳」，简单稳定，CI 快。

共用的是 `webui/` 的 Vite 构建产物——一次 build，桌面浏览器 / Tauri 桌面 / Capacitor 移动三处消费。

### Android

前置：

- JDK 21
- Android Studio + SDK（API 34+）
- `ANDROID_HOME` 指向 SDK

初始化（**首次**）：

```bash
npm --prefix webui run build     # 先把前端 dist 打好
npm --prefix mobile install      # 安装 Capacitor 依赖
npm run mobile:android:init      # cap add android → 生成 mobile/android/ Gradle 工程
npm run mobile:sync              # 把 dist 同步进原生壳
```

构建：

```bash
cd mobile/android
./gradlew assembleDebug          # 输出 APK（debug-signed，可 sideload）
./gradlew assembleRelease bundleRelease  # 需要 release.keystore 配置好；输出 APK + AAB
```

### iOS

前置：

- macOS + Xcode 15+
- CocoaPods（`gem install cocoapods`）
- Apple Developer Account（$99/yr，签名 / TestFlight / App Store 必需；模拟器不需要）

初始化（**首次**）：

```bash
npm --prefix webui run build
npm --prefix mobile install
npm run mobile:ios:init          # cap add ios → 生成 mobile/ios/ Xcode 工程
npm run mobile:sync
cd mobile/ios/App && pod install --repo-update
```

构建：

```bash
# 签名 release 流程（需准备好 .p12 + provisioning profile）：
xcodebuild -workspace App.xcworkspace -scheme App \
  -configuration Release -destination "generic/platform=iOS" \
  -archivePath build/App.xcarchive archive
xcodebuild -exportArchive -archivePath build/App.xcarchive \
  -exportPath build/ipa -exportOptionsPlist ExportOptions.plist

# 未签名 simulator 快速验证：
xcodebuild -workspace App.xcworkspace -scheme App \
  -configuration Release -destination "generic/platform=iOS Simulator" \
  -sdk iphonesimulator CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY="" CODE_SIGNING_ALLOWED=NO \
  -derivedDataPath build
```

### 为什么移动端不支持本地模式

iOS / Android 沙箱禁止应用启动外部进程，Python sidecar 没法跑。要让扫描逻辑在移动端本地运行，只有两条路：

1. **捆绑 Python 解释器**（Chaquopy / BeeWare）。Android 可行，iOS 复杂；二进制膨胀到 ~100MB，且移动后台无法长时运行扫描任务（iOS 后台执行限制会杀掉 Python 进程），体验比云端模式差。
2. **把扫描核心 Rust 化**（`pt_invite_watcher/engines/*.py` → `src-tauri/engines-rs/`，全平台复用）。工作量大（~2-3k 行），但能做成真的离线扫描。

两条路都属于长期规划。现阶段移动端走远程模式（连接用户自托管的桌面 / 服务器实例）是最务实的选择。

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

## GitHub Actions 自动构建

仓库 `.github/workflows/` 里有三条针对多端打包的 workflow，**push 一个 `v*` 标签**就会全部触发，产物挂到 GitHub Release 草稿；**手动 Run workflow** 则只产出 `actions/upload-artifact` 附件，适合验证构建环境。

| 文件 | 产物 | Runner | 可选 Secrets |
|---|---|---|---|
| `desktop.yml` | `.dmg` (Apple Silicon + Intel)、`.msi` + `.exe`、`.AppImage` + `.deb` | macos-14 / macos-13 / windows-latest / ubuntu-22.04（并行） | `APPLE_SIGNING_IDENTITY`、`APPLE_ID`、`APPLE_PASSWORD`、`APPLE_TEAM_ID`、`TAURI_SIGNING_PRIVATE_KEY`、`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` |
| `android.yml` | `.apk` + `.aab` | ubuntu-22.04 | `ANDROID_KEYSTORE_BASE64`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` |
| `ios.yml` | `.ipa`（签名时）或 `.app`（simulator） | macos-14 | `APPLE_CERTIFICATE`（base64 .p12）、`APPLE_CERTIFICATE_PASSWORD`、`APPLE_PROVISIONING_PROFILE`（base64 .mobileprovision）、`APPLE_SIGNING_IDENTITY`、`APPLE_TEAM_ID` |

**关键点**：

- **没有 secret 也能跑**。desktop.yml 产出未签名的 dmg/msi/AppImage；android.yml 产出 debug-signed APK；ios.yml 产出模拟器用 `.app`。只是无法上架 / 无法绕 Gatekeeper / SmartScreen 首次警告而已。
- **Rust + Cargo 缓存** 已经用 `Swatinem/rust-cache` 做了，首次 ~20min，之后每轮 ~5-8min。Gradle / Node 缓存同理。
- **Tauri android/ios init 会产生 `src-tauri/gen/`**。workflow 里判断了已生成则跳过，所以首次运行会建出 Gradle / Xcode 工程，后续缓存命中直接 build。
- **macOS 双架构**：没用 `universal2` 合并，而是分别跑 macos-13（Intel）和 macos-14（Apple Silicon）两个 runner，各产一个 .dmg。这样 CI 总时长不变（并行），但用户下载的包尺寸只有一半。

### Secrets 配置速查

Apple 签名（macOS desktop + iOS）：

```bash
# 从钥匙串导出 Developer ID Application .p12，然后：
base64 -i developer_id.p12 | pbcopy     # 粘到 secrets.APPLE_CERTIFICATE
# appleid.apple.com → 账户 → App 专用密码 → 生成后粘到 secrets.APPLE_PASSWORD
```

Android 签名：

```bash
# 已有 keystore（见 docs 上文 keytool 命令）
base64 -i ~/.android/pt-invite-watcher.keystore | pbcopy   # → secrets.ANDROID_KEYSTORE_BASE64
```

Windows 签名：

```bash
# EV 证书通常厂商给 .pfx 文件
# TAURI_SIGNING_PRIVATE_KEY 就是 .pfx 的绝对路径（runner 会解密到 $PATH）
# 简单做法：base64 .pfx 然后在 workflow 加一步 decode 到 /tmp/cert.pfx
```

### 触发与发布策略

**只有 tag push 会创建 GitHub Release**——手动 `workflow_dispatch` 只把产物挂到 Actions → Artifacts 面板（保留 30 天），不动 Release。这样做的目的：

- 每次 commit 跑 4 个 runner 的 native build 既费时（~30 分钟/提交）又无人下载，违背分发价值。
- 开发阶段只想看「native 壳还能编过吗」时，用 `workflow_dispatch` 按需跑；正式发版打 tag。

**两种 tag 命名空间**：

| Tag 形式 | 触发哪些 workflow | 用途 |
|---|---|---|
| `v0.1.0` | desktop + android + ios | 三端同步发版（最常见） |
| `desktop-v0.1.0` | 仅 desktop.yml | 只改桌面端（例：macOS 签名修复） |
| `android-v0.1.0` | 仅 android.yml | 只补 Android 版本 |
| `ios-v0.1.0` | 仅 ios.yml | 只补 iOS 版本 |

每个 workflow 会把产物挂到 **同一个 tag 对应的 draft Release**（`softprops/action-gh-release` 自动按 tag name 合并）。review 完草稿点 "Publish" 即生效。

**Docker 镜像 workflow** 独立：`main` 分支 push 时自动构建 + 推 Docker Hub，并用 `paths` 白名单过滤纯文档 / Tauri 壳 / 移动配置类改动（这些不影响后端容器）。Docker 镜像不走 Release，继续滚动覆盖 `:latest`。

```bash
# 三端同步发版
git tag v0.1.0 && git push origin v0.1.0

# 仅桌面补丁（Android / iOS 不变）
git tag desktop-v0.1.1 && git push origin desktop-v0.1.1

# CI 调试：不动 Release
# GitHub Actions 页面 → Run workflow → 选分支
```

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
