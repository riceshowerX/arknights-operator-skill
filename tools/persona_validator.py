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
        r"##\s+Layer\s*0.*?\n(.*?)(?=\n##\s+Layer|\n##\s+Correction|\Z)",
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
        r"##\s+Layer\s*2.*?\n(.*?)(?=\n##\s+Layer|\n##\s+Correction|\Z)",
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
        r"##\s+Layer\s*5.*?\n(.*?)(?=\n##\s+Correction|\Z)",
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
        r"##\s+Correction\s*记录.*?\n(.*?)(?=\n##\s+|\Z)",
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
    untestable_count = sum(1 for p in passes if "不可自动检测" in p)
    testable = total - untestable_count
    # pass_count 仅统计可测试规则中通过的数量
    testable_passes = [p for p in passes if "不可自动检测" not in p]
    pass_count = len(testable_passes)
    score = round(pass_count / testable * 100, 1) if testable > 0 else 100

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

    # "从不说/从不用/从不会 + 引号内容" — 通用否定结构，仅提取引号内的具体反例
    # 避免匹配过宽：只从引号内容中提取，不匹配自由文本
    # 同时去重：跳过已被前面 "不说/不用/不会" 捕获的短语
    already_matched = {p for p, _ in patterns}
    never_say = re.findall(r'从不(?:会|用|说|能)?[「\u201c\u2018]([^」\u201d\u2019]{2,20})[」\u201d\u2019]', rule)
    for phrase in never_say:
        escaped = re.escape(phrase)
        if escaped not in already_matched:
            patterns.append((escaped, f"使用了'{phrase}'"))

    # === 从引号内容提取反例 ===
    # 规则中常见格式："不应该'xxx'，应该'yyy'"
    # 我们检测 'xxx'（反例）是否出现在对话中
    # 去重：跳过已被前面模式捕获的短语
    already_matched = {p for p, _ in patterns}
    quoted_phrases = re.findall(r'[「\u201c\u2018]([^」\u201d\u2019]+)[」\u201d\u2019]', rule)
    # 检查引号内容是否在"不"后面 → 是反例
    for phrase in quoted_phrases:
        # 如果引号内容在"不"后面，说明这是反例，应该检测
        if re.search(rf"不[^」\u201d\u2019]*{re.escape(phrase)}", rule):
            if len(phrase) >= 2:
                escaped = re.escape(phrase)
                if escaped not in already_matched:
                    patterns.append((escaped, f"使用了反例表达'{phrase}'"))

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
# 语境化验证（升级新增）
# ──────────────────────────────────────────────

