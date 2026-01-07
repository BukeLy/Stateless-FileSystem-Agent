"""Lambda handler for SQS Consumer.

Processes messages from SQS queue, calls Agent Server, sends response to Telegram.
"""
import asyncio
import json
from typing import Any

import httpx
from telegram import Bot, Update
from telegram.constants import ParseMode, ChatAction
from telegram.helpers import escape_markdown
from telegram.error import BadRequest

from config import Config


def lambda_handler(event: dict, context: Any) -> dict:
    """SQS Consumer Lambda entry point."""
    for record in event['Records']:
        try:
            message_data = json.loads(record['body'])
        except json.JSONDecodeError as e:
            # Invalid message format - log and skip
            import logging
            logger = logging.getLogger()
            logger.error(f"Failed to parse SQS message: {e}")
            continue

        try:
            asyncio.run(process_message(message_data))
        except Exception as e:
            # Log and let SQS retry on failure
            import logging
            logger = logging.getLogger()
            logger.exception(f"Failed to process message: {e}")
            raise  # Re-raise to fail the batch item

    return {'statusCode': 200}


async def process_message(message_data: dict) -> None:
    """Process single message from SQS queue."""
    import logging
    logger = logging.getLogger()

    config = Config.from_env()
    bot = Bot(config.telegram_token)

    # Reconstruct Update object from stored data
    update = Update.de_json(message_data['telegram_update'], bot)
    message = update.message or update.edited_message

    if not message:
        logger.warning("Received update with no message or edited_message")
        return

    if not config.is_command_allowed(message.text):
        logger.info(
            "Skipping non-whitelisted command",
            extra={
                'chat_id': message.chat_id,
                'message_id': message.message_id,
            },
        )
        try:
            await bot.send_message(
                chat_id=message.chat_id,
                text="Unsupported command.",
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
            )
        except Exception:
            logger.warning("Failed to send local command response", exc_info=True)
        return

    # Send typing indicator
    await bot.send_chat_action(
        chat_id=message.chat_id,
        action=ChatAction.TYPING,
        message_thread_id=message.message_thread_id,
    )

    # Initialize result with default error response
    # This ensures result is always defined, even if Agent Server call fails
    result = {
        'response': '',
        'is_error': True,
        'error_message': 'Failed to get response from Agent Server'
    }

    # Call Agent Server
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
            response.raise_for_status()
            result = response.json()

    except httpx.TimeoutException:
        logger.warning(f"Agent Server timeout for chat_id={message.chat_id}")
        await bot.send_message(
            chat_id=message.chat_id,
            text="Request timed out.",
            message_thread_id=message.message_thread_id,
        )
        raise  # Re-raise to trigger SQS retry for transient errors

    except Exception as e:
        logger.exception(f"Agent Server error for chat_id={message.chat_id}")
        error_text = f"Error: {str(e)[:200]}"
        try:
            await bot.send_message(
                chat_id=message.chat_id,
                text=error_text,
                message_thread_id=message.message_thread_id,
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message to Telegram: {send_error}")
        # Don't re-raise - error message already sent to user, retrying would cause duplicate messages

    # Format response (result is guaranteed to be defined now)
    if result.get('is_error'):
        text = f"Agent error: {result.get('error_message', 'Unknown')}"
    else:
        text = result.get('response') or 'No response'

    if len(text) > 4000:
        text = text[:4000] + "\n\n... (truncated)"

    # Send response to Telegram
    try:
        await bot.send_message(
            chat_id=message.chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
            message_thread_id=message.message_thread_id,
            reply_to_message_id=message.message_id,
        )
    except BadRequest as e:
        if "parse entities" in str(e).lower():
            safe_text = escape_markdown(text, version=2)
            await bot.send_message(
                chat_id=message.chat_id,
                text=safe_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
            )
        else:
            raise
