# Notification Setup Guide

## Overview

PT Invite Watcher 支持两种通知渠道：
- **Telegram Bot**
- **企业微信应用消息**

## Telegram 通知

### 1. 创建 Bot

1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令
3. 按提示设置 Bot 名称
4. 获取 **Bot Token**（格式：`123456:ABC-DEF...`）

### 2. 获取 Chat ID

**方式一：私聊**
1. 向你的 Bot 发送任意消息
2. 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. 找到 `chat.id` 字段

**方式二：群组**
1. 将 Bot 添加到群组
2. 在群组中发送消息
3. 访问上述 URL 获取群组 Chat ID（负数）

### 3. 配置

**Web UI:**
1. 访问 配置 → 通知设置
2. 启用 Telegram
3. 填写 Token 和 Chat ID
4. 点击「测试」验证

**API:**
```bash
curl -X PUT "http://localhost:8003/api/config/notifications" \
  -H "Content-Type: application/json" \
  -d '{
    "telegram": {
        "enabled": true,
        "token": "123456:ABC-DEF...",
        "chat_id": "12345678"
    }
  }'
```

## 企业微信通知

### 1. 创建企业应用

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/)
2. 进入 应用管理 → 应用 → 创建应用
3. 获取以下信息：
   - **CorpID**：企业 ID（在 我的企业 页面）
   - **AgentID**：应用 ID
   - **Secret**：应用密钥

### 2. 配置可信 IP

1. 进入应用设置
2. 配置 API 接收 → 企业可信 IP
3. 添加运行 PT Invite Watcher 的服务器 IP

### 3. 配置

**Web UI:**
1. 访问 配置 → 通知设置
2. 启用企业微信
3. 填写 CorpID、Secret、AgentID
4. 设置接收者（默认 @all）
5. 点击「测试」验证

**API:**
```bash
curl -X PUT "http://localhost:8003/api/config/notifications" \
  -H "Content-Type: application/json" \
  -d '{
    "wecom": {
        "enabled": true,
        "corpid": "ww1234567890",
        "app_secret": "xxx",
        "agent_id": "1000001",
        "to_user": "@all",
        "to_party": "",
        "to_tag": ""
    }
  }'
```

### 接收者配置

| 字段 | 说明 |
|------|------|
| `to_user` | 用户 ID，多个用 `|` 分隔，`@all` 表示所有人 |
| `to_party` | 部门 ID，多个用 `|` 分隔 |
| `to_tag` | 标签 ID，多个用 `|` 分隔 |

## 通知触发条件

以下情况会触发通知：

1. **站点开放注册**
   - 状态从 `closed` 变为 `open`

2. **邀请名额变化**
   - 状态从 `closed` 变为 `open`
   - 可用数量增加

3. **连通性变化**
   - 站点从不可达变为可达
   - 站点从可达变为不可达

## 通知消息格式

```
🎉 站点状态变更

站点：Example Site (example.com)
注册：closed → open
邀请：5 个可用
时间：2024-01-01 12:00:00
```

## 测试通知

### Web UI

点击对应渠道的「测试」按钮。

### API

```bash
# 测试 Telegram
curl -X POST "http://localhost:8003/api/config/notifications/test/telegram"

# 测试企业微信
curl -X POST "http://localhost:8003/api/config/notifications/test/wecom"
```

## 故障排查

### Telegram 发送失败

1. 检查 Token 是否正确
2. 检查 Chat ID 是否正确
3. 确保 Bot 已加入聊天/群组
4. 检查网络是否可访问 Telegram API

### 企业微信发送失败

1. 检查 CorpID、Secret、AgentID 是否正确
2. 检查可信 IP 是否已配置
3. 检查 Access Token 是否有效
4. 查看日志获取详细错误码

### 通知设置

**Location:** `notify/manager.py`

通知配置存储在 `kv.notifications`：

```json
{
    "telegram": {
        "enabled": true,
        "token": "xxx",
        "chat_id": "xxx"
    },
    "wecom": {
        "enabled": true,
        "corpid": "xxx",
        "app_secret": "xxx",
        "agent_id": "xxx",
        "to_user": "@all",
        "to_party": "",
        "to_tag": ""
    }
}
```

## 代码位置

| 模块 | 文件 | 说明 |
|------|------|------|
| 通知管理器 | `notify/manager.py` | 渠道调度 |
| Telegram | `notify/telegram.py` | Telegram Bot API |
| 企业微信 | `notify/wecom.py` | WeCom API |
