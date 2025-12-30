"""Configuration management for agent-container Lambda."""
import os
from dataclasses import dataclass


@dataclass
class BedrockConfig:
    """Bedrock configuration."""
    use_bedrock: bool
    access_key_id: str
    secret_access_key: str
    region: str


@dataclass
class Config:
    """Agent container configuration from environment variables."""

    # Session storage
    session_bucket: str
    session_table: str
    project_path: str

    # Bedrock
    bedrock: BedrockConfig

    # Auth
    auth_token: str

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables."""
        return cls(
            session_bucket=os.getenv('SESSION_BUCKET', 'agent-sessions'),
            session_table=os.getenv('SESSION_TABLE', 'agent-sessions-table'),
            project_path=os.getenv('PROJECT_PATH', '-tmp-workspace'),
            bedrock=BedrockConfig(
                use_bedrock=os.getenv('CLAUDE_CODE_USE_BEDROCK', '0') == '1',
                access_key_id=os.getenv('AWS_ACCESS_KEY_ID', ''),
                secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', ''),
                region=os.getenv('AWS_REGION', 'us-east-1'),
            ),
            auth_token=os.getenv('SDK_CLIENT_AUTH_TOKEN', 'default-token'),
        )
