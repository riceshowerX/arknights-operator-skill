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


def _get_fingerprint_dim(data: dict, dim_key: str) -> dict:
    """从对话指纹数据中提取某个维度，兼容两种结构：
    - 嵌套结构（context 模式输出）：data["global"]["dimensions"]["1_sentence_length"]
    - 扁平结构（传统模式输出）：data["sentence_length"]
    """
    # 嵌套结构
    global_data = data.get("global", {})
    dimensions = global_data.get("dimensions", {})
    if dim_key in dimensions:
        return dimensions[dim_key]
    # 按数字前缀匹配（如 "1_sentence_length"）
    for k, v in dimensions.items():
        if k.endswith(dim_key) or dim_key in k:
            return v if isinstance(v, dict) else {}
    # 扁平结构
    flat = data.get(dim_key, {})
    return flat if isinstance(flat, dict) else {}


def format_fingerprint(data: dict) -> str:
    """格式化对话指纹数据（兼容嵌套与扁平两种结构）"""
    if not data:
        return "（对话指纹数据不可用）"

    lines = ["### 对话指纹数据（来自 dialogue_fingerprint 8 维度分析）\n"]

    # 维度 1: 句式长度
    sl = _get_fingerprint_dim(data, "sentence_length")
    if sl:
        p = sl.get("percentiles", {}) or {}
        lines.append(f"- **句式长度**：{sl.get('type', '未知')}，"
                      f"中位数 {sl.get('median', p.get('p50', '?'))} 字，"
                      f"P25={p.get('p25', '?')} / P75={p.get('p75', '?')}，"
                      f"变异系数 CV={sl.get('cv', '?')}（节奏{sl.get('rhythm', '?')}）")

    # 维度 2: 停顿习惯
    pm = _get_fingerprint_dim(data, "pause_markers")
    if pm:
        lines.append(f"- **停顿习惯**：省略号频率 {pm.get('ellipsis_pct', 0)}%，"
                      f"感叹号频率 {pm.get('exclamation_pct', 0)}%，"
                      f"问号频率 {pm.get('question_pct', 0)}%")

    # 维度 3: 自称模式
    sr = _get_fingerprint_dim(data, "self_reference")
    if sr:
        primary = sr.get("primary", "未知")
        freq = sr.get("frequency_per_line", 0)
        lines.append(f"- **自称**：主要使用「{primary}」，频率 {freq} 次/句")

    # 维度 4: 情感光谱
    em = _get_fingerprint_dim(data, "emotion_vocabulary")
    if not em:
        em = _get_fingerprint_dim(data, "emotion")
    if em:
        dominant = em.get("dominant", "未知")
        breadth = em.get("breadth", 0)
        spectrum = em.get("spectrum", {}) or em.get("spectrum_pct", {})
        top3 = sorted(spectrum.items(), key=lambda x: x[1], reverse=True)[:3] if spectrum else []
        top3_str = "、".join(f"{k}({v})" for k, v in top3) if top3 else "无"
        lines.append(f"- **情感光谱**：主导情感「{dominant}」，"
                      f"情感谱系宽度 {breadth}，"
                      f"Top3: {top3_str}")

    # 维度 5: 修辞偏好
    rh = _get_fingerprint_dim(data, "rhetoric_patterns")
    if not rh:
        rh = _get_fingerprint_dim(data, "rhetoric")
    if rh:
        lines.append(f"- **修辞偏好**：反问 {rh.get('rhetorical_question_pct', 0)}%，"
                      f"比喻 {rh.get('metaphor_pct', 0)}%，"
                      f"排比 {rh.get('parallelism_pct', 0)}%")

    # 维度 6: 称呼模式
    addr = _get_fingerprint_dim(data, "address_pattern")
    if not addr:
        addr = _get_fingerprint_dim(data, "address_patterns")
    if addr:
        primary_addr = addr.get("pattern", addr.get("primary", "未知"))
        lines.append(f"- **称呼模式**：{primary_addr}")

    # 维度 7: 自然意象
    ni = _get_fingerprint_dim(data, "natural_imagery")
    if ni:
        density = ni.get("density_per_line", 0)
        level = ni.get("density_level", "未知")
        lines.append(f"- **自然意象**：密度{level}（{density}个/句）")

    # 维度 8: 口头禅
    cp = _get_fingerprint_dim(data, "catchphrases")
    if cp:
        phrases = cp.get("signature_phrases", [])
        if phrases:
            top5 = phrases[:5]
            phrases_str = "、".join(f"「{p['phrase']}」({p['count']}次)" for p in top5)
            lines.append(f"- **口头禅/标志性短语**：{phrases_str}")

    # 综合摘要
    summary = data.get("summary")
    if not summary:
        summary = data.get("global", {}).get("summary")
    if summary:
        if isinstance(summary, str):
            lines.append(f"\n**综合画像**：{summary}")
        elif isinstance(summary, dict):
            desc = summary.get("overall_description", "") or summary.get("description", "")
            if desc:
                lines.append(f"\n**综合画像**：{desc}")

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
    """格式化关系图谱数据

    兼容两种数据来源：
    - context.json 的 annotated_relations / relation_trajectories（语境化模式）
    - 独立 relationships.json 的 relations / evolutions（传统模式，旧测试兼容）
    """
    if not data:
        return "（关系图谱数据不可用）"

    lines = ["### 关系图谱数据（来自 relationship_graph）\n"]

    # 关系列表：优先 annotated_relations，回退 relations
    relations = data.get("annotated_relations", []) or data.get("relations", [])
    if relations:
        lines.append("**核心关系**：")
        for r in relations[:10]:
            target = r.get("target", r.get("name", "未知"))
            rel_type = r.get("type", r.get("relation_type", "未知"))
            strength = r.get("strength", 0)
            evidence = r.get("evidence_count", r.get("count", 0))
            lines.append(f"- **{target}**：{rel_type}（强度 {strength:.2f}，"
                          f"{evidence} 条证据）")

    # 关系演变：优先 relation_trajectories，回退 evolutions
    evolutions = data.get("relation_trajectories", []) or data.get("evolutions", [])
    if evolutions:
        lines.append("\n**关系演变**：")
        for e in evolutions[:5]:
            # 旧格式 evolutions: {pair, direction, delta, from_phase, to_phase}
            if "pair" in e or "direction" in e:
                pair = e.get("pair", e.get("target", e.get("name", "")))
                direction = e.get("direction", "")
                delta = e.get("delta", 0)
                from_phase = e.get("from_phase", "")
                to_phase = e.get("to_phase", "")
                lines.append(f"- {pair}：{from_phase} → {to_phase}，"
                              f"关系{direction}（变化量 {delta:+.2f}）")
            # 新格式 relation_trajectories: {target, trajectory: [{phase, strength}]}
            else:
                target = e.get("target", e.get("name", ""))
                trajectory = e.get("trajectory", [])
                if trajectory:
                    traj_str = " → ".join(
                        f"{t.get('phase','?')}({t.get('strength', 0):.2f})"
                        for t in trajectory
                    )
                    lines.append(f"- {target}：{traj_str}")

    if not relations and not evolutions:
        lines.append("- （未检测到显著关系，建议补充剧情数据）")

    return "\n".join(lines)