def validate_with_context(persona_path: str, context_path: str) -> dict:
    """
    基于 context.json 的多切片验证

    按 period 和 interlocutor 分片验证 Persona，
    检查各层规则在不同场景下的一致性。
    """
    persona = parse_persona(persona_path)

    with open(context_path, encoding='utf-8') as f:
        context = json.load(f)

    lines = context.get("annotated_lines", [])

    # 全局对话
    all_dialogues = [
        l.get("text", "") for l in lines
        if l.get("source") != "archive" and l.get("text")
    ]

    if not all_dialogues:
        return {"error": "context.json 中无可用对话数据", "score": 0}

    # 全局验证
    global_result = _validate_against_dialogues(persona, all_dialogues)

    # 按 period 分片验证
    phase_results = {}
    by_phase: dict[str, list[str]] = {}
    for line in lines:
        if line.get("source") == "archive" or not line.get("text"):
            continue
        phase = line.get("context", {}).get("phase", "unknown")
        if phase != "unknown":
            by_phase.setdefault(phase, []).append(line["text"])

    MIN_SLICE_SIZE = 2
    for phase, phase_dialogues in by_phase.items():
        if len(phase_dialogues) >= MIN_SLICE_SIZE:
            result = _validate_against_dialogues(persona, phase_dialogues)
            result["_sample_size"] = len(phase_dialogues)
            result["_confidence"] = _confidence_level(len(phase_dialogues))
            phase_results[phase] = result

    # 按 interlocutor 分片验证
    interlocutor_results = {}
    by_interlocutor: dict[str, list[str]] = {}
    for line in lines:
        if line.get("source") == "archive" or not line.get("text"):
            continue
        person = line.get("context", {}).get("interlocutor") or "unknown"
        if person != "unknown":
            by_interlocutor.setdefault(person, []).append(line["text"])

    for person, person_dialogues in by_interlocutor.items():
        if len(person_dialogues) >= MIN_SLICE_SIZE:
            result = _validate_against_dialogues(persona, person_dialogues)
            result["_sample_size"] = len(person_dialogues)
            result["_confidence"] = _confidence_level(len(person_dialogues))
            interlocutor_results[person] = result

    # 按 situation_type 分片验证
    situation_results = {}
    by_situation: dict[str, list[str]] = {}
    for line in lines:
        if line.get("source") == "archive" or not line.get("text"):
            continue
        situation = line.get("context", {}).get("situation_type", "unknown")
        if situation != "unknown":
            by_situation.setdefault(situation, []).append(line["text"])

    for situation, situation_dialogues in by_situation.items():
        if len(situation_dialogues) >= MIN_SLICE_SIZE:
            result = _validate_against_dialogues(persona, situation_dialogues)
            result["_sample_size"] = len(situation_dialogues)
            result["_confidence"] = _confidence_level(len(situation_dialogues))
            situation_results[situation] = result

    # 按 source 分片验证（voice vs story）
    source_results = {}
    by_source: dict[str, list[str]] = {}
    for line in lines:
        if not line.get("text"):
            continue
        src = line.get("source", "unknown")
        if src != "archive":
            by_source.setdefault(src, []).append(line["text"])

    for src, src_dialogues in by_source.items():
        if len(src_dialogues) >= MIN_SLICE_SIZE:
            result = _validate_against_dialogues(persona, src_dialogues)
            result["_sample_size"] = len(src_dialogues)
            result["_confidence"] = _confidence_level(len(src_dialogues))
            source_results[src] = result

    # 检测切片间不一致
    slice_inconsistencies = _detect_slice_inconsistencies(
        global_result, phase_results, interlocutor_results, situation_results
    )

    # 生成 Persona 修改建议
    recommendations = _generate_recommendations(
        global_result, phase_results, interlocutor_results,
        situation_results, source_results, slice_inconsistencies
    )

    # 构建切片质量概览
    slice_quality = _build_slice_quality_overview(
        phase_results, interlocutor_results, situation_results, source_results
    )

    return {
        "mode": "contextual",
        "overall_score": global_result["overall_score"],
        "grade": global_result["grade"],
        "dialogue_count": len(all_dialogues),
        "global": global_result,
        "by_phase": phase_results,
        "by_interlocutor": interlocutor_results,
        "by_situation": situation_results,
        "by_source": source_results,
        "slice_inconsistencies": slice_inconsistencies,
        "recommendations": recommendations,
        "slice_quality": slice_quality,
        "phases_tested": list(phase_results.keys()),
        "interlocutors_tested": list(interlocutor_results.keys()),
        "situations_tested": list(situation_results.keys()),
        "sources_tested": list(source_results.keys()),
    }


def _validate_against_dialogues(persona: dict, dialogues: list[str]) -> dict:
    """对一组对话执行完整验证"""
    layer0_result = validate_layer0(dialogues, persona["layer0_rules"])
    layer2_result = validate_layer2_style(dialogues, persona["layer2_style"])
    layer5_result = validate_layer5_taboos(dialogues, persona["layer5_taboos"])

    overall_score = (
        layer0_result["score"] * 0.5
        + layer2_result["score"] * 0.3
        + layer5_result["score"] * 0.2
    )

    return {
        "overall_score": round(overall_score, 1),
        "layer0_core_personality": layer0_result,
        "layer2_expression_style": layer2_result,
        "layer5_boundaries": layer5_result,
        "dialogue_count": len(dialogues),
        "grade": _score_to_grade(overall_score),
    }


