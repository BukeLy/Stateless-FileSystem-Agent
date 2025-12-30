# Agent SDK Server - 任务清单

参考: https://github.com/anthropics/claude-agent-sdk-demos/tree/main/simple-chatapp

## 文件结构

```
agent-sdk-server/
├── agent_session.py    # AgentSession 类 (参考 ai-client.ts)
├── session_store.py    # SessionStore 类 (参考 chat-store.ts)
├── handler.py          # Lambda Handler 入口
├── config.py           # 配置管理
├── Dockerfile          # Container 镜像
└── TASKLIST.md
```

## 已完成 ✅

### 1. agent_session.py
- [x] `setup_bedrock_profile()` - Lambda 环境下 Bedrock 凭证配置
- [x] `process_message()` 函数 - 流式处理消息
  - [x] 支持 `session_id` 参数 (None = 新会话, str = 恢复)
  - [x] `ClaudeAgentOptions` 配置 (model, permission_mode, max_turns, allowed_tools)
  - [x] 处理 `AssistantMessage` 和 `ResultMessage`
  - [x] 返回: response, session_id, cost_usd, num_turns, is_error, error_message

### 2. session_store.py
- [x] `SessionStore` 类
  - [x] `get_session_id(chat_id, thread_id)` - 从 DynamoDB 查询映射
  - [x] `save_session_id(chat_id, thread_id, session_id)` - 保存映射
  - [x] `update_session_timestamp()` - 更新时间戳和 TTL
  - [x] `download_session_files(session_id)` - 从 S3 下载 session 文件
  - [x] `upload_session_files(session_id)` - 上传 session 文件到 S3

### 3. handler.py
- [x] Lambda 入口 `lambda_handler(event, context)`
- [x] 输入格式: `{"user_message": "xxx", "chat_id": "123", "thread_id": "opt", "model": "sonnet"}`
- [x] 输出格式: `{"response": "xxx", "session_id": "xxx", "cost_usd": 0.01, ...}`
- [x] Auth Token 验证
- [x] 流程: 解析输入 → 查询session → 下载文件 → 调用Agent → 保存mapping → 上传文件 → 返回

### 4. config.py
- [x] `Config` dataclass - 环境变量配置
- [x] `BedrockConfig` dataclass - Bedrock 配置

### 5. Dockerfile
- [x] 基于 `public.ecr.aws/lambda/python:3.12-arm64`
- [x] 安装 uv, nodejs, npm
- [x] 安装 Claude Code CLI (`@anthropic-ai/claude-code`)
- [x] 安装 Python 依赖 (boto3, claude-agent-sdk)
- [x] 创建 ~/.claude 和 ~/.aws 目录

## 待跟进 📋

### 部署与测试
- [ ] 构建并推送 Docker 镜像到 ECR
- [ ] 创建 Lambda 函数 (Container Image)
- [ ] 创建 DynamoDB 表 (`session_key` 为主键)
- [ ] 创建 S3 存储桶
- [ ] 配置 Lambda 环境变量
- [ ] 端到端测试

### 集成
- [ ] 与 TicketBot 集成测试
- [ ] API Gateway 配置 (如需要)

## 环境变量

| 变量 | 说明 |
|------|------|
| `SESSION_BUCKET` | S3 存储桶 |
| `SESSION_TABLE` | DynamoDB 表名 |
| `PROJECT_PATH` | 项目路径标识 (默认 `-tmp-workspace`) |
| `SDK_CLIENT_AUTH_TOKEN` | API 认证 Token |
| `BEDROCK_ACCESS_KEY_ID` | Bedrock 专用 Access Key |
| `BEDROCK_SECRET_ACCESS_KEY` | Bedrock 专用 Secret Key |
| `CLAUDE_CODE_USE_BEDROCK` | 设为 `1` |

## 依赖

- claude-agent-sdk
- boto3
- @anthropic-ai/claude-code (npm)
