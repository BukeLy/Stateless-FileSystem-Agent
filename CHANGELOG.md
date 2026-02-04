# Changelog

## [Unreleased]

## [0.3.0] - 2025-02-04

### Added
- **SQS FIFO 队列**: 升级为 FIFO 队列，保证同一会话内消息顺序处理
- **Telegram Webhook 安全验证**: 支持 `X-Telegram-Bot-Api-Secret-Token` HMAC 验证
- **本地命令 Handler 系统**: 支持 `static` (静态回复) 和 `handler` (处理函数) 两种类型
- **新命令**:
  - `/newchat` - 在群组 Forum 中创建新 Topic 开始独立对话
  - `/debug` - 下载当前会话的 session 文件 (conversation.jsonl, debug.txt, todos.json)
  - `/start` - 私聊欢迎消息
- **持续打字指示**: Consumer 每 4 秒发送打字状态，改善长请求时的用户体验
- **Markdown 转换管道**: 将 Agent 输出转换为 Telegram MarkdownV2 格式
- **消息时间戳**: `message_time` 字段透传到 Agent Server
- **Forum 群组支持**:
  - Bot 入群时自动检查 Topics 功能和权限
  - General Topic 拦截非命令消息，引导用户使用 `/newchat`
- **用户白名单**: 支持限制私聊和群组邀请权限

### Changed
- **Node.js 升级**: Docker 镜像升级到 Node.js 20+ (MCP undici 依赖要求)
- **HOME 目录**: 从 `/root` 改为 `/tmp` (MCP auth 文件写入兼容)
- **npm 缓存**: 配置 `/tmp/.npm` 目录
- **环境变量清理**: 移除重复的 `ANTHROPIC_DEFAULT_OPUS_4_5_MODEL`
- **Producer 权限扩展**: 新增 DynamoDB 读取和 S3 读取权限 (支持 /debug 命令)

### Fixed
- 移除无效的 `release-changelog.yml` workflow

## [0.2.0] - 2025-01-04

### Changed
- **架构调整：从同步到异步处理模式**
  - 重构SDK Client为SQS异步架构
  - Producer Lambda（SdkClientFunction）：接收Telegram webhook，立即返回200，消息写入SQS队列
  - Consumer Lambda（ConsumerFunction）：异步处理SQS消息，调用Agent Server，返回结果给Telegram
  - 解决Telegram 30秒webhook超时问题，支持长运行任务

### Added
- SQS任务队列（TaskQueue）和死信队列（DLQueue）
- SNS告警主题（AlarmTopic）用于CloudWatch通知
- CloudWatch告警和自定义指标监控
- DynamoDB会话表用于多轮对话状态管理

## [0.0.1-beta] - 2024-12-15

### Added
- 初始版本
- Claude Agent SDK 集成
- S3 + DynamoDB 会话持久化
- Telegram Bot 集成
- SubAgent 和 Skills 支持
- MCP 服务器集成
