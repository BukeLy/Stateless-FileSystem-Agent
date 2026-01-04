# 重构 SDK Client 为 SQS 异步架构

## 问题分析

**根本原因**: Lambda handler 在处理完成后才返回 200，而不是立即返回。

```python
def lambda_handler(event, context):
    asyncio.run(process_webhook(body))  # 阻塞 30-70s
    return {'statusCode': 200}           # 处理完才返回
```

**因果链**:
1. Telegram webhook → Lambda 开始处理
2. Lambda 等待 Agent Server 处理 (30-70s)
3. **Telegram 27-28s 后超时**，认为请求失败
4. Telegram 重试 → 启动第二个 Lambda
5. 两个 Lambda 并发处理 → 创建两个 session → 用户收到重复响应

**当前分支 `copilot/fix-sdk-client-blocking` 的问题**:
- DynamoDB 去重可以防止第二个请求处理消息
- 但第一个 Lambda **仍然阻塞 30-70s** 才返回 200
- Telegram 在 27s 时还是会超时重试
- **治标不治本**

## 方案评估结果

### Lambda Destination 方案 ❌
- API Gateway 返回 **202** (非 200)，不符合 Telegram 要求
- 无法获取执行结果返回给 Telegram
- 固定重试 2 次，不灵活

### SQS + Lambda Consumer 方案 ✅ (推荐)
- Producer 立即返回 **200 OK** 给 Telegram
- Consumer 异步处理，无超时限制
- 灵活重试策略 + DLQ
- 成本增量 < $1/月

## 实施计划

### 架构改动

```
原架构:
Telegram → API Gateway → SdkClient Lambda (同步等待 Agent Server) → 返回 200

新架构:
Telegram → API Gateway → Producer Lambda → 写入 SQS → 立即返回 200
                                            ↓
                                       SQS Queue
                                            ↓
                                    Consumer Lambda → Agent Server → Telegram
```

### 关键文件

1. **agent-sdk-client/handler.py** (重构为 Producer)
   - 保留消息解析逻辑
   - 移除去重和 Agent Server 调用
   - 新增 SQS 发送逻辑

2. **agent-sdk-client/consumer.py** (新建 Consumer)
   - 从 SQS 读取消息
   - 调用 Agent Server (原 `process_webhook` 逻辑)
   - 发送响应给 Telegram

3. **template.yaml** (SAM 配置)
   - 新增 `TaskQueue` (Standard 队列)
   - 新增 `DLQueue` (死信队列)
   - 新增 `ConsumerFunction` (Lambda)
   - 配置 SQS 触发器和 IAM 权限

### 代码改动概要

#### 1. Producer Lambda (伪代码)

```python
def lambda_handler(event, context):
    # 1. 解析 Telegram webhook
    body = parse_json(event['body'])

    # 2. 快速验证消息格式
    if not valid_telegram_message(body):
        return 200

    # 3. 写入 SQS
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=serialize(body)
    )

    # 4. 立即返回 200
    return 200
```

**关键改动**:
- 移除 `is_message_duplicate()` 调用
- 移除 `process_webhook()` 调用
- 响应时间: 30-70s → < 100ms

#### 2. Consumer Lambda (伪代码)

```python
def lambda_handler(event, context):
    for record in event['Records']:
        message = parse_json(record['body'])

        # 1. 发送 typing 状态
        telegram.send_chat_action(TYPING)

        # 2. 调用 Agent Server (原逻辑)
        result = httpx.post(
            agent_server_url,
            json={'user_message': message.text},
            timeout=600
        )

        # 3. 发送响应给 Telegram
        telegram.send_message(result.response)
```

**关键特性**:
- 无超时限制 (Lambda 最长 15 分钟)
- 异常自动重试 (maxReceiveCount=3)
- 失败进入 DLQ

#### 3. SAM Template 配置

```yaml
Resources:
  TaskQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 900  # = Lambda timeout
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt DLQueue.Arn
        maxReceiveCount: 3

  DLQueue:
    Type: AWS::SQS::Queue

  ConsumerFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: consumer.lambda_handler
      Events:
        SQSEvent:
          Type: SQS
          Properties:
            Queue: !GetAtt TaskQueue.Arn
            BatchSize: 1
```

### 用户确认的决策

1. ✅ **BatchSize=1**: 每条消息独立处理，失败不影响其他消息
2. ✅ **移除 DynamoDB 去重**: 简化架构，依赖 SQS 至少一次投递

### 部署步骤

1. 创建新分支 `feature/sqs-async-architecture`
2. 实施代码改动
3. 本地测试 (Mock SQS)
4. 部署到开发环境
5. 端到端测试
6. 部署到生产环境

### 预期收益

- ✅ Telegram Webhook 响应时间: 30-70s → < 1s
- ✅ 消除超时重试问题
- ✅ 提升用户体验 (立即收到确认)
- ✅ 更好的可观测性 (队列深度监控)
- ✅ 灵活的重试和错误处理
- ✅ 架构简化: 移除 DynamoDB 去重表

### 成本影响

- SQS 请求: ~$0.40/月 (10 万次调用)
- Lambda 调用翻倍: +$0.20/月
- **节省**: 移除 DynamoDB 去重表
- 总增量: **< $1/月**

### 可能的极少数重复场景

由于 SQS Standard 队列不保证恰好一次投递，以下场景**可能**出现重复:
- SQS 内部故障导致消息重复投递 (概率极低)
- Consumer Lambda 处理成功但删除消息前崩溃

**影响评估**:
- Telegram 用户可能极少数情况下收到重复响应
- Agent Server 会为同一个问题执行两次
- 如不可接受，可保留 DynamoDB 去重 (在 Consumer 端检查)
