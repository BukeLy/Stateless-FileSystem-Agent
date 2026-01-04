from pathlib import Path
import shutil
import sys
import types

import pytest


PROJECT_ROOT = Path(__file__).parent.parent
AGENT_SERVER_DIR = PROJECT_ROOT / "agent-sdk-server"

if str(AGENT_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_SERVER_DIR))

# Provide minimal stub for claude_agent_sdk to import agent_session without external dependency
claude_agent_sdk = types.ModuleType("claude_agent_sdk")
claude_agent_sdk.query = lambda *args, **kwargs: None
claude_agent_sdk.ClaudeAgentOptions = type("ClaudeAgentOptions", (), {})
claude_agent_sdk.AgentDefinition = type("AgentDefinition", (), {})
claude_agent_sdk.AssistantMessage = type("AssistantMessage", (), {})
claude_agent_sdk.ResultMessage = type("ResultMessage", (), {})
claude_agent_sdk.TextBlock = type("TextBlock", (), {})
sys.modules["claude_agent_sdk"] = claude_agent_sdk

import agent_session  # noqa: E402,E401


def test_setup_lambda_environment_logs_and_raises_on_copytree_error(monkeypatch, tmp_path, capsys):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "skills").mkdir()

    monkeypatch.setattr(agent_session, "CONFIG_SRC", src)
    monkeypatch.setattr(agent_session, "CONFIG_DST", dst)

    def failing_copytree(*args, **kwargs):
        raise PermissionError("no access")

    monkeypatch.setattr(shutil, "copytree", failing_copytree)

    with pytest.raises(RuntimeError) as excinfo:
        agent_session.setup_lambda_environment()

    assert "Failed to copy config item" in str(excinfo.value)
    captured = capsys.readouterr().out
    assert "Failed to copy config item" in captured


def test_setup_lambda_environment_raises_on_copy2_error(monkeypatch, tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "config.json").write_text("{}")

    monkeypatch.setattr(agent_session, "CONFIG_SRC", src)
    monkeypatch.setattr(agent_session, "CONFIG_DST", dst)

    def failing_copy2(*args, **kwargs):
        raise PermissionError("no write access")

    monkeypatch.setattr(shutil, "copy2", failing_copy2)

    with pytest.raises(RuntimeError) as excinfo:
        agent_session.setup_lambda_environment()

    assert "Failed to copy config item" in str(excinfo.value)
