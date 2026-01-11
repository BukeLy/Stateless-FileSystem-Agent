# Forum 群组安全设计

## 背景

Bot 设计上依赖 Telegram Forum (Topics) 功能，需要确保：
1. Bot 只在满足条件的群组中工作
2. 用户得到清晰的配置指引

## 安全策略

### 1. 用户白名单 (最高优先级)

非白名单用户拉 Bot 进群 → 直接退群，不做任何处理。

```python
if should_leave_group(update, config.user_whitelist):
    bot.leave_chat(chat_id)
    return
```

### 2. 入群预检

白名单用户拉 Bot 进群时，检查：
- `chat.is_forum` - 群组是否开启 Topics
- `can_manage_topics` - Bot 是否有 Topic 管理权限

预检失败时发送详细配置指引，但不退群（给用户配置时间）。

### 3. 消息过滤 (统一入口)

非 Forum 群组的消息在 producer 入口处直接忽略：

```python
# 群组消息：非 Forum 直接忽略
if message.chat.type in ('group', 'supergroup') and not message.chat.is_forum:
    return {'statusCode': 200}
```

**优点**：
- 一行代码，所有命令无需单独检查
- 私聊不受影响
- 用户已在入群时收到预检提示

## 处理流程

```
Bot 被添加到群组
       ↓
┌─────────────────────┐
│ 白名单检查          │
└─────────────────────┘
       ↓
    通过? ──No──→ 退群
       ↓ Yes
┌─────────────────────┐
│ Topic 预检          │
│ - is_forum?         │
│ - can_manage_topics?│
└─────────────────────┘
       ↓
    通过? ──No──→ 发送配置指引
       ↓ Yes
    正常工作

---

收到群组消息
       ↓
┌─────────────────────┐
│ is_forum 检查       │
└─────────────────────┘
       ↓
    是 Forum? ──No──→ 静默忽略
       ↓ Yes
    正常处理命令
```
