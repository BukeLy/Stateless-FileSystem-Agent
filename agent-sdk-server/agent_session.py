"""Claude Agent SDK wrapper for Lambda environment.

Bedrock 配置通过 settings.json 注入，由 Dockerfile 复制到 CLAUDE_CONFIG_DIR。
"""
import os
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


SYSTEM_PROMPT = """You are a helpful AI assistant running in a serverless environment.
You can help users with various tasks including coding, analysis, and general questions.
Be concise and helpful in your responses."""


async def process_message(
    user_message: str,
    session_id: Optional[str] = None,
    cwd: str = '/tmp/workspace',
    model: str = 'sonnet',
    max_turns: int = 50,
) -> dict:
    """Process user message with Claude Agent SDK.

    For new session (session_id=None):
        - SDK creates new session and returns session_id in ResultMessage
        - Caller should save session_id to DynamoDB

    For existing session (session_id provided):
        - Session files should be downloaded from S3 before calling
        - SDK resumes context via resume parameter
        - Session files should be uploaded to S3 after return

    Args:
        user_message: User input message
        session_id: Existing session ID to resume, or None for new session
        cwd: Working directory for agent operations
        model: Model to use (sonnet, opus, haiku)
        max_turns: Maximum conversation turns per invocation

    Returns:
        dict with keys: response, session_id, cost_usd, num_turns, is_error, error_message
    """
    # Ensure working directory exists
    os.makedirs(cwd, exist_ok=True)

    options = ClaudeAgentOptions(
        cwd=cwd,
        resume=session_id,  # None = new session, str = resume existing
        model=model,
        permission_mode='bypassPermissions',  # Lambda has no interactive terminal
        max_turns=max_turns,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=[
            'Bash', 'Read', 'Write', 'Edit',
            'Glob', 'Grep', 'WebFetch',
        ],
    )

    response_texts: list[str] = []
    result_session_id = session_id or ''
    cost_usd = 0.0
    num_turns = 0
    is_error = False
    error_message: Optional[str] = None

    try:
        async for message in query(prompt=user_message, options=options):
            # Handle AssistantMessage - extract text from content blocks
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_texts.append(block.text)

            # Handle ResultMessage - extract session_id and metadata
            elif isinstance(message, ResultMessage):
                result_session_id = message.session_id
                cost_usd = message.total_cost_usd or 0.0
                num_turns = message.num_turns
                is_error = message.is_error
                if is_error and message.result:
                    error_message = message.result

    except Exception as e:
        is_error = True
        error_message = str(e)

    return {
        'response': '\n'.join(response_texts) if response_texts else '',
        'session_id': result_session_id,
        'cost_usd': cost_usd,
        'num_turns': num_turns,
        'is_error': is_error,
        'error_message': error_message,
    }
