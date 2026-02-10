# Scheduler Architecture

## Overview

调度器负责定时触发站点扫描任务，支持多实例部署时的 Leader 选举。

**Location:** `pt_invite_watcher/scheduler.py`

## Core Components

### SchedulerLeaseManager

基于 Lease 的分布式锁管理器。

```
Location: scheduler.py:20-55
```

| Method | Description |
|--------|-------------|
| `try_acquire()` | 尝试获取 leader 锁 |
| `release()` | 释放锁 |
| `_compute_ttl()` | 计算锁 TTL |

**TTL 计算逻辑:**
- 基础 TTL = `scan_interval_minutes * 60 * 2`
- 最小 TTL = 120 秒
- 最大 TTL = 3600 秒

### Scheduler Loop

主调度循环逻辑。

```
Location: scheduler.py:58-120
```

**流程:**
1. 尝试获取 Leader 锁
2. 获取成功 → 执行扫描
3. 获取失败 → 等待下次尝试
4. 按配置间隔重复

## Leader Election

### 工作原理

```
┌─────────────────────────────────────────────────────────┐
│                    Instance A                            │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │ Startup │───▶│ Try Acquire │───▶│ Got Lock? (Yes) │ │
│  └─────────┘    └─────────────┘    └────────┬────────┘ │
│                                              │          │
│                                    ┌─────────▼────────┐ │
│                                    │   Run Scanner    │ │
│                                    └─────────┬────────┘ │
│                                              │          │
│                                    ┌─────────▼────────┐ │
│                                    │  Release Lock    │ │
│                                    └─────────┬────────┘ │
│                                              │          │
│                                    ┌─────────▼────────┐ │
│                                    │ Sleep(interval)  │ │
│                                    └─────────┬────────┘ │
│                                              │          │
│                                              ▼          │
│                                         (loop back)     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Instance B                            │
│  ┌─────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │ Startup │───▶│ Try Acquire │───▶│ Got Lock? (No)  │ │
│  └─────────┘    └─────────────┘    └────────┬────────┘ │
│                                              │          │
│                                    ┌─────────▼────────┐ │
│                                    │ Sleep(interval)  │ │
│                                    └─────────┬────────┘ │
│                                              ▼          │
│                                         (loop back)     │
└─────────────────────────────────────────────────────────┘
```

### Lease 存储

Lease 通过 `storage/lease_store.py` 管理，数据存储在 KV 表：

| Key | Value (JSON) |
|-----|--------------|
| `lease:scheduler` | `{"owner": "host:pid", "expire_at": "..."}` |

## Lifecycle

### 启动

```python
# app.py lifespan
await start_scheduler(store, scanner)
```

**Location:** `scheduler.py:122-140`

### 停止

```python
await stop_scheduler()
```

**Location:** `scheduler.py:142-155`

**行为:**
- 设置停止标志
- 取消运行中的任务
- 等待任务完成（最多 5 秒）

## Configuration

调度器从运行时配置读取：

| Config Key | Description | Default |
|------------|-------------|---------|
| `scan_interval_minutes` | 扫描间隔（分钟） | 30 |
| `scheduler_enabled` | 是否启用调度器 | true |

**配置来源:** `kv.app_config`

## Error Handling

| Scenario | Behavior |
|----------|----------|
| 扫描失败 | 记录错误，继续下次调度 |
| 锁获取失败 | 跳过本轮，等待下次 |
| 配置读取失败 | 使用默认配置 |

## Concurrency

### 单实例

- 同一时刻只有一个扫描任务在运行
- 使用 `asyncio.Lock` 保护扫描入口

### 多实例

- Lease 机制确保只有一个 Leader 执行扫描
- 非 Leader 实例保持待命状态
- Leader 故障时，其他实例可接管

## Integration Points

| Component | Interaction |
|-----------|-------------|
| Scanner | 调用 `scanner.run_full_scan()` |
| LeaseStore | 获取/释放调度器锁 |
| SqliteStore | 读取配置 |
| EventLog | 记录调度事件 |
