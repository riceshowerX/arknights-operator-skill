#!/usr/bin/env python3
"""
Persona 一致性验证器 —— 用角色已知对话验证生成 Persona 的准确度

这是 arknights-operator-skill 的核心差异化工具之一：
不只生成 Persona，还能量化验证它与角色实际对话的匹配程度。

用法:
    python persona_validator.py --persona ./persona.md --dialogues ./lines.txt --format plain
    python persona_validator.py --persona ./persona.md --dialogues ./voices.json --format prts-json

输出:
    JSON 格式的一致性报告，包含各层匹配度评分和具体违反示例
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Persona 解析
# ──────────────────────────────────────────────

def parse_persona(filepath: str) -> dict:
    """
    从 persona.md 中提取各层规则

    返回: {
        "layer0_rules": [...],
        "layer2_style": {...},
        "layer3_values": [...],
        "layer5_taboos": [...],
        "corrections": [...]
    }
    """
    content = Path(filepath).read_text(encoding="utf-8")

    result = {
        "layer0_rules": [],
        "layer2_style": {},
        "layer3_values": [],
        "layer5_taboos": [],
        "corrections": [],
    }

    # 提取 Layer 0 规则
    layer0_match = re.search(
        r"## Layer 0.*?\n(.*?)(?=\n## Layer|\n## Correction|\Z)",
        content,
        re.DOTALL,
    )
    if layer0_match:
        rules_text = layer0_match.group(1)
        for line in rules_text.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                result["layer0_rules"].append(line.lstrip("- "))

    # 提取 Layer 2 表达风格
    layer2_match = re.search(
        r"## Layer 2.*?\n(.*?)(?=\n## Layer|\n## Correction|\Z)",
        content,
        re.DOTALL,
    )
    if layer2_match:
        style_text = layer2_match.group(1)
        # 提取口头禅
        catchphrase_match = re.search(r"口头禅[：:](.*?)(?:\n|$)", style_text)
        if catchphrase_match:
            result["layer2_style"]["catchphrases"] = catchphrase_match.group(1).strip()
        # 提取高频词
        freq_match = re.search(r"高频词[：:](.*?)(?:\n|$)", style_text)
        if freq_match:
            result["layer2_style"]["frequent_words"] = [
                w.strip() for w in freq_match.group(1).split("、") if w.strip()
            ]
        # 提取自称
        self_ref_match = re.search(r"自称[：:](.*?)(?:\n|$)", style_text)
        if self_ref_match:
            result["layer2_style"]["self_reference"] = self_ref_match.group(1).strip()

    # 提取 Layer 5 禁忌
    layer5_match = re.search(
        r"## Layer 5.*?\n(.*?)(?=\n## Correction|\Z)",
        content,
        re.DOTALL,
    )
    if layer5_match:
        taboo_text = layer5_match.group(1)
        for line in taboo_text.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                result["layer5_taboos"].append(line.lstrip("- "))

    # 提取 Correction
    correction_match = re.search(
        r"## Correction 记录.*?\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )
    if correction_match:
        corr_text = correction_match.group(1)
        if "暂无" not in corr_text:
            for line in corr_text.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("###"):
                    result["corrections"].append(line.lstrip("- #"))

    return result


# ──────────────────────────────────────────────
# 对话加载
# ──────────────────────────────────────────────

def load_dialogues(filepath: str, fmt: str = "plain") -> list[str]:
    """加载对话文本列表"""
    path = Path(filepath)
    content = path.read_text(encoding="utf-8")

    if fmt == "prts-json":
        data = json.loads(content)
        if isinstance(data, dict) and "voice_lines" in data:
            return [v.get("text", "") for v in data["voice_lines"] if v.get("text")]
        return []

    elif fmt == "csv":
        lines = []
        for i, row in enumerate(content.strip().split("\n")):
            if i == 0 and "label" in row.lower():
                continue  # skip header
            parts = row.split(",", 1)
            if len(parts) == 2:
                lines.append(parts[1].strip())
            elif len(parts) == 1 and parts[0].strip():
                lines.append(parts[0].strip())
        return lines

    else:  # plain
        lines = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in [":", "：", "|"]:
                if sep in line:
                    _, _, text = line.partition(sep)
                    lines.append(text.strip())
                    break
            else:
                lines.append(line)
        return lines


# ──────────────────────────────────────────────
# 对话/叙述区分
# ──────────────────────────────────────────────

def _is_likely_dialogue(text: str) -> bool:
    """
    判断文本是否更可能是角色直接说出的台词而非叙述性文本

    启发式规则：
    - 包含引号包裹的直接引语 → 是
    - 第一人称 + 口语化表达 → 是
    - 包含感叹号/问号等情绪标记 → 是
    - 纯叙述（第三人称、时间线、描述性语言）→ 否
    """
    # 有引号包裹的内容
    if re.search(r'[「\u201c\u2018].*[」\u201d\u2019]', text):
        return True

    # 有明显的口语化标记
    if re.search(r"[！!？?……—]", text) and len(text) < 60:
        return True

    # 包含第一人称且是短句（更像台词）
    if re.search(r"^(我|吾|我们|咱们)", text) and len(text) < 50:
        return True

    # 明显的叙述特征（年份、人名开头、长描述）
    if re.search(r"^泰拉历|^\d{4}|^[A-Z][a-z]+（|成立于|属于|是.*组织|是.*角色", text):
        return False

    # 超长文本（>200字）通常是叙述
    if len(text) > 200:
        return False

    # 默认：短文本倾向当作对话，长文本倾向当作叙述
    return len(text) < 80


def _filter_dialogue_lines(lines: list[str]) -> list[str]:
    """
    过滤输入文本，只保留可能是角色直接说出的台词

    这样可以避免叙述性文本（如时间线、关系描述）触发禁忌检测
    """
    return [line for line in lines if _is_likely_dialogue(line)]


# ──────────────────────────────────────────────
# 验证逻辑
# ──────────────────────────────────────────────

def validate_layer0(dialogues: list[str], rules: list[str]) -> dict:
    """
    验证对话是否违反 Layer 0 规则

    检测策略：从每条 Layer 0 规则中提取关键否定约束，
    检查对话中是否存在违反
    """
    violations = []
    passes = []

    for rule in rules:
        rule_violated = False
        violation_examples = []

        # 从规则中提取否定模式
        negation_patterns = _extract_negation_patterns(rule)

        # 无可检测模式 → 标记为 untested
        if not negation_patterns:
            passes.append(rule[:100] + " (不可自动检测)")
            continue

        for i, dialogue in enumerate(dialogues):
            for pattern, description in negation_patterns:
                if re.search(pattern, dialogue):
                    rule_violated = True
                    violation_examples.append({
                        "dialogue_index": i + 1,
                        "dialogue": dialogue[:100],
                        "violation": description,
                    })

        if rule_violated:
            violations.append({
                "rule": rule[:100],
                "violation_count": len(violation_examples),
                "examples": violation_examples[:3],
            })
        else:
            passes.append(rule[:100])

    total = len(rules)
    testable = total - sum(1 for p in passes if "不可自动检测" in p)
    pass_count = len(passes)
    score = round(pass_count / total * 100, 1) if total > 0 else 100

    return {
        "score": score,
        "total_rules": total,
        "testable_rules": testable,
        "passed": pass_count,
        "violated": total - pass_count,
        "violations": violations,
        "pass_examples": passes[:5],
    }


def _extract_negation_patterns(rule: str) -> list[tuple[str, str]]:
    """
    从 Layer 0 规则文本中提取可检测的否定模式

    支持两种提取方式：
    1. 内置模式匹配（常见否定结构）
    2. 从引号内容提取（规则中的具体反例）
    """
    patterns = []

    # === 内置模式 ===

    # "从不用感叹号" / "没有感叹号" / "不用感叹号"
    if re.search(r"不.*感叹号|没有感叹号|不用！", rule):
        patterns.append((r"[！!]", "使用了感叹号"))

    # "从不用命令" / "不用命令口吻"
    if re.search(r"不.*命令", rule):
        patterns.append((r"命令|给我|必须|立刻|马上", "使用了命令式语气"))

    # "不说'xxx'" / "从不说'xxx'" / "不用'xxx'"
    say_negation = re.findall(r'不(?:会|用|说|能)?[「\u201c\u2018]([^」\u201d\u2019]{2,20})[」\u201d\u2019]', rule)
    for phrase in say_negation:
        patterns.append((re.escape(phrase), f"使用了'{phrase}'"))

    # "不会哭" / "不会流泪"
    if re.search(r"不.*(?:哭|流泪|泪水)", rule):
        patterns.append((r"哭了|流泪|泪流|泪水", "出现了哭泣描写"))

    # "不会咆哮" / "不会吼"
    if re.search(r"不.*(?:咆哮|吼|大喊)", rule):
        patterns.append((r"咆哮|怒吼|大吼|吼道|大喊", "出现了咆哮描写"))

    # "从不...用..." — 通用否定结构
    never_use = re.findall(r"从不用?([^\s，。]{2,10})", rule)
    for phrase in never_use:
        if phrase not in ["感叹号", "命令", "口吻"]:  # 已处理
            escaped = re.escape(phrase)
            if len(phrase) >= 2:  # 只匹配 2 字以上，避免误报
                patterns.append((escaped, f"使用了'{phrase}'"))

    # === 从引号内容提取反例 ===
    # 规则中常见格式："不应该'xxx'，应该'yyy'"
    # 我们检测 'xxx'（反例）是否出现在对话中
    quoted_phrases = re.findall(r'[「\u201c\u2018]([^」\u201d\u2019]+)[」\u201d\u2019]', rule)
    # 检查引号内容是否在"不/从不/不会"后面 → 是反例
    for phrase in quoted_phrases:
        # 如果引号内容在"不"后面，说明这是反例，应该检测
        if re.search(rf"不[^」\u201d\u2019]*{re.escape(phrase)}", rule):
            if len(phrase) >= 2:
                patterns.append((re.escape(phrase), f"使用了反例表达'{phrase}'"))

    return patterns


def validate_layer2_style(dialogues: list[str], style: dict) -> dict:
    """
    验证对话是否符合 Layer 2 表达风格

    检测项：
    1. 口头禅是否出现在对话中
    2. 高频词是否确实高频
    3. 自称模式是否一致
    """
    checks = []

    # 口头禅检测
    catchphrases = style.get("catchphrases", "")
    if catchphrases:
        # 提取引号中的口头禅（支持中文引号「」、弯引号""、直引号""）
        phrases = re.findall(r'[「\u201c"]([^」\u201d"]+)[」\u201d"]', catchphrases)
        if not phrases:
            phrases = [w.strip() for w in catchphrases.split("、") if w.strip()]

        for phrase in phrases:
            # 去掉引号标记，只检测核心词
            clean_phrase = phrase.strip("「」""''")
            count = sum(1 for d in dialogues if clean_phrase in d)
            freq = round(count / len(dialogues) * 100, 1) if dialogues else 0
            checks.append({
                "type": "catchphrase",
                "item": clean_phrase,
                "occurrence_count": count,
                "frequency_pct": freq,
                "status": "consistent" if freq > 5 or count > 0 else "absent",
            })

    # 高频词检测
    freq_words = style.get("frequent_words", [])
    for word in freq_words:
        count = sum(d.count(word) for d in dialogues)
        checks.append({
            "type": "frequent_word",
            "item": word,
            "occurrence_count": count,
            "status": "frequent" if count >= 3 else "rare",
        })

    # 自称模式检测
    self_ref = style.get("self_reference", "")
    if "省略" in self_ref or "极少" in self_ref:
        # 检查"我"的使用频率
        wo_count = sum(d.count("我") for d in dialogues)
        avg_per_line = round(wo_count / len(dialogues), 2) if dialogues else 0
        checks.append({
            "type": "self_reference",
            "item": "我",
            "occurrence_count": wo_count,
            "avg_per_line": avg_per_line,
            "expected": "low",
            "status": "consistent" if avg_per_line < 1.0 else "inconsistent",
        })

    consistent = sum(1 for c in checks if c["status"] in ["consistent", "frequent"])
    total = len(checks) if checks else 1
    score = round(consistent / total * 100, 1)

    return {
        "score": score,
        "checks": checks,
    }


def validate_layer5_taboos(dialogues: list[str], taboos: list[str]) -> dict:
    """
    验证对话是否触碰 Layer 5 禁忌

    改进：只检测可能是角色直接说出的台词，跳过叙述性文本，
    避免将时间线、关系描述等叙述内容误判为角色违反禁忌。
    """
    # 过滤出可能是角色台词的行
    dialogue_lines = _filter_dialogue_lines(dialogues)

    hits = []

    for taboo in taboos:
        # 提取禁忌中的核心词
        keywords = _extract_taboo_keywords(taboo)

        for i, dialogue in enumerate(dialogue_lines):
            for kw in keywords:
                if kw in dialogue:
                    hits.append({
                        "taboo": taboo[:80],
                        "keyword": kw,
                        "dialogue": dialogue[:100],
                    })

    score = 100 if not hits else max(0, 100 - len(hits) * 10)

    return {
        "score": score,
        "taboo_count": len(taboos),
        "total_lines": len(dialogues),
        "dialogue_lines_checked": len(dialogue_lines),
        "narrative_lines_skipped": len(dialogues) - len(dialogue_lines),
        "violation_count": len(hits),
        "violations": hits[:5],
    }


def _extract_taboo_keywords(taboo: str) -> list[str]:
    """从禁忌描述中提取可检测的关键词"""
    keywords = []

    # 检测引号中的词（优先级最高，最精确）
    quoted = re.findall(r'[「\u201c\u2018]([^」\u201d\u2019]+)[」\u201d\u2019]', taboo)
    for q in quoted:
        if len(q) >= 2:  # 只用 2 字以上关键词，避免单字误报
            keywords.append(q)

    # 检测常见的敏感行为词（仅 2 字以上）
    sensitive = ["牺牲", "棋子", "放弃", "消灭", "贱民", "低等"]
    for s in sensitive:
        if s in taboo and s not in keywords:
            keywords.append(s)

    # 注意：不再包含"杀"和"死"等单字关键词，
    # 因为在叙述文本中误报率极高（如"以勒什死去"）
    # 如果需要检测死亡相关，用更精确的 2 字词组
    death_phrases = ["去死", "杀了", "弄死", "处死"]
    for s in death_phrases:
        if s in taboo:
            keywords.append(s)

    return keywords


# ──────────────────────────────────────────────
# 主验证流程
# ──────────────────────────────────────────────

def validate(persona_path: str, dialogues_path: str, fmt: str = "plain") -> dict:
    """执行完整的 Persona 一致性验证"""
    persona = parse_persona(persona_path)
    dialogues = load_dialogues(dialogues_path, fmt)

    if not dialogues:
        return {"error": "未找到任何对话数据", "score": 0}

    # 各层验证
    layer0_result = validate_layer0(dialogues, persona["layer0_rules"])
    layer2_result = validate_layer2_style(dialogues, persona["layer2_style"])
    layer5_result = validate_layer5_taboos(dialogues, persona["layer5_taboos"])

    # 综合评分（Layer 0 权重最高）
    overall_score = (
        layer0_result["score"] * 0.5
        + layer2_result["score"] * 0.3
        + layer5_result["score"] * 0.2
    )

    return {
        "overall_score": round(overall_score, 1),
        "dialogue_count": len(dialogues),
        "layer0_core_personality": layer0_result,
        "layer2_expression_style": layer2_result,
        "layer5_boundaries": layer5_result,
        "corrections_count": len(persona["corrections"]),
        "grade": _score_to_grade(overall_score),
    }


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A — 高度一致，Persona 准确反映角色特征"
    elif score >= 75:
        return "B — 基本一致，存在少量违反需修正"
    elif score >= 60:
        return "C — 部分一致，需要补充 Correction 或调整 Layer 0"
    else:
        return "D — 严重不一致，建议重写 Persona"


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Persona 一致性验证器 — 用角色实际对话验证 Persona 的准确度",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python persona_validator.py --persona ./persona.md --dialogues ./lines.txt
  python persona_validator.py --persona ./persona.md --dialogues ./voices.json --format prts-json
  python persona_validator.py --persona ./persona.md --dialogues ./data.csv --format csv
        """,
    )

    parser.add_argument("--persona", required=True, help="persona.md 文件路径")
    parser.add_argument("--dialogues", required=True, help="对话数据文件路径")
    parser.add_argument("--format", choices=["plain", "prts-json", "csv"], default="plain", help="对话格式")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    result = validate(args.persona, args.dialogues, args.format)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"验证报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
