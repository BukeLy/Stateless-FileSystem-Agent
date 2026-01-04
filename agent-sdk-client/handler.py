"""Lambda handler for sdk-client.

Receives Telegram webhook, calls agent-server, sends response back.
"""
import asyncio
import json
import time
from typing import Any

import boto3
import httpx
from botocore.exceptions import ClientError
from telegram import Bot, Update
from telegram.constants import ParseMode, ChatAction

from config import Config

# Reuse DynamoDB resource across invocations for connection pooling
_dynamodb_resource = None


def _get_dynamodb_resource():
    """Get or create DynamoDB resource singleton."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource('dynamodb')
    return _dynamodb_resource


def is_message_duplicate(config: Config, chat_id: int, message_id: int) -> bool:
    """Check if message was already processed using DynamoDB.

    Uses conditional put to atomically check and mark message as processing.
    Returns True if message is a duplicate (already being processed).
    """
    if not config.message_dedup_table:
        return False

    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(config.message_dedup_table)

    dedup_key = f"{chat_id}:{message_id}"
    current_time = int(time.time())
    # TTL: 24 hours - messages older than this are safe to reprocess
    ttl = current_time + 86400

    try:
        # Conditional put - fails if item already exists
        table.put_item(
            Item={
                'message_key': dedup_key,
                'created_at': current_time,
                'ttl': ttl,
            },
            ConditionExpression='attribute_not_exists(message_key)',
        )
        return False  # Successfully inserted - not a duplicate
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return True  # Item exists - this is a duplicate
        raise  # Re-raise other errors


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda entry point."""
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return {'statusCode': 200}

    asyncio.run(process_webhook(body))
    return {'statusCode': 200}


async def process_webhook(body: dict) -> None:
    """Process Telegram webhook payload."""
    config = Config.from_env()
    bot = Bot(config.telegram_token)

    update = Update.de_json(body, bot)
    if not update:
        return

    message = update.message or update.edited_message
    if not message or not message.text:
        return

    # Check for duplicate message (Telegram webhook retry)
    if is_message_duplicate(config, message.chat_id, message.message_id):
        return  # Skip duplicate processing

    if message.text.startswith('/'):
        await bot.send_message(
            chat_id=message.chat_id,
            text="Commands not supported yet. Just send me a message!",
            message_thread_id=message.message_thread_id,
        )
        return

    await bot.send_chat_action(
        chat_id=message.chat_id,
        action=ChatAction.TYPING,
        message_thread_id=message.message_thread_id,
    )

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                config.agent_server_url,
                headers={
                    'Authorization': f'Bearer {config.auth_token}',
                    'Content-Type': 'application/json',
                },
                json={
                    'user_message': message.text,
                    'chat_id': str(message.chat_id),
                    'thread_id': str(message.message_thread_id) if message.message_thread_id else None,
                },
            )
            result = response.json()

    except httpx.TimeoutException:
        await bot.send_message(chat_id=message.chat_id, text="Request timed out.",
                              message_thread_id=message.message_thread_id)
        return
    except Exception as e:
        await bot.send_message(chat_id=message.chat_id, text=f"Error: {str(e)[:200]}",
                              message_thread_id=message.message_thread_id)
        return

    if result.get('is_error'):
        text = f"Agent error: {result.get('error_message', 'Unknown')}"
    else:
        text = result.get('response', 'No response')

    if len(text) > 4000:
        text = text[:4000] + "\n\n... (truncated)"

    await bot.send_message(
        chat_id=message.chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        message_thread_id=message.message_thread_id,
        reply_to_message_id=message.message_id,
    )
