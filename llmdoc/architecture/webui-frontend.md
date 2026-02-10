# WebUI Frontend Architecture

## Overview

WebUI 是基于 Vue 3 + TypeScript + Vite 构建的单页应用。

**Location:** `webui/src/`

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Vue | 3.x | UI Framework |
| TypeScript | 5.x | Type Safety |
| Vite | 5.x | Build Tool |
| Vue Router | 4.x | Routing |
| Pinia | (可选) | State Management |
| Axios | - | HTTP Client |

## Directory Structure

```
webui/
├── src/
│   ├── api.ts          # API 客户端 (6.5KB)
│   ├── router.ts       # 路由配置
│   ├── ws.ts           # WebSocket 客户端
│   ├── App.vue         # 根组件
│   ├── main.ts         # 入口文件
│   ├── views/          # 页面组件
│   │   ├── Dashboard.vue
│   │   ├── Sites.vue
│   │   ├── Config.vue
│   │   ├── Notifications.vue
│   │   └── Logs.vue
│   └── components/     # 通用组件
├── index.html
├── vite.config.ts
└── package.json
```

## Routing

**Location:** `webui/src/router.ts`

| Path | Component | Description |
|------|-----------|-------------|
| `/` | Dashboard | 仪表盘首页 |
| `/sites` | Sites | 站点列表管理 |
| `/config` | Config | 系统配置 |
| `/notifications` | Notifications | 通知设置 |
| `/logs` | Logs | 事件日志 |

## API Client

**Location:** `webui/src/api.ts`

### Type Definitions

```typescript
// 主要类型（简化展示）
interface ScanStatus {
  ok: boolean;
  site_count: number;
  scanned_count: number;
  last_run_at: string;
  moviepilot_configured: boolean;
  moviepilot_ok: boolean;
}

interface SiteRow {
  domain: string;
  name: string;
  url: string;
  registration_state: string;
  invites_state: string;
  invites_available: number | null;
  reachability_state: string;
  last_checked_at: string;
}

interface DashboardResponse {
  scan_status: ScanStatus;
  sites_summary: SitesSummary;
}
```

### API Methods

| Method | Endpoint | Description |
|--------|----------|-------------|
| `dashboard()` | `GET /api/dashboard` | 获取仪表盘数据 |
| `scanRun()` | `POST /api/scan/run` | 触发全量扫描 |
| `scanRunOne(domain)` | `POST /api/scan/run/{domain}` | 单站点扫描 |
| `sitesList()` | `GET /api/sites` | 获取站点列表 |
| `siteGet(domain)` | `GET /api/sites/{domain}` | 获取站点详情 |
| `sitePut(domain, data)` | `PUT /api/sites/{domain}` | 更新站点配置 |
| `siteDelete(domain)` | `DELETE /api/sites/{domain}` | 删除站点 |
| `configGet()` | `GET /api/config` | 获取配置 |
| `configPut(data)` | `PUT /api/config` | 更新配置 |
| `notificationsGet()` | `GET /api/config/notifications` | 获取通知配置 |
| `notificationsPut(data)` | `PUT /api/config/notifications` | 更新通知配置 |
| `notificationsTest(channel)` | `POST /api/config/notifications/test/{channel}` | 测试通知 |
| `logsGet(params)` | `GET /api/logs` | 获取日志 |

### Error Handling

API 客户端统一处理错误响应：

```typescript
// api.ts 错误处理模式
try {
  const response = await axios.get(url);
  return response.data;
} catch (error) {
  // 统一错误格式
  throw { message: error.response?.data?.detail || 'Unknown error' };
}
```

## WebSocket Client

**Location:** `webui/src/ws.ts`

### Features

- 自动重连（指数退避）
- Ping/Pong 心跳（30 秒）
- Vue Composable 集成

### Usage

```typescript
// 在组件中使用
import { useWS } from './ws';

const { connected, lastEvent, onEvent } = useWS();

// 监听特定事件
onEvent('scan_done', (data) => {
  console.log('Scan completed:', data);
});
```

### Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `scan_start` | `{}` | 扫描开始 |
| `scan_done` | `{site_count, duration}` | 扫描完成 |
| `site_state_changed` | `{domain, ...changes}` | 站点状态变更 |
| `config_changed` | `{key}` | 配置变更 |

### Connection Lifecycle

```
┌─────────┐    ┌──────────┐    ┌───────────┐
│ Connect │───▶│ Handshake│───▶│ Connected │
└─────────┘    └──────────┘    └─────┬─────┘
                                     │
                               ┌─────▼─────┐
                               │  Ping/    │◀─── 30s interval
                               │  Pong     │
                               └─────┬─────┘
                                     │
                     ┌───────────────┼───────────────┐
                     │               │               │
               ┌─────▼─────┐  ┌──────▼─────┐  ┌─────▼─────┐
               │ Receive   │  │  Error/    │  │  Close    │
               │ Message   │  │  Timeout   │  │           │
               └───────────┘  └──────┬─────┘  └─────┬─────┘
                                     │              │
                               ┌─────▼──────────────▼─────┐
                               │      Auto Reconnect      │
                               │   (exponential backoff)  │
                               └──────────────────────────┘
```

## Build & Deployment

### Development

```bash
cd webui
npm install
npm run dev  # 启动开发服务器
```

### Production Build

```bash
npm run build  # 输出到 webui_dist/
```

### Static Serving

构建产物由 FastAPI 静态文件服务提供：

```python
# app.py
app.mount("/", StaticFiles(directory="webui_dist", html=True))
```

## State Management

当前使用 Vue 3 Composition API 的响应式状态，无全局状态管理库。

### 页面级状态

每个 View 组件管理自己的状态：

```typescript
// Dashboard.vue 示例
const scanStatus = ref<ScanStatus | null>(null);
const loading = ref(false);

async function fetchDashboard() {
  loading.value = true;
  try {
    const data = await api.dashboard();
    scanStatus.value = data.scan_status;
  } finally {
    loading.value = false;
  }
}
```

### 实时更新

WebSocket 事件触发状态刷新：

```typescript
onEvent('scan_done', () => {
  fetchDashboard();  // 重新获取数据
});
```

## Styling

使用 CSS 变量和 scoped styles：

```vue
<style scoped>
.card {
  --card-bg: #fff;
  background: var(--card-bg);
}
</style>
```

## Key Patterns

| Pattern | Usage |
|---------|-------|
| Composition API | 所有组件使用 `<script setup>` |
| TypeScript | 全量类型定义 |
| 响应式引用 | `ref()` / `reactive()` |
| 异步数据加载 | `onMounted` + `async/await` |
| WebSocket | Composable 封装 |
