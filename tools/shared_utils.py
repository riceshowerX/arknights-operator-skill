#!/usr/bin/env python3
"""
共享工具函数 —— 跨模块复用的通用工具

包含：
- slug 验证（防止路径遍历）
- 句子分割
- 路径安全验证
- 日志配置
"""

import logging
import re
import sys
from pathlib import Path

# 支持从 tools 目录内和从项目根目录两种导入方式
try:
    from constants import SLUG_RE
except ImportError:
    from tools.constants import SLUG_RE

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
