#!/usr/bin/env python3
"""
数据注入器 - 将工具输出的量化数据格式化为 Prompt 可用的数据上下文

职责：
1. 读取 operators/{slug}/ 下的所有分析 JSON 文件
2. 将量化数据格式化为结构化的 Markdown 数据上下文
3. 输出可直接嵌入 persona_builder.md / knowledge_builder.md 的数据段

使用方式：
    python -m tools.data_injector --slug theresa
    python -m tools.data_injector --slug theresa --section fingerprint
    python -m tools.data_injector --slug theresa --section relationships
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict | list | None:
    """安全加载 JSON 文件"""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def format_fingerprint(data: dict) -> str:
    """格式化对话指纹数据"""
    if not data:
        return "（对话指纹数据不可用）"

    lines = ["### 对话指纹数据（来自 dialogue_fingerprint 8 维度分析）\n"]

    # 维度 1: 句式长度
    sl = data.get("sentence_length", {})
    if sl:
        lines.append(f"- **句式长度**：{sl.get('type', '未知')}，"
                      f"中位数 {sl.get('median', '?')} 字，"
                      f"P25={sl.get('p25', '?')} / P75={sl.get('p75', '?')}，"
                      f"变异系数 CV={sl.get('cv', '?')}（节奏{sl.get('rhythm', '?')}）")

    # 维度 2: 停顿习惯
    pm = data.get("pause_markers", {})
    if pm:
        lines.append(f"- **停顿习惯**：省略号频率 {pm.get('ellipsis_pct', 0)}%，"
                      f"感叹号频率 {pm.get('exclamation_pct', 0)}%，"
                      f"问号频率 {pm.get('question_pct', 0)}%")

    # 维度 3: 自称模式
    sr = data.get("self_reference", {})
    if sr:
        primary = sr.get("primary", "未知")
        freq = sr.get("frequency_per_line", 0)
        lines.append(f"- **自称**：主要使用「{primary}」，频率 {freq} 次/句")

    # 维度 4: 情感光谱
    em = data.get("emotion", {})
    if em:
        dominant = em.get("dominant", "未知")
        breadth = em.get("breadth", 0)
        spectrum = em.get("spectrum", {})
        top3 = sorted(spectrum.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = "、".join(f"{k}({v}次)" for k, v in top3)
        lines.append(f"- **情感光谱**：主导情感「{dominant}」，"
                      f"情感谱系宽度 {breadth}，"
                      f"Top3: {top3_str}")

    # 维度 5: 修辞偏好
    rh = data.get("rhetoric", {})
    if rh:
        lines.append(f"- **修辞偏好**：反问 {rh.get('rhetorical_question_pct', 0)}%，"
                      f"比喻 {rh.get('metaphor_pct', 0)}%，"
                      f"排比 {rh.get('parallelism_pct', 0)}%")

    # 维度 6: 称呼模式
    addr = data.get("address_patterns", {})
    if addr:
        primary_addr = addr.get("primary", "未知")
        lines.append(f"- **称呼模式**：主要称呼方式「{primary_addr}」")

    # 维度 7: 自然意象
    ni = data.get("nature_imagery", {})
    if ni:
        dominant_img = ni.get("dominant", "无")
        freq = ni.get("frequency_per_line", 0)
        lines.append(f"- **自然意象**：主导意象「{dominant_img}」，"
                      f"频率 {freq} 次/句")

    # 维度 8: 口头禅
    cp = data.get("catchphrases", {})
    if cp:
        phrases = cp.get("signature_phrases", [])
        if phrases:
            top5 = phrases[:5]
            phrases_str = "、".join(f"「{p['phrase']}」({p['count']}次)" for p in top5)
            lines.append(f"- **口头禅/标志性短语**：{phrases_str}")

    # 综合摘要
    summary = data.get("summary", {})
    if summary:
        lines.append(f"\n**综合画像**：{summary.get('overall_description', '')}")

    return "\n".join(lines)


def format_speech_acts(data: dict) -> str:
    """格式化话语行为分析数据"""
    if not data:
        return "（话语行为数据不可用）"

    lines = ["### 话语行为数据（来自 speech_act_analyzer）\n"]

    # 行为模式
    patterns = data.get("behavioral_patterns", [])
    if patterns:
        lines.append("**行为模式**：")
        for p in patterns:
            conf = p.get("confidence", 0)
            if conf >= 0.5:
                lines.append(f"- [{conf:.0%}置信度] {p.get('description', p.get('pattern', ''))}")

    # 行为链
    chains = data.get("behavioral_chains", [])
    if chains:
        lines.append("\n**行为链**（角色特有的行为序列）：")
        for chain in chains[:5]:
            seq = chain.get("sequence", [])
            count = chain.get("count", 0)
            seq_str = " → ".join(seq)
            lines.append(f"- {seq_str}（出现 {count} 次）")

    # 类型分布
    dist = data.get("type_distribution", {})
    if dist:
        lines.append("\n**行为类型分布**：")
        sorted_types = sorted(dist.items(), key=lambda x: x[1], reverse=True)
        for t, count in sorted_types[:5]:
            lines.append(f"- {t}: {count} 次")

    return "\n".join(lines)


def format_relationships(data: dict) -> str:
    """格式化关系图谱数据"""
    if not data:
        return "（关系图谱数据不可用）"

    lines = ["### 关系图谱数据（来自 relationship_graph）\n"]

    # 关系列表
    relations = data.get("relations", [])
    if relations:
        lines.append("**核心关系**：")
        for r in relations[:10]:
            target = r.get("target", "未知")
            rel_type = r.get("type", "未知")
            strength = r.get("strength", 0)
            evidence = r.get("evidence_count", 0)
            lines.append(f"- **{target}**：{rel_type}（强度 {strength:.2f}，"
                          f"{evidence} 条证据）")

    # 关系演变
    evolutions = data.get("evolutions", [])
    if evolutions:
        lines.append("\n**关系演变**：")
        for e in evolutions[:5]:
            pair = e.get("pair", "")
            direction = e.get("direction", "")
            delta = e.get("delta", 0)
            from_phase = e.get("from_phase", "")
            to_phase = e.get("to_phase", "")
            lines.append(f"- {pair}：{from_phase} → {to_phase}，"
                          f"关系{direction}（变化量 {delta:+.2f}）")

    return "\n".join(lines)


def format_temporal(data: dict) -> str:
    """格式化时序切片数据"""
    if not data:
        return "（时序切片数据不可用）"

    lines = ["### 时序演变数据（来自 temporal_slicer）\n"]

    # 情感弧线
    arc = data.get("emotion_arc", {})
    if arc:
        arc_type = arc.get("arc", "未知")
        trajectory = arc.get("trajectory", [])
        lines.append(f"- **情感弧线**：{arc_type}")
        if trajectory:
            traj_str = " → ".join(f"{v:.2f}" for v in trajectory)
            lines.append(f"  轨迹：{traj_str}")

    # 时序规则
    rules = data.get("temporal_rules", [])
    if rules:
        lines.append("\n**时序演变规则**：")
        for rule in rules[:8]:
            desc = rule.get("description", "")
            if desc:
                lines.append(f"- {desc}")

    # 切片指标
    metrics = data.get("slice_metrics", {})
    if metrics:
        lines.append("\n**各时期关键指标**：")
        for phase, m in metrics.items():
            ellipsis = m.get("ellipsis_pct", 0)
            avg_len = m.get("avg_length", 0)
            lines.append(f"- {phase}：省略号 {ellipsis}%，平均句长 {avg_len} 字")

    return "\n".join(lines)


def format_context(data: dict) -> str:
    """格式化语境标注数据"""
    if not data:
        return "（语境标注数据不可用）"

    lines = ["### 语境标注数据（来自 context_annotator）\n"]

    # 场景分布
    situations = data.get("situation_distribution", {})
    if situations:
        lines.append("**场景分布**：")
        sorted_sit = sorted(situations.items(), key=lambda x: x[1], reverse=True)
        for sit, count in sorted_sit[:5]:
            lines.append(f"- {sit}: {count} 条")

    # 对象分布
    interlocutors = data.get("interlocutor_distribution", {})
    if interlocutors:
        lines.append("\n**对话对象分布**：")
        sorted_int = sorted(interlocutors.items(), key=lambda x: x[1], reverse=True)
        for person, count in sorted_int[:5]:
            lines.append(f"- {person}: {count} 条")

    return "\n".join(lines)


def generate_data_context(slug: str, base_dir: str = "./operators",
                          sections: list[str] | None = None) -> str:
    """
    生成完整的数据上下文

    Args:
        slug: 角色 slug
        base_dir: 基础目录
        sections: 要包含的数据段（None=全部）

    Returns:
        格式化的 Markdown 数据上下文
    """
    operator_dir = Path(base_dir) / slug
    if not operator_dir.exists():
        return f"错误：角色目录 {operator_dir} 不存在"

    all_sections = {
        "fingerprint": ("fingerprint.json", format_fingerprint),
        "speech_acts": ("speech_acts.json", format_speech_acts),
        "relationships": ("relationships.json", format_relationships),
        "temporal": ("temporal.json", format_temporal),
        "context": ("context.json", format_context),
    }

    if sections is None:
        sections = list(all_sections.keys())

    header = f"## 量化分析数据上下文（{slug}）\n"
    header += "> 以下数据来自角色实际对话的量化分析，**生成 Persona/Knowledge 时必须严格遵守这些数据约束**。\n\n"

    parts = [header]

    for section_name in sections:
        if section_name not in all_sections:
            continue
        filename, formatter = all_sections[section_name]
        filepath = operator_dir / filename
        data = load_json(filepath)
        if data:
            parts.append(formatter(data))
            parts.append("")  # 空行分隔

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="数据注入器 - 格式化工具输出为 Prompt 数据上下文")
    parser.add_argument("--slug", required=True, help="角色 slug")
    parser.add_argument("--base-dir", default="./operators", help="基础目录")
    parser.add_argument("--section", action="append",
                        choices=["fingerprint", "speech_acts", "relationships", "temporal", "context"],
                        help="只输出指定数据段（可多次指定）")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    result = generate_data_context(
        slug=args.slug,
        base_dir=args.base_dir,
        sections=args.section,
    )

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"数据上下文已写入: {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
