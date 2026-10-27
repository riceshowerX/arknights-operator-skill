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
import math
import re
import sys
from pathlib import Path

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from constants import ACT_TYPE_LABELS
from shared_utils import atomic_write_json, read_text_utf8, setup_logging, split_sentences

logger = setup_logging("temporal_slicer")


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

    texts = [line.get("text", "") for line in lines]
    total = len(texts)

    # 句式长度（使用共享分句函数）
    lengths = []
    for t in texts:
        for s in split_sentences(t):
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

def compare_metrics(
    baseline: dict,
    comparison: dict,
    *,
    with_significance: bool = False,
    base_values: dict | None = None,
    comp_values: dict | None = None,
) -> list[dict]:
    """比较两个切片的指标，返回显著差异。

    ``with_significance=False``（默认）返回**旧字段集合**：每项含
    ``metric/baseline/comparison/shift_pct/interpretation``（话语行为项为
    ``metric/baseline_pct/comparison_pct/shift_pct/interpretation``），
    与 3.x 的 ``compare_metrics`` 输出逐字段一致。

    ``with_significance=True`` 额外附带 ``significance``/``p_value``/
    ``effect_size``/``sample_warning``，即原 ``compare_metrics_v2`` 的输出。

    阈值（句式 0.25 / 省略号 0.3 / 否定 0.3 / 话语行为 0.1）与显著性判定
    全部沿用产品既有取值，本函数不含任何阈值改动。

    Args:
        baseline: 基准切片指标。
        comparison: 对比切片指标。
        with_significance: 是否附带统计显著性字段。
        base_values: 基准切片原始数值（键名沿用旧实现 ``sentence_lengths``）。
        comp_values: 对比切片原始数值。

    Returns:
        显著差异列表。顺序固定（三个连续指标在前，话语行为项按 type 字典序），
        因此在任意 ``PYTHONHASHSEED`` 下同一输入输出顺序一致。
    """
    insufficient_sample = (
        baseline.get("line_count", 0) < MIN_SAMPLE_SIZE
        or comparison.get("line_count", 0) < MIN_SAMPLE_SIZE
    )

    diffs: list[dict] = []

    def _continuous(
        metric_name: str,
        b_val: float,
        c_val: float,
        b_vals: list[float] | None,
        c_vals: list[float] | None,
        interpretation: str,
    ) -> dict:
        """构造连续指标差异项（按需附带统计检验字段）。"""
        item: dict = {
            "metric": metric_name,
            "baseline": b_val,
            "comparison": c_val,
            "shift_pct": round((c_val - b_val) / b_val * 100, 1),
            "interpretation": interpretation,
        }
        if not with_significance:
            return item

        p_value = 1.0
        effect_size = 0.0
        if b_vals and c_vals and len(b_vals) >= 2 and len(c_vals) >= 2:
            _, p_value = _mann_whitney_u(b_vals, c_vals)
            effect_size = _cohen_d(b_vals, c_vals)
        elif not insufficient_sample:
            # 无原始数据时，用大样本正态近似做粗估
            pct_change = (c_val - b_val) / b_val
            effect_size = abs(pct_change) * 0.5
            p_value = 0.04 if abs(pct_change) > 0.4 else 0.15

        item["significance"] = _classify_significance(p_value, effect_size, insufficient_sample)
        item["p_value"] = round(p_value, 4)
        item["effect_size"] = round(effect_size, 3)
        item["sample_warning"] = insufficient_sample
        return item

    # 句式长度偏移
    b_avg = baseline.get("avg_sentence_length", 0)
    c_avg = comparison.get("avg_sentence_length", 0)
    if b_avg > 0 and abs(c_avg - b_avg) / b_avg > 0.25:
        direction = "偏短" if c_avg < b_avg else "偏长"
        diffs.append(_continuous(
            "avg_sentence_length", b_avg, c_avg,
            (base_values or {}).get("sentence_lengths", []),
            (comp_values or {}).get("sentence_lengths", []),
            f"句式{direction}（{b_avg}→{c_avg}字）",
        ))

    # 省略号频率偏移
    b_ell = baseline.get("ellipsis_pct", 0)
    c_ell = comparison.get("ellipsis_pct", 0)
    if b_ell > 0 and abs(c_ell - b_ell) / b_ell > 0.3:
        direction = "增多" if c_ell > b_ell else "减少"
        diffs.append(_continuous(
            "ellipsis_pct", b_ell, c_ell, None, None,
            f"沉默/停顿{direction}（{b_ell}%→{c_ell}%）",
        ))

    # 否定句频率偏移
    b_neg = baseline.get("negation_pct", 0)
    c_neg = comparison.get("negation_pct", 0)
    if b_neg > 0 and abs(c_neg - b_neg) / b_neg > 0.3:
        direction = "增多" if c_neg > b_neg else "减少"
        diffs.append(_continuous(
            "negation_pct", b_neg, c_neg, None, None,
            f"否定表达{direction}（{b_neg}%→{c_neg}%）",
        ))

    # 话语行为分布偏移（遍历顺序固定为 type 字典序，避免 set 迭代顺序随 PYTHONHASHSEED 波动）
    b_acts = baseline.get("speech_act_distribution", {})
    c_acts = comparison.get("speech_act_distribution", {})
    b_total = sum(b_acts.values()) or 1
    c_total = sum(c_acts.values()) or 1

    for act_type in sorted(set(b_acts) | set(c_acts)):
        b_pct = b_acts.get(act_type, 0) / b_total
        c_pct = c_acts.get(act_type, 0) / c_total
        delta = c_pct - b_pct
        if abs(delta) > 0.1:
            label = ACT_TYPE_LABELS.get(act_type, act_type)
            direction = "显著增多" if delta > 0 else "显著减少"
            item = {
                "metric": f"speech_act:{act_type}",
                "baseline_pct": round(b_pct * 100, 1),
                "comparison_pct": round(c_pct * 100, 1),
                "shift_pct": round(delta * 100, 1),
                "interpretation": f"{label}行为{direction}（{round(b_pct*100,1)}%→{round(c_pct*100,1)}%）",
            }
            if with_significance:
                item["significance"] = (
                    "low" if insufficient_sample else "high" if abs(delta) > 0.2 else "medium"
                )
                item["sample_warning"] = insufficient_sample
            diffs.append(item)

    return diffs


