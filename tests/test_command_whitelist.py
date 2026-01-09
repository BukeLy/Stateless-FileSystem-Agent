import importlib.util
from pathlib import Path

import pytest

CLIENT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent-sdk-client" / "config.py"
spec = importlib.util.spec_from_file_location("agent_sdk_client_config", CLIENT_CONFIG_PATH)
config_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(config_module)
Config = config_module.Config
load_command_whitelist = config_module.load_command_whitelist


def test_load_command_whitelist(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[white_list_commands]
whitelist = ["/allowed", "/another"]
"""
    )

    assert load_command_whitelist(config_path) == ["/allowed", "/another"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello world", True),
        ("/allowed", True),
        ("/allowed extra args", True),
        ("/allowed@bot", True),
        ("/@bot", True),
        ("/", True),
        ("/blocked", False),
        (" /blocked ", False),
    ],
)
def test_is_command_allowed(text, expected):
    cfg = Config(
        telegram_token="",
        agent_server_url="",
        auth_token="",
        queue_url="",
        command_whitelist=["/allowed"],
    )

    assert cfg.is_command_allowed(text) is expected


def test_empty_whitelist_allows_commands():
    cfg = Config(
        telegram_token="",
        agent_server_url="",
        auth_token="",
        queue_url="",
        command_whitelist=[],
    )
    assert cfg.is_command_allowed("/anything") is False


def test_none_text_treated_as_allowed():
    cfg = Config(
        telegram_token="",
        agent_server_url="",
        auth_token="",
        queue_url="",
        command_whitelist=["/allowed"],
    )
    assert cfg.is_command_allowed(None)


def test_load_whitelist_non_string_entries(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[white_list_commands]
whitelist = ["/ok", 123, { a = 1 }]
"""
    )
    assert load_command_whitelist(config_path) == ["/ok"]


def test_load_whitelist_invalid_type_logs_and_returns_empty(tmp_path, caplog):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """[white_list_commands]
whitelist = "not-a-list"
"""
    )
    with caplog.at_level("WARNING"):
        result = load_command_whitelist(config_path)
    assert result == []
    assert any("Command whitelist is not a list" in rec.message for rec in caplog.records)


def test_load_whitelist_missing_file_returns_empty(tmp_path):
    missing = tmp_path / "missing.toml"
    assert load_command_whitelist(missing) == []


def test_load_whitelist_malformed_toml_returns_empty(tmp_path, caplog):
    config_path = tmp_path / "config.toml"
    config_path.write_text("not = [ [")
    with caplog.at_level("WARNING"):
        result = load_command_whitelist(config_path)
    assert result == []
    assert any("Failed to load command whitelist" in rec.message for rec in caplog.records)
