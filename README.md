# OmniCloud-Ops-Agent

[English](#english-documentation) | [中文](#中文文档)

A Serverless AI Agent system built on Claude Agent SDK, implementing stateful conversation persistence across stateless containers using S3+DynamoDB.

---

# English Documentation

## Project Overview

A Serverless AI Agent system built on Claude Agent SDK, implementing stateful conversation persistence across stateless containers using S3+DynamoDB.

> **Exploratory Project** | This project explores how to achieve stateful AI Agent sessions using FileSystem + Stateless Containers (AWS Lambda with Firecracker runtime as the foundation). It demonstrates how to maintain conversation persistence across stateless function invocations.

## Architecture

```
Telegram User → Bot API → API Gateway → sdk-client Lambda
                                             ↓
                             API Gateway → agent-container Lambda
                                             ↓
                             DynamoDB (Session mapping) + S3 (Session files) + Bedrock (Claude)
```

**Core Design**: Uses the Hybrid Sessions pattern recommended by Claude Agent SDK

## Features

- **Session Persistence**: DynamoDB for mapping storage, S3 for conversation history, cross-request recovery support
- **Multi-tenant Isolation**: Client isolation based on Telegram chat_id + thread_id
- **SubAgent Support**: Configurable specialized Agents (e.g., AWS support) with example implementations
- **Skills Support**: Reusable skill modules with hello-world example
- **MCP Integration**: Support for HTTP and local command-based MCP servers
- **Auto Cleanup**: 25-day TTL + S3 lifecycle management
- **Quick Start**: Provides example Skill/SubAgent/MCP configurations for adding other components

## Project Structure

```
├── agent-sdk-server/          # Agent Runtime (Docker Container)
│   ├── handler.py             # Lambda Entry Point
│   ├── agent_session.py       # SDK Wrapper
│   ├── session_store.py       # Session Persistence
│   └── claude-config/         # Configuration Files
│       ├── agents.json        # SubAgent Definitions
│       ├── mcp.json           # MCP Server Configuration
│       ├── skills/            # Skills Definitions
│       │   └── hello-world/   # Example Skill
│       └── system_prompt.md   # System Prompt
│
├── agent-sdk-client/          # Telegram Client (ZIP Deployment)
│   └── handler.py             # Webhook Handler
│
├── docs/                      # Documentation
│   └── anthropic-agent-sdk-official/  # SDK Official Docs Reference
│
├── template.yaml              # SAM Deployment Template
└── samconfig.toml             # SAM Configuration
```

## Deployment

### Prerequisites

- AWS CLI + SAM CLI
- Docker
- Amazon Bedrock access (Claude models)
- Telegram Bot Token

### Configuration

1. Copy and modify configuration files:
```bash
cp .env.example .env
# Edit .env to fill in required environment variables
```

2. Build and deploy:
```bash
sam build
sam deploy --guided
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SESSION_BUCKET` | S3 bucket name (auto-created) |
| `SESSION_TABLE` | DynamoDB table name (auto-created) |
| `BEDROCK_ACCESS_KEY_ID` | Bedrock access key |
| `BEDROCK_SECRET_ACCESS_KEY` | Bedrock secret key |
| `SDK_CLIENT_AUTH_TOKEN` | Internal authentication token |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |

## Tech Stack

- **Runtime**: Python 3.12 + Claude Agent SDK
- **Computing**: AWS Lambda (ARM64)
- **Storage**: S3 + DynamoDB
- **AI**: Claude via Amazon Bedrock
- **Orchestration**: AWS SAM
- **Integration**: Telegram Bot API + MCP

## Session Management

**Lifecycle**:
1. New message → Query DynamoDB mapping
2. Mapping exists → Download `conversation.jsonl` from S3 → Restore session
3. No mapping → Create new session → Save mapping to DynamoDB
4. Processing done → Upload updates to S3

**Persistent Files**:
- `conversation.jsonl` - Conversation history (required for restoration)
- `debug.txt` - Debug logs
- `todos.json` - Task status

## Configure SubAgents

Edit `agent-sdk-server/claude-config/agents.json`:

```json
{
  "agent-name": {
    "description": "Agent description",
    "prompt_file": "agents/prompt.md",
    "tools": ["specific tool name"],
    "model": "haiku"
  }
}
```

**Note**: The `tools` field does not support wildcards; you must specify complete tool names.

## Configure Skills

Create a new Skill in the `agent-sdk-server/claude-config/skills/` directory:

1. Create a folder: `skills/your-skill/`
2. Create a `SKILL.md` file with YAML frontmatter and Markdown description
3. Claude Agent SDK will auto-discover and use these Skills

Example: `skills/hello-world/SKILL.md`

## Configure MCP Servers

Edit `agent-sdk-server/claude-config/mcp.json`, supporting two types:

- **HTTP MCP**: HTTP endpoint pointing to remote MCP servers
- **Command-line MCP**: Start local MCP servers via `command` and `args`

Examples include AWS knowledge base MCP servers. Refer to existing configurations to add more MCP servers.

## Quick Start Examples

The project includes the following example components; follow these examples to add other components:

- **SubAgent Example**: `aws-support` Agent in `agents.json`
- **Skill Example**: `skills/hello-world/SKILL.md`
- **MCP Example**: AWS knowledge base and documentation MCP servers in `mcp.json`

## TODO

- [ ] Multi-tenant TenantID isolation

## License

MIT

---

# 中文文档

## 项目概述

基于 Claude Agent SDK 构建的 Serverless AI Agent 系统，通过 S3+DynamoDB 实现无状态容器的"有状态"会话持久化。

> **探索性项目** | 本项目旨在探索如何通过 FileSystem + 无状态容器（以 Firecracker 为底层的 AWS Lambda）实现有状态 AI Agent 会话。项目展示了在无状态函数调用间维持对话持久化的实现方式。

## 架构

```
Telegram User → Bot API → API Gateway → sdk-client Lambda
                                             ↓
                             API Gateway → agent-container Lambda
                                             ↓
                             DynamoDB (Session映射) + S3 (Session文件) + Bedrock (Claude)
```

**核心设计**：采用 Claude Agent SDK 官方推荐的 Hybrid Sessions 模式

## 特性

- **Session 持久化**：DynamoDB 存储映射，S3 存储对话历史，支持跨请求恢复
- **多租户隔离**：基于 Telegram chat_id + thread_id 实现客户端隔离
- **SubAgent 支持**：可配置多个专业 Agent（如 AWS 支持），包含示例实现
- **Skills 支持**：可复用的技能模块，包含 hello-world 示例
- **MCP 集成**：支持 HTTP 和本地命令类型的 MCP 服务器
- **自动清理**：25天 TTL + S3 生命周期管理
- **快速开始**：提供示例 Skill/SubAgent/MCP 配置，可按照示例添加其他组件

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
│   └── handler.py             # Webhook处理
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

## 技术栈

- **Runtime**: Python 3.12 + Claude Agent SDK
- **计算**: AWS Lambda (ARM64)
- **存储**: S3 + DynamoDB
- **AI**: Claude via Amazon Bedrock
- **编排**: AWS SAM
- **集成**: Telegram Bot API + MCP

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

## 配置 Skills

在 `agent-sdk-server/claude-config/skills/` 目录下创建新 Skill：

1. 创建文件夹：`skills/your-skill/`
2. 在文件夹中创建 `SKILL.md` 文件，包含 YAML 前置和 Markdown 描述
3. Claude Agent SDK 会自动发现并使用这些 Skills

参考示例：`skills/hello-world/SKILL.md`

## 配置 MCP 服务器

编辑 `agent-sdk-server/claude-config/mcp.json`，支持两种类型：

- **HTTP MCP**：指向远程 MCP 服务器的 HTTP 端点
- **命令行 MCP**：通过 `command` 和 `args` 启动本地 MCP 服务器

示例中配置了 AWS 知识库 MCP 服务器。可参考现有配置添加更多 MCP 服务器。

## 快速开始示例

项目已包含以下示例组件，可按照这些示例添加其他组件：

- **SubAgent 示例**：`agents.json` 中的 `aws-support` Agent
- **Skill 示例**：`skills/hello-world/SKILL.md`
- **MCP 示例**：`mcp.json` 中的 AWS 知识库和文档 MCP 服务器

## TODO

- [ ] 多租户 TenantID 隔离

## License

MIT
