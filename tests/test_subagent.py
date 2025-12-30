"""Test SubAgent and MCP configuration with Claude Agent SDK."""
import asyncio
import json
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
    ToolResultBlock,
)

# 本地测试使用agent-sdk-server的claude-config
CONFIG_DIR = Path(__file__).parent.parent / 'agent-sdk-server' / 'claude-config'


def load_mcp_servers() -> dict:
    """Load MCP servers configuration from mcp.json."""
    mcp_file = CONFIG_DIR / 'mcp.json'
    if mcp_file.exists():
        with open(mcp_file) as f:
            config = json.load(f)
            return config.get('mcpServers', {})
    return {}


def load_agents() -> dict[str, AgentDefinition]:
    """Load SubAgent definitions from agents.json + prompt files."""
    agents_config = CONFIG_DIR / 'agents.json'
    if not agents_config.exists():
        return {}

    with open(agents_config) as f:
        config = json.load(f)

    agents = {}
    for name, definition in config.items():
        prompt_file = CONFIG_DIR / definition.get('prompt_file', '')
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


async def test_subagent():
    import os
    cwd = '/tmp/test-workspace'
    os.makedirs(cwd, exist_ok=True)

    mcp_servers = load_mcp_servers()
    agents = load_agents()

    print("=== Loaded MCP Servers ===")
    for name, cfg in mcp_servers.items():
        print(f"  {name}: {cfg}")

    print("\n=== Loaded SubAgents ===")
    for name, agent in agents.items():
        print(f"  {name}:")
        print(f"    description: {agent.description[:60]}...")
        print(f"    tools: {agent.tools}")
        print(f"    model: {agent.model}")

    # 测试查询：让agent列出可用的tools
    options = ClaudeAgentOptions(
        cwd=cwd,
        model='haiku',  # 使用haiku节省成本
        permission_mode='bypassPermissions',
        max_turns=3,
        allowed_tools=['Task'],
        mcp_servers=mcp_servers if mcp_servers else None,
        agents=agents if agents else None,
    )

    print("\n=== Testing aws-support SubAgent with MCP ===")
    print("Prompt: Use aws-support agent to search for Lambda cold start")

    subagent_texts = []
    subagent_tool_results = []

    async for message in query(
        prompt="Use the aws-support agent to explain what is AWS Lambda cold start and how to reduce it.",
        options=options
    ):
        msg_type = type(message).__name__
        # 检查是否来自SubAgent
        is_subagent = hasattr(message, 'parent_tool_use_id') and message.parent_tool_use_id
        prefix = "  [SubAgent] " if is_subagent else ""

        print(f"{prefix}Message type: {msg_type}")

        if hasattr(message, 'content'):
            for block in message.content:
                if hasattr(block, 'text'):
                    # SubAgent文本输出完整保存
                    if is_subagent:
                        subagent_texts.append(block.text)
                    text = block.text[:200] + "..." if len(block.text) > 200 else block.text
                    print(f"{prefix}Text: {text}")
                elif hasattr(block, 'name'):
                    # ToolUseBlock
                    print(f"{prefix}>>> Tool call: {block.name}")
                elif isinstance(block, ToolResultBlock):
                    # ToolResultBlock - MCP工具返回结果
                    content_str = str(block.content)[:500] if block.content else "None"
                    print(f"{prefix}<<< Tool result ({len(str(block.content))} chars): {content_str[:200]}...")
                    if is_subagent and block.content:
                        subagent_tool_results.append(str(block.content))

        if hasattr(message, 'result'):
            result = message.result[:500] + "..." if len(message.result) > 500 else message.result
            print(f"\n=== Final Result ===\n{result}")

    # 打印SubAgent完整输出
    print("\n" + "="*60)
    print("=== SubAgent Complete Output ===")
    print("="*60)
    if subagent_texts:
        print("\n--- SubAgent Text Responses ---")
        for i, t in enumerate(subagent_texts):
            print(f"[{i}] {t[:1000]}{'...' if len(t)>1000 else ''}")
    if subagent_tool_results:
        print("\n--- SubAgent MCP Tool Results ---")
        for i, r in enumerate(subagent_tool_results):
            print(f"[{i}] {r[:1000]}{'...' if len(r)>1000 else ''}")


if __name__ == '__main__':
    asyncio.run(test_subagent())
