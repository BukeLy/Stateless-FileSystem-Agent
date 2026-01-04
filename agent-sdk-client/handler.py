"""Lambda handler for sdk-client (Producer).

Receives Telegram webhook, writes to SQS, returns 200 immediately.
"""
import json
import os
from typing import Any

import boto3
from telegram import Bot, Update

from config import Config

# Reuse SQS client across invocations
_sqs_client = None


def _get_sqs_client():
    """Get or create SQS client singleton."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client('sqs')
    return _sqs_client


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda entry point - Producer.

    Validates Telegram message and writes to SQS queue.
    Returns 200 immediately without waiting for processing.
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return {'statusCode': 200}

    config = Config.from_env()

    # Quick validation - parse update to check if it's a valid message
    bot = Bot(config.telegram_token)
    update = Update.de_json(body, bot)

    if not update:
        return {'statusCode': 200}

    message = update.message or update.edited_message
    if not message or not message.text:
        return {'statusCode': 200}

    # Write to SQS for async processing
    sqs = _get_sqs_client()
    sqs.send_message(
        QueueUrl=config.queue_url,
        MessageBody=json.dumps({
            'telegram_update': body,
            'chat_id': message.chat_id,
            'message_id': message.message_id,
            'text': message.text,
            'thread_id': message.message_thread_id,
        }),
    )

    # Return 200 immediately - processing happens async in consumer
    return {'statusCode': 200}
