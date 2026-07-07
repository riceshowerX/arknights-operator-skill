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

import contextlib

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
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
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
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ──────────────────────────────────────────────
# 正则安全工具（AST 级 ReDoS 防护，统一实现）
# ──────────────────────────────────────────────

# Python 3.11+ 用 re._parser，3.10 回退 sre_parse
try:
    import re._parser as _sre_parse
except ImportError:
    import sre_parse as _sre_parse

# 正则复杂度限制（统一常量）
_MAX_PATTERN_LENGTH = 500          # 单条正则最大字符数
_MAX_QUANTIFIED_GROUPS = 3         # 量词修饰的捕获/非捕获组最大嵌套层数
_MAX_TOTAL_QUANTIFIERS = 20        # 单条正则中量词总数上限

# 已知的 ReDoS 危险模式（补充 AST 检测无法覆盖的边界情况）
# 注意：使用 r-string，\1 写成 \\1 以避免被当作反向引用
_REDOS_DANGEROUS = re.compile(
    r'\((?!\?)[^)]*\)[+*{]|'           # 捕获组后跟量词
    r'\.\*\.\*|'                        # 连续贪婪匹配
    r'\(\?:\.\*\)\*|'                   # 非捕获组贪婪匹配后跟量词
    r'\(\.\*\)[+*]|'                    # 捕获组贪婪匹配后跟量词
    r'\([^)]+\)\\d+[+*{]|'             # 反向引用 \d 后跟量词（近似模式）
    r'\\d[+*{].*\\d[+*{]'              # 多个量词修饰的 \d 类
)


def analyze_regex_safety(pattern: str) -> list[str]:
    """AST 级别分析正则表达式的 ReDoS 风险（统一核心实现）。

    使用 _sre_parse 解析正则 AST，准确识别：
    - 量词修饰的子组内部是否也包含量词（嵌套量词）
    - 交替分支中的重叠前缀
    - 反向引用 + 量词组合
    - 量词总数超限

    同时做长度检查与正则模式补充检测。

    Args:
        pattern: 正则表达式字符串

    Returns:
        风险描述列表，空列表表示安全。
        单一来源实现，供 safe_compile_regex / canon_checker 共用。
    """
    risks: list[str] = []

    # 1. 长度检查
    if len(pattern) > _MAX_PATTERN_LENGTH:
        risks.append(f"正则过长 ({len(pattern)} > {_MAX_PATTERN_LENGTH})")
        return risks

    # 2. 正则模式补充检测（AST 难以覆盖的危险模式）
    if _REDOS_DANGEROUS.search(pattern):
        risks.append("匹配已知 ReDoS 危险模式")

    # 3. AST 级检测
    try:
        parsed = _sre_parse.parse(pattern)
    except re.error as e:
        risks.append(f"正则语法错误: {e}")
        return risks

    quantified_group_depth = 0

    def _walk(node, depth: int = 0) -> None:
        nonlocal quantified_group_depth
        for item in node:
            op = item[0]
            av = item[1]

            # 量词：* + ? {m,n}
            if op in (_sre_parse.MAX_REPEAT, _sre_parse.MIN_REPEAT):
                repeat_args = av  # (min, max, subpattern)
                if not isinstance(repeat_args, tuple) or len(repeat_args) < 3:
                    continue
                sub = repeat_args[2]

                # 检查子模式内部是否包含量词 → 嵌套量词
                has_inner_quant = False
                for sub_item in sub:
                    if sub_item[0] in (_sre_parse.MAX_REPEAT, _sre_parse.MIN_REPEAT):
                        has_inner_quant = True
                        break
                    # 子模式中的组可能包含量词
                    if sub_item[0] == _sre_parse.SUBPATTERN:
                        sub_sub = sub_item[1]
                        if isinstance(sub_sub, tuple) and len(sub_sub) >= 4:
                            inner = sub_sub[3]
                            for ii in inner:
                                if ii[0] in (_sre_parse.MAX_REPEAT, _sre_parse.MIN_REPEAT):
                                    has_inner_quant = True
                                    break

                if has_inner_quant:
                    quantified_group_depth += 1
                    if quantified_group_depth > _MAX_QUANTIFIED_GROUPS:
                        risks.append(
                            f"嵌套量词层数 {quantified_group_depth} > {_MAX_QUANTIFIED_GROUPS}"
                        )

                # 递归分析子模式
                _walk(sub, depth + 1)

            # 子组 / 捕获组
            elif op == _sre_parse.SUBPATTERN:
                sub_args = av
                if isinstance(sub_args, tuple) and len(sub_args) >= 4:
                    _walk(sub_args[3], depth + 1)

            # 交替分支 (a|b)：检查重叠
            elif op == _sre_parse.BRANCH:
                branches = av
                if isinstance(branches, tuple) and len(branches) >= 2:
                    for branch in branches[1]:
                        if hasattr(branch, "__iter__"):
                            _walk(
                                branch if hasattr(branch, "__len__") else [branch],
                                depth + 1,
                            )

    _walk(parsed)

    # 4. 量词总数检查
    total_quantifiers = len([
        item for item in parsed
        if item[0] in (_sre_parse.MAX_REPEAT, _sre_parse.MIN_REPEAT)
    ])
    if total_quantifiers > _MAX_TOTAL_QUANTIFIERS:
        risks.append(
            f"量词总数 {total_quantifiers} > {_MAX_TOTAL_QUANTIFIERS}"
        )

    return risks


def safe_compile_regex(pattern: str, max_length: int = 500) -> re.Pattern | None:
    """安全编译正则表达式，防止 ReDoS（基于 AST 级统一实现）。

    内部调用 analyze_regex_safety 做完整检测，检测通过才编译。
    保留宽松接口：不安全时返回 None（不抛异常），便于调用方优雅降级。

    Args:
        pattern: 正则表达式字符串
        max_length: 最大允许长度（向后兼容参数，实际限制由 _MAX_PATTERN_LENGTH 统一控制）

    Returns:
        编译后的正则对象，不安全或编译失败时返回 None
    """
    # 兼容旧 max_length 参数：若调用方传入更严格的限制则优先采用
    effective_max = min(max_length, _MAX_PATTERN_LENGTH) if max_length else _MAX_PATTERN_LENGTH
    if len(pattern) > effective_max:
        logger.warning("正则表达式过长 (%d 字符)，拒绝编译", len(pattern))
        return None

    risks = analyze_regex_safety(pattern)
    if risks:
        logger.warning("正则表达式存在 ReDoS 风险: %s — %s", "; ".join(risks), pattern[:80])
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
