#!/usr/bin/env python3
"""测试 Claude Agent SDK Skills 加载位置"""

import asyncio
import os
import tempfile
from pathlib import Path

# 创建测试目录结构
def setup_test_dirs():
    """创建不同位置的 skill 测试目录"""
    # 1. Project skills: {cwd}/.claude/skills/
    # 2. User skills: ~/.claude/skills/
    # 3. CLAUDE_CONFIG_DIR 相关位置

    test_base = Path(tempfile.mkdtemp(prefix="skill_test_"))

    # 模拟不同的目录结构
    locations = {
        "project_cwd": test_base / "workspace",  # cwd
        "config_dir": test_base / "claude-code",  # CLAUDE_CONFIG_DIR
    }

    # 创建 skill 在不同位置
    skill_content = """---
description: Test skill for location verification
---

# Test Skill

This is a test skill to verify loading location.
"""

    # Project skills: {cwd}/.claude/skills/test-skill/SKILL.md
    project_skill_dir = locations["project_cwd"] / ".claude" / "skills" / "test-skill"
    project_skill_dir.mkdir(parents=True, exist_ok=True)
    (project_skill_dir / "SKILL.md").write_text(skill_content)

    # Config dir skills: {CLAUDE_CONFIG_DIR}/skills/test-skill/SKILL.md
    config_skill_dir = locations["config_dir"] / "skills" / "test-skill"
    config_skill_dir.mkdir(parents=True, exist_ok=True)
    (config_skill_dir / "SKILL.md").write_text(skill_content)

    # Config dir .claude/skills: {CLAUDE_CONFIG_DIR}/.claude/skills/test-skill/SKILL.md
    config_claude_skill_dir = locations["config_dir"] / ".claude" / "skills" / "test-skill"
    config_claude_skill_dir.mkdir(parents=True, exist_ok=True)
    (config_claude_skill_dir / "SKILL.md").write_text(skill_content)

    print(f"Test base: {test_base}")
    print(f"Project cwd: {locations['project_cwd']}")
    print(f"Config dir: {locations['config_dir']}")
    print(f"\nCreated skills at:")
    print(f"  1. {project_skill_dir}/SKILL.md")
    print(f"  2. {config_skill_dir}/SKILL.md")
    print(f"  3. {config_claude_skill_dir}/SKILL.md")

    return locations


async def test_skill_loading(cwd: str, config_dir: str = None):
    """测试不同配置下 skill 是否被加载"""
    from claude_agent_sdk import query, ClaudeAgentOptions

    print(f"\n{'='*60}")
    print(f"Testing with:")
    print(f"  cwd: {cwd}")
    print(f"  CLAUDE_CONFIG_DIR: {config_dir or 'not set'}")

    # 设置环境变量
    if config_dir:
        os.environ['CLAUDE_CONFIG_DIR'] = config_dir
    elif 'CLAUDE_CONFIG_DIR' in os.environ:
        del os.environ['CLAUDE_CONFIG_DIR']

    options = ClaudeAgentOptions(
        cwd=cwd,
        setting_sources=["user", "project"],
        allowed_tools=["Skill"],
        model="haiku",
        max_turns=1,
    )

    try:
        print(f"\nQuerying: 'What skills are available?'")
        async for message in query(
            prompt="What skills are available? Just list them briefly.",
            options=options
        ):
            print(f"  Response type: {type(message).__name__}")
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        print(f"  Text: {block.text[:200]}...")
    except Exception as e:
        print(f"  Error: {e}")


async def main():
    locations = setup_test_dirs()

    # 测试 1: cwd 指向 workspace，不设置 CLAUDE_CONFIG_DIR
    await test_skill_loading(
        cwd=str(locations["project_cwd"]),
        config_dir=None
    )

    # 测试 2: cwd 指向 workspace，CLAUDE_CONFIG_DIR 指向 config_dir
    await test_skill_loading(
        cwd=str(locations["project_cwd"]),
        config_dir=str(locations["config_dir"])
    )

    # 测试 3: cwd 指向 config_dir
    await test_skill_loading(
        cwd=str(locations["config_dir"]),
        config_dir=str(locations["config_dir"])
    )


if __name__ == "__main__":
    asyncio.run(main())
