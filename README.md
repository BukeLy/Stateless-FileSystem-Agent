# OmniCloud-Ops-Agent

基于 Claude Agent SDK 构建的 Serverless AI Agent 系统，通过 S3+DynamoDB 实现无状态容器的"有状态"会话持久化。

## 架构

```
Telegram User → Bot API → API Gateway → Producer Lambda → SQS Queue → Consumer Lambda
                                              ↓                            ↓
                                        立即返回 200              agent-server Lambda
                                                                        ↓
                                              DynamoDB (Session映射) + S3 (Session文件) + Bedrock (Claude)
```

**核心设计**：
- 采用 Claude Agent SDK 官方推荐的 Hybrid Sessions 模式
- **SQS 异步架构**：Producer 立即返回 200 给 Telegram，Consumer 异步处理请求

## 特性

- **Session 持久化**：DynamoDB 存储映射，S3 存储对话历史，支持跨请求恢复
- **多租户隔离**：基于 Telegram chat_id + thread_id 实现客户端隔离
- **SubAgent 支持**：可配置多个专业 Agent（如 AWS 支持）
- **Skills 支持**：可复用的技能模块
- **MCP 集成**：支持 HTTP 和本地命令类型的 MCP 服务器
- **自动清理**：25天 TTL + S3 生命周期管理
- **SQS 队列**：异步处理 + 自动重试 + 死信队列

## 项目结构

```
├── agent-sdk-server/          # Agent Runtime (Docker容器)
│   ├── handler.py             # Lambda入口
│   ├── agent_session.py       # SDK包装器
│   ├── session_store.py       # Session持久化
│   └── claude-config/         # 配置文件
│       ├── agents.json        # SubAgent定义
│       ├── mcp.json           # MCP服务器配置
│       ├── skills/            # Skills定义
│       │   └── hello-world/   # 示例 Skill
│       └── system_prompt.md   # 系统提示
│
├── agent-sdk-client/          # Telegram客户端 (ZIP部署)
│   ├── handler.py             # Producer: Webhook接收，写入SQS
│   ├── consumer.py            # Consumer: SQS消费，调用Agent
│   └── config.py              # 配置管理
│
├── docs/                      # 文档
│   └── anthropic-agent-sdk-official/  # SDK官方文档参考
│
├── template.yaml              # SAM部署模板
└── samconfig.toml             # SAM配置
```

## 部署

### 前置条件

- AWS CLI + SAM CLI
- Docker
- Amazon Bedrock 访问权限（Claude模型）
- Telegram Bot Token

### 配置

1. 复制并修改配置文件：
```bash
cp .env.example .env
# 编辑 .env 填入必要的环境变量
```

2. 构建和部署：
```bash
sam build
sam deploy --guided
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `SESSION_BUCKET` | S3桶名称（自动创建） |
| `SESSION_TABLE` | DynamoDB表名（自动创建） |
| `BEDROCK_ACCESS_KEY_ID` | Bedrock访问密钥 |
| `BEDROCK_SECRET_ACCESS_KEY` | Bedrock密钥 |
| `SDK_CLIENT_AUTH_TOKEN` | 内部认证Token |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `QUEUE_URL` | SQS队列URL（自动创建） |

## 技术栈

- **Runtime**: Python 3.12 + Claude Agent SDK
- **计算**: AWS Lambda (ARM64)
- **存储**: S3 + DynamoDB
- **消息队列**: AWS SQS (Standard Queue + DLQ)
- **AI**: Claude via Amazon Bedrock
- **编排**: AWS SAM
- **集成**: Telegram Bot API + MCP

## SQS 异步架构

**解决的问题**：Telegram Webhook 在 ~27s 后超时重试，而 Agent 处理可能需要 30-70s，导致重复响应。

**解决方案**：
1. Producer Lambda 接收 Webhook，写入 SQS，立即返回 200（<1s）
2. Consumer Lambda 从 SQS 消费，调用 Agent Server，发送响应给 Telegram
3. 失败重试 3 次，最终失败进入死信队列（DLQ）

**队列配置**：
- VisibilityTimeout: 900s（= Lambda 超时）
- maxReceiveCount: 3（重试 3 次）
- DLQ 告警：消息进入 DLQ 时触发 CloudWatch 告警

## Session 管理

**生命周期**：
1. 新消息 → 查询 DynamoDB 映射
2. 存在映射 → 从 S3 下载 `conversation.jsonl` → 恢复会话
3. 不存在 → 创建新 session → 保存映射到 DynamoDB
4. 处理完成 → 上传更新到 S3

**持久化文件**：
- `conversation.jsonl` - 对话历史（恢复必需）
- `debug.txt` - 调试日志
- `todos.json` - 任务状态

## 配置 SubAgent

编辑 `agent-sdk-server/claude-config/agents.json`：

```json
{
  "agent-name": {
    "description": "Agent描述",
    "prompt_file": "agents/prompt.md",
    "tools": ["具体工具名称"],
    "model": "haiku"
  }
}
```

**注意**：`tools` 字段不支持通配符，必须指定完整工具名称。

## TODO

- [ ] 多租户 TenantID 隔离

## License

MIT