# ──────────────────────────────────────────────
# 统计显著性比较（升级新增 — 含 Mann-Whitney U 检验）
# ──────────────────────────────────────────────

# 最小样本量门槛
MIN_SAMPLE_SIZE = 5

# 显著性阈值
_ALPHA = 0.05   # 显著性水平
_ALPHA_STRICT = 0.01  # 严格显著性水平


def _mann_whitney_u(x: list[float], y: list[float]) -> tuple[float, float]:
    """Mann-Whitney U 检验（无外部依赖实现）。

    用于检验两组独立样本是否来自同一分布。
    适用场景：不假设正态分布，适合小样本和有序数据。

    Args:
        x: 第一组样本值
        y: 第二组样本值

    Returns:
        (U 统计量, p-value 双侧)
        p-value < 0.05 表示两组分布显著不同
    """
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    # 合并排序，计算秩
    combined = [(val, 0) for val in x] + [(val, 1) for val in y]
    combined.sort(key=lambda t: t[0])

    # 计算秩（处理并列值：取平均秩）
    ranks: list[float] = [0.0] * (n1 + n2)
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0  # 1-indexed 平均秩
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    # 计算第一组的秩和
    r1 = sum(ranks[i] for i in range(len(combined)) if combined[i][1] == 0)

    # U 统计量
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    # 正态近似计算 p-value（当 n1, n2 >= 8 时足够准确）
    mean_u = n1 * n2 / 2.0
    # 修正并列值的方差
    tie_counts: dict[float, int] = {}
    for val, _ in combined:
        tie_counts[val] = tie_counts.get(val, 0) + 1
    tie_correction = sum(t**3 - t for t in tie_counts.values() if t > 1)

    var_u = (n1 * n2 / 12.0) * ((n1 + n2 + 1) - tie_correction / ((n1 + n2) * (n1 + n2 - 1)))
    if var_u <= 0:
        var_u = n1 * n2 * (n1 + n2 + 1) / 12.0

    # 连续性修正
    z = abs(u - mean_u - 0.5) / math.sqrt(var_u) if var_u > 0 else 0.0

    # 标准正态 CDF 近似 (Abramowitz & Stegun)
    p_one_sided = _normal_cdf(-z)
    p_two_sided = 2 * p_one_sided

    return u, min(p_two_sided, 1.0)


