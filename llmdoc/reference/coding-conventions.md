# Coding Conventions Reference

## Overview

本项目的编码规范和约定。

## Python Backend

### 代码风格

| Aspect | Convention |
|--------|------------|
| 格式化工具 | Black |
| 导入排序 | isort |
| 类型检查 | mypy (optional) |
| 行长度 | 88 字符 (Black 默认) |

### 导入顺序

```python
# 1. Future imports
from __future__ import annotations

# 2. Standard library
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

# 3. Third-party
import httpx
from fastapi import APIRouter

# 4. Local imports
from pt_invite_watcher.models import Site
from pt_invite_watcher.storage import SqliteStore
```

### 数据类

使用 `@dataclass(frozen=True)` 表示不可变数据：

```python
# models.py 示例
@dataclass(frozen=True)
class Evidence:
    url: str
    http_status: Optional[int]
    reason: str
    matched: Optional[str] = None
```

### 类型注解

| Pattern | Usage |
|---------|-------|
| `Optional[T]` | 可能为 None 的值 |
| `Literal["a", "b"]` | 枚举值 |
| `list[T]` | 列表 (Python 3.9+) |
| `dict[K, V]` | 字典 |

**类型别名：**

```python
# models.py
State = Literal["open", "closed", "unknown"]
ReachabilityState = Literal["up", "down", "unknown"]
```

### 异步编程

| Pattern | Usage |
|---------|-------|
| `async def` | 所有 I/O 操作 |
| `await` | 调用异步函数 |
| `asyncio.gather()` | 并发执行 |
| `asyncio.create_task()` | 后台任务 |

**示例：**

```python
async def run_scan(self):
    async with self._lock:
        results = await asyncio.gather(
            *[self._check_site(site) for site in sites],
            return_exceptions=True
        )
```

### HTTP 客户端

使用 `httpx.AsyncClient`：

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url, cookies=cookies)
    # 始终关闭响应
    await response.aclose()
```

**重要：** 必须关闭响应对象防止资源泄漏。

### 错误处理

```python
try:
    result = await some_operation()
except httpx.TimeoutException:
    logger.warning("Operation timed out")
    return default_value
except Exception as e:
    logger.exception("Unexpected error")
    raise
```

### 日志

使用 `structlog`：

```python
import structlog

logger = structlog.get_logger()

logger.info("scan_started", site_count=10)
logger.error("scan_failed", error=str(e), domain=site.domain)
```

### 命名约定

| Type | Convention | Example |
|------|------------|---------|
| 模块 | snake_case | `scanner_impl.py` |
| 类 | PascalCase | `SiteCheckResult` |
| 函数/方法 | snake_case | `run_full_scan()` |
| 常量 | UPPER_SNAKE | `DEFAULT_TIMEOUT` |
| 私有成员 | 前缀 `_` | `_lock`, `_client` |

### 文件组织

| Directory | Purpose |
|-----------|---------|
| `engines/` | 检测引擎 |
| `providers/` | 外部服务集成 |
| `routes/` | API 路由 |
| `storage/` | 数据持久化 |
| `notify/` | 通知渠道 |
| `utils/` | 工具函数 |

## TypeScript Frontend

### 代码风格

| Aspect | Convention |
|--------|------------|
| 格式化 | Prettier |
| 类型 | 严格 TypeScript |
| 组件 | Vue 3 Composition API |

### 类型定义

```typescript
// 接口定义
interface ScanStatus {
  ok: boolean;
  site_count: number;
  last_run_at: string;
}

// 类型推导
const loading = ref(false);  // Ref<boolean>
```

### Vue 组件

使用 `<script setup lang="ts">`：

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from './api';

const data = ref<ScanStatus | null>(null);

onMounted(async () => {
  data.value = await api.dashboard();
});
</script>
```

### API 调用

统一使用 `api.ts` 中的方法：

```typescript
// 正确
const sites = await api.sitesList();

// 错误
const sites = await axios.get('/api/sites');
```

## 通用约定

### 文档注释

Python:
```python
def check_site(self, site: Site) -> SiteCheckResult:
    """检查单个站点状态。

    Args:
        site: 站点信息

    Returns:
        检查结果
    """
```

TypeScript:
```typescript
/**
 * 获取站点列表
 * @returns 站点数组
 */
async function sitesList(): Promise<SiteRow[]> {
```

### 错误消息

- 使用英文编写错误消息
- 包含足够的上下文信息
- 避免暴露敏感信息

```python
# 好
raise ValueError(f"Invalid domain format: {domain}")

# 差
raise ValueError("Error")
```

### 配置管理

- 环境变量：启动时配置
- KV 存储：运行时配置
- 配置项使用 snake_case

## 测试

### 文件命名

```
tests/
├── test_scanner.py
├── test_models.py
└── conftest.py
```

### 测试函数

```python
async def test_scan_returns_results():
    """测试扫描返回正确结果。"""
    scanner = Scanner(store)
    result = await scanner.run_full_scan()
    assert result.ok
```
