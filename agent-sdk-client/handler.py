"""Lambda handler for sdk-client (Producer).

Receives Telegram webhook, writes to SQS, returns 200 immediately.
"""
import asyncio
import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from telegram import Bot, Update

from config import Config
from security import is_user_allowed, should_leave_group

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Reuse SQS client across invocations
_sqs_client = None
_cloudwatch_client = None


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
    """Send message to SQS with comprehensive error handling.

    Returns:
        True if message sent successfully, False otherwise.
    """
    try:
        response = sqs.send_message(
            QueueUrl=queue_url, MessageBody=json.dumps(message_body)
        )
        message_id = response.get('MessageId', 'unknown')
        logger.info(f"Message sent to SQS: {message_id}")
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


def _handle_local_command(bot: Bot, message, config: Config, cmd: str) -> bool:
    """Handle local commands or unknown commands."""
    if config.is_local_command(cmd):
        text = config.local_response(cmd)
    else:
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
        logger.warning("Failed to send local command response", exc_info=True)

    logger.info(
        'Handled non-whitelisted command locally',
        extra={
            'chat_id': message.chat_id,
            'message_id': message.message_id,
        },
    )
    return True


async def _check_forum_requirements(bot: Bot, chat_id: int) -> tuple[bool, str]:
    """检查群组 Topic 功能要求。

    Returns:
        (is_ok, error_message) - 如果满足要求返回 (True, "")，否则返回 (False, 错误提示)
    """
    try:
        chat = await bot.get_chat(chat_id)
        if not chat.is_forum:
            return False, (
                "⚠️ 群组未开启 Topics 功能\n\n"
                "请按以下步骤开启:\n"
                "1. 打开群组设置\n"
                "2. 点击「Topics」\n"
                "3. 开启 Topics 功能\n"
                "4. 重新添加 Bot"
            )

        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        if not getattr(member, 'can_manage_topics', False):
            return False, (
                "⚠️ Bot 缺少「管理 Topics」权限\n\n"
                "请按以下步骤授权:\n"
                "1. 打开群组设置 > 管理员\n"
                "2. 选择此 Bot\n"
                "3. 开启「Manage Topics」权限"
            )
        return True, ""
    except Exception as e:
        logger.warning(f"Failed to check forum requirements: {e}")
        return False, f"检查权限失败: {str(e)[:100]}"


async def _handle_newchat_command(
    bot: Bot, message, body: dict, config: Config, sqs, prompts: str
) -> bool:
    """处理 /newchat - 创建 Topic 并发送消息到 SQS。

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

    # Handle my_chat_member event (bot added to group)
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
            # 授权群组的 Topic 预检
            member_update = update.my_chat_member
            old_status = member_update.old_chat_member.status
            new_status = member_update.new_chat_member.status

            if old_status in ('left', 'kicked') and new_status in (
                'member',
                'administrator',
            ):
                chat_id = member_update.chat.id

                async def _run_topic_precheck():
                    is_ok, error_msg = await _check_forum_requirements(bot, chat_id)
                    if not is_ok:
                        await bot.send_message(chat_id=chat_id, text=error_msg)
                        logger.warning(
                            "Forum requirements check failed",
                            extra={'chat_id': chat_id, 'error_msg': error_msg},
                        )
                        _send_metric('TopicPrecheck.Failed')

                asyncio.run(_run_topic_precheck())
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

    cmd = config.get_command(message.text)

    # /newchat 特殊处理 - 创建 Topic 后发 SQS
    if cmd == '/newchat':
        # 提取 prompts：移除命令部分（包括可能的 @bot 后缀）
        parts = message.text.strip().split(maxsplit=1)
        prompts = parts[1] if len(parts) > 1 else ''
        if not prompts:
            bot.send_message(
                chat_id=message.chat_id,
                text="用法: /newchat <消息内容>",
                message_thread_id=message.message_thread_id,
            )
            return {'statusCode': 200}

        sqs = _get_sqs_client()
        asyncio.run(_handle_newchat_command(bot, message, body, config, sqs, prompts))
        return {'statusCode': 200}

    # 其他 local command 正常处理
    if cmd and config.is_local_command(cmd):
        _handle_local_command(bot, message, config, cmd)
        return {'statusCode': 200}

    if cmd and not config.is_agent_command(cmd):
        _handle_local_command(bot, message, config, cmd)
        return {'statusCode': 200}

    # Write to SQS for async processing
    sqs = _get_sqs_client()
    message_body = {
        'telegram_update': body,
        'chat_id': message.chat_id,
        'message_id': message.message_id,
        'text': message.text,
        'thread_id': message.message_thread_id,
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