def _detect_slice_inconsistencies(
    global_result: dict,
    phase_results: dict[str, dict],
    interlocutor_results: dict[str, dict],
    situation_results: dict[str, dict] | None = None,
) -> list[dict]:
    """
    检测切片间不一致：某规则在某切片违反但其他切片通过

    这类不一致通常意味着 Persona 规则过于绝对，
    需要添加场景条件或时期条件。

    支持四种切片维度：phase、interlocutor、situation、source
    """
    inconsistencies = []

    # ── Phase 维度 ──
    # 收集每条规则在各切片中的违反情况
    # key = rule_text[:80], value = {phase: violation_count}
    rule_violation_map: dict[str, dict[str, int]] = {}

    for phase, result in phase_results.items():
        for v in result.get("layer0_core_personality", {}).get("violations", []):
            rule_key = v.get("rule", "")[:80]
            rule_violation_map.setdefault(rule_key, {})[phase] = v.get("violation_count", 0)

    # 找出只在部分时期违反的规则
    for rule_key, phase_violations in rule_violation_map.items():
        phases_with_violation = list(phase_violations.keys())
        all_phases = list(phase_results.keys())
        phases_without = [p for p in all_phases if p not in phases_with_violation]

        if phases_without and len(phases_with_violation) < len(all_phases):
            inconsistencies.append({
                "type": "phase_specific_violation",
                "dimension": "phase",
                "rule": rule_key,
                "description": f"规则在{', '.join(phases_with_violation)}时期被违反，但在{', '.join(phases_without)}时期未违反——可能是时期特有的行为，Persona 需要添加条件",
                "violated_phases": phases_with_violation,
                "clean_phases": phases_without,
            })

    # ── Interlocutor 维度 ──
    if len(interlocutor_results) >= 2:
        scores = {
            person: result.get("overall_score", 0)
            for person, result in interlocutor_results.items()
        }
        if scores:
            max_score = max(scores.values())
            min_score = min(scores.values())
            if max_score - min_score > 20:
                inconsistencies.append({
                    "type": "interlocutor_score_gap",
                    "dimension": "interlocutor",
                    "description": f"不同对话对象的验证分数差距较大（{min_score} vs {max_score}），Persona 可能需要为不同对象添加差异化规则",
                    "scores": scores,
                })

    # ── Situation 维度 ──
    if situation_results and len(situation_results) >= 2:
        sit_scores = {
            sit: result.get("overall_score", 0)
            for sit, result in situation_results.items()
        }
        if sit_scores:
            max_sit = max(sit_scores.values())
            min_sit = min(sit_scores.values())
            if max_sit - min_sit > 25:
                inconsistencies.append({
                    "type": "situation_score_gap",
                    "dimension": "situation",
                    "description": f"不同场景类型的验证分数差距较大（{min_sit} vs {max_sit}），Persona 可能需要为不同场景添加条件规则",
                    "scores": sit_scores,
                })

        # 检测 confront 场景中的特定违规
        confront_result = situation_results.get("confront")
        casual_result = situation_results.get("casual")
        if confront_result and casual_result:
            confront_violations = {
                v.get("rule", "")[:80]
                for v in confront_result.get("layer0_core_personality", {}).get("violations", [])
            }
            casual_violations = {
                v.get("rule", "")[:80]
                for v in casual_result.get("layer0_core_personality", {}).get("violations", [])
            }
            confront_only = confront_violations - casual_violations
            if confront_only:
                inconsistencies.append({
                    "type": "situation_specific_violation",
                    "dimension": "situation",
                    "description": f"规则仅在 confront 场景下被违反，可能是战斗状态下的合理行为偏差，Persona 应允许条件例外",
                    "confront_only_violations": list(confront_only)[:5],
                })

    return inconsistencies


