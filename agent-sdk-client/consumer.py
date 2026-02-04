"""Lambda handler for SQS Consumer.

Processes messages from SQS queue, calls Agent Server, sends response to Telegram.
"""
import asyncio
import json
import re
from typing import Any

import httpx
from telegram import Bot, Update
from telegram.constants import ParseMode, ChatAction
from telegramify_markdown import markdownify
from telegram.error import BadRequest

from config import Config


def fix_heading_bold(text: str) -> str:
    """Remove bold markers from headings: ## **Title** -> ## Title.

    Only applies when heading contains **bold** markers.
    """
    if re.search(r'^#{1,6}\s*\*\*', text, flags=re.MULTILINE):
        return re.sub(r'^(#{1,6})\s*\*\*(.+?)\*\*\s*$', r'\1 \2', text, flags=re.MULTILINE)
    return text


def fix_code_escaping(text: str) -> str:
    """Remove escaping inside code blocks: \\| -> |, \\- -> -.

    Only applies when code blocks contain escaped characters.
    """
    if '```' not in text and '`' not in text:
        return text

    escaped_chars = '`|-.()+!#={}[]><_*~'

    def unescape(content: str) -> str:
        for char in escaped_chars:
            content = content.replace(f'\\{char}', char)
        return content

    # Fix fenced code blocks
    if '```' in text:
        text = re.sub(
            r'```(.*?)```',
            lambda m: f'```{unescape(m.group(1))}```',
            text,
            flags=re.DOTALL
        )
    # Fix inline code
    if '`' in text:
        text = re.sub(
            r'`([^`]+)`',
            lambda m: f'`{unescape(m.group(1))}`',
            text
        )
    return text


def fix_unescaped_chars(text: str) -> str:
    """Escape special chars outside code blocks that markdownify missed.

    Only applies when unescaped special chars exist outside code blocks.
    """
    # Extract code blocks to protect them
    blocks = []
    def save(m):
        blocks.append(m.group(0))
        return f'\x00{len(blocks)-1}\x00'

    protected = re.sub(r'```.*?```', save, text, flags=re.DOTALL)
    protected = re.sub(r'`[^`]+`', save, protected)

    # Check if any unescaped chars exist
    chars = r'-.!()+=|{}[]#>'
    if not re.search(rf'(?<!\\)[{re.escape(chars)}]', protected):
        return text

    # Escape unescaped special chars
    for char in chars:
        protected = re.sub(rf'(?<!\\){re.escape(char)}', f'\\{char}', protected)

    # Restore code blocks
    for i, block in enumerate(blocks):
        protected = protected.replace(f'\x00{i}\x00', block)

    return protected


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
    logger.setLevel(logging.INFO)

    config = Config.from_env()
    bot = Bot(config.telegram_token)

    # Reconstruct Update object from stored data
    update = Update.de_json(message_data['telegram_update'], bot)
    message = update.message or update.edited_message

    if not message:
        logger.warning("Received update with no message or edited_message")
        return

    # Initialize result with default error response
    # This ensures result is always defined, even if Agent Server call fails
    result = {
        'response': '',
        'is_error': True,
        'error_message': 'Failed to get response from Agent Server'
    }

    # Use message_data fields for SQS message (allows handler to override text/thread_id)
    user_message = message_data.get('text') or message.text
    thread_id = message_data.get('thread_id') or message.message_thread_id

    async def keep_typing():
        """Send typing indicator every 4 seconds (Telegram typing expires after 5s)."""
        while True:
            try:
                await bot.send_chat_action(
                    chat_id=message.chat_id,
                    action=ChatAction.TYPING,
                    message_thread_id=thread_id,
                )
            except Exception:
                pass  # Ignore typing errors, don't interrupt main flow
            await asyncio.sleep(4)

    async def call_agent_server():
        """Call Agent Server and return result."""
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                config.agent_server_url,
                headers={
                    'Authorization': f'Bearer {config.auth_token}',
                    'Content-Type': 'application/json',
                },
                json={
                    'user_message': user_message,
                    'chat_id': str(message.chat_id),
                    'thread_id': str(thread_id) if thread_id else None,
                    'message_time': message_data.get('message_time'),
                },
            )
            response.raise_for_status()
            return response.json()

    # Call Agent Server with continuous typing indicator
    typing_task = asyncio.create_task(keep_typing())
    try:
        result = await call_agent_server()

    except httpx.TimeoutException:
        logger.warning(f"Agent Server timeout for chat_id={message.chat_id}")
        await bot.send_message(
            chat_id=message.chat_id,
            text="Request timed out.",
            message_thread_id=thread_id,
        )
        raise  # Re-raise to trigger SQS retry for transient errors

    except Exception as e:
        logger.exception(f"Agent Server error for chat_id={message.chat_id}")
        error_text = f"Error: {str(e)[:200]}"
        try:
            await bot.send_message(
                chat_id=message.chat_id,
                text=error_text,
                message_thread_id=thread_id,
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message to Telegram: {send_error}")
        # Don't re-raise - error message already sent to user, retrying would cause duplicate messages

    finally:
        # Stop typing indicator
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Format response (result is guaranteed to be defined now)
    if result.get('is_error'):
        text = f"Agent error: {result.get('error_message', 'Unknown')}"
    else:
        text = result.get('response') or 'No response'

    if len(text) > 4000:
        text = text[:4000] + "\n\n... (truncated)"

    # Send response to Telegram
    # Convert standard Markdown to Telegram MarkdownV2 format
    # Pipeline: fix_heading_bold -> markdownify -> fix_code_escaping -> fix_unescaped_chars
    telegram_text = fix_unescaped_chars(fix_code_escaping(markdownify(fix_heading_bold(text))))

    # Only reply_to original message if thread_id matches (not for /newchat)
    reply_to_id = (
        message.message_id
        if thread_id == message.message_thread_id
        else None
    )

    try:
        await bot.send_message(
            chat_id=message.chat_id,
            text=telegram_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_id,
        )
        logger.info(
            "Sent response to Telegram",
            extra={'chat_id': message.chat_id, 'thread_id': thread_id},
        )
    except BadRequest as e:
        logger.warning(f"BadRequest sending message: {e}")
        if "parse entities" in str(e).lower():
            # Fallback: send as plain text without any formatting
            await bot.send_message(
                chat_id=message.chat_id,
                text=text,
                message_thread_id=thread_id,
                reply_to_message_id=reply_to_id,
            )
        else:
            raise
