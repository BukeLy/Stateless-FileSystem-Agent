"""测试 Claude Agent SDK 返回的消息结构."""
import asyncio
import os

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
)


async def test_sdk_response():
    """测试 SDK 返回内容."""
    options = ClaudeAgentOptions(
        cwd='/tmp',
        model='haiku',
        permission_mode='bypassPermissions',
        max_turns=5,
    )

    print("=" * 60)
    print("测试 SDK 返回的消息结构")
    print("=" * 60)

    async for message in query(prompt="说 Hello World", options=options):
        print(f"\n--- Message Type: {type(message).__name__} ---")

        if isinstance(message, AssistantMessage):
            print(f"  model: {message.model}")
            print(f"  content blocks: {len(message.content)}")
            for i, block in enumerate(message.content):
                print(f"    [{i}] {type(block).__name__}: {repr(block)[:200]}")

        elif isinstance(message, ResultMessage):
            print(f"  session_id: {message.session_id}")
            print(f"  is_error: {message.is_error}")
            print(f"  result: {message.result}")
            print(f"  num_turns: {message.num_turns}")
            print(f"  total_cost_usd: {message.total_cost_usd}")


if __name__ == '__main__':
    asyncio.run(test_sdk_response())