def format_temporal(data: dict) -> str:
    """格式化时序切片数据（匹配 temporal_slicer 实际输出结构）"""
    if not data:
        return "（时序切片数据不可用）"

    lines = ["### 时序演变数据（来自 temporal_slicer）\n"]

    # 情感弧线
    arc = data.get("emotion_arc")
    if arc and isinstance(arc, dict):
        arc_type = arc.get("arc", "未知")
        desc = arc.get("description", "")
        trajectory = arc.get("trajectory", [])
        lines.append(f"- **情感弧线**：{arc_type}")
        if desc:
            lines.append(f"  {desc}")
        if trajectory:
            traj_str = " → ".join(f"{v:.2f}" for v in trajectory)
            lines.append(f"  轨迹：{traj_str}")
    else:
        lines.append("- **情感弧线**：数据不足或未检测")

    # 时序规则
    rules = data.get("temporal_rules", [])
    if rules:
        lines.append("\n**时序演变规则**：")
        for rule in rules[:8]:
            rule_text = rule.get("rule", rule.get("description", ""))
            confidence = rule.get("confidence", 0)
            if rule_text:
                lines.append(f"- {rule_text}（置信度 {confidence:.2f}）")

    # 切片指标：slices 是 {phase: {metrics, line_count}} 结构
    slices = data.get("slices", {})
    if slices:
        lines.append("\n**各时期关键指标**：")
        for phase, sdata in slices.items():
            m = sdata.get("metrics", {}) if isinstance(sdata, dict) else {}
            ellipsis = m.get("ellipsis_pct", 0)
            avg_len = m.get("avg_sentence_length", m.get("avg_length", 0))
            line_count = sdata.get("line_count", 0) if isinstance(sdata, dict) else 0
            lines.append(f"- {phase}：{line_count} 条对话，省略号 {ellipsis}%，平均句长 {avg_len} 字")

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
        "speech_acts": ("speech_act_profile.json", format_speech_acts),
        "relationships": ("context.json", format_relationships),
        "temporal": ("temporal_slices.json", format_temporal),
        "context": ("context.json", format_context),
    }

    if sections is None:
        sections = list(all_sections.keys())

    header = f"## 量化分析数据上下文（{slug}）\n"
    header += "> 以下数据来自角色实际对话的量化分析，**生成 Persona/Knowledge 时必须严格遵守这些数据约束**。\n\n"

    parts = [header]

    # relationships 与 context 都读 context.json，避免重复输出
    seen_files: set[str] = set()
    for section_name in sections:
        if section_name not in all_sections:
            continue
        filename, formatter = all_sections[section_name]
        # relationships section 从 context.json 提取，跳过以避免与 context section 重复
        if section_name == "relationships" and "context" in sections:
            continue
        filepath = operator_dir / filename
        if str(filepath) in seen_files and section_name != "relationships":
            continue
        seen_files.add(str(filepath))
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
