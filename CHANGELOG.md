# Changelog

## [Unreleased]

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
