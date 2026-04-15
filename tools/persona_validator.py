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
        # 如 "从不用感叹号" → 检查对话是否有感叹号
        negation_patterns = _extract_negation_patterns(rule)

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
    pass_count = len(passes)
    score = round(pass_count / total * 100, 1) if total > 0 else 100

    return {
        "score": score,
        "total_rules": total,
        "passed": pass_count,
        "violated": total - pass_count,
        "violations": violations,
        "pass_examples": passes[:5],
    }


def _extract_negation_patterns(rule: str) -> list[tuple[str, str]]:
    """
    从 Layer 0 规则文本中提取可检测的否定模式

    返回: [(正则模式, 违反描述), ...]
    """
    patterns = []

    # "从不用感叹号" → 检测 ！或!
    if "不用感叹号" in rule or "不用！" in rule or "没有感叹号" in rule:
        patterns.append((r"[！!]", "使用了感叹号"))

    # "从不用命令" / "不用命令口吻" → 检测命令式语气词
    if "不用命令" in rule or "不用" in rule and "命令" in rule:
        patterns.append((r"命令|给我|必须|立刻|马上", "使用了命令式语气"))

    # "从不说'我的子民'" → 检测该词
    if "不说" in rule and "子民" in rule:
        patterns.append((r"我的子民", "使用了'我的子民'"))

    # "不会说'这是慈悲'" → 检测
    if "不会说" in rule and "慈悲" in rule:
        patterns.append((r"这是慈悲", "使用了'这是慈悲'的表述"))

    # "不会哭" / "不会流泪" → 检测哭泣表达
    if "不会哭" in rule or "不会流泪" in rule:
        patterns.append((r"哭了|流泪|泪流|泪水", "出现了哭泣描写"))

    # "不会咆哮" / "不会吼" → 检测咆哮
    if "不会咆哮" in rule or "不会吼" in rule:
        patterns.append((r"咆哮|怒吼|大吼|吼道", "出现了咆哮描写"))

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
        # 提取引号中的口头禅
        phrases = re.findall(r"[「""]([^」""]+)[」""]", catchphrases)
        if not phrases:
            phrases = [w.strip() for w in catchphrases.split("、") if w.strip()]

        for phrase in phrases:
            count = sum(1 for d in dialogues if phrase in d)
            freq = round(count / len(dialogues) * 100, 1) if dialogues else 0
            checks.append({
                "type": "catchphrase",
                "item": phrase,
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

    检测策略：从禁忌描述中提取关键词，检查对话是否包含
    """
    hits = []

    for taboo in taboos:
        # 提取禁忌中的核心词
        keywords = _extract_taboo_keywords(taboo)

        for i, dialogue in enumerate(dialogues):
            for kw in keywords:
                if kw in dialogue:
                    hits.append({
                        "taboo": taboo[:80],
                        "keyword": kw,
                        "dialogue_index": i + 1,
                        "dialogue": dialogue[:100],
                    })

    score = 100 if not hits else max(0, 100 - len(hits) * 10)

    return {
        "score": score,
        "taboo_count": len(taboos),
        "violation_count": len(hits),
        "violations": hits[:5],
    }


def _extract_taboo_keywords(taboo: str) -> list[str]:
    """从禁忌描述中提取可检测的关键词"""
    keywords = []

    # 检测引号中的词
    quoted = re.findall(r"[「""'']([^」""]+)[」""]", taboo)
    keywords.extend(quoted)

    # 检测常见的敏感行为词
    sensitive = ["牺牲", "棋子", "放弃", "消灭", "杀", "死", "贱民", "低等"]
    for s in sensitive:
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
        """,
    )

    parser.add_argument("--persona", required=True, help="persona.md 文件路径")
    parser.add_argument("--dialogues", required=True, help="对话数据文件路径")
    parser.add_argument("--format", choices=["plain", "prts-json"], default="plain", help="对话格式")
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
