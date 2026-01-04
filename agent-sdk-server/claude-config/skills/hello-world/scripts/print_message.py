#!/usr/bin/env python3
"""输出 reference/message.json 中的所有字符"""

import json
from pathlib import Path

ref_path = Path(__file__).parent.parent / "reference" / "message.json"
content = ref_path.read_text(encoding="utf-8")

for char in content:
    print(char, end="")
