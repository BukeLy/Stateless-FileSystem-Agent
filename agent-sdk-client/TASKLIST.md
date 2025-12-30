# Agent SDK Client - 任务清单

Telegram Webhook Lambda (轻量级，zip 部署)

## 文件结构

```
agent-sdk-client/
├── handler.py          # Lambda Handler 入口
├── telegram_bot.py     # Telegram API 客户端
├── config.py           # 配置管理
└── TASKLIST.md
```

## 待实现

### 1. config.py
- [ ] `Config` dataclass
  - `telegram_bot_token`
  - `telegram_webhook_secret`
  - `agent_function_name` (Agent Lambda ARN)
  - `aws_region`
- [ ] `Config.from_env()` 从环境变量加载

### 2. telegram_bot.py
- [ ] `TelegramMessage` dataclass
  - `chat_id`, `message_id`, `text`, `thread_id`
  - `from_webhook(data)` 解析 Webhook payload
- [ ] `TelegramBot` 类
  - `send_message(chat_id, text, thread_id)`
  - `send_chat_action(chat_id, action, thread_id)`
  - `verify_webhook_secret(secret, expected)`
- [ ] 使用 httpx 异步客户端

### 3. handler.py
- [ ] `lambda_handler(event, context)`
- [ ] 流程:
  1. 验证 Webhook secret
  2. 解析 Telegram 消息
  3. 立即返回 200 OK
  4. 异步调用 Agent Lambda (`boto3.client('lambda').invoke_async`)
  5. 等待响应
  6. 发送 Telegram 回复
- [ ] 错误处理

## 环境变量

| 变量 | 说明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Bot Token |
| `TELEGRAM_WEBHOOK_SECRET` | Webhook 验证密钥 |
| `AGENT_FUNCTION_NAME` | Agent Lambda ARN |
| `AWS_REGION` | 区域 |

## 依赖

- httpx
- boto3

## SAM 部署

在根目录创建 `template.yaml`:
- 定义两个 Lambda: WebhookHandler (zip) + AgentContainer (ECR)
- API Gateway HTTP API
- S3 + DynamoDB
- IAM 权限
