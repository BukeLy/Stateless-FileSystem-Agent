"""Claude Agent SDK wrapper for Lambda environment.

Uses SDK's built-in types directly - no custom dataclass needed.
"""
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

# Config source (in Docker image) and destination (Lambda writable)
CONFIG_SRC = Path('/opt/claude-config')
CONFIG_DST = Path('/tmp/.claude-code')
SKILLS_SRC = Path('/opt/claude-skills')
SKILLS_DST = CONFIG_DST / 'skills'


def setup_lambda_environment():
    """Setup Lambda environment for Claude Agent SDK.

    1. Create AWS credentials file with bedrock profile (for cross-account Bedrock access)
    2. Copy config files from /opt/claude-config to /tmp/.claude-code

    Note: Static config (CLAUDE_CONFIG_DIR, model ARNs, etc.) are set in template.yaml.
    """
    # Setup /tmp directories for Lambda
    aws_dir = Path('/tmp/.aws')
    aws_dir.mkdir(exist_ok=True)
    CONFIG_DST.mkdir(exist_ok=True)

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
    credentials_file.chmod(0o600)

    # Copy pre-configured files from Docker image to Lambda writable /tmp
    if CONFIG_SRC.exists():
        for item in CONFIG_SRC.iterdir():
            dst = CONFIG_DST / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        print(f"Config copied from {CONFIG_SRC} to {CONFIG_DST}")

    # Copy skills to CLAUDE_CONFIG_DIR/skills/ for SDK to discover
    if SKILLS_SRC.exists():
        SKILLS_DST.mkdir(parents=True, exist_ok=True)
        for item in SKILLS_SRC.iterdir():
            dst = SKILLS_DST / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        print(f"Skills copied from {SKILLS_SRC} to {SKILLS_DST}")

    print(f"Bedrock profile created at {credentials_file}")


def load_mcp_servers() -> dict:
    """Load MCP servers configuration from mcp.json."""
    mcp_file = CONFIG_DST / 'mcp.json'
    if mcp_file.exists():
        with open(mcp_file) as f:
            config = json.load(f)
            return config.get('mcpServers', {})
    return {}


def load_agents() -> dict[str, AgentDefinition]:
    """Load SubAgent definitions from agents.json + prompt files."""
    agents_config = CONFIG_DST / 'agents.json'
    if not agents_config.exists():
        return {}

    with open(agents_config) as f:
        config = json.load(f)

    agents = {}
    for name, definition in config.items():
        # Load prompt from external .md file
        prompt_file = CONFIG_DST / definition.get('prompt_file', '')
        prompt = ''
        if prompt_file.exists():
            prompt = prompt_file.read_text()

        agents[name] = AgentDefinition(
            description=definition.get('description', ''),
            prompt=prompt,
            tools=definition.get('tools'),
            model=definition.get('model'),
        )

    return agents


def load_system_prompt() -> str:
    """Load system prompt from system_prompt.md."""
    prompt_file = CONFIG_DST / 'system_prompt.md'
    if prompt_file.exists():
        return prompt_file.read_text()
    # Fallback default
    return "You are a helpful AI assistant. Be concise and helpful in your responses."


# Setup on module load
setup_lambda_environment()


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

    # Load config from external files
    mcp_servers = load_mcp_servers()
    agents = load_agents()
    system_prompt = load_system_prompt()

    options = ClaudeAgentOptions(
        cwd=cwd,
        resume=session_id,  # None = new session, str = resume existing
        model=model,
        permission_mode='bypassPermissions',  # Lambda has no interactive terminal
        max_turns=max_turns,
        system_prompt=system_prompt,
        setting_sources=['user'],  # Load skills from CLAUDE_CONFIG_DIR/skills/
        allowed_tools=[
            #'Bash', 'Read', 'Write', 'Edit',
            #'Glob', 'Grep', 'WebFetch',
            'Task',   # For SubAgents
            'Skill',  # For Skills
        ],
        mcp_servers=mcp_servers if mcp_servers else None,
        agents=agents if agents else None,
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
