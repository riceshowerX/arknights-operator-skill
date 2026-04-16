#!/usr/bin/env python3
"""
时序切片器 — 按 period 切片分析角色语言，检测跨期演变

这是语境化架构的深度分析组件。它消费 context.json，按 timeline 的
period 切片，对每个切片独立运行指纹分析，然后比较切片之间的差异，
输出可写入 Persona Layer 2 的行为演变规则。

典型发现示例：
  - "巴别塔时期：省略号频率 42%，复活后降至 18% → 情感表达从克制转向直接"
  - "对博士：承诺行为占 35%；对凯尔希：承诺行为占 10% → 承诺是对博士特有的"

用法：
    python3 temporal_slicer.py --context-json operators/te-lei-xi-ya/context.json
    python3 temporal_slicer.py --context-json context.json --output slices.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ──────────────────────────────────────────────
# 切片构建
# ──────────────────────────────────────────────

def build_slices(context: dict) -> dict[str, list[dict]]:
    """按 period 切分 annotated_lines"""
    lines = context.get("annotated_lines", [])
    slices: dict[str, list[dict]] = {}

    for line in lines:
        if line.get("source") == "archive":
            continue
        phase = line.get("context", {}).get("phase", "unknown")
        if phase == "unknown":
            continue
        slices.setdefault(phase, []).append(line)

    return slices


# ──────────────────────────────────────────────
# 切片级指标计算
# ──────────────────────────────────────────────

def compute_slice_metrics(lines: list[dict]) -> dict:
    """计算单个切片的量化指标"""
    if not lines:
        return {"line_count": 0}

    texts = [l.get("text", "") for l in lines]
    total = len(texts)

    # 句式长度
    lengths = []
    for t in texts:
        sentences = re.split(r"[。！？；…—]+", t)
        for s in sentences:
            s = s.strip()
            if len(s) > 0:
                lengths.append(len(s))

    avg_length = round(sum(lengths) / len(lengths), 1) if lengths else 0

    # 省略号频率
    ellipsis_count = sum(1 for t in texts if "…" in t or "..." in t)
    ellipsis_pct = round(ellipsis_count / total * 100, 1) if total else 0

    # 感叹号频率
    exclamation_count = sum(1 for t in texts if "！" in t or "!" in t)
    exclamation_pct = round(exclamation_count / total * 100, 1) if total else 0

    # 否定句频率
    negation_patterns = [
        r"(不|未|莫|别)\s*[是能为会有在到想需该]",
        r"没有", r"无法", r"并非", r"绝不|决不",
    ]
    negation_count = sum(
        1 for t in texts
        if any(re.search(p, t) for p in negation_patterns)
    )
    negation_pct = round(negation_count / total * 100, 1) if total else 0

    # 话语行为分布
    speech_act_dist = {}
    for line in lines:
        for act in line.get("speech_acts", []):
            act_type = act.get("type", "unknown")
            speech_act_dist[act_type] = speech_act_dist.get(act_type, 0) + 1

    # 自称频率
    first_person_words = ["我", "吾", "本王", "吾辈", "在下", "朕", "本人", "咱"]
    fp_count = sum(t.count(w) for t in texts for w in first_person_words)
    fp_freq = round(fp_count / total, 2) if total else 0

    # 对话对象分布
    interlocutor_dist = {}
    for line in lines:
        person = line.get("context", {}).get("interlocutor") or "unknown"
        interlocutor_dist[person] = interlocutor_dist.get(person, 0) + 1

    return {
        "line_count": total,
        "avg_sentence_length": avg_length,
        "ellipsis_pct": ellipsis_pct,
        "exclamation_pct": exclamation_pct,
        "negation_pct": negation_pct,
        "self_reference_freq": fp_freq,
        "speech_act_distribution": speech_act_dist,
        "interlocutor_distribution": interlocutor_dist,
    }


# ──────────────────────────────────────────────
# 跨切片比较
# ──────────────────────────────────────────────

def compare_metrics(baseline: dict, comparison: dict) -> list[dict]:
    """比较两个切片的指标，返回显著差异"""
    diffs = []

    # 句式长度偏移
    b_avg = baseline.get("avg_sentence_length", 0)
    c_avg = comparison.get("avg_sentence_length", 0)
    if b_avg > 0 and abs(c_avg - b_avg) / b_avg > 0.25:
        direction = "偏短" if c_avg < b_avg else "偏长"
        diffs.append({
            "metric": "avg_sentence_length",
            "baseline": b_avg,
            "comparison": c_avg,
            "shift_pct": round((c_avg - b_avg) / b_avg * 100, 1),
            "interpretation": f"句式{direction}（{b_avg}→{c_avg}字）",
        })

    # 省略号频率偏移
    b_ell = baseline.get("ellipsis_pct", 0)
    c_ell = comparison.get("ellipsis_pct", 0)
    if b_ell > 0 and abs(c_ell - b_ell) / b_ell > 0.3:
        direction = "增多" if c_ell > b_ell else "减少"
        diffs.append({
            "metric": "ellipsis_pct",
            "baseline": b_ell,
            "comparison": c_ell,
            "shift_pct": round((c_ell - b_ell) / b_ell * 100, 1),
            "interpretation": f"沉默/停顿{direction}（{b_ell}%→{c_ell}%）",
        })

    # 否定句频率偏移
    b_neg = baseline.get("negation_pct", 0)
    c_neg = comparison.get("negation_pct", 0)
    if b_neg > 0 and abs(c_neg - b_neg) / b_neg > 0.3:
        direction = "增多" if c_neg > b_neg else "减少"
        diffs.append({
            "metric": "negation_pct",
            "baseline": b_neg,
            "comparison": c_neg,
            "shift_pct": round((c_neg - b_neg) / b_neg * 100, 1),
            "interpretation": f"否定表达{direction}（{b_neg}%→{c_neg}%）",
        })

    # 话语行为分布偏移
    b_acts = baseline.get("speech_act_distribution", {})
    c_acts = comparison.get("speech_act_distribution", {})
    b_total = sum(b_acts.values()) or 1
    c_total = sum(c_acts.values()) or 1

    act_labels = {
        "invite": "邀请", "evade": "回避", "question": "质问",
        "commit": "承诺", "console": "宽慰", "restrain": "克制",
        "affirm_presence": "存在确认", "promise_remember": "记忆承诺",
        "farewell": "告别", "soothe": "安抚",
    }

    for act_type in set(list(b_acts.keys()) + list(c_acts.keys())):
        b_pct = b_acts.get(act_type, 0) / b_total
        c_pct = c_acts.get(act_type, 0) / c_total
        delta = c_pct - b_pct
        if abs(delta) > 0.1:
            label = act_labels.get(act_type, act_type)
            direction = "显著增多" if delta > 0 else "显著减少"
            diffs.append({
                "metric": f"speech_act:{act_type}",
                "baseline_pct": round(b_pct * 100, 1),
                "comparison_pct": round(c_pct * 100, 1),
                "shift_pct": round(delta * 100, 1),
                "interpretation": f"{label}行为{direction}（{round(b_pct*100,1)}%→{round(c_pct*100,1)}%）",
            })

    return diffs


# ──────────────────────────────────────────────
# 生成 Persona 规则
# ──────────────────────────────────────────────

def generate_temporal_rules(
    slices: dict[str, list[dict]],
    slice_metrics: dict[str, dict],
    timeline: list[dict],
) -> list[dict]:
    """从切片差异生成可写入 Persona Layer 2 的行为演变规则"""
    rules = []
    phase_names = sorted(slice_metrics.keys())

    if len(phase_names) < 2:
        return rules

    # 按 timeline 顺序排序
    timeline_order = [t.get("id", t.get("label", "")) for t in timeline]
    ordered = []
    for t_id in timeline_order:
        if t_id in phase_names:
            ordered.append(t_id)
    # 加入未在 timeline 中的 period
    for p in phase_names:
        if p not in ordered:
            ordered.append(p)

    # 相邻时期比较（每对相邻时期）
    for i in range(1, len(ordered)):
        prev = slice_metrics.get(ordered[i - 1], {})
        current = slice_metrics.get(ordered[i], {})
        diffs = compare_metrics(prev, current)

        for diff in diffs:
            rule_text = f"{ordered[i]}时期相比{ordered[i-1]}时期：{diff['interpretation']}"
            rules.append({
                "rule": rule_text,
                "layer": 2,
                "metric": diff["metric"],
                "phases": [ordered[i - 1], ordered[i]],
                "confidence": min(abs(diff.get("shift_pct", 0)) / 50, 0.95),
            })

    # 对象维度：每个 period 内的对象差异
    for phase in ordered:
        phase_lines = slices.get(phase, [])
        by_person: dict[str, list[dict]] = {}
        for line in phase_lines:
            person = line.get("context", {}).get("interlocutor") or "unknown"
            if person != "unknown":
                by_person.setdefault(person, []).append(line)

        if len(by_person) >= 2:
            person_metrics = {
                person: compute_slice_metrics(person_lines)
                for person, person_lines in by_person.items()
                if len(person_lines) >= 2
            }

            if len(person_metrics) >= 2:
                persons = list(person_metrics.keys())
                for i in range(len(persons)):
                    for j in range(i + 1, len(persons)):
                        p_diffs = compare_metrics(
                            person_metrics[persons[i]],
                            person_metrics[persons[j]],
                        )
                        for diff in p_diffs:
                            rule_text = (
                                f"{phase}时期，对{persons[i]}与对{persons[j]}的"
                                f"表达差异：{diff['interpretation']}"
                            )
                            rules.append({
                                "rule": rule_text,
                                "layer": 4,
                                "metric": diff["metric"],
                                "phases": [phase],
                                "interlocutors": [persons[i], persons[j]],
                                "confidence": min(abs(diff.get("shift_pct", 0)) / 40, 0.9),
                            })

    # 按置信度排序
    rules.sort(key=lambda r: r.get("confidence", 0), reverse=True)

    return rules


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="时序切片器")
    parser.add_argument(
        "--context-json", required=True,
        help="context.json 路径"
    )
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    with open(args.context_json, encoding='utf-8') as f:
        context = json.load(f)

    # 构建切片
    slices = build_slices(context)
    timeline = context.get("timeline", [])

    # 计算各切片指标
    slice_metrics = {}
    for phase, lines in slices.items():
        slice_metrics[phase] = compute_slice_metrics(lines)

    # 生成时序规则
    rules = generate_temporal_rules(slices, slice_metrics, timeline)

    result = {
        "character": context.get("character", ""),
        "slice_count": len(slices),
        "slices": {
            phase: {
                "metrics": metrics,
                "line_count": len(slices.get(phase, [])),
            }
            for phase, metrics in slice_metrics.items()
        },
        "temporal_rules": rules,
        "rule_count": len(rules),
    }

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "success": True,
        "slice_count": result["slice_count"],
        "rule_count": result["rule_count"],
        "top_rules": [r["rule"] for r in rules[:5]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
