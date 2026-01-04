"""Lambda handler for agent-container.

HTTP API endpoint that processes messages via Claude Agent SDK.
"""
import asyncio
import json
import logging
from typing import Any

from config import Config
from session_store import SessionStore
from agent_session import process_message

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context: Any) -> dict:
    """Lambda entry point.

    Request body:
    {
        "user_message": "Hello",
        "chat_id": "123456",
        "thread_id": "optional",
        "model": "sonnet"  // optional
    }

    Response:
    {
        "response": "Agent response text",
        "session_id": "agent-xxx",
        "cost_usd": 0.01,
        "num_turns": 1,
        "is_error": false,
        "error_message": null
    }
    """
    # Load config
    config = Config.from_env()

    # Validate auth token
    headers = event.get('headers', {})
    auth_header = headers.get('authorization', headers.get('Authorization', ''))
    if auth_header != f'Bearer {config.auth_token}':
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Unauthorized'})
        }

    # Parse request
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON'})
        }

    user_message = body.get('user_message', '')
    chat_id = body.get('chat_id', '')
    thread_id = body.get('thread_id')
    model = body.get('model', 'sonnet')

    if not user_message or not chat_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing user_message or chat_id'})
        }

    # Initialize session store
    store = SessionStore(
        bucket=config.session_bucket,
        table=config.session_table,
        project_path=config.project_path,
    )

    # Get existing session_id (if any)
    session_id = store.get_session_id(chat_id, thread_id)

    # Download session files if resuming
    if session_id:
        try:
            store.download_session_files(session_id)
        except Exception as e:
            logger.error(f"Failed to download session files for session_id={session_id}: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to download session'})
            }

    # Process message with Agent SDK
    try:
        result = asyncio.run(process_message(
            user_message=user_message,
            session_id=session_id,
            model=model,
        ))
    except Exception as e:
        logger.exception(f"Agent SDK processing failed for chat_id={chat_id}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response': '',
                'session_id': session_id,
                'cost_usd': 0.0,
                'num_turns': 0,
                'is_error': True,
                'error_message': f'Agent processing error: {str(e)[:200]}'
            })
        }

    # Get session_id from result (SDK generates it for new sessions)
    result_session_id = result.get('session_id', '')

    # Save session mapping if new session
    if result_session_id and result_session_id != session_id:
        try:
            store.save_session_id(chat_id, thread_id, result_session_id)
        except Exception as e:
            logger.error(f"Failed to save session mapping for chat_id={chat_id}: {e}")
            # Continue anyway - session can still work with S3 files

    # Upload session files
    if result_session_id:
        try:
            store.upload_session_files(result_session_id)
            store.update_session_timestamp(chat_id, thread_id)
        except Exception as e:
            logger.error(f"Failed to upload session files for session_id={result_session_id}: {e}")
            # Continue anyway - result is already available to return

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result)
    }
