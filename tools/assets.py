#!/usr/bin/env python3
"""领域资产定位 —— `data/` 目录解析、JSON 读取回退、默认路径推断（单一契约源）。

本模块解决两类「同一个位置/同一个回退逻辑写了多份」的问题：

1. 「读 JSON，失败回退内建值」原先在 4 个模块各写一遍（`dialogue_fingerprint`、
   `speech_act_analyzer`、`relationship_graph`、`canon_checker`），告警文案不一、
   异常类型不一。统一收敛为 :func:`load_json_or`。
2. `data/` 目录原先在 5 处硬编码 `Path(__file__).parent.parent / "data"`，安装态
   （wheel / 非仓库根 CWD）必然失效。统一收敛为 :func:`data_dir`，权威副本位于
   包内 `tools/_data/`，并保留仓库根 `data/` 作为「用户本地覆盖位」。

分区（按批次）：
  * 批次 3：``load_json_or()``
  * 批次 4：``data_dir()`` / ``data_file()`` / ``project_root()`` /
    ``default_base_dir()`` / ``assert_data_assets()``

设计约束：
  * 只依赖标准库 + `shared_utils`（不 import 任何业务模块，避免循环依赖）。
  * 任何函数都不抛 `UnicodeDecodeError`（走 `shared_utils.read_text_utf8`）。
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# 确保 tools 目录在 import 路径中（同时支持 `python tools/xxx.py` 与 `import tools.xxx`）
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from shared_utils import read_text_utf8

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

#: 包内权威资产目录名（相对 `tools/`）
PACKAGE_DATA_DIRNAME = "_data"

#: 资产目录必须包含的文件（缺任一即视为「资产缺失」）
REQUIRED_DATA_FILES: tuple[str, ...] = (
    "operator_db.json",
    "emotion_lexicon.json",
    "speech_act_rules.json",
    "misconceptions.json",
    "context.schema.json",
    "pinyin_map.json",
)

#: 用于判定「仓库根 data/ 是可用的用户覆盖位」的哨兵文件
_LEGACY_SENTINEL = "operator_db.json"

#: 向上查找项目根时识别的标记文件
_PROJECT_MARKERS: tuple[str, ...] = ("pyproject.toml", ".git")

#: 环境变量：显式指定资产目录
ENV_DATA_DIR = "ARKNIGHTS_DATA_DIR"
#: 环境变量：显式指定 operators 目录
ENV_OPERATORS_DIR = "ARKNIGHTS_OPERATORS_DIR"
#: 环境变量：显式指定 Prompt 模板目录
ENV_PROMPTS_DIR = "ARKNIGHTS_PROMPTS_DIR"

#: 包内 Prompt 模板目录名（相对 `tools/`）
PACKAGE_PROMPTS_DIRNAME = "_prompts"

#: Prompt 模板目录必须包含的文件（供自检；缺任一视为「模板缺失」）
REQUIRED_PROMPT_FILES: tuple[str, ...] = (
    "knowledge_builder.md",
    "knowledge_analyzer.md",
    "persona_builder.md",
    "persona_analyzer.md",
    "intake.md",
    "correction_handler.md",
    "merger.md",
)


# ──────────────────────────────────────────────
# 批次 3 · JSON 读取回退（D-5）
# ──────────────────────────────────────────────


def load_json_or(filepath: str | Path, builtin: Any, *, kind: str = "JSON 资产") -> Any:
    """读取 JSON 文件；文件不存在或解析失败时告警并返回内建默认值。

    收敛原先 4 份重复的「try: json.loads(read_text_utf8(...)) except: 回退内建值」
    实现，统一为：文件不存在 → 静默返回 `builtin`；解析/解码/IO 失败 →
    ``logger.warning`` 后返回 `builtin`。

    Args:
        filepath: JSON 文件路径。
        builtin: 解析失败时返回的内建默认值（原样返回，不做拷贝）。
        kind: 告警文案中的人类可读资产名（如「情感词典」）。

    Returns:
        解析后的 JSON 对象，或 `builtin`。

    Note:
        调用方若需要「解析成功但结构不符」的二次校验（例如必须是 dict），
        应在本函数返回后自行判断；本函数只吞掉「读不出来」这一类错误。
    """
    path = Path(filepath)
    if not path.exists():
        logger.debug("%s 不存在，使用内建默认值: %s", kind, path)
        return builtin
    try:
        return json.loads(read_text_utf8(path))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        logger.warning("%s 解析失败 %s: %s，使用内建默认值", kind, path, exc)
        return builtin


# ──────────────────────────────────────────────
# 批次 4 · 项目根与资产目录（P1-6 / P1-8）
# ──────────────────────────────────────────────


def project_root() -> Path:
    """推断项目根目录。

    从本文件所在目录向上逐级查找含 `pyproject.toml` 或 `.git` 的目录；
    找不到（例如被解包到任意目录的 wheel）时返回 `tools/` 的父目录。

    Returns:
        项目根目录的绝对路径。
    """
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate
    return here.parent


def data_dir() -> Path:
    """解析领域资产目录（四级，优先级从高到低）。

    1. 环境变量 ``ARKNIGHTS_DATA_DIR``：显式覆盖（CI / 用户魔改 / 只读挂载）。
    2. ``<项目根>/data``：老仓库布局与用户本地覆盖位（存在哨兵文件即生效）。
    3. ``tools/_data``：包内权威副本（wheel 安装后的正常命中路径）。
    4. ``importlib.resources`` 的 ``tools/_data``：zipimport / 非常规安装兜底。

    若以上均不存在，则回落到 ``<tools 父目录>/data``（最老布局），
    以便调用方沿用原有的「目录不存在 → 返回空/内建值」降级语义。

    Returns:
        资产目录路径（不保证存在，调用方需自行判存在性）。
    """
    env_dir = os.environ.get(ENV_DATA_DIR)
    if env_dir:
        return Path(env_dir).expanduser()

    legacy = project_root() / "data"
    if (legacy / _LEGACY_SENTINEL).exists():
        return legacy

    packaged = Path(__file__).parent / PACKAGE_DATA_DIRNAME
    if packaged.is_dir():
        return packaged

    try:
        resource_dir = Path(str(importlib.resources.files("tools"))) / PACKAGE_DATA_DIRNAME
    except (ImportError, ModuleNotFoundError, TypeError):
        resource_dir = None
    if resource_dir is not None and resource_dir.is_dir():
        return resource_dir

    return Path(__file__).parent.parent / "data"


def data_file(name: str) -> Path:
    """返回资产目录下某个文件的完整路径。

    Args:
        name: 文件名（如 ``operator_db.json``）。

    Returns:
        资产文件的绝对/相对路径（不保证存在）。
    """
    return data_dir() / name


def prompts_dir() -> Path:
    """解析 Prompt 模板目录（三级，优先级从高到低）。

    1. 环境变量 ``ARKNIGHTS_PROMPTS_DIR``：显式覆盖。
    2. ``tools/_prompts``：包内权威副本（v3.6.1 起随 wheel 分发；
       源码态与安装态命中同一路径）。
    3. ``<项目根>/prompts``：v3.6.0 及更早的仓库根布局（老工作副本兼容位）。

    Returns:
        模板目录路径（不保证存在，调用方需自行判存在性）。
    """
    env_dir = os.environ.get(ENV_PROMPTS_DIR)
    if env_dir:
        return Path(env_dir).expanduser()

    packaged = Path(__file__).parent / PACKAGE_PROMPTS_DIRNAME
    if packaged.is_dir():
        return packaged

    return project_root() / "prompts"


def prompt_file(name: str) -> Path:
    """返回模板目录下某个文件的完整路径。

    Args:
        name: 文件名（如 ``knowledge_builder.md``）。

    Returns:
        模板文件的绝对/相对路径（不保证存在）。
    """
    return prompts_dir() / name


def missing_prompt_files(required: tuple[str, ...] | None = None) -> list[str]:
    """返回模板目录中缺失的必需文件名列表（空列表表示模板完整）。"""
    names = REQUIRED_PROMPT_FILES if required is None else required
    directory = prompts_dir()
    return [name for name in names if not (directory / name).exists()]


def default_base_dir() -> Path:
    """推断 operators 目录（`--base-dir` 的默认值）。

    优先级：
    1. 环境变量 ``ARKNIGHTS_OPERATORS_DIR``
    2. ``<项目根>/operators``（项目根由 :func:`project_root` 推断）
    3. ``./operators``（相对 CWD，兼容脚本直接调用的老行为）

    Returns:
        operators 目录路径（不保证存在）。
    """
    env_dir = os.environ.get(ENV_OPERATORS_DIR)
    if env_dir:
        return Path(env_dir).expanduser()

    candidate = project_root() / "operators"
    if candidate.is_dir():
        return candidate

    return Path("./operators")


def missing_data_files(required: tuple[str, ...] | None = None) -> list[str]:
    """返回资产目录中缺失的必需文件名列表（空列表表示资产完整）。

    Args:
        required: 期望的必需文件列表，默认 :data:`REQUIRED_DATA_FILES`。

    Returns:
        缺失的文件名列表（按 `required` 顺序）。
    """
    names = REQUIRED_DATA_FILES if required is None else required
    directory = data_dir()
    return [name for name in names if not (directory / name).exists()]


def assert_data_assets(required: tuple[str, ...] | None = None) -> Path:
    """校验资产目录完整；缺失时记录错误并抛 :class:`DataAssetsMissingError`。

    CLI 入口在 ``main()`` 起始调用，捕获后以退出码 2（用法/前置错误）退出，
    避免安装态「静默降级为空能力」。

    Args:
        required: 期望的必需文件列表，默认 :data:`REQUIRED_DATA_FILES`。

    Returns:
        实际生效的资产目录。

    Raises:
        DataAssetsMissingError: 任一必需资产缺失。
    """
    directory = data_dir()
    missing = missing_data_files(required)
    if missing:
        raise DataAssetsMissingError(directory, missing)
    logger.debug("资产目录：%s", directory)
    return directory


class DataAssetsMissingError(RuntimeError):
    """领域资产缺失（CLI 应映射为退出码 2）。"""

    def __init__(self, directory: Path, missing: list[str]) -> None:
        self.directory = directory
        self.missing = missing
        super().__init__(
            f"领域资产缺失：{directory} 中缺少 {', '.join(missing)}。"
            f"请检查安装完整性，或通过 {ENV_DATA_DIR} 指定资产目录。"
        )
