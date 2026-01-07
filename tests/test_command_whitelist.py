import runpy
from pathlib import Path

import pytest

CLIENT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "agent-sdk-client" / "config.py"
config_module = runpy.run_path(CLIENT_CONFIG_PATH)
Config = config_module["Config"]
load_command_whitelist = config_module["load_command_whitelist"]


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
