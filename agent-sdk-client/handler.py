"""Lambda handler for sdk-client.

Receives Telegram webhook, calls agent-server, sends response back.
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

    # Try MARKDOWN_V2 first, fallback with escape on parse errors
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
            print(f"[MARKDOWN_V2] Parse error: {e}, retrying with escaped text")
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
