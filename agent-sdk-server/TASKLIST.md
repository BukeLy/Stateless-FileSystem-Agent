# Agent SDK Server - 任务清单

参考: https://github.com/anthropics/claude-agent-sdk-demos/tree/main/simple-chatapp

## 文件结构

```
agent-sdk-server/
├── agent_session.py    # AgentSession 类 (参考 ai-client.ts)
├── session_store.py    # SessionStore 类 (参考 chat-store.ts)
├── handler.py          # Lambda Handler 入口
├── Dockerfile          # Container 镜像
└── TASKLIST.md
```

## 待实现

### 1. agent_session.py
- [ ] `AgentSession` 类
  - `__init__(session_id: Optional[str])` - 初始化，支持 resume
  - `send_message(prompt: str) -> AsyncIterator[dict]` - 流式返回响应
  - `_create_options() -> ClaudeAgentOptions` - 创建配置
- [ ] 使用 `ClaudeSDKClient` 管理会话
- [ ] 处理消息类型: `TextBlock`, `ToolUseBlock`, `ToolResultBlock`, `ResultMessage`

### 2. session_store.py
- [ ] `SessionStore` 类
  - DynamoDB: `chat_id:thread_id` → `session_id` 映射
  - S3: session 文件存储
- [ ] 方法:
  - `get_session_id(chat_id, thread_id)` - 查询映射
  - `save_session_mapping(chat_id, session_id, thread_id)` - 保存映射
  - `download_session(session_id)` - 从 S3 下载到 `~/.claude/`
  - `upload_session(session_id)` - 上传到 S3

### 3. handler.py
- [ ] Lambda 入口 `lambda_handler(event, context)`
- [ ] 输入格式: `{"prompt": "xxx", "session_id": "xxx", "chat_id": 123}`
- [ ] 输出格式: `{"response": "xxx", "session_id": "xxx"}`
- [ ] 流程:
  1. 解析输入
  2. 下载 session (如有)
  3. 调用 AgentSession
  4. 上传 session
  5. 返回响应

### 4. Dockerfile
- [ ] 基于 `public.ecr.aws/lambda/python:3.12`
- [ ] 安装 Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- [ ] 复制代码和依赖
- [ ] 设置 `CLAUDE_CODE_USE_BEDROCK=1`

## 环境变量

| 变量 | 说明 |
|------|------|
| `SESSION_BUCKET` | S3 存储桶 |
| `SESSION_TABLE` | DynamoDB 表名 |
| `CLAUDE_CODE_USE_BEDROCK` | 设为 `1` |
| `AWS_REGION` | Bedrock 区域 |

## 依赖

- claude-agent-sdk
- boto3
- loguru
