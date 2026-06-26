#!/usr/bin/env python3
"""
共享工具函数 —— 跨模块复用的通用工具

包含：
- slug 验证（防止路径遍历）
- 句子分割
- 路径安全验证
- 日志配置
"""

import json
import logging
import re
import sys
from pathlib import Path

# 确保 tools 目录在 import 路径中，支持从任意位置运行
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from constants import SLUG_RE

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Slug 验证
# ──────────────────────────────────────────────


def validate_slug(slug: str) -> str:
    """验证 slug 格式，防止路径遍历和非法字符

    Args:
        slug: 角色标识符

    Returns:
        验证通过的 slug

    Raises:
        ValueError: slug 格式不合法
    """
    slug = slug.strip()
    if not SLUG_RE.match(slug):
        raise ValueError(
            f"非法 slug: '{slug}'。slug 只能包含小写字母、数字和连字符，"
            f"且不能以连字符开头。示例: te-lei-xi-ya"
        )
    return slug


# ──────────────────────────────────────────────
# 路径安全验证
# ──────────────────────────────────────────────


def validate_path(path: str, allowed_prefixes: list[str] | None = None) -> str:
    """验证文件路径是否在允许范围内，防止路径遍历攻击

    使用 Path.relative_to() 做精确前缀匹配，避免 startswith 绕过。

    Args:
        path: 待验证的路径
        allowed_prefixes: 允许的目录前缀列表，默认 [cwd, home, /tmp]

    Returns:
        解析后的绝对路径

    Raises:
        ValueError: 路径不在允许范围内
    """
    if allowed_prefixes is None:
        allowed_prefixes = [
            str(Path.cwd()),
            str(Path.home()),
            "/tmp",
        ]

    resolved = Path(path).resolve()
    for prefix in allowed_prefixes:
        prefix_path = Path(prefix).resolve()
        try:
            resolved.relative_to(prefix_path)
            return str(resolved)
        except ValueError:
            continue

    raise ValueError(
        f"安全限制：路径 '{path}' 不在允许的目录内。"
        f"允许的目录: {', '.join(allowed_prefixes)}"
    )


# ──────────────────────────────────────────────
# 句子分割
# ──────────────────────────────────────────────


def split_sentences(text: str) -> list[str]:
    """将文本分割为句子

    处理中文标点（。！？）和英文标点（.!?），
    同时处理省略号（...）和中文省略号（……）。

    Args:
        text: 输入文本

    Returns:
        句子列表
    """
    # 先保护省略号
    text = text.replace("……", "\x00ELLIPSIS\x00")
    text = text.replace("...", "\x00ELLIPSIS\x00")

    # 按标点分割
    parts = re.split(r'[。！？!?\n]+', text)

    # 恢复省略号
    parts = [p.replace("\x00ELLIPSIS\x00", "……") for p in parts]

    return [p.strip() for p in parts if p.strip()]


# ──────────────────────────────────────────────
# 日志配置
# ──────────────────────────────────────────────


def setup_logging(name: str = "arknights-operator-skill", level: int = logging.INFO) -> logging.Logger:
    """配置统一的日志格式

    Args:
        name: logger 名称
        level: 日志级别

    Returns:
        配置好的 logger
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


# ──────────────────────────────────────────────
# 原子写入
# ──────────────────────────────────────────────


def atomic_write_json(filepath: str | Path, data: dict, indent: int = 2) -> None:
    """原子写入 JSON 文件

    先写入临时文件，再原子性重命名，防止写入中断导致文件损坏。

    Args:
        filepath: 目标文件路径
        data: 要写入的数据
        indent: JSON 缩进
    """
    import json
    import os
    import tempfile

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 写入临时文件，再原子性重命名
    fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent,
        prefix=f".{filepath.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.write("\n")
        os.replace(tmp_path, filepath)
    except BaseException:
        # 写入失败时清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json_safe(filepath: str | Path) -> dict | None:
    """安全加载 JSON 文件，文件不存在或格式错误时返回 None

    Args:
        filepath: JSON 文件路径

    Returns:
        解析后的数据，或 None
    """
    import json

    filepath = Path(filepath)
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ──────────────────────────────────────────────
# 正则安全工具
# ──────────────────────────────────────────────


def safe_compile_regex(pattern: str, max_length: int = 500) -> re.Pattern | None:
    """安全编译正则表达式，防止 ReDoS

    Args:
        pattern: 正则表达式字符串
        max_length: 最大允许长度

    Returns:
        编译后的正则对象，不安全时返回 None
    """
    if len(pattern) > max_length:
        logger.warning("正则表达式过长 (%d 字符)，拒绝编译", len(pattern))
        return None

    # 检查嵌套量词（ReDoS 的常见特征）
    nested_quantifier_count = len(re.findall(r'[\*\+][\*\+]', pattern))
    nested_quantifier_count += len(re.findall(r'\{[\d,]+?\}[\*\+]', pattern))
    if nested_quantifier_count > 2:
        logger.warning("正则表达式包含过多嵌套量词 (%d)，可能存在 ReDoS 风险", nested_quantifier_count)
        return None

    try:
        return re.compile(pattern)
    except re.error as e:
        logger.warning("正则表达式编译失败: %s", e)
        return None


# ──────────────────────────────────────────────
# Context JSON Schema 验证
# ──────────────────────────────────────────────

# 当前支持的 schema 版本
_CONTEXT_SCHEMA_VERSION = "1.0.0"

# AnnotatedLine id 格式: V001 / S001 / A001
_LINE_ID_RE = re.compile(r'^[VSA]\d{3,}$')
_SLUG_FORMAT_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


class SchemaValidationError(Exception):
    """context.json schema 验证错误"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"schema 验证失败 ({len(errors)} 项): " + "; ".join(errors[:5]))


