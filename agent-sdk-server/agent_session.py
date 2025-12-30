"""Claude Agent SDK wrapper for Lambda environment.

Uses SDK's built-in types directly - no custom dataclass needed.
"""
import os
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


def setup_bedrock_profile():
    """Create AWS credentials file with bedrock profile.

    This keeps Lambda's execution role credentials intact for DynamoDB/S3,
    while providing separate credentials for Claude Code to use Bedrock.

    Lambda only allows writes to /tmp, so we configure:
    - CLAUDE_CONFIG_DIR=/tmp/.claude-code (for Claude Code config)
    - AWS_SHARED_CREDENTIALS_FILE=/tmp/.aws/credentials (for AWS profile)
    """
    # Setup /tmp directories for Lambda
    aws_dir = Path('/tmp/.aws')
    claude_dir = Path('/tmp/.claude-code')
    aws_dir.mkdir(exist_ok=True)
    claude_dir.mkdir(exist_ok=True)

    # Create AWS credentials file with bedrock profile
    bedrock_key = os.environ.get('BEDROCK_ACCESS_KEY_ID', '')
    bedrock_secret = os.environ.get('BEDROCK_SECRET_ACCESS_KEY', '')

    credentials_content = f"""[bedrock]
aws_access_key_id = {bedrock_key}
aws_secret_access_key = {bedrock_secret}
region = us-east-1
"""
    credentials_file = aws_dir / 'credentials'
    credentials_file.write_text(credentials_content)

    # Configure Claude Code to use /tmp
    os.environ['CLAUDE_CONFIG_DIR'] = str(claude_dir)
    os.environ['AWS_SHARED_CREDENTIALS_FILE'] = str(credentials_file)
    os.environ['DISABLE_AUTOUPDATER'] = '1'
    os.environ['DISABLE_TELEMETRY'] = '1'

    # Set Bedrock model ARNs
    os.environ['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = 'arn:aws:bedrock:us-east-1:287422227648:application-inference-profile/0toltxz33ekq'
    os.environ['ANTHROPIC_DEFAULT_SONNET_MODEL'] = 'arn:aws:bedrock:us-east-1:287422227648:application-inference-profile/p5aqcahes47k'
    os.environ['ANTHROPIC_DEFAULT_OPUS_4_5_MODEL'] = 'arn:aws:bedrock:us-east-1:287422227648:application-inference-profile/6u1o6pf6hqm4'
    os.environ['ANTHROPIC_DEFAULT_OPUS_MODEL'] = os.environ['ANTHROPIC_DEFAULT_OPUS_4_5_MODEL']

    print(f"Bedrock profile created at {credentials_file}")
    print(f"Claude config dir: {claude_dir}")


# Setup on module load
setup_bedrock_profile()


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
        # Use bedrock profile for Claude Code
        os.environ['AWS_PROFILE'] = 'bedrock'

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
    finally:
        # Restore default profile (Lambda execution role)
        if 'AWS_PROFILE' in os.environ:
            del os.environ['AWS_PROFILE']

    return {
        'response': '\n'.join(response_texts) if response_texts else '',
        'session_id': result_session_id,
        'cost_usd': cost_usd,
        'num_turns': num_turns,
        'is_error': is_error,
        'error_message': error_message,
    }