def _normal_cdf(x: float) -> float:
    """标准正态分布 CDF 近似（Abramowitz & Stegun 26.2.17）。

    最大误差 < 7.5e-8，对统计检验精度足够。
    """
    if x < -8:
        return 0.0
    if x > 8:
        return 1.0

    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-x * x / 2.0) * (
        t * (0.319381530 +
        t * (-0.356563782 +
        t * (1.781477937 +
        t * (-1.821255978 +
        t * 1.330274429))))
    )
    return 1.0 - p if x > 0 else p


def _cohen_d(x: list[float], y: list[float]) -> float:
    """Cohen's d 效应量。

    Returns:
        效应量（绝对值），<0.2 微弱, 0.2-0.5 小, 0.5-0.8 中, >0.8 大
    """
    n1, n2 = len(x), len(y)
    if n1 < 2 or n2 < 2:
        return 0.0

    mean1, mean2 = sum(x) / n1, sum(y) / n2
    var1 = sum((v - mean1) ** 2 for v in x) / (n1 - 1)
    var2 = sum((v - mean2) ** 2 for v in y) / (n2 - 1)

    # 合并标准差
    pooled_std = math.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0

    return abs(mean1 - mean2) / pooled_std


def _classify_significance(p_value: float, effect_size: float, insufficient: bool) -> str:
    """综合 p-value 和效应量判定显著性等级。

    策略：
    - 样本不足 → low（即使 p 值显著也不可信）
    - p < 0.01 且效应量 >= 0.5 → high
    - p < 0.05 且效应量 >= 0.2 → medium
    - 其他 → low
    """
    if insufficient:
        return "low"
    if p_value < _ALPHA_STRICT and effect_size >= 0.5:
        return "high"
    if p_value < _ALPHA and effect_size >= 0.2:
        return "medium"
    return "low"


def compare_metrics_v2(baseline: dict, comparison: dict,
                       baseline_values: dict | None = None,
                       comparison_values: dict | None = None) -> list[dict]:
    """带统计显著性的切片比较（薄包装，委托 :func:`compare_metrics`）

    改进点（相对纯百分比比较）：
    1. 最小样本量门槛：样本太小时只报告差异但不生成规则
    2. Mann-Whitney U 检验：非参数检验，不假设正态分布
    3. Cohen's d 效应量：衡量实际差异大小
    4. 综合判定：p-value + 效应量 → significance 等级

    实现上等价于 ``compare_metrics(..., with_significance=True,
    base_values=..., comp_values=...)``；签名与返回结构保持 3.x 不变。

    Args:
        baseline: 基准切片指标
        comparison: 对比切片指标
        baseline_values: 基准切片的原始数值列表（用于统计检验）
        comparison_values: 对比切片的原始数值列表

    Returns:
        显著差异列表，每项含 significance, p_value, effect_size 字段
    """
    return compare_metrics(
        baseline,
        comparison,
        with_significance=True,
        base_values=baseline_values,
        comp_values=comparison_values,
    )


# ──────────────────────────────────────────────
# 情感弧线检测（升级新增）
# ──────────────────────────────────────────────

