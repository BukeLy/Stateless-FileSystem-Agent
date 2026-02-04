"""Configuration for sdk-client Lambda."""
import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LocalCommand:
    """Local command configuration."""
    type: str  # "static" or "handler"
    response: str = ""  # for static type
    handler: str = ""  # for handler type

logger = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.toml")


def extract_command(text: Optional[str]) -> Optional[str]:
    """Extract command (with leading slash) from text, ignoring arguments/bot names."""
    if not text:
        return None

    trimmed = text.strip()
    if not trimmed.startswith('/'):
        return None

    command = trimmed.split()[0]
    if '@' in command:
        command = command.split('@', 1)[0]
    command = command.strip()
    if not command or command == '/':
        return None
    return command


def _parse_local_command(name: str, value) -> tuple[str, LocalCommand | None]:
    """Parse a single local command entry.

    Args:
        name: Command name (with or without leading slash)
        value: Command value (string for legacy, dict for new format)

    Returns:
        Tuple of (normalized_cmd, LocalCommand) or (normalized_cmd, None) if invalid
    """
    cmd = f"/{name.lstrip('/')}" if not name.startswith('/') else name

    # Legacy format: string value = static response
    if isinstance(value, str):
        return cmd, LocalCommand(type="static", response=value)

    # New format: dict with type field
    if isinstance(value, dict):
        cmd_type = value.get('type', '')
        if cmd_type == 'static':
            response = value.get('response', '')
            if not response:
                logger.warning(f"Local command {cmd} has no response; skipping")
                return cmd, None
            return cmd, LocalCommand(type="static", response=response)
        elif cmd_type == 'handler':
            handler = value.get('handler', '')
            if not handler:
                logger.warning(f"Local command {cmd} has no handler; skipping")
                return cmd, None
            return cmd, LocalCommand(type="handler", handler=handler)
        else:
            logger.warning(f"Local command {cmd} has unknown type: {cmd_type}; skipping")
            return cmd, None

    logger.warning(f"Local command {cmd} has invalid value type; skipping")
    return cmd, None


def _load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[list[str], dict[str, LocalCommand], list[int | str]]:
    """Load commands and security config from TOML config file.

    Returns:
        Tuple of (agent_commands, local_commands, user_whitelist).
    """
    if not config_path.exists():
        return [], {}, ['all']

    try:
        with config_path.open('rb') as f:
            data = tomllib.load(f)

        # Load agent commands
        agent_commands = data.get('agent_commands', {}).get('commands', [])
        if not isinstance(agent_commands, list):
            logger.warning("Agent commands config is not a list; ignoring configuration")
            agent_commands = []
        agent_commands = [cmd for cmd in agent_commands if isinstance(cmd, str)]

        # Load local commands (supports both legacy string and new dict format)
        local_commands_raw = data.get('local_commands', {})
        if not isinstance(local_commands_raw, dict):
            logger.warning("Local commands config is not a table; ignoring configuration")
            local_commands_raw = {}
        local_commands: dict[str, LocalCommand] = {}
        for name, value in local_commands_raw.items():
            if not isinstance(name, str):
                continue
            cmd, parsed = _parse_local_command(name, value)
            if parsed:
                local_commands[cmd] = parsed

        # Load security whitelist
        security = data.get('security', {})
        whitelist = security.get('user_whitelist', ['all'])
        if not isinstance(whitelist, list):
            logger.warning("user_whitelist is not a list; using default ['all']")
            whitelist = ['all']
        else:
            validated = []
            for item in whitelist:
                if item == 'all':
                    validated.append('all')
                elif isinstance(item, int):
                    validated.append(item)
                else:
                    logger.warning(f"Invalid whitelist entry: {item}; skipping")
            whitelist = validated if validated else ['all']

        return agent_commands, local_commands, whitelist

    except (OSError, tomllib.TOMLDecodeError) as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to load configuration: %s", exc)
    return [], {}, ['all']


@dataclass
class Config:
    """Client configuration from environment variables."""

    telegram_token: str
    agent_server_url: str
    auth_token: str
    queue_url: str
    agent_commands: list[str]
    local_commands: dict[str, LocalCommand]
    user_whitelist: list[int | str]
    telegram_webhook_secret: str = ""

    @classmethod
    def from_env(cls, config_path: Optional[Path] = None) -> 'Config':
        """Load configuration from environment variables."""
        agent_cmds, local_cmds, whitelist = _load_config(config_path or DEFAULT_CONFIG_PATH)
        return cls(
            telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            agent_server_url=os.getenv('AGENT_SERVER_URL', ''),
            auth_token=os.getenv('SDK_CLIENT_AUTH_TOKEN', 'default-token'),
            queue_url=os.getenv('QUEUE_URL', ''),
            agent_commands=agent_cmds,
            local_commands=local_cmds,
            user_whitelist=whitelist,
            telegram_webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET', ''),
        )

    def get_command(self, text: Optional[str]) -> Optional[str]:
        return extract_command(text)

    def is_agent_command(self, cmd: Optional[str]) -> bool:
        return bool(cmd) and cmd in self.agent_commands

    def is_local_command(self, cmd: Optional[str]) -> bool:
        return bool(cmd) and cmd in self.local_commands

    def get_local_command(self, cmd: str) -> LocalCommand | None:
        """Get local command config by command name."""
        return self.local_commands.get(cmd)

    def local_response(self, cmd: str) -> str:
        """Get static response for a local command (legacy compatibility)."""
        local_cmd = self.local_commands.get(cmd)
        if local_cmd and local_cmd.type == "static":
            return local_cmd.response
        return "Unsupported command."

    def unknown_command_message(self) -> str:
        parts = []
        if self.agent_commands:
            parts.append("Agent commands:\n" + "\n".join(self.agent_commands))
        if self.local_commands:
            parts.append("Local commands:\n" + "\n".join(self.local_commands.keys()))
        if not parts:
            return "Unsupported command."
        return "Unsupported command.\n\n" + "\n\n".join(parts)
