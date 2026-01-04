---
description: Hello World 示例 Skill，演示如何读取 reference 文件并执行脚本
---

# Hello World Skill

这是一个示例 Skill，用于演示 Skills 的基本结构。

## 使用方法

1. 读取 `reference/message.json` 获取消息内容
2. 运行 `scripts/print_message.py` 输出所有字符

## 文件结构

```
hello-world/
├── SKILL.md
├── reference/
│   └── message.json
└── scripts/
    └── print_message.py
```
