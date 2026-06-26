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

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from constants import ACT_TYPE_LABELS, ACT_TYPE_ALIASES
from shared_utils import setup_logging, atomic_write_json

logger = setup_logging("speech_act_analyzer")


# ──────────────────────────────────────────────
# 话语行为规则库
# ──────────────────────────────────────────────

# 每条规则：(正则, 行为类型, 置信度, 中文标签)
#
# 规则从 data/speech_act_rules.json 加载；如文件不存在则使用以下内建默认值。
# 要调整规则，编辑 data/speech_act_rules.json 即可，无需修改源码。

_SPEECH_ACT_RULES_BUILTIN = [
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

    # 宽慰：减轻对方负担（合并原 console + soothe）
    (r"不是你的错", "comfort", 0.9, "宽慰"),
    (r"你不必.{1,15}", "comfort", 0.85, "宽慰"),
    (r"(已经足够|不要紧)", "comfort", 0.85, "宽慰"),
    (r"没关系(?!.{0,5}[。…])", "comfort", 0.8, "宽慰"),   # "没关系"后无句号/省略号 → 宽慰
    (r"我(理解|明白|知道你的).{0,10}", "comfort", 0.75, "宽慰"),
    (r"(好了|没事|别担心)", "comfort", 0.7, "安抚"),
    (r"(睡吧|休息吧)", "comfort", 0.75, "安抚"),

    # 克制：压抑情感
    (r"[悲伤痛苦遗憾].{0,5}[………]", "restrain", 0.8, "克制"),
    (r"我(知道|明白).{0,8}$", "restrain", 0.7, "克制"),
    (r"没关系.{0,5}[。…]", "restrain", 0.7, "克制"),   # "没关系。" → 克制（语气收敛）

    # 存在表达（合并原 affirm_presence + promise_remember + farewell）
    (r"我在", "presence", 0.9, "存在确认"),
    (r"我会记住", "presence", 0.85, "记忆承诺"),
    (r"再(见|会)[。…]?", "presence", 0.8, "告别"),
    (r"保重", "presence", 0.75, "告别"),
]


def _load_speech_act_rules(filepath: str | None = None) -> list[tuple]:
    """加载话语行为规则。优先从 JSON 文件加载，失败则使用内建默认值。

    JSON 格式: [{"pattern": "...", "type": "...", "confidence": 0.85, "label": "..."}, ...]

    Args:
        filepath: 自定义规则文件路径。None 时使用默认 data/speech_act_rules.json

    Returns:
        [(pattern_str, act_type, confidence, label), ...] 列表
    """
    json_path = Path(filepath) if filepath else Path(__file__).parent.parent / "data" / "speech_act_rules.json"

    if not json_path.exists():
        return _SPEECH_ACT_RULES_BUILTIN

    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"警告：话语行为规则文件解析失败 {json_path}: {e}，使用内建规则", file=sys.stderr)
        return _SPEECH_ACT_RULES_BUILTIN

    if not isinstance(raw, list):
        print(f"警告：话语行为规则文件应为 JSON 数组，使用内建规则", file=sys.stderr)
        return _SPEECH_ACT_RULES_BUILTIN

    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern")
        act_type = item.get("type")
        confidence = item.get("confidence", 0.8)
        label = item.get("label", "")
        if pattern and act_type:
            result.append((pattern, act_type, float(confidence), label))

    return result if result else _SPEECH_ACT_RULES_BUILTIN


