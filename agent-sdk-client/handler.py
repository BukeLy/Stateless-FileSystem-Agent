"""Lambda handler for sdk-client (Producer).

Receives Telegram webhook, writes to SQS, returns 200 immediately.
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError
from telegram import Bot, Update

from config import Config
from security import is_user_allowed, should_leave_group, verify_telegram_secret_token

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Reuse boto3 clients across invocations (Lambda container reuse)
_sqs_client = None
_cloudwatch_client = None
_dynamodb_resource = None
_s3_client = None


def _get_sqs_client():
    """Get or create SQS client singleton."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client('sqs')
    return _sqs_client


def _get_cloudwatch_client():
    """Get or create CloudWatch client singleton."""
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client('cloudwatch')
    return _cloudwatch_client


def _get_dynamodb_resource():
    """Get or create DynamoDB resource singleton."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource('dynamodb')
    return _dynamodb_resource


def _get_s3_client():
    """Get or create S3 client singleton."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3')
    return _s3_client


def _send_metric(metric_name: str, value: float = 1.0):
    """Send custom metric to CloudWatch (non-blocking)."""
    try:
        cloudwatch = _get_cloudwatch_client()
        cloudwatch.put_metric_data(
            Namespace='OmniCloudAgent/Producer',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': 'Count',
                }
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to send CloudWatch metric: {e}")


def _send_to_sqs_safe(sqs, queue_url: str, message_body: dict) -> bool:
    """Send message to SQS FIFO queue with comprehensive error handling.

    Uses chat_id:thread_id as MessageGroupId to ensure same-session ordering.

    Returns:
        True if message sent successfully, False otherwise.
    """
    try:
        # FIFO queue requires MessageGroupId and MessageDeduplicationId
        chat_id = message_body.get('chat_id')
        thread_id = message_body.get('thread_id') or 'default'
        message_group_id = f"{chat_id}:{thread_id}"
        dedup_id = f"{chat_id}-{message_body.get('message_id')}-{uuid.uuid4().hex[:8]}"

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageGroupId=message_group_id,
            MessageDeduplicationId=dedup_id,
        )
        message_id = response.get('MessageId', 'unknown')
        logger.info(f"Message sent to SQS: {message_id}, group: {message_group_id}")
        _send_metric('SQSMessageSent')
        return True

    except sqs.exceptions.QueueDoesNotExist:
        logger.error(
            f"CRITICAL: Queue does not exist: {queue_url}",
            extra={'queue_url': queue_url},
        )
        _send_metric('SQSError.QueueNotFound')
        return False

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', '')

        if error_code in ('AccessDenied', 'AccessDeniedException'):
            logger.error(
                f"CRITICAL: IAM permission denied for SQS: {error_msg}",
                extra={'error_code': error_code, 'queue_url': queue_url},
            )
            _send_metric('SQSError.AccessDenied')

        elif error_code in ('ThrottlingException', 'RequestThrottled'):
            logger.warning(
                f"SQS throttled (will be retried by consumer): {error_msg}",
                extra={'error_code': error_code},
            )
            _send_metric('SQSError.Throttled')

        elif error_code == 'InvalidParameterValue':
            logger.error(
                f"CRITICAL: Invalid SQS parameter: {error_msg}",
                extra={'error_code': error_code, 'message_body': message_body},
            )
            _send_metric('SQSError.InvalidParameter')

        else:
            logger.error(
                f"SQS ClientError [{error_code}]: {error_msg}",
                extra={'error_code': error_code, 'error_msg': error_msg},
            )
            _send_metric(f'SQSError.{error_code}')

        return False

    except Exception as e:
        logger.exception(
            f"Unexpected error sending to SQS: {e}",
            extra={'exception_type': type(e).__name__},
        )
        _send_metric('SQSError.Unexpected')
        return False


# Handler type 命令处理器映射
HANDLER_TYPE_HANDLERS = {
    'newchat': '_handle_newchat_handler',
    'start': '_handle_start_handler',
    'debug': '_handle_debug_handler',
}


def _handle_newchat_handler(bot: Bot, message, body: dict, config: Config, sqs) -> bool:
    """处理 /newchat - 创建 Topic 后发 SQS 调用 Agent。

    Returns:
        True: 已完全处理
    """
    # 限制只能在 General Topic 执行 (General Topic ID 为 1 或 None)
    if message.message_thread_id and message.message_thread_id != 1:
        asyncio.run(
            bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ /newchat 只能在主频道中使用",
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
            )
        )
        return True

    parts = message.text.strip().split(maxsplit=1)
    prompts = parts[1] if len(parts) > 1 else ''

    if not prompts:
        asyncio.run(
            bot.send_message(
                chat_id=message.chat_id,
                text="用法: /newchat <消息内容>",
                message_thread_id=message.message_thread_id,
            )
        )
        return True

    asyncio.run(_handle_newchat_async(bot, message, body, config, sqs, prompts))
    return True