def _confidence_level(sample_size: int) -> str:
    """根据样本量给出置信度评级"""
    if sample_size >= 20:
        return "high"
    elif sample_size >= 10:
        return "medium"
    elif sample_size >= 3:
        return "low"
    else:
        return "very_low"


def _generate_recommendations(
    global_result: dict,
    phase_results: dict[str, dict],
    interlocutor_results: dict[str, dict],
    situation_results: dict[str, dict],
    source_results: dict[str, dict],
    inconsistencies: list[dict],
) -> list[dict]:
    """
    基于验证结果和不一致性，生成具体的 Persona 修改建议
    """
    recommendations = []

    # ── 基于全局评分的建议 ──
    overall = global_result.get("overall_score", 0)
    if overall < 60:
        recommendations.append({
            "priority": "high",
            "target": "global",
            "issue": f"全局一致性评分仅为 {overall}，Persona 严重偏离角色实际表现",
            "suggestion": "建议重新审视 Layer 0 核心规则，确保规则与角色对话数据一致",
        })
    elif overall < 75:
        recommendations.append({
            "priority": "medium",
            "target": "global",
            "issue": f"全局一致性评分 {overall}，存在部分违反",
            "suggestion": "检查 layer0_violations 中标记的规则，考虑添加条件或放宽绝对性表述",
        })

    # ── 基于不一致性的建议 ──
    for inc in inconsistencies:
        inc_type = inc.get("type", "")

        if inc_type == "phase_specific_violation":
            rule = inc.get("rule", "未知规则")
            violated = inc.get("violated_phases", [])
            recommendations.append({
                "priority": "medium",
                "target": "Layer 0",
                "issue": inc.get("description", ""),
                "suggestion": f"为规则「{rule}」添加时期条件：在 {', '.join(violated)} 时期，此规则可以有例外或不同表现",
            })

        elif inc_type == "interlocutor_score_gap":
            scores = inc.get("scores", {})
            recommendations.append({
                "priority": "medium",
                "target": "Layer 2-3",
                "issue": inc.get("description", ""),
                "suggestion": f"考虑在 Layer 2 或 Layer 3 中添加针对不同对话对象的表达差异规则，当前分数差异：{scores}",
            })

        elif inc_type == "situation_score_gap":
            scores = inc.get("scores", {})
            recommendations.append({
                "priority": "medium",
                "target": "Layer 0-2",
                "issue": inc.get("description", ""),
                "suggestion": f"考虑为不同场景类型（confront/casual/comfort）添加条件规则，当前分数差异：{scores}",
            })

        elif inc_type == "situation_specific_violation":
            violations = inc.get("confront_only_violations", [])
            recommendations.append({
                "priority": "low",
                "target": "Layer 0",
                "issue": inc.get("description", ""),
                "suggestion": f"为 confront 场景添加例外条款，允许在战斗/对抗情境下的合理偏差。涉及规则：{violations[:3]}",
            })

    # ── 数据源差异建议 ──
    if len(source_results) >= 2:
        source_scores = {
            src: result.get("overall_score", 0)
            for src, result in source_results.items()
        }
        if source_scores:
            max_src = max(source_scores.values())
            min_src = min(source_scores.values())
            if max_src - min_src > 15:
                lower_src = min(source_scores, key=source_scores.get)
                recommendations.append({
                    "priority": "low",
                    "target": "data_quality",
                    "issue": f"数据源一致性差异：{source_scores}",
                    "suggestion": f"{lower_src} 数据源的一致性较低，可能是因为该来源对话场景较单一。建议补充更多样化的{lower_src}数据",
                })

    # ── 低置信度切片警告 ──
    low_confidence_slices = []
    for phase, result in phase_results.items():
        if result.get("_confidence") in ("low", "very_low"):
            low_confidence_slices.append(f"phase:{phase}(n={result.get('_sample_size', 0)})")
    for person, result in interlocutor_results.items():
        if result.get("_confidence") in ("low", "very_low"):
            low_confidence_slices.append(f"interlocutor:{person}(n={result.get('_sample_size', 0)})")

    if low_confidence_slices:
        recommendations.append({
            "priority": "info",
            "target": "data_coverage",
            "issue": f"以下切片样本量不足，验证结果可靠性有限：{', '.join(low_confidence_slices)}",
            "suggestion": "补充更多对话数据以提高切片验证的置信度",
        })

    return recommendations


