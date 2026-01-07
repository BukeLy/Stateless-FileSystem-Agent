"""Configuration for sdk-client Lambda."""
import logging
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
    if not command:
        return None
    return command


def load_command_whitelist(config_path: Path = DEFAULT_CONFIG_PATH) -> list[str]:
    """Load command whitelist from TOML config file."""
    if not config_path.exists():
        return []

    try:
        with config_path.open('rb') as f:
            data = tomllib.load(f)
        whitelist = data.get('white_list_commands', {}).get('whitelist', [])
        if not isinstance(whitelist, list):
            logger.warning("Command whitelist is not a list; ignoring configuration")
            return []

        commands = [cmd for cmd in whitelist if isinstance(cmd, str)]
        if len(commands) != len(whitelist):
            logger.warning("Ignoring non-string entries in command whitelist")
        return commands
    except (OSError, tomllib.TOMLDecodeError) as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to load command whitelist: %s", exc)
    return []


@dataclass
class Config:
    """Client configuration from environment variables."""

    telegram_token: str
    agent_server_url: str
    auth_token: str
    queue_url: str
    command_whitelist: list[str]

    @classmethod
    def from_env(cls, config_path: Optional[Path] = None) -> 'Config':
        """Load configuration from environment variables."""
        return cls(
            telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            agent_server_url=os.getenv('AGENT_SERVER_URL', ''),
            auth_token=os.getenv('SDK_CLIENT_AUTH_TOKEN', 'default-token'),
            queue_url=os.getenv('QUEUE_URL', ''),
            command_whitelist=load_command_whitelist(config_path or DEFAULT_CONFIG_PATH),
        )

    def is_command_allowed(self, text: Optional[str]) -> bool:
        """Check whether text should be forwarded to Agent backend."""
        command = extract_command(text)
        if command is None:
            return True
        return command in self.command_whitelist
