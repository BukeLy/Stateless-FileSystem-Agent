import importlib.util
from pathlib import Path

import pytest

CLIENT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent-sdk-client" / "config.py"
spec = importlib.util.spec_from_file_location("agent_sdk_client_config", CLIENT_CONFIG_PATH)
config_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(config_module)
Config = config_module.Config
extract_command = config_module.extract_command


def load_config_from_text(text: str, tmp_path: Path) -> Config:
    config_path = tmp_path / "config.toml"
    config_path.write_text(text)
    return Config.from_env(config_path=config_path)


def test_load_agent_and_local_commands(tmp_path):
    cfg = load_config_from_text(
        """[agent_commands]
commands = ["/a", "/b"]

[local_commands]
help = "Hello"
""",
        tmp_path,
    )
    assert cfg.agent_commands == ["/a", "/b"]
    assert cfg.local_commands == {"/help": "Hello"}


@pytest.mark.parametrize(
    "text,cmd",
    [
        ("hello world", None),
        ("/allowed", "/allowed"),
        ("/allowed extra args", "/allowed"),
        ("/allowed@bot", "/allowed"),
        ("/@bot", None),
        ("/", None),
        (None, None),
    ],
)
def test_extract_command(text, cmd):
    assert extract_command(text) == cmd


def test_command_classification(tmp_path):
    cfg = load_config_from_text(
        """[agent_commands]
commands = ["/agent"]

[local_commands]
help = "Hello World"
""",
        tmp_path,
    )
    assert cfg.is_agent_command("/agent")
    assert not cfg.is_agent_command("/other")
    assert cfg.is_local_command("/help")
    assert not cfg.is_local_command("/agent")


def test_unknown_command_message_lists_known():
    cfg = Config(
        telegram_token="",
        agent_server_url="",
        auth_token="",
        queue_url="",
        agent_commands=["/agent1"],
        local_commands={"/help": "hi"},
    )
    msg = cfg.unknown_command_message()
    assert "Agent commands" in msg and "/agent1" in msg
    assert "Local commands" in msg and "/help" in msg


def test_invalid_agent_commands_type(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        cfg = load_config_from_text(
            """[agent_commands]
commands = "not-a-list"
""",
            tmp_path,
        )
    assert cfg.agent_commands == []
    assert any("Agent commands config is not a list" in rec.message for rec in caplog.records)


def test_invalid_local_commands_type(tmp_path, caplog):
    cfg = load_config_from_text(
        """[local_commands]
value = 1
""",
        tmp_path,
    )
    assert cfg.local_commands == {}


def test_missing_config_file(tmp_path):
    missing = tmp_path / "missing.toml"
    cfg = Config.from_env(config_path=missing)
    assert cfg.agent_commands == []
    assert cfg.local_commands == {}


def test_malformed_toml_returns_empty(tmp_path, caplog):
    path = tmp_path / "bad.toml"
    path.write_text("not = [ [")
    with caplog.at_level("WARNING"):
        cfg = Config.from_env(config_path=path)
    assert cfg.agent_commands == []
    assert cfg.local_commands == {}
    assert any("Failed to load command configuration" in rec.message for rec in caplog.records)