def _build_slice_quality_overview(
    phase_results: dict[str, dict],
    interlocutor_results: dict[str, dict],
    situation_results: dict[str, dict],
    source_results: dict[str, dict],
) -> dict:
    """构建切片质量概览，展示各维度的覆盖情况和评分"""
    overview = {
        "phase": {
            name: {
                "score": result.get("overall_score", 0),
                "grade": result.get("grade", ""),
                "sample_size": result.get("_sample_size", 0),
                "confidence": result.get("_confidence", "unknown"),
            }
            for name, result in phase_results.items()
        },
        "interlocutor": {
            name: {
                "score": result.get("overall_score", 0),
                "grade": result.get("grade", ""),
                "sample_size": result.get("_sample_size", 0),
                "confidence": result.get("_confidence", "unknown"),
            }
            for name, result in interlocutor_results.items()
        },
        "situation": {
            name: {
                "score": result.get("overall_score", 0),
                "grade": result.get("grade", ""),
                "sample_size": result.get("_sample_size", 0),
                "confidence": result.get("_confidence", "unknown"),
            }
            for name, result in situation_results.items()
        },
        "source": {
            name: {
                "score": result.get("overall_score", 0),
                "grade": result.get("grade", ""),
                "sample_size": result.get("_sample_size", 0),
                "confidence": result.get("_confidence", "unknown"),
            }
            for name, result in source_results.items()
        },
    }

    # 维度覆盖统计
    total_slices = (
        len(phase_results) + len(interlocutor_results)
        + len(situation_results) + len(source_results)
    )
    high_conf = sum(
        1 for results in [phase_results, interlocutor_results, situation_results, source_results]
        for r in results.values() if r.get("_confidence") == "high"
    )

    # 覆盖率：有数据切片的维度数 / 总维度数
    # 有数据的维度（至少1个切片）计为已覆盖
    covered_dims = sum(
        1 for d in [phase_results, interlocutor_results, situation_results, source_results]
        if len(d) >= 1
    )

    overview["meta"] = {
        "total_slices": total_slices,
        "high_confidence_slices": high_conf,
        "covered_dimensions": covered_dims,
        "total_dimensions": 4,
        "coverage_pct": round(covered_dims / 4 * 100),
    }

    return overview


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Persona 一致性验证器 — 用角色实际对话验证 Persona 的准确度（支持多切片验证）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 传统模式
  python persona_validator.py --persona ./persona.md --dialogues ./lines.txt
  python persona_validator.py --persona ./persona.md --dialogues ./voices.json --format prts-json

  # 语境化模式（多切片验证）
  python persona_validator.py --persona ./persona.md --context-json operators/te-lei-xi-ya/context.json
        """,
    )

    # 传统模式参数
    parser.add_argument("--persona", required=True, help="persona.md 文件路径")
    parser.add_argument("--dialogues", help="对话数据文件路径（传统模式）")
    parser.add_argument("--format", choices=["plain", "prts-json", "csv"], default="plain", help="对话格式")

    # 语境化模式参数
    parser.add_argument("--context-json", help="context.json 路径（语境化模式，替代 --dialogues）")

    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    if not args.dialogues and not args.context_json:
        print("错误：请指定 --dialogues（传统模式）或 --context-json（语境化模式）", file=sys.stderr)
        sys.exit(1)

    if args.context_json:
        result = validate_with_context(args.persona, args.context_json)
    else:
        result = validate(args.persona, args.dialogues, args.format)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"验证报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