def _handle_start_handler(bot: Bot, message, body: dict, config: Config, sqs) -> bool:
    """私聊 /start - 发送欢迎消息。"""
    if message.chat.type != 'private':
        return True
    asyncio.run(bot.send_message(
        chat_id=message.chat_id,
        text="👋 欢迎！直接发送消息即可开始对话。",
    ))
    return True


def _handle_debug_handler(bot: Bot, message, body: dict, config: Config, sqs) -> bool:
    """处理 /debug - 下载当前会话的 session 文件并发送给用户。"""
    asyncio.run(_handle_debug_async(bot, message))
    return True


async def _handle_debug_async(bot: Bot, message) -> None:
    """异步处理 /debug 命令。"""
    import tempfile
    from pathlib import Path

    chat_id = str(message.chat_id)
    thread_id = str(message.message_thread_id) if message.message_thread_id else 'default'

    # 1. 查询 DynamoDB 获取 session_id
    session_key = f"{chat_id}:{thread_id}"
    session_table = os.environ.get('SESSION_TABLE')
    session_bucket = os.environ.get('SESSION_BUCKET')

    if not session_table or not session_bucket:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ 环境变量未配置 (SESSION_TABLE/SESSION_BUCKET)",
            message_thread_id=message.message_thread_id,
        )
        return

    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(session_table)

    try:
        response = table.get_item(Key={'session_key': session_key})
    except Exception as e:
        logger.error(f"DynamoDB query failed: {e}")
        await bot.send_message(
            chat_id=message.chat_id,
            text=f"❌ 查询会话失败: {str(e)[:100]}",
            message_thread_id=message.message_thread_id,
        )
        return

    if 'Item' not in response:
        await bot.send_message(
            chat_id=message.chat_id,
            text="❌ 当前会话无历史记录",
            message_thread_id=message.message_thread_id,
        )
        return

    session_id = response['Item']['session_id']

    # 2. 从 S3 下载文件
    s3 = _get_s3_client()

    files_to_send = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for s3_name in ['conversation.jsonl', 'debug.txt', 'todos.json']:
            s3_key = f'sessions/{session_id}/{s3_name}'
            local_path = Path(tmpdir) / s3_name
            try:
                s3.download_file(session_bucket, s3_key, str(local_path))
                files_to_send.append(local_path)
            except Exception:
                pass  # 文件可能不存在

        # 3. 发送文件到 Telegram
        if not files_to_send:
            await bot.send_message(
                chat_id=message.chat_id,
                text=f"❌ Session `{session_id}` 无可用文件",
                parse_mode='MarkdownV2',
                message_thread_id=message.message_thread_id,
            )
            return

        # 转义 session_id 中的特殊字符
        escaped_session_id = session_id.replace('-', r'\-').replace('.', r'\.')
        await bot.send_message(
            chat_id=message.chat_id,
            text=f"📦 Session: `{escaped_session_id}`",
            parse_mode='MarkdownV2',
            message_thread_id=message.message_thread_id,
        )

        for file_path in files_to_send:
            with open(file_path, 'rb') as f:
                await bot.send_document(
                    chat_id=message.chat_id,
                    document=f,
                    filename=file_path.name,
                    message_thread_id=message.message_thread_id,
                )


def _handle_local_command(
    bot: Bot, message, body: dict, config: Config, sqs, cmd: str
) -> bool:
    """处理 local command，根据配置的 type 分发。

    Returns:
        True: 已完全处理，不需要发 SQS
    """
    local_cmd = config.get_local_command(cmd)

    if not local_cmd:
        # 未知命令
        text = config.unknown_command_message()
        try:
            asyncio.run(
                bot.send_message(
                    chat_id=message.chat_id,
                    text=text,
                    message_thread_id=message.message_thread_id,
                    reply_to_message_id=message.message_id,
                )
            )
        except Exception:
            logger.warning("Failed to send unknown command response", exc_info=True)
        return True

    if local_cmd.type == 'static':
        # 静态回复
        try:
            asyncio.run(
                bot.send_message(
                    chat_id=message.chat_id,
                    text=local_cmd.response,
                    message_thread_id=message.message_thread_id,
                    reply_to_message_id=message.message_id,
                )
            )
        except Exception:
            logger.warning("Failed to send static command response", exc_info=True)

    elif local_cmd.type == 'handler':
        # 调用 handler 函数
        handler_name = HANDLER_TYPE_HANDLERS.get(local_cmd.handler)
        if handler_name:
            handler_func = globals().get(handler_name)
            if handler_func:
                return handler_func(bot, message, body, config, sqs)
            else:
                logger.error(f"Handler function {handler_name} not found")
        else:
            logger.error(f"Unknown handler: {local_cmd.handler}")

    logger.info(
        'Handled local command',
        extra={
            'chat_id': message.chat_id,
            'message_id': message.message_id,
            'cmd': cmd,
            'type': local_cmd.type,
        },
    )
    return True


