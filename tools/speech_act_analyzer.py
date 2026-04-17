#!/usr/bin/env python3
"""
话语行为分析器 — 从"她说了什么词"升级到"她用这句话做什么事"

这是还原度升级的核心组件之一。它不做主观描述，而是从角色实际对话中
分类话语行为（邀请/回避/质问/承诺/宽慰/克制等），然后输出
场景维度的行为分布和可执行的行为模式规则。

输入：context.json
输出：
  - 更新 context.json 的 speech_acts 字段
  - speech_act_profile.json（话语行为分布画像 + 行为模式）

用法：
    python3 speech_act_analyzer.py --context-json operators/te-lei-xi-ya/context.json
    python3 speech_act_analyzer.py --context-json context.json --output-profile profile.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


# 话语行为类型 → 中文标签（单一来源，供所有下游工具引用）
ACT_TYPE_LABELS = {
    "invite": "邀请", "evade": "回避", "question": "质问",
    "commit": "承诺", "console": "宽慰", "restrain": "克制",
    "affirm_presence": "存在确认", "promise_remember": "记忆承诺",
    "farewell": "告别", "soothe": "安抚",
}


# ──────────────────────────────────────────────
# 话语行为规则库
# ──────────────────────────────────────────────

# 每条规则：(正则, 行为类型, 置信度, 中文标签)
SPEECH_ACT_RULES = [
    # 邀请：用温和方式提出要求
    (r"(你|您)(愿意|想|要不要).{1,15}[吗？?]", "invite", 0.85, "邀请"),
    (r"我们一起.{1,10}", "invite", 0.9, "邀请"),
    (r"(不如|要不|让我们).{1,10}[吧。]", "invite", 0.8, "邀请"),
    (r"来吧", "invite", 0.7, "邀请"),

    # 回避：不正面回答
    # 匹配行末的省略号停顿（……、...、…），至少2个省略号字符或6个点
    (r".{0,8}(?:…{2,}|\.{6,})$", "evade", 0.75, "回避"),
    (r"^(?:…{2,}|\.{6,})", "evade", 0.7, "回避"),
    (r"你呢[？?]", "evade", 0.8, "回避"),
    (r"(也许|或许|大概|可能).{0,10}$", "evade", 0.7, "回避"),
    (r"我不知道.{0,5}$", "evade", 0.65, "回避"),

    # 质问：追问立场
    (r"为什么.{1,15}[？?]", "question", 0.8, "质问"),
    (r"你(觉得|认为|打算).{1,15}[？?]", "question", 0.75, "质问"),
    (r"(难道|岂).{1,15}[？?]", "question", 0.85, "质问"),

    # 承诺：明确表态
    (r"我(会|一定|绝不|将).{1,20}$", "commit", 0.85, "承诺"),
    (r"(一定|必定|绝对).{1,15}", "commit", 0.8, "承诺"),
    (r"请(相信|放心).{0,10}", "commit", 0.75, "承诺"),

    # 宽慰：减轻对方负担
    (r"不是你的错", "console", 0.9, "宽慰"),
    (r"你不必.{1,15}", "console", 0.85, "宽慰"),
    (r"(已经足够|不要紧)", "console", 0.85, "宽慰"),
    (r"没关系(?!.{0,5}[。…])", "console", 0.8, "宽慰"),   # "没关系"后无句号/省略号 → 宽慰
    (r"我(理解|明白|知道你的).{0,10}", "console", 0.75, "宽慰"),

    # 克制：压抑情感
    (r"[悲伤痛苦遗憾].{0,5}[………]", "restrain", 0.8, "克制"),
    (r"我(知道|明白).{0,8}$", "restrain", 0.7, "克制"),
    (r"没关系.{0,5}[。…]", "restrain", 0.7, "克制"),   # "没关系。" → 克制（语气收敛）

    # 存在确认（明日方舟特色）
    (r"我在", "affirm_presence", 0.9, "存在确认"),
    (r"我会记住", "promise_remember", 0.85, "记忆承诺"),

    # 告别
    (r"再(见|会)[。…]?", "farewell", 0.8, "告别"),
    (r"保重", "farewell", 0.75, "告别"),

    # 安抚（比宽慰更轻）
    (r"(好了|没事|别担心)", "soothe", 0.7, "安抚"),
    (r"(睡吧|休息吧)", "soothe", 0.75, "安抚"),
]

# 编译正则
COMPILED_RULES = [
    (re.compile(p, re.UNICODE), act_type, conf, label)
    for p, act_type, conf, label in SPEECH_ACT_RULES
]


# ──────────────────────────────────────────────
# 分类
# ──────────────────────────────────────────────

def classify_speech_acts(text: str) -> list[dict]:
    """对单条台词分类话语行为

    同一行为类型只保留置信度最高的一次匹配，避免多条规则命中同一类型时产生重复。
    """
    acts = []
    seen_types: dict[str, float] = {}  # type → best confidence
    for pattern, act_type, confidence, label in COMPILED_RULES:
        if pattern.search(text):
            # 同类型只保留置信度最高的匹配
            if act_type in seen_types and seen_types[act_type] >= confidence:
                continue
            seen_types[act_type] = confidence
            # 如果之前已添加过同类型低置信度结果，移除旧的
            acts = [a for a in acts if a["type"] != act_type]
            acts.append({
                "type": act_type,
                "label": label,
                "confidence": confidence,
            })
    return acts


# ──────────────────────────────────────────────
# 画像构建
# ──────────────────────────────────────────────

def build_speech_act_profile(annotated_lines: list[dict]) -> dict:
    """构建话语行为分布画像"""
    global_dist = {}
    by_situation = {}
    by_interlocutor = {}
    by_phase = {}
    lines_with_acts = 0

    for line in annotated_lines:
        # 只分析语音和剧情行
        if line.get("source") == "archive":
            continue

        acts = line.get("speech_acts", [])
        if not acts:
            continue
        lines_with_acts += 1

        ctx = line.get("context", {})
        situation = ctx.get("situation_type", "unknown")
        interlocutor = ctx.get("interlocutor") or "unknown"
        phase = ctx.get("phase", "unknown")

        for act in acts:
            act_type = act["type"]

            global_dist[act_type] = global_dist.get(act_type, 0) + 1

            by_situation.setdefault(situation, {})
            by_situation[situation][act_type] = by_situation[situation].get(act_type, 0) + 1

            by_interlocutor.setdefault(interlocutor, {})
            by_interlocutor[interlocutor][act_type] = by_interlocutor[interlocutor].get(act_type, 0) + 1

            by_phase.setdefault(phase, {})
            by_phase[phase][act_type] = by_phase[phase].get(act_type, 0) + 1

    # 归一化全局分布
    total = sum(global_dist.values()) or 1
    global_pct = {k: round(v / total, 3) for k, v in global_dist.items()}

    return {
        "global": global_pct,
        "global_raw": global_dist,
        "by_situation": by_situation,
        "by_interlocutor": by_interlocutor,
        "by_phase": by_phase,
        "total_acts": sum(global_dist.values()),
        "lines_with_acts": lines_with_acts,
    }


# ──────────────────────────────────────────────
# 行为模式检测
# ──────────────────────────────────────────────

def detect_behavioral_patterns(profile: dict) -> list[dict]:
    """检测行为模式，生成可直接写入 Persona 的规则"""
    patterns = []
    global_dist = profile.get("global", {})
    by_situation = profile.get("by_situation", {})
    by_interlocutor = profile.get("by_interlocutor", {})
    by_phase = profile.get("by_phase", {})

    # 模式1：高回避倾向
    evade_ratio = global_dist.get("evade", 0)
    if evade_ratio > 0.12:
        patterns.append({
            "pattern": "high_evade",
            "rule": f"在被追问时倾向回避直接回答（回避行为占比{evade_ratio:.0%}），常用省略号结尾或反问代替回答",
            "layer": 0,
            "confidence": min(evade_ratio * 3, 1.0),
        })

    # 模式2：选择性邀请
    # by_situation 使用原始计数，需要归一化后比较
    comfort_total = sum(by_situation.get("comfort", {}).values()) or 1
    confront_total = sum(by_situation.get("confront", {}).values()) or 1
    comfort_invite_ratio = by_situation.get("comfort", {}).get("invite", 0) / comfort_total
    confront_invite_ratio = by_situation.get("confront", {}).get("invite", 0) / confront_total
    if comfort_invite_ratio > 0 and confront_invite_ratio == 0:
        patterns.append({
            "pattern": "selective_invite",
            "rule": "只在安慰他人时发出邀请，在面对对抗时从不邀请——即使在冲突中也保持邀请姿态是罕见的",
            "layer": 0,
            "confidence": 0.7,
        })

    # 模式3：克制型情感表达
    restrain_ratio = global_dist.get("restrain", 0)
    console_ratio = global_dist.get("console", 0)
    if restrain_ratio > 0.08 and console_ratio > 0.08:
        patterns.append({
            "pattern": "restrained_consolation",
            "rule": "安慰他人时倾向用克制的表达（先说'我明白'，再轻描淡写地宽慰），而不是热情的鼓励",
            "layer": 2,
            "confidence": min((restrain_ratio + console_ratio) * 2, 1.0),
        })

    # 模式4：对象差异化
    for person, person_acts in by_interlocutor.items():
        if person == "unknown" or not person_acts:
            continue
        total_person = sum(person_acts.values()) or 1
        dominant_act = max(person_acts, key=person_acts.get)
        dominant_pct = person_acts[dominant_act] / total_person
        if dominant_pct > 0.3 and person_acts[dominant_act] >= 2:
            act_label = ACT_TYPE_LABELS.get(dominant_act, dominant_act)
            patterns.append({
                "pattern": f"interlocutor_{dominant_act}",
                "rule": f"对{person}的对话中，{act_label}行为占比最高（{dominant_pct:.0%}）——用{act_label}的方式回应{person}",
                "layer": 4,
                "confidence": min(dominant_pct, 0.9),
            })

    # 模式5：时期偏移
    if len(by_phase) >= 2:
        for phase_id, phase_acts in by_phase.items():
            if phase_id == "unknown":
                continue
            phase_total = sum(phase_acts.values()) or 1
            for act_type, count in phase_acts.items():
                phase_pct = count / phase_total
                global_pct = global_dist.get(act_type, 0)
                delta = phase_pct - global_pct
                if abs(delta) > 0.15 and count >= 2:
                    act_label = ACT_TYPE_LABELS.get(act_type, act_type)
                    direction = "显著增多" if delta > 0 else "显著减少"
                    patterns.append({
                        "pattern": f"phase_shift_{phase_id}_{act_type}",
                        "rule": f"{phase_id}时期，{act_label}行为{direction}（偏移{abs(delta):.0%}）",
                        "layer": 2,
                        "confidence": min(abs(delta) * 2, 0.9),
                    })

    # 按置信度排序
    patterns.sort(key=lambda p: p.get("confidence", 0), reverse=True)

    return patterns


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="话语行为分析器")
    parser.add_argument(
        "--context-json", required=True,
        help="context.json 路径"
    )
    parser.add_argument(
        "--output-profile",
        help="话语行为画像输出路径（默认不输出独立文件）"
    )
    args = parser.parse_args()

    with open(args.context_json, encoding='utf-8') as f:
        context = json.load(f)

    # 分类话语行为
    for line in context.get("annotated_lines", []):
        if line.get("source") == "archive":
            continue
        acts = classify_speech_acts(line["text"])
        line["speech_acts"] = acts

    # 构建画像
    profile = build_speech_act_profile(context["annotated_lines"])

    # 检测行为模式
    patterns = detect_behavioral_patterns(profile)

    # 回写 context.json
    with open(args.context_json, 'w', encoding='utf-8') as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    # 输出画像
    profile["behavioral_patterns"] = patterns
    if args.output_profile:
        Path(args.output_profile).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_profile, 'w', encoding='utf-8') as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "success": True,
        "total_acts": profile["total_acts"],
        "lines_with_acts": profile["lines_with_acts"],
        "patterns_detected": len(patterns),
        "top_acts": list(sorted(profile["global"].items(), key=lambda x: -x[1]))[:5],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
