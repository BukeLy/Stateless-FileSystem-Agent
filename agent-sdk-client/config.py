"""Configuration for sdk-client Lambda."""
import os
from dataclasses import dataclass


@dataclass
class Config:
    """Client configuration from environment variables."""

    telegram_token: str
    agent_server_url: str
    auth_token: str
    message_dedup_table: str

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        return cls(
            telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            agent_server_url=os.getenv('AGENT_SERVER_URL', ''),
            auth_token=os.getenv('SDK_CLIENT_AUTH_TOKEN', 'default-token'),
            message_dedup_table=os.getenv('MESSAGE_DEDUP_TABLE', ''),
        )