MSG_NO_FORUM = (
    "⚠️ 群组未开启 Topics 功能\n\n"
    "请按以下步骤开启:\n"
    "1. 打开群组设置\n"
    "2. 点击「Topics」\n"
    "3. 开启 Topics 功能\n"
    "4. 重新添加 Bot"
)

MSG_NO_PERMISSION = (
    "⚠️ Bot 缺少「管理 Topics」权限\n\n"
    "请按以下步骤授权:\n"
    "1. 打开群组设置 > 管理员\n"
    "2. 选择此 Bot\n"
    "3. 开启「Manage Topics」权限"
)


async def _check_forum_requirements(bot: Bot, chat_id: int) -> tuple[bool, str]:
    """检查群组 Topic 功能要求。"""
    try:
        chat = await bot.get_chat(chat_id)
        if not chat.is_forum:
            return False, MSG_NO_FORUM

        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        if not getattr(member, 'can_manage_topics', False):
            return False, MSG_NO_PERMISSION
        return True, ""
    except Exception as e:
        logger.warning(f"Failed to check forum requirements: {e}")
        return False, f"检查权限失败: {str(e)[:100]}"


async def _on_bot_joined(bot: Bot, chat_id: int) -> None:
    """Bot 入群时：检查 is_forum，提示授予管理员权限。"""
    try:
        chat = await bot.get_chat(chat_id)
        if not chat.is_forum:
            await bot.send_message(chat_id=chat_id, text=MSG_NO_FORUM)
            _send_metric('TopicPrecheck.NoForum')
        else:
            await bot.send_message(
                chat_id=chat_id,
                text="👋 已加入群组！请将 Bot 设为管理员并授予「管理 Topics」权限。",
            )
    except Exception as e:
        logger.warning(f"Failed to check forum: {e}")


async def _on_bot_promoted(bot: Bot, chat_id: int) -> None:
    """Bot 被提升为管理员时：检查权限，发送欢迎消息。"""
    is_ok, error_msg = await _check_forum_requirements(bot, chat_id)
    if not is_ok:
        await bot.send_message(chat_id=chat_id, text=error_msg)
        _send_metric('TopicPrecheck.Failed')
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="👋 欢迎使用！使用 /newchat <消息> 开始新对话。",
        )
        _send_metric('TopicPrecheck.Success')


