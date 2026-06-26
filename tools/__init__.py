"""
工具包初始化 — 确保 tools 目录内的模块可以互相导入

当通过 `from tools.xxx import ...` 或直接运行 tools/ 下的脚本时，
此模块确保 tools 目录在 sys.path 中，使同目录模块可以直接导入。
"""

import sys
from pathlib import Path

_TOOLS_DIR = str(Path(__file__).parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