# 模块级初始化：从 JSON 文件加载（如存在），否则用内建值
SPEECH_ACT_RULES = _load_speech_act_rules()

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
    使用 dict 存储最优结果，避免每次匹配都重建列表，时间复杂度从 O(n²) 降至 O(n)。
    """
    best: dict[str, tuple[float, str]] = {}  # type → (confidence, label)
    for pattern, act_type, confidence, label in COMPILED_RULES:
        if pattern.search(text):
            # 同类型只保留置信度最高的匹配
            if act_type in best and best[act_type][0] >= confidence:
                continue
            best[act_type] = (confidence, label)

    return [
        {"type": act_type, "label": label, "confidence": conf}
        for act_type, (conf, label) in best.items()
    ]


# ──────────────────────────────────────────────
# 上下文感知分类（升级新增）
# ──────────────────────────────────────────────

def classify_with_context(
    lines: list[dict],
    window: int = 2,
) -> list[list[dict]]:
    """上下文感知的话语行为分类

    考虑前 window 条台词的场景和对象，调整分类置信度。
    例如：前一条是质问时，当前条的省略号更可能是回避而非克制。

    Args:
        lines: annotated_lines 列表（每条含 text 和 context）
        window: 上下文窗口大小

    Returns:
        每条台词的话语行为分类结果列表
    """
    results: list[list[dict]] = []

    for i, line in enumerate(lines):
        text = line.get("text", "")
        if not text or line.get("source") == "archive":
            results.append([])
            continue

        acts = classify_speech_acts(text)

        # 收集上下文中的行为类型
        prev_act_types: set[str] = set()
        for j in range(max(0, i - window), i):
            if j < len(results):
                for act in results[j]:
                    prev_act_types.add(act["type"])

        # 上下文调整规则
        for act in acts:
            # 规则1：前一条是质问 → 当前省略号更可能是回避
            if "question" in prev_act_types and act["type"] == "evade":
                act["confidence"] = min(act["confidence"] + 0.15, 1.0)
                act["context_boost"] = "preceded_by_question"

            # 规则2：前一条是宽慰 → 当前承诺更可能是回应性承诺
            if "comfort" in prev_act_types and act["type"] == "commit":
                act["confidence"] = min(act["confidence"] + 0.10, 1.0)
                act["context_boost"] = "response_to_comfort"

            # 规则3：前一条是回避 → 当前质问更可能是追问
            if "evade" in prev_act_types and act["type"] == "question":
                act["confidence"] = min(act["confidence"] + 0.12, 1.0)
                act["context_boost"] = "follow_up_question"

            # 规则4：前一条是存在表达 → 当前宽慰更可能是告别前的安慰
            if "presence" in prev_act_types and act["type"] == "comfort":
                act["confidence"] = min(act["confidence"] + 0.08, 1.0)
                act["context_boost"] = "farewell_comfort"

        results.append(acts)

    return results


# ──────────────────────────────────────────────
# 行为链检测（升级新增）
# ──────────────────────────────────────────────

def detect_behavior_chains(
    lines: list[dict],
    min_chain_length: int = 3,
    min_occurrences: int = 2,
) -> list[dict]:
    """检测重复出现的行为链模式

    行为链是连续多条台词的话语行为序列，如：
    质问 → 回避 → 宽慰 → 承诺（"接纳仪式"）
    质问 → 质问 → 回避（"追问模式"）

    Args:
        lines: annotated_lines 列表
        min_chain_length: 最小链长度
        min_occurrences: 最小出现次数

    Returns:
        检测到的行为链模式列表
    """
    from collections import Counter

    # 提取行为序列
    act_sequence: list[str] = []
    for line in lines:
        if line.get("source") == "archive":
            continue
        acts = line.get("speech_acts", [])
        if acts:
            # 取置信度最高的行为
            best_act = max(acts, key=lambda a: a.get("confidence", 0))
            act_sequence.append(best_act["type"])

    if len(act_sequence) < min_chain_length:
        return []

    # 提取所有 n-gram（n = min_chain_length 到 min_chain_length + 2）
    chain_counter: Counter = Counter()
    for n in range(min_chain_length, min(min_chain_length + 3, len(act_sequence) + 1)):
        for i in range(len(act_sequence) - n + 1):
            chain = tuple(act_sequence[i:i + n])
            chain_counter[chain] += 1

    # 筛选高频链
    chains: list[dict] = []
    for chain, count in chain_counter.most_common(20):
        if count < min_occurrences:
            break

        # 生成自然语言描述
        labels = [ACT_TYPE_LABELS.get(t, t) for t in chain]
        chain_desc = " → ".join(labels)

        # 解读行为链的含义
        interpretation = _interpret_chain(chain)

        chains.append({
            "chain": list(chain),
            "labels": labels,
            "description": chain_desc,
            "count": count,
            "interpretation": interpretation,
            "rule": f"存在重复行为链「{chain_desc}」（出现{count}次）——{interpretation}",
        })

    return chains


def _interpret_chain(chain: tuple[str, ...]) -> str:
    """解读行为链的含义"""
    chain_str = "→".join(chain)

    # 预定义的链解读
    interpretations = {
        "question→evade→comfort": "先追问立场，再回避自己的感受，最后宽慰对方——典型的'先确认再安抚'模式",
        "question→evade→commit": "追问后回避，最终做出承诺——'被逼表态'模式",
        "comfort→commit→presence": "宽慰后承诺，最后确认存在——'告别仪式'模式",
        "evade→restrain→comfort": "先回避，再克制，最后宽慰——'自我压抑后转向关怀'模式",
        "question→question→evade": "连续追问后回避——'追问到沉默'模式",
        "invite→commit": "邀请后承诺——'共同行动'模式",
        "comfort→comfort": "连续宽慰——'深度安抚'模式",
    }

    if chain_str in interpretations:
        return interpretations[chain_str]

    # 通用解读
    if "question" in chain and "evade" in chain:
        return "包含追问与回避的交互，体现角色在信息交换中的保留态度"
    if "comfort" in chain and "commit" in chain:
        return "包含宽慰与承诺，体现角色在情感支持中的坚定姿态"
    if chain.count(chain[0]) == len(chain):
        return f"连续重复{ACT_TYPE_LABELS.get(chain[0], chain[0])}行为，体现角色在此类场景中的持续性"

    return "体现角色在特定场景中的固定行为序列"


def detect_emotion_asymmetry(
    profile: dict,
) -> list[dict]:
    """检测角色对不同对象的情感不对称

    例如：对 A 宽慰但对 B 回避 → 角色对两人的信任度不同
    """
    by_interlocutor = profile.get("by_interlocutor", {})
    asymmetries: list[dict] = []

    persons = list(by_interlocutor.keys())
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            p1, p2 = persons[i], persons[j]
            if p1 == "unknown" or p2 == "unknown":
                continue

            acts1 = by_interlocutor[p1]
            acts2 = by_interlocutor[p2]
            total1 = sum(acts1.values()) or 1
            total2 = sum(acts2.values()) or 1

            # 找出差异最大的行为类型
            all_types = set(acts1.keys()) | set(acts2.keys())
            max_delta = 0
            max_type = ""
            for t in all_types:
                pct1 = acts1.get(t, 0) / total1
                pct2 = acts2.get(t, 0) / total2
                delta = abs(pct1 - pct2)
                if delta > max_delta:
                    max_delta = delta
                    max_type = t

            if max_delta > 0.2 and max_type:
                label = ACT_TYPE_LABELS.get(max_type, max_type)
                pct1 = acts1.get(max_type, 0) / total1
                pct2 = acts2.get(max_type, 0) / total2
                more_to = p1 if pct1 > pct2 else p2
                less_to = p2 if pct1 > pct2 else p1

                asymmetries.append({
                    "persons": [p1, p2],
                    "act_type": max_type,
                    "delta": round(max_delta, 3),
                    "rule": (
                        f"对{more_to}的{label}行为显著多于对{less_to}"
                        f"（差异{max_delta:.0%}）——角色对两人的态度存在明显不对称"
                    ),
                })

    return asymmetries


# ──────────────────────────────────────────────
# 画像构建
# ──────────────────────────────────────────────

def build_speech_act_profile(annotated_lines: list[dict]) -> dict:
    """构建话语行为分布画像"""
    from collections import defaultdict

    global_dist: dict[str, int] = defaultdict(int)
    by_situation: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_interlocutor: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_phase: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
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
            act_type = ACT_TYPE_ALIASES.get(act["type"], act["type"])
            global_dist[act_type] += 1
            by_situation[situation][act_type] += 1
            by_interlocutor[interlocutor][act_type] += 1
            by_phase[phase][act_type] += 1

    # 归一化全局分布
    total = sum(global_dist.values()) or 1
    global_pct = {k: round(v / total, 3) for k, v in global_dist.items()}

    return {
        "global": global_pct,
        "global_raw": dict(global_dist),
        "by_situation": {k: dict(v) for k, v in by_situation.items()},
        "by_interlocutor": {k: dict(v) for k, v in by_interlocutor.items()},
        "by_phase": {k: dict(v) for k, v in by_phase.items()},
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
    comfort_ratio = global_dist.get("comfort", 0)
    if restrain_ratio > 0.08 and comfort_ratio > 0.08:
        patterns.append({
            "pattern": "restrained_consolation",
            "rule": "安慰他人时倾向用克制的表达（先说'我明白'，再轻描淡写地宽慰），而不是热情的鼓励",
            "layer": 2,
            "confidence": min((restrain_ratio + comfort_ratio) * 2, 1.0),
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

    # 分类话语行为（使用上下文感知分类）
    annotated_lines = context.get("annotated_lines", [])
    context_results = classify_with_context(annotated_lines)

    for idx, line in enumerate(annotated_lines):
        if line.get("source") == "archive":
            continue
        if idx < len(context_results):
            line["speech_acts"] = context_results[idx]
        else:
            line["speech_acts"] = classify_speech_acts(line["text"])

    # 构建画像
    profile = build_speech_act_profile(context["annotated_lines"])

    # 检测行为模式
    patterns = detect_behavioral_patterns(profile)

    # 检测行为链（升级新增）
    chains = detect_behavior_chains(context["annotated_lines"])
    if chains:
        for chain in chains:
            patterns.append({
                "pattern": f"chain_{'_'.join(chain['chain'])}",
                "rule": chain["rule"],
                "layer": 2,
                "confidence": min(chain["count"] / 5, 0.9),
            })

    # 检测情感不对称（升级新增）
    asymmetries = detect_emotion_asymmetry(profile)
    if asymmetries:
        for asym in asymmetries:
            patterns.append({
                "pattern": f"asymmetry_{asym['act_type']}",
                "rule": asym["rule"],
                "layer": 4,
                "confidence": min(asym["delta"] * 2, 0.9),
            })

    # 回写 context.json
    atomic_write_json(args.context_json, context)

    # 输出画像
    profile["behavioral_patterns"] = patterns
    if args.output_profile:
        atomic_write_json(args.output_profile, profile)

    print(json.dumps({
        "success": True,
        "total_acts": profile["total_acts"],
        "lines_with_acts": profile["lines_with_acts"],
        "patterns_detected": len(patterns),
        "top_acts": list(sorted(profile["global"].items(), key=lambda x: -x[1]))[:5],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