def detect_emotion_arc(
    slice_metrics: dict[str, dict],
    timeline: list[dict],
) -> dict:
    """检测跨时期的情感弧线

    识别模式如：
    - "U型弧线"：早期积极 → 中期低沉 → 后期回归
    - "下降弧线"：持续从积极走向沉重
    - "上升弧线"：持续从沉重走向释然
    - "平稳弧线"：情感基调始终一致
    - "波动型"：无明显趋势

    Args:
        slice_metrics: 各时期的指标字典
        timeline: 时间线定义

    Returns:
        情感弧线分析结果
    """
    # 按 timeline 顺序排列
    timeline_order = [t.get("id", t.get("label", "")) for t in timeline]
    ordered_phases = [p for p in timeline_order if p in slice_metrics]

    if len(ordered_phases) < 3:
        return {
            "arc": "insufficient_data",
            "reason": f"仅有 {len(ordered_phases)} 个时期，需要至少 3 个",
        }

    # 提取每个时期的情感指标序列
    # 综合情感得分：省略号多 → 克制/沉重，否定多 → 抗拒/痛苦
    emotion_scores: list[float] = []
    phase_details: list[dict] = []

    for phase in ordered_phases:
        m = slice_metrics[phase]
        ellipsis = m.get("ellipsis_pct", 0)
        negation = m.get("negation_pct", 0)
        exclamation = m.get("exclamation_pct", 0)

        # 情感沉重度得分（越高越沉重/克制）
        heaviness = ellipsis * 0.5 + negation * 0.3 - exclamation * 0.2
        emotion_scores.append(heaviness)

        phase_details.append({
            "phase": phase,
            "heaviness": round(heaviness, 2),
            "ellipsis_pct": ellipsis,
            "negation_pct": negation,
            "exclamation_pct": exclamation,
        })

    # 检测趋势
    n = len(emotion_scores)
    first_half = emotion_scores[:n // 2]
    second_half = emotion_scores[n // 2:]

    avg_first = sum(first_half) / len(first_half) if first_half else 0
    avg_second = sum(second_half) / len(second_half) if second_half else 0
    avg_mid = sum(emotion_scores[n // 3:2 * n // 3]) / max(len(emotion_scores[n // 3:2 * n // 3]), 1)

    # 判断弧线类型
    if avg_first < avg_mid < avg_second:
        arc_type = "持续沉重"
        arc_desc = "情感基调从轻松逐渐走向沉重，体现角色经历的累积压力"
    elif avg_first > avg_mid > avg_second:
        arc_type = "逐渐释然"
        arc_desc = "情感基调从沉重逐渐走向释然，体现角色的成长与和解"
    elif avg_first < avg_mid and avg_mid > avg_second:
        arc_type = "倒U型弧线"
        arc_desc = "中期情感最为沉重，前后相对平缓——角色在中期经历最大考验"
    elif avg_first > avg_mid and avg_mid < avg_second:
        arc_type = "U型弧线"
        arc_desc = "中期情感最为克制，前后相对活跃——角色在中期经历低谷后回归"
    elif abs(avg_first - avg_second) < 5:
        arc_type = "平稳弧线"
        arc_desc = "情感基调始终一致，体现角色性格的稳定性"
    else:
        arc_type = "波动型"
        arc_desc = "情感基调无明显趋势，体现角色在不同场景下的多变表达"

    return {
        "arc": arc_type,
        "description": arc_desc,
        "trajectory": emotion_scores,
        "phase_details": phase_details,
        "summary": f"情感弧线：{arc_type}——{arc_desc}",
    }


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

    context = json.loads(read_text_utf8(args.context_json))

    # 构建切片
    slices = build_slices(context)
    timeline = context.get("timeline", [])

    # 计算各切片指标
    slice_metrics = {}
    for phase, lines in slices.items():
        slice_metrics[phase] = compute_slice_metrics(lines)

    # 生成时序规则
    rules = generate_temporal_rules(slices, slice_metrics, timeline)

    # 情感弧线检测（升级新增）
    emotion_arc = detect_emotion_arc(slice_metrics, timeline)

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
        "emotion_arc": emotion_arc,
    }

    if args.output:
        atomic_write_json(args.output, result)

    print(json.dumps({
        "success": True,
        "slice_count": result["slice_count"],
        "rule_count": result["rule_count"],
        "top_rules": [r["rule"] for r in rules[:5]],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