async def _handle_newchat_async(
    bot: Bot, message, body: dict, config: Config, sqs, prompts: str
) -> bool:
    """处理 /newchat 的异步部分 - 创建 Topic 并发送消息到 SQS。

    Args:
        bot: Telegram Bot 实例
        message: Telegram Message 对象
        body: 原始 webhook body (用于构造 SQS 消息)
        config: 配置对象
        sqs: SQS 客户端
        prompts: 用户输入的消息内容

    Returns:
        True 如果成功，False 如果失败
    """
    from datetime import datetime

    chat_id = message.chat_id
    topic_name = f"Chat {datetime.now().strftime('%m/%d %H:%M')}"

    try:
        forum_topic = await bot.create_forum_topic(chat_id=chat_id, name=topic_name)
        new_thread_id = forum_topic.message_thread_id

        # 发送确认消息到原位置（General Topic）
        # Telegram 私有群 Topic 链接格式: t.me/c/<channel>/<thread_id>/<message_id>
        # Topic ID 就是创建该 Topic 的服务消息 ID，所以用 thread_id 作为 message_id
        internal_chat_id = str(chat_id).replace('-100', '')
        topic_link = f"https://t.me/c/{internal_chat_id}/{new_thread_id}/{new_thread_id}"

        # 显示名称: 用消息前20字
        display_name = prompts[:20] + ('...' if len(prompts) > 20 else '')

        await bot.send_message(
            chat_id=chat_id,
            text=f'✅ 已创建新对话: <a href="{topic_link}">{display_name}</a>',
            parse_mode='HTML',
            message_thread_id=message.message_thread_id,
            reply_to_message_id=message.message_id,
        )

        # 使用标准 SQS 消息格式，覆盖 text 和 thread_id
        message_body = {
            'telegram_update': body,
            'chat_id': chat_id,
            'message_id': message.message_id,
            'text': prompts,
            'thread_id': new_thread_id,
        }

        success = _send_to_sqs_safe(sqs, config.queue_url, message_body)
        if not success:
            await bot.send_message(
                chat_id=chat_id,
                text="发送消息失败，请重试",
                message_thread_id=new_thread_id,
            )
        return success

    except Exception as e:
        logger.warning(f"Failed to create forum topic: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text=f"创建 Topic 失败: {str(e)[:100]}",
            message_thread_id=message.message_thread_id,
        )
        return False


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda entry point - Producer.

    Validates Telegram message and writes to SQS queue.
    Returns 200 immediately without waiting for processing.
    """
    # Verify Telegram secret token (if configured)
    headers = event.get('headers', {})
    request_token = headers.get('x-telegram-bot-api-secret-token')
    expected_token = os.getenv('TELEGRAM_WEBHOOK_SECRET')

    if not verify_telegram_secret_token(request_token, expected_token):
        logger.warning('Invalid or missing Telegram secret token')
        _send_metric('SecurityBlock.InvalidSecretToken')
        return {'statusCode': 401}

    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        logger.warning('Invalid JSON in webhook body')
        return {'statusCode': 200}

    config = Config.from_env()

    # Quick validation - parse update to check if it's a valid message
    bot = Bot(config.telegram_token)
    update = Update.de_json(body, bot)

    if not update:
        logger.debug('Ignoring non-update webhook')
        return {'statusCode': 200}

    if update.my_chat_member:
        if should_leave_group(update, config.user_whitelist):
            chat_id = update.my_chat_member.chat.id
            inviter_id = update.my_chat_member.from_user.id
            asyncio.run(bot.leave_chat(chat_id))
            logger.info(
                f"Left unauthorized group",
                extra={'chat_id': chat_id, 'inviter_id': inviter_id},
            )
            _send_metric('SecurityBlock.UnauthorizedGroup')
        else:
            member_update = update.my_chat_member
            old_status = member_update.old_chat_member.status
            new_status = member_update.new_chat_member.status
            chat_id = member_update.chat.id

            if old_status in ('left', 'kicked') and new_status in ('member', 'administrator'):
                asyncio.run(_on_bot_joined(bot, chat_id))
            elif old_status == 'member' and new_status == 'administrator':
                asyncio.run(_on_bot_promoted(bot, chat_id))
        return {'statusCode': 200}

    message = update.message or update.edited_message
    if not message or not message.text:
        logger.debug('Ignoring webhook without text message')
        return {'statusCode': 200}

    # Check private message whitelist
    if message.chat.type == 'private':
        user_id = message.from_user.id if message.from_user else None
        if user_id and not is_user_allowed(user_id, config.user_whitelist):
            logger.info(
                f"Blocked private message from unauthorized user",
                extra={'user_id': user_id},
            )
            _send_metric('SecurityBlock.UnauthorizedPrivate')
            return {'statusCode': 200}

    # 群组消息：非 Forum 直接忽略（用户入群时已收到预检提示）
    if message.chat.type in ('group', 'supergroup') and not message.chat.is_forum:
        return {'statusCode': 200}

    # 拦截 General Topic (message_thread_id=1 或 None) 的普通消息
    if message.chat.type in ('group', 'supergroup') and message.chat.is_forum:
        thread_id = message.message_thread_id
        if thread_id is None or thread_id == 1:
            # 仅拦截非命令消息
            if not message.text.startswith('/'):
                asyncio.run(bot.send_message(
                    chat_id=message.chat_id,
                    text="⚠️ 请到具体的对话窗口中与 AI 对话，本 Topic 仅限创建新对话。\n\n使用 /newchat <消息> 创建新对话。",
                    message_thread_id=thread_id,
                    reply_to_message_id=message.message_id,
                ))
                return {'statusCode': 200}

    cmd = config.get_command(message.text)
    sqs = _get_sqs_client()

    # Local command 统一处理 (包括 /newchat)
    if cmd and config.is_local_command(cmd):
        _handle_local_command(bot, message, body, config, sqs, cmd)
        return {'statusCode': 200}

    # 未知命令
    if cmd and not config.is_agent_command(cmd):
        _handle_local_command(bot, message, body, config, sqs, cmd)
        return {'statusCode': 200}

    # Write to SQS for async processing
    message_body = {
        'telegram_update': body,
        'chat_id': message.chat_id,
        'message_id': message.message_id,
        'text': message.text,
        'thread_id': message.message_thread_id,
        'message_time': message.date.isoformat(),  # ISO 8601格式
    }

    success = _send_to_sqs_safe(sqs, config.queue_url, message_body)

    # Return 200 immediately - processing happens async in consumer
    # Note: Even if SQS fails, we return 200 to prevent Telegram webhook retries
    if not success:
        logger.error(
            f'Failed to send message to SQS but returning 200 to Telegram',
            extra={
                'chat_id': message.chat_id,
                'message_id': message.message_id,
            },
        )

    return {'statusCode': 200}
