"""Lambda handler for sdk-client (Producer).

Receives Telegram webhook, writes to SQS, returns 200 immediately.
"""
import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from telegram import Bot, Update

from config import Config

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


def _handle_local_command(bot: Bot, message, config: Config) -> bool:
    """Handle non-whitelisted commands locally to give user feedback."""
    if config.is_command_allowed(message.text):
        return False

    allowed = config.command_whitelist
    if allowed:
        allowed_list = "\n".join(allowed)
        text = f"Unsupported command. Allowed commands:\n{allowed_list}"
    else:
        text = "Unsupported command."

    try:
        bot.send_message(
            chat_id=message.chat_id,
            text=text,
            message_thread_id=message.message_thread_id,
            reply_to_message_id=message.message_id,
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

    message = update.message or update.edited_message
    if not message or not message.text:
        logger.debug('Ignoring webhook without text message')
        return {'statusCode': 200}

    if _handle_local_command(bot, message, config):
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
