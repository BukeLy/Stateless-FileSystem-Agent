"""Lambda handler for agent-container.

HTTP API endpoint that processes messages via Claude Agent SDK.
"""
import asyncio
import json
from typing import Any

from config import Config
from session_store import SessionStore
from agent_session import process_message


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
        store.download_session_files(session_id)

    # Process message with Agent SDK
    result = asyncio.run(process_message(
        user_message=user_message,
        session_id=session_id,
        model=model,
    ))

    # Get session_id from result (SDK generates it for new sessions)
    result_session_id = result.get('session_id', '')

    # Save session mapping if new session
    if result_session_id and result_session_id != session_id:
        store.save_session_id(chat_id, thread_id, result_session_id)

    # Upload session files
    if result_session_id:
        store.upload_session_files(result_session_id)
        store.update_session_timestamp(chat_id, thread_id)

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result)
    }