def validate_context(data: dict, strict: bool = False) -> list[str]:
    """验证 context.json 数据是否符合 schema。

    不依赖外部库（如 jsonschema），使用纯 Python 手写校验，
    确保零依赖约束不变。

    Args:
        data: context.json 反序列化后的 dict
        strict: 严格模式 — 警告也视为错误

    Returns:
        错误列表（空列表 = 通过）
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- 顶层必填字段 ---
    for field in ("character", "slug", "annotated_lines", "stats"):
        if field not in data:
            errors.append(f"缺少必填字段: {field}")

    # --- schema_version ---
    if "schema_version" not in data:
        warnings.append("缺少 schema_version 字段，建议添加以支持版本化校验")
    elif data["schema_version"] != _CONTEXT_SCHEMA_VERSION:
        warnings.append(
            f"schema_version={data['schema_version']} != 当前版本 {_CONTEXT_SCHEMA_VERSION}，"
            f"可能存在不兼容"
        )

    # --- slug 格式 ---
    slug = data.get("slug", "")
    if slug and not _SLUG_FORMAT_RE.match(slug):
        errors.append(f"slug 格式无效: {slug!r}，应为小写字母数字+连字符")

    # --- annotated_lines ---
    lines = data.get("annotated_lines", [])
    if not isinstance(lines, list):
        errors.append("annotated_lines 应为数组")
    else:
        for i, line in enumerate(lines):
            if not isinstance(line, dict):
                errors.append(f"annotated_lines[{i}] 应为对象")
                continue

            # 必填字段
            for field in ("id", "text", "source", "context"):
                if field not in line:
                    errors.append(f"annotated_lines[{i}] 缺少必填字段: {field}")

            # id 格式
            line_id = line.get("id", "")
            if line_id and not _LINE_ID_RE.match(line_id):
                errors.append(f"annotated_lines[{i}].id 格式无效: {line_id!r}")

            # source 枚举
            source = line.get("source", "")
            valid_sources = {"voice", "story", "archive"}
            if source and source not in valid_sources:
                errors.append(
                    f"annotated_lines[{i}].source={source!r} 不在有效值 {valid_sources} 中"
                )

            # context 必填
            ctx = line.get("context")
            if isinstance(ctx, dict):
                if "phase" not in ctx:
                    errors.append(f"annotated_lines[{i}].context 缺少必填字段: phase")
            elif ctx is None:
                errors.append(f"annotated_lines[{i}].context 为 null")

    # --- stats ---
    stats = data.get("stats")
    if isinstance(stats, dict):
        for field in ("total_lines", "source_distribution", "phase_distribution"):
            if field not in stats:
                errors.append(f"stats 缺少必填字段: {field}")

        total = stats.get("total_lines")
        if isinstance(total, int) and total != len(lines):
            warnings.append(
                f"stats.total_lines={total} != annotated_lines 实际长度 {len(lines)}"
            )

    return errors + warnings if strict else errors


def validate_context_file(path: str | Path, strict: bool = False) -> list[str]:
    """从文件加载并验证 context.json。

    Args:
        path: context.json 文件路径
        strict: 严格模式

    Returns:
        错误列表
    """
    filepath = Path(path)
    if not filepath.exists():
        return [f"context.json 文件不存在: {filepath}"]

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"context.json 解析失败: {e}"]

    if not isinstance(data, dict):
        return ["context.json 顶层应为对象"]

    return validate_context(data, strict=strict)
