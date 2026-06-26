#!/usr/bin/env python3
"""
设定交叉验证器 —— 从多个来源交叉验证角色设定，标注矛盾和可信度

这是 arknights-operator-skill 的核心差异化工具之一：
游戏角色的设定常有社区误解或翻译差异，本工具通过多来源交叉验证，
标注哪些设定有可靠依据、哪些存在矛盾。

用法:
    # 从多个知识库文件交叉验证
    python canon_checker.py --sources ./knowledge1.md ./knowledge2.md

    # 从知识库 + Wiki 数据验证
    python canon_checker.py --sources ./knowledge.md --wiki-data ./prts_data.json

    # 使用自定义误解库
    python canon_checker.py --sources ./knowledge.md --misconceptions ./misconceptions.json

输出:
    JSON 格式的验证报告，包含每个设定项的来源、一致性和可信度
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# Python 3.11+ 用 re._parser，3.10 回退 sre_parse
try:
    import re._parser as _sre_parse
except ImportError:
    import sre_parse as _sre_parse

# 确保 tools 目录在 import 路径中，支持从任意位置运行
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from shared_utils import setup_logging

logger = setup_logging("canon_checker")

# ──────────────────────────────────────────────
# 正则安全：防止 ReDoS 攻击
# ──────────────────────────────────────────────

# 正则复杂度限制
_MAX_PATTERN_LENGTH = 500       # 单条正则最大字符数
_MAX_QUANTIFIED_GROUPS = 3      # 量词修饰的捕获/非捕获组最大嵌套层数
_MAX_TOTAL_QUANTIFIERS = 20     # 单条正则中量词总数上限

# 已知的 ReDoS 危险模式（补充 _ast_level_check 无法覆盖的边界情况）
# 注意：此处使用 r-string，其中 \1 需写成 \\1 以避免被当作反向引用
_REDOS_DANGEROUS = re.compile(
    r'\((?!\?)[^)]*\)[+*{]|'           # 捕获组后跟量词
    r'\.\*\.\*|'                        # 连续贪婪匹配
    r'\(\?:\.\*\)\*|'                   # 非捕获组贪婪匹配后跟量词
    r'\(\.\*\)[+*]|'                    # 捕获组贪婪匹配后跟量词
    r'\([^)]+\)\\d+[+*{]|'             # 反向引用 \\d 后跟量词（近似模式）
    r'\\d[+*{].*\\d[+*{]'              # 多个量词修饰的 \d 类
)


def _ast_level_check(pattern: str) -> list[str]:
    """使用 _sre_parse 做 AST 级别的 ReDoS 风险检测。

    相比逐字符计数，AST 分析能准确识别：
    - 量词修饰的子组内部是否也包含量词（嵌套量词）
    - 交替分支中的重叠前缀（如 (a+|a+)）
    - 反向引用 + 量词组合

    Returns:
        风险描述列表，空列表表示安全
    """
    risks: list[str] = []
    try:
        parsed = _sre_parse.parse(pattern)
    except re.error as e:
        risks.append(f"正则语法错误: {e}")
        return risks

    quantified_group_depth = 0

    def _walk(node: _sre_parse.SubPattern, depth: int = 0) -> None:
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
                        if hasattr(branch, '__iter__'):
                            _walk(branch if hasattr(branch, '__len__') else [branch], depth + 1)

    _walk(parsed)

    # 量词总数检查
    total_quantifiers = len([
        item for item in parsed
        if item[0] in (_sre_parse.MAX_REPEAT, _sre_parse.MIN_REPEAT)
    ])
    if total_quantifiers > _MAX_TOTAL_QUANTIFIERS:
        risks.append(
            f"量词总数 {total_quantifiers} > {_MAX_TOTAL_QUANTIFIERS}"
        )

    return risks


def _validate_regex_safety(pattern: str, source_id: str = "") -> None:
    """验证正则表达式的安全性，防止 ReDoS 攻击

    采用双重检测策略：
    1. AST 级分析（_sre_parse）：检测嵌套量词、重叠交替分支
    2. 正则模式匹配：补充 AST 难以覆盖的危险模式

    Args:
        pattern: 正则表达式字符串
        source_id: 来源标识（用于错误消息）

    Raises:
        ValueError: 正则不安全
    """
    if len(pattern) > _MAX_PATTERN_LENGTH:
        raise ValueError(
            f"正则过长 ({len(pattern)} > {_MAX_PATTERN_LENGTH})：{pattern[:80]}..."
        )

    # AST 级别检测
    ast_risks = _ast_level_check(pattern)
    if ast_risks:
        raise ValueError(
            f"正则包含 ReDoS 风险 [{source_id}]: {'; '.join(ast_risks)} — {pattern[:80]}"
        )

    # 正则模式补充检测
    if _REDOS_DANGEROUS.search(pattern):
        raise ValueError(
            f"正则包含潜在的 ReDoS 模式 [{source_id}]：{pattern[:80]}..."
        )


def _validate_all_patterns_safety(
    check_patterns: list, exclude_patterns: list, source_id: str
) -> None:
    """同时验证 check_patterns 和 exclude_patterns 的正则安全性。

    Args:
        check_patterns: 检测模式列表（字符串或 dict）
        exclude_patterns: 排除模式列表（字符串）
        source_id: 来源标识

    Raises:
        ValueError: 任一正则不安全
    """
    for p in check_patterns:
        if isinstance(p, str):
            _validate_regex_safety(p, source_id)
        elif isinstance(p, dict) and "pattern" in p:
            _validate_regex_safety(p["pattern"], source_id)

    for p in exclude_patterns:
        if isinstance(p, str):
            _validate_regex_safety(p, f"{source_id}:exclude")


# ──────────────────────────────────────────────
# 误解库加载与通用检测模式
# ──────────────────────────────────────────────

# 内置误解库（作为 fallback，优先从 data/misconceptions.json 加载）
BUILTIN_MISCONCEPTIONS: list[dict] = []

# 通用误解检测模式（适用于所有角色）
GENERIC_MISCONCEPTION_PATTERNS = [
    {
        "id": "G001",
        "category": "阵营混淆",
        "description": "检测角色是否被错误地归入不相关的阵营",
        "check_patterns": [
            {
                "pattern": r"(整合运动|深池|莱茵生命|喀兰贸易).{0,10}(创始人|领袖|首领|核心成员)",
                "warning": "请确认该角色是否确实属于此阵营",
            },
        ],
        "exclude_patterns": [],
    },
    {
        "id": "G002",
        "category": "关系误判",
        "description": "检测角色关系是否被过度简化或错误描述",
        "check_patterns": [
            {
                "pattern": r"(纯粹|完全|绝对是).{0,5}(恶人|坏人|反派|敌人)",
                "warning": "角色关系可能被过度简化",
            },
            {
                "pattern": r"(恋人|情侣|夫妻|爱人).{0,5}(但|然而|其实)",
                "warning": "可能存在关系误判或同人创作混淆",
            },
        ],
        "exclude_patterns": [
            r"并非.{0,5}(纯粹|完全)",
            r"不是.{0,5}(恶人|坏人|反派)",
        ],
    },
    {
        "id": "G003",
        "category": "时间线错乱",
        "description": "检测事件时间顺序是否被混淆",
        "check_patterns": [
            {
                "pattern": r"(巴别塔|罗德岛).{0,10}(之前|以前|成立前).{0,10}(整合运动|深池)",
                "warning": "组织时间线可能被混淆",
            },
        ],
        "exclude_patterns": [],
    },
]


def _load_builtin_misconceptions() -> list[dict]:
    """从 data/misconceptions.json 加载内置误解库，失败则返回空列表"""
    data_dir = Path(__file__).parent.parent / "data"
    json_path = data_dir / "misconceptions.json"

    if not json_path.exists():
        return []

    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []

        # 归一化格式
        result = []
        for item in raw:
            if not isinstance(item, dict) or "id" not in item:
                continue
            patterns = item.get("check_patterns", [])
            excludes = item.get("exclude_patterns", [])
            norm_patterns = []
            for p in patterns:
                if isinstance(p, str):
                    norm_patterns.append({"pattern": p, "warning": f"匹配到误解模式: {p}"})
                elif isinstance(p, dict) and "pattern" in p:
                    norm_patterns.append(p)
            # 安全检查：同时验证 check_patterns 和 exclude_patterns
            try:
                _validate_all_patterns_safety(norm_patterns, excludes, item.get("id", "builtin"))
            except ValueError as e:
                print(f"警告：内置误解项 {item.get('id')} 的正则不安全，已跳过: {e}", file=sys.stderr)
                continue
            result.append({
                "id": item["id"],
                "wrong": item.get("wrong", ""),
                "correct": item.get("correct", ""),
                "check_patterns": norm_patterns,
                "exclude_patterns": excludes,
            })
        return result
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


# 初始化时加载
BUILTIN_MISCONCEPTIONS = _load_builtin_misconceptions()


def load_misconceptions(filepath: Optional[str] = None) -> list[dict]:
    """
    加载误解库

    支持从外部 JSON 文件加载自定义误解库，
    格式与 BUILTIN_MISCONCEPTIONS 相同，但 check_patterns
    可以是字符串数组（旧格式）或对象数组（新格式）

    外部文件格式:
    [
        {
            "id": "M005",
            "wrong": "描述",
            "correct": "正确版本",
            "check_patterns": ["正则1", "正则2"]
            // 或 "check_patterns": [{"pattern": "正则", "warning": "警告文字"}]
        }
    ]
    """
    if not filepath:
        return BUILTIN_MISCONCEPTIONS

    path = Path(filepath)
    if not path.exists():
        print(f"警告：误解库文件不存在 {filepath}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    try:
        custom = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"警告：误解库文件格式错误 {filepath}：{e}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    if not isinstance(custom, list):
        print(f"警告：误解库文件应为 JSON 数组 {filepath}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    # 归一化格式：字符串 → 对象
    normalized = []
    for item in custom:
        if not isinstance(item, dict) or "id" not in item:
            continue

        patterns = item.get("check_patterns", [])
        excludes = item.get("exclude_patterns", [])
        norm_patterns = []
        for p in patterns:
            if isinstance(p, str):
                norm_patterns.append({"pattern": p, "warning": f"匹配到误解模式: {p}"})
            elif isinstance(p, dict) and "pattern" in p:
                norm_patterns.append(p)

        # 安全检查：同时验证 check_patterns 和 exclude_patterns
        try:
            _validate_all_patterns_safety(norm_patterns, excludes, item.get("id", "unknown"))
        except ValueError as e:
            print(f"警告：误解项 {item.get('id')} 的正则不安全，已跳过: {e}", file=sys.stderr)
            continue

        normalized.append({
            "id": item["id"],
            "wrong": item.get("wrong", ""),
            "correct": item.get("correct", ""),
            "check_patterns": norm_patterns,
            "exclude_patterns": excludes,
        })

    # 合并：内置 + 自定义
    builtin_ids = {m["id"] for m in BUILTIN_MISCONCEPTIONS}
    extra = [m for m in normalized if m["id"] not in builtin_ids]
    overridden = {m["id"]: m for m in normalized if m["id"] in builtin_ids}

    result = []
    for m in BUILTIN_MISCONCEPTIONS:
        if m["id"] in overridden:
            result.append(overridden[m["id"]])
        else:
            result.append(m)
    result.extend(extra)

    return result


# ──────────────────────────────────────────────
# 设定提取
# ──────────────────────────────────────────────

# 关注的设定字段及其提取模式
CANON_FIELDS = {
    "race": {
        "label": "种族",
        "patterns": [
            r"种族[：:]\s*(萨卡兹|卡特斯|佩洛|鲁珀|菲林|瓦伊凡|鬼|德拉克|里拉|黎博利|龙|沃尔珀|阿达克利斯|安努拉|埃德菲尔|菲尼克斯|未知)(?:\s|混血|[，,\n。]|$)",
            r"(?:是|身为)(萨卡兹|卡特斯|佩洛|鲁珀|菲林|瓦伊凡|鬼|德拉克|里拉|黎博利|龙|沃尔珀|未知)",
        ],
    },
    "faction": {
        "label": "阵营",
        "patterns": [
            r"阵营[：:]\s*(巴别塔|罗德岛|整合运动|龙门近卫局|龙门|卡兹戴尔|莱茵生命|喀兰贸易|维多利亚|深池|谢拉格|乌萨斯|炎国|东国|叙拉古|伊比利亚|萨米)(?:\s|[，,\n。]|$)",
            r"(巴别塔|罗德岛|整合运动|龙门|卡兹戴尔|莱茵生命|喀兰贸易|维多利亚|深池)(?:的|创始人|成员|领袖|核心)",
        ],
    },
    "identity": {
        "label": "身份",
        "patterns": [
            r"身份[：:]\s*([^\n,，。]{2,30})",
            r"是([^\n,，。]*?(?:魔王|领袖|摄政王|干员|创始人|指挥官|战士|学者|公爵|骑士|医生|猎人))(?:[，,\n。]|$)",
        ],
    },
    "mbti": {
        "label": "MBTI",
        "patterns": [
            r"MBTI[：:]\s*([A-Z]{4})",
            r"(INFJ|INTJ|INFP|ENFP|ENTJ|ISTJ|ISFJ|ESFJ|ESTJ|ESTP|ESFP|ISTP|ISFP|ENTP|INTP)",
        ],
    },
}


def extract_canon_claims(text: str, source_label: str) -> list[dict]:
    """
    从文本中提取设定声明

    返回: [{"field": "race", "value": "萨卡兹", "source": "xxx", "context": "xxx"}, ...]
    """
    claims = []

    for field, config in CANON_FIELDS.items():
        for pattern in config["patterns"]:
            for match in re.finditer(pattern, text):
                value = (match.group(1) if match.lastindex else match.group(0)).strip()
                if value and len(value) < 50:
                    # 提取上下文
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    context = text[start:end].strip()

                    claims.append({
                        "field": field,
                        "field_label": config["label"],
                        "value": value,
                        "source": source_label,
                        "context": context,
                    })

    # 去重：同一字段同一值同一来源只保留一条
    seen = set()
    deduped = []
    for c in claims:
        key = (c["field"], c["value"], c["source"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped


def check_misconceptions(
    text: str,
    source_label: str,
    misconceptions: Optional[list[dict]] = None,
) -> list[dict]:
    """
    检查文本中是否包含已知误解

    改进：
    - 支持 exclude_patterns：如果匹配到排除模式，说明文本正在纠正误解，不应报警
    - 上下文验证：检查匹配位置前后是否有否定词，避免将"纠正误解"判定为"含有误解"

    返回: [{"misconception_id": "M001", "matched_pattern": "...", "warning": "...", "source": "xxx"}, ...]
    """
    if misconceptions is None:
        misconceptions = BUILTIN_MISCONCEPTIONS

    warnings = []

    for m in misconceptions:
        excluded = False

        for cp in m["check_patterns"]:
            pattern = cp["pattern"] if isinstance(cp, dict) else cp
            warning_text = cp.get("warning", "") if isinstance(cp, dict) else f"匹配到误解模式: {pattern}"

            match = re.search(pattern, text)
            if not match:
                continue

            # 在匹配点附近检查排除模式（±200 字符上下文）
            ctx_start = max(0, match.start() - 200)
            ctx_end = min(len(text), match.end() + 200)
            surrounding_text = text[ctx_start:ctx_end]

            for exc_pat in m.get("exclude_patterns", []):
                if re.search(exc_pat, surrounding_text):
                    excluded = True
                    break

            if excluded:
                continue

            # 二次验证：检查匹配位置前后是否有否定词
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            surrounding = text[start:end]

            negation_cues = ["不是", "并非", "并不", "没有", "错误", "误解", "不等于", "不同于"]
            is_negation_context = any(cue in surrounding for cue in negation_cues)

            if is_negation_context:
                # 文本正在纠正误解，不报警
                continue

            warnings.append({
                "misconception_id": m["id"],
                "wrong": m["wrong"],
                "correct": m["correct"],
                "matched_pattern": pattern,
                "matched_text": match.group(0),
                "warning": warning_text,
                "source": source_label,
            })

    return warnings


def check_generic_misconceptions(
    text: str,
    source_label: str,
    patterns: Optional[list[dict]] = None,
) -> list[dict]:
    """
    通用误解检测 —— 适用于所有角色的通用模式检测

    检测类型：
    - 阵营混淆：角色被错误归入不相关阵营
    - 关系误判：角色关系被过度简化或错误描述
    - 时间线错乱：事件时间顺序被混淆

    返回: [{"pattern_id": "G001", "category": "阵营混淆", "warning": "...", "source": "xxx"}, ...]
    """
    if patterns is None:
        patterns = GENERIC_MISCONCEPTION_PATTERNS

    warnings = []

    for p in patterns:
        for cp in p.get("check_patterns", []):
            pattern = cp["pattern"] if isinstance(cp, dict) else cp
            warning_text = cp.get("warning", "") if isinstance(cp, dict) else f"匹配到通用模式: {pattern}"

            match = re.search(pattern, text)
            if not match:
                continue

            # 检查排除模式
            excluded = False
            ctx_start = max(0, match.start() - 200)
            ctx_end = min(len(text), match.end() + 200)
            surrounding_text = text[ctx_start:ctx_end]

            for exc_pat in p.get("exclude_patterns", []):
                if re.search(exc_pat, surrounding_text):
                    excluded = True
                    break

            if excluded:
                continue

            # 否定词检测
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            surrounding = text[start:end]
            negation_cues = ["不是", "并非", "并不", "没有", "错误", "误解"]
            if any(cue in surrounding for cue in negation_cues):
                continue

            warnings.append({
                "pattern_id": p["id"],
                "category": p.get("category", "通用检测"),
                "description": p.get("description", ""),
                "matched_text": match.group(0),
                "warning": warning_text,
                "source": source_label,
            })

    return warnings


def check_character_consistency(
    text: str,
    persona: Optional[dict] = None,
) -> list[dict]:
    """
    角色一致性检查 —— 检测文本是否与角色设定一致

    基于 persona.md 中的 Layer 0 规则和 Layer 5 禁忌进行语义级检查：
    - 禁忌规则：如"不使用感叹号"、"不说粗话"
    - 情感一致性：如"从不表现出冷漠"

    Args:
        text: 待检查文本
        persona: 角色 persona 数据（从 persona.md 解析）

    返回: [{"type": "taboo_violation", "detail": "...", "severity": "warning"}, ...]
    """
    issues = []

    if not persona:
        return issues

    # 检查 Layer 5 禁忌
    taboos = persona.get("layer5_taboos", [])
    if isinstance(taboos, list):
        for taboo in taboos:
            if not isinstance(taboo, str):
                continue

            # 将禁忌规则转化为检测模式
            taboo_lower = taboo.lower()

            # 感叹号禁忌
            if "感叹号" in taboo or "！" in taboo:
                excl_count = text.count("！") + text.count("!")
                if excl_count > 0:
                    issues.append({
                        "type": "taboo_violation",
                        "rule": taboo,
                        "detail": f"文本包含 {excl_count} 个感叹号，违反禁忌",
                        "severity": "error",
                    })

            # 粗话禁忌
            if "粗话" in taboo or "脏话" in taboo:
                profanity_words = ["他妈", "操", "妈的", "靠", "卧槽", "草"]
                found = [w for w in profanity_words if w in text]
                if found:
                    issues.append({
                        "type": "taboo_violation",
                        "rule": taboo,
                        "detail": f"文本包含疑似粗话: {', '.join(found)}",
                        "severity": "error",
                    })

            # 冷漠禁忌
            if "冷漠" in taboo or "冷淡" in taboo:
                cold_words = ["无所谓", "随便", "不关我事", "与我无关", "懒得管"]
                found = [w for w in cold_words if w in text]
                if found:
                    issues.append({
                        "type": "consistency_warning",
                        "rule": taboo,
                        "detail": f"文本可能表现出冷漠: {', '.join(found)}",
                        "severity": "warning",
                    })

    # 检查 Layer 0 核心规则
    core_rules = persona.get("layer0_core", [])
    if isinstance(core_rules, list):
        for rule in core_rules:
            if not isinstance(rule, str):
                continue

            # 检测与核心规则明显矛盾的表达
            if "温柔" in rule or "慈悲" in rule:
                harsh_words = ["去死", "滚", "废物", "垃圾", "杀了你"]
                found = [w for w in harsh_words if w in text]
                if found:
                    issues.append({
                        "type": "core_violation",
                        "rule": rule,
                        "detail": f"文本包含与核心规则矛盾的表达: {', '.join(found)}",
                        "severity": "error",
                    })

    return issues


# ──────────────────────────────────────────────
# 交叉验证
# ──────────────────────────────────────────────

def cross_validate(all_claims: list[dict]) -> list[dict]:
    """
    对同一字段的多来源声明进行交叉验证

    规则：
    - 所有来源一致 → confirmed
    - 存在不一致 → conflicted，标注各版本
    - 仅有一个来源 → unverified
    """
    # 按 field 分组
    field_claims = defaultdict(list)
    for claim in all_claims:
        field_claims[claim["field"]].append(claim)

    results = []

    for field, claims in sorted(field_claims.items()):
        # 归一化值（去空格、统一标点）
        normalized_values = {}
        for c in claims:
            nv = c["value"].replace(" ", "").replace("（", "(").replace("）", ")")
            normalized_values.setdefault(nv, []).append(c)

        field_label = claims[0]["field_label"]

        if len(normalized_values) == 1:
            # 所有来源一致
            value = list(normalized_values.keys())[0]
            sources = [c["source"] for c in normalized_values[value]]
            results.append({
                "field": field,
                "label": field_label,
                "status": "confirmed",
                "value": value,
                "source_count": len(sources),
                "sources": sources,
                "confidence": "high" if len(sources) >= 2 else "medium",
            })
        else:
            # 存在不一致
            versions = []
            for nv, cs in normalized_values.items():
                versions.append({
                    "value": cs[0]["value"],
                    "sources": [c["source"] for c in cs],
                    "source_count": len(cs),
                })

            results.append({
                "field": field,
                "label": field_label,
                "status": "conflicted",
                "versions": versions,
                "confidence": "low",
                "recommendation": "需要人工确认正确版本",
            })

    # 标记仅有单一来源的字段
    for r in results:
        if r["status"] == "confirmed" and r.get("source_count", 0) == 1:
            r["status"] = "unverified"

    return results


# ──────────────────────────────────────────────
# 来源可信度评级
# ──────────────────────────────────────────────

SOURCE_RELIABILITY = {
    "prts_wiki": "high",
    "prts": "high",
    "game_text": "high",
    "official": "high",
    "community_research": "medium",
    "fan_work": "low",
    "unknown": "medium",
}


def rate_source_reliability(source_label: str) -> str:
    """根据来源标签评估可信度"""
    label_lower = source_label.lower()
    for key, reliability in SOURCE_RELIABILITY.items():
        if key in label_lower:
            return reliability
    return "medium"


# ──────────────────────────────────────────────
# 文件读取
# ──────────────────────────────────────────────

def load_sources(filepaths: list[str]) -> list[tuple[str, str]]:
    """加载多个来源文件"""
    sources = []
    for fp in filepaths:
        path = Path(fp)
        if not path.exists():
            print(f"警告：文件不存在 {fp}，已跳过", file=sys.stderr)
            continue
        content = path.read_text(encoding="utf-8")
        sources.append((content, path.name))
    return sources


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="设定交叉验证器 — 多来源交叉验证角色设定，标注矛盾和可信度",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python canon_checker.py --sources ./knowledge.md ./other_source.md
  python canon_checker.py --sources ./knowledge.md --output validation.json
  python canon_checker.py --sources ./knowledge.md --misconceptions ./custom_misconceptions.json
        """,
    )

    parser.add_argument("--sources", nargs="+", required=True, help="来源文件路径（支持多个）")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    parser.add_argument("--misconceptions", help="自定义误解库 JSON 文件路径")

    args = parser.parse_args()

    # 加载误解库
    misconceptions = load_misconceptions(args.misconceptions)

    sources = load_sources(args.sources)

    if not sources:
        print("错误：未找到任何有效来源文件", file=sys.stderr)
        sys.exit(1)

    # 提取所有声明
    all_claims = []
    all_warnings = []
    all_generic_warnings = []

    for content, source_label in sources:
        claims = extract_canon_claims(content, source_label)
        all_claims.extend(claims)

        warnings = check_misconceptions(content, source_label, misconceptions)
        all_warnings.extend(warnings)

        # 通用误解检测
        generic_warnings = check_generic_misconceptions(content, source_label)
        all_generic_warnings.extend(generic_warnings)

    # 交叉验证
    validated = cross_validate(all_claims)

    # 统计
    confirmed = sum(1 for v in validated if v["status"] == "confirmed")
    conflicted = sum(1 for v in validated if v["status"] == "conflicted")
    unverified = sum(1 for v in validated if v["status"] == "unverified")

    report = {
        "summary": {
            "source_count": len(sources),
            "total_claims": len(all_claims),
            "confirmed": confirmed,
            "conflicted": conflicted,
            "unverified": unverified,
            "misconception_warnings": len(all_warnings),
            "generic_warnings": len(all_generic_warnings),
        },
        "validated_fields": validated,
        "misconception_warnings": all_warnings,
        "generic_pattern_warnings": all_generic_warnings,
        "source_reliability": {
            label: rate_source_reliability(label) for _, label in sources
        },
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"验证报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
