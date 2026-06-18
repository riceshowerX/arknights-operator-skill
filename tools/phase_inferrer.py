#!/usr/bin/env python3
"""
phase_inferrer.py — 多层级时期自动推断引擎

消除手动映射依赖，从 PRTS 元数据自动推断角色/章节时期。

推断优先级（从高到低）：
1. 内容精确匹配 (PHASE_PATTERNS)  — 正则，最高优先
2. 内容关键词匹配 (PHASE_KEYWORDS)  — 包含匹配，次优先
3. PRTS 活动元数据  — 从活动页面的 {{活动信息}} 模板提取
4. PRTS 分类标签  — 干员页面的"属于XX的干员"分类
5. 章节代码映射  — CHAPTER_PHASE_MAP（保留作为快速路径）
6. 内容聚类 fallback  — 对话内容关键词聚合推断
7. 交互式 CLI  — 置信度不足时提示用户

每条推断结果附带 source 字段，说明推断依据，便于审查。
"""

import json
import re
import sys
from pathlib import Path

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from constants import (
    PHASE_ORDER,
    PHASE_PATTERNS,
    PHASE_KEYWORDS,
    CHAPTER_PHASE_MAP,
    ACTIVITY_PHASE_MAP,
    FACTION_CATEGORY_PHASE,
    CLUSTER_KEYWORDS,
)
from prts_client import fetch_page_categories as _fetch_page_categories
from shared_utils import setup_logging

logger = setup_logging("phase_inferrer")


def fetch_page_categories(page_title: str) -> list[str]:
    """获取 PRTS 页面的分类标签（委托给 prts_client）"""
    return _fetch_page_categories(page_title)


def fetch_activity_info(page_title: str) -> dict:
    """从 PRTS 活动页面提取 {{活动信息}} 模板数据（委托给 prts_client）"""
    from prts_client import fetch_activity_info as _prts_fetch_activity_info
    return _prts_fetch_activity_info(page_title)


# ──────────────────────────────────────────────
# 推断引擎
# ──────────────────────────────────────────────

class PhaseInferenceResult:
    """时期推断结果，附带推断来源和置信度"""

    def __init__(self, phase: str, source: str, confidence: str = "low"):
        """
        Args:
            phase: 推断的时期 (early/babel/resurrected/unknown)
            source: 推断来源描述
            confidence: 置信度 (high/medium/low)
        """
        self.phase = phase
        self.source = source
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "source": self.source,
            "confidence": self.confidence,
        }


def infer_phase_from_content(text: str) -> PhaseInferenceResult | None:
    """从文本内容推断时期（优先级 1-2）

    Returns:
        PhaseInferenceResult 或 None（无法从内容推断）
    """
    # 优先级 1：精确模式匹配
    for pattern, phase in PHASE_PATTERNS:
        if pattern.search(text):
            return PhaseInferenceResult(phase, f"内容正则匹配: {pattern.pattern}", "high")

    # 优先级 2：关键词匹配
    for phase, keywords in PHASE_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in text]
        if matched:
            return PhaseInferenceResult(phase, f"内容关键词匹配: {', '.join(matched)}", "medium")

    return None


def infer_phase_from_chapter_code(chapter: str) -> PhaseInferenceResult | None:
    """从章节代码推断时期（优先级 5）

    快速路径，仅依赖章节名前缀匹配。
    """
    for ch_key, phase in CHAPTER_PHASE_MAP.items():
        if ch_key in chapter:
            return PhaseInferenceResult(phase, f"章节代码映射: {ch_key} → {phase}", "medium")
    return None


def infer_phase_from_activity_meta(chapter: str) -> PhaseInferenceResult | None:
    """从 PRTS 活动元数据推断时期（优先级 3）

    自动从活动页面提取 {{活动信息}} 模板，匹配活动名称。
    """
    # 先检查已知活动名映射（缓存）
    for activity, phase in ACTIVITY_PHASE_MAP.items():
        if activity in chapter:
            return PhaseInferenceResult(phase, f"活动名称映射: {activity} → {phase}", "medium")

    # 尝试从 PRTS 获取活动信息
    # 从章节代码提取活动名（如 "DM-ST-1 求生/NBT" → 查询 "生于黑夜"）
    # 通常章节页面名中包含活动名，但格式不统一
    # 这里尝试用章节代码前缀查 PRTS 活动页面
    code_match = re.match(r"^([A-Z]+)-", chapter)
    if code_match:
        code_prefix = code_match.group(1)
        # 查询该前缀对应的活动页面
        activity_page = _find_activity_page(code_prefix, chapter)
        if activity_page:
            info = fetch_activity_info(activity_page)
            if info:
                name = info.get("名称缩短", info.get("名称", ""))
                act_type = info.get("类型", "")
                # 缓存结果
                if name and name not in ACTIVITY_PHASE_MAP:
                    inferred = _infer_phase_from_activity_type(name, act_type, info)
                    if inferred:
                        ACTIVITY_PHASE_MAP[name] = inferred.phase
                        return inferred

    return None


def infer_phase_from_operator_categories(operator_name: str) -> PhaseInferenceResult | None:
    """从干员 PRTS 分类标签推断默认时期（优先级 4）

    干员页面的"分类:属于XX的干员"标签可以推断角色的主要时期。
    """
    categories = fetch_page_categories(operator_name)
    for cat in categories:
        if cat in FACTION_CATEGORY_PHASE:
            phase = FACTION_CATEGORY_PHASE[cat]
            return PhaseInferenceResult(
                phase,
                f"PRTS分类标签: '{cat}' → {phase}",
                "medium",
            )

    # 检查是否是干员
    is_operator = any("干员" in c for c in categories)
    if is_operator:
        # 是干员但没有阵营分类 → 默认 early
        return PhaseInferenceResult(
            "early",
            "干员页面无阵营分类，默认 early",
            "low",
        )

    return None


def infer_phase_from_content_cluster(texts: list[str]) -> PhaseInferenceResult | None:
    """从多条对话内容聚类推断时期（优先级 6）

    当其他方法全部失败时，统计对话内容中各时期关键词的频率，
    选择得分最高的时期。
    """
    scores = {phase: 0 for phase in PHASE_ORDER}
    matched_keywords = {phase: [] for phase in PHASE_ORDER}

    for text in texts:
        for phase, keywords in CLUSTER_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[phase] += 1
                    if kw not in matched_keywords[phase]:
                        matched_keywords[phase].append(kw)

    if not any(scores.values()):
        return None

    best_phase = max(scores, key=lambda p: scores[p])
    total = sum(scores.values())
    ratio = scores[best_phase] / total if total > 0 else 0

    confidence = "low"
    if ratio >= 0.6 and scores[best_phase] >= 5:
        confidence = "medium"

    return PhaseInferenceResult(
        best_phase,
        f"内容聚类: {best_phase} ({scores[best_phase]}/{total} 次匹配, "
        f"关键词: {', '.join(matched_keywords[best_phase][:5])})",
        confidence,
    )


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _find_activity_page(code_prefix: str, chapter: str) -> str | None:
    """从章节代码和名称推测活动页面名

    策略：
    1. 从章节名中提取中文活动名（如 "DM-ST-1 求生/NBT" → 无直接活动名）
    2. 用代码前缀查 PRTS（如 "DM" → 查询 DM 系列活动）
    """
    # 代码前缀 → 已知活动页面名映射
    CODE_TO_ACTIVITY = {
        "DM": "生于黑夜",
        "BB": "巴别塔",
        "WD": "遗尘漫步",
        "LT": "伦蒂尼姆",
    }

    if code_prefix in CODE_TO_ACTIVITY:
        return CODE_TO_ACTIVITY[code_prefix]

    # 尝试直接用章节名中的中文部分
    cn_match = re.search(r"[A-Z]+-ST-\d+\s+(.+?)(?:/NBT)?$", chapter)
    if cn_match:
        potential_name = cn_match.group(1).strip()
        # 验证是否是有效的 PRTS 页面
        cats = fetch_page_categories(potential_name)
        if any("支线故事" in c or "主线" in c for c in cats):
            return potential_name

    return None


def _infer_phase_from_activity_type(
    name: str, act_type: str, info: dict
) -> PhaseInferenceResult | None:
    """从活动类型和名称推断时期

    规则：
    - 主线第8-9章 → babel
    - 主线第10+章 → resurrected
    - 主线第0-7章 → early
    - 支线故事 → 需要根据名称关键词判断
    - 纪念活动 → early（通常是复刻）
    """
    # 检查是否主线
    if act_type == "主线" or "主线" in info.get("类型", ""):
        # 从名称中提取章节号
        ch_match = re.search(r"第(\d+)章", name)
        if ch_match:
            ch_num = int(ch_match.group(1))
            if ch_num >= 10:
                return PhaseInferenceResult("resurrected", f"主线第{ch_num}章 → resurrected", "high")
            elif ch_num >= 8:
                return PhaseInferenceResult("babel", f"主线第{ch_num}章 → babel", "high")
            else:
                return PhaseInferenceResult("early", f"主线第{ch_num}章 → early", "high")

    # 支线故事 — 用名称关键词推断
    if "支线故事" in act_type:
        for phase, keywords in CLUSTER_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    return PhaseInferenceResult(
                        phase, f"支线故事名称含'{kw}' → {phase}", "low"
                    )

    return None


# ──────────────────────────────────────────────
# 统一推断入口
# ──────────────────────────────────────────────

def infer_phase(
    text: str,
    chapter: str = "",
    operator_name: str = "",
    all_texts: list[str] | None = None,
    interactive: bool = False,
) -> PhaseInferenceResult:
    """统一时期推断入口

    按优先级依次尝试，返回最高置信度的结果。

    Args:
        text: 单条对话文本
        chapter: 章节/页面名
        operator_name: 干员页面名（用于查 PRTS 分类）
        all_texts: 所有对话文本列表（用于聚类 fallback）
        interactive: 是否启用交互式 CLI fallback

    Returns:
        PhaseInferenceResult
    """
    # 优先级 1-2：内容匹配
    result = infer_phase_from_content(text)
    if result:
        return result

    # 优先级 5：章节代码映射（快速路径，不依赖网络）
    if chapter:
        result = infer_phase_from_chapter_code(chapter)
        if result:
            return result

    # 优先级 3：活动元数据
    if chapter:
        result = infer_phase_from_activity_meta(chapter)
        if result:
            return result

    # 优先级 6：内容聚类 fallback
    if all_texts:
        result = infer_phase_from_content_cluster(all_texts)
        if result:
            return result

    # 优先级 7：交互式 CLI
    if interactive:
        result = _interactive_fallback(text, chapter, operator_name)
        if result:
            return result

    # 最终兜底
    return PhaseInferenceResult("unknown", "所有推断方法均失败", "low")


# ──────────────────────────────────────────────
# 多证据融合推断（升级新增）
# ──────────────────────────────────────────────

# 各证据层级的权重
_EVIDENCE_WEIGHTS = {
    "content_regex": 3.0,      # 正则匹配：最精确
    "content_keyword": 2.0,    # 关键词匹配：较精确
    "activity_meta": 2.0,      # 活动元数据：可靠
    "operator_category": 1.5,  # 分类标签：中等可靠
    "chapter_code": 1.0,       # 章节代码：快速但可能粗糙
    "content_cluster": 0.5,    # 内容聚类：统计推断
}


def infer_phase_ensemble(
    text: str,
    chapter: str = "",
    operator_name: str = "",
    all_texts: list[str] | None = None,
) -> PhaseInferenceResult:
    """多证据融合时期推断

    收集所有层级的推断结果，加权投票选出最可能的时期。
    当多证据一致时，置信度更高。

    权重分配：
    - 正则匹配：3.0（最精确）
    - 关键词匹配：2.0
    - 活动元数据：2.0
    - 分类标签：1.5
    - 章节代码：1.0
    - 内容聚类：0.5

    Args:
        text: 单条对话文本
        chapter: 章节/页面名
        operator_name: 干员页面名
        all_texts: 所有对话文本列表

    Returns:
        PhaseInferenceResult（附带投票详情）
    """
    votes: dict[str, float] = {}  # phase → weighted_score
    evidence: list[dict] = []  # 所有证据记录

    # 证据1：内容正则/关键词匹配
    content_result = infer_phase_from_content(text)
    if content_result:
        weight_key = "content_regex" if "正则" in content_result.source else "content_keyword"
        weight = _EVIDENCE_WEIGHTS[weight_key]
        votes[content_result.phase] = votes.get(content_result.phase, 0) + weight
        evidence.append({
            "source": weight_key,
            "phase": content_result.phase,
            "detail": content_result.source,
            "weight": weight,
        })

    # 证据2：章节代码映射
    if chapter:
        chapter_result = infer_phase_from_chapter_code(chapter)
        if chapter_result:
            weight = _EVIDENCE_WEIGHTS["chapter_code"]
            votes[chapter_result.phase] = votes.get(chapter_result.phase, 0) + weight
            evidence.append({
                "source": "chapter_code",
                "phase": chapter_result.phase,
                "detail": chapter_result.source,
                "weight": weight,
            })

    # 证据3：活动元数据（跳过网络请求，仅用缓存）
    if chapter:
        for activity, phase in ACTIVITY_PHASE_MAP.items():
            if activity in chapter:
                weight = _EVIDENCE_WEIGHTS["activity_meta"]
                votes[phase] = votes.get(phase, 0) + weight
                evidence.append({
                    "source": "activity_meta",
                    "phase": phase,
                    "detail": f"活动名称映射: {activity}",
                    "weight": weight,
                })
                break

    # 证据4：内容聚类
    if all_texts:
        cluster_result = infer_phase_from_content_cluster(all_texts)
        if cluster_result:
            weight = _EVIDENCE_WEIGHTS["content_cluster"]
            votes[cluster_result.phase] = votes.get(cluster_result.phase, 0) + weight
            evidence.append({
                "source": "content_cluster",
                "phase": cluster_result.phase,
                "detail": cluster_result.source,
                "weight": weight,
            })

    # 加权投票
    if not votes:
        return PhaseInferenceResult("unknown", "无证据", "low")

    best_phase = max(votes, key=votes.get)
    total_weight = sum(votes.values())
    best_weight = votes[best_phase]
    ratio = best_weight / total_weight if total_weight > 0 else 0

    # 置信度判断
    if ratio >= 0.6 and best_weight >= 3.0:
        confidence = "high"
    elif ratio >= 0.4 and best_weight >= 2.0:
        confidence = "medium"
    else:
        confidence = "low"

    # 构建来源描述
    vote_summary = ", ".join(f"{p}:{w:.1f}" for p, w in sorted(votes.items(), key=lambda x: -x[1]))
    source_desc = f"多证据融合 [{vote_summary}] → {best_phase}"

    result = PhaseInferenceResult(best_phase, source_desc, confidence)
    result.evidence = evidence  # 附加证据详情
    result.votes = votes  # 附加投票详情

    return result


def infer_default_phase_for_operator(
    operator_name: str,
    operator_data: dict | None = None,
) -> PhaseInferenceResult:
    """推断干员的默认时期（用于语音行标注）

    优先级：
    1. PRTS 分类标签
    2. operator_data 中的阵营信息
    3. 内容聚类（使用语音行内容）
    4. 交互式 CLI

    Args:
        operator_name: 干员页面名（如 "W", "魔王"）
        operator_data: game_data_parser 输出（可选）
    """
    # 优先级 4：PRTS 分类标签
    result = infer_phase_from_operator_categories(operator_name)
    if result and result.confidence != "low":
        return result

    # 备选：从 operator_data 的阵营信息推断
    if operator_data:
        faction = operator_data.get("faction", "") or operator_data.get("所属势力", "")
        if faction:
            faction_lower = faction.strip()
            faction_to_phase = {
                "巴别塔": "babel",
                "罗德岛": "resurrected",
                "整合运动": "early",
                "卡兹戴尔": "early",
            }
            for fkey, phase in faction_to_phase.items():
                if fkey in faction_lower:
                    return PhaseInferenceResult(
                        phase,
                        f"阵营信息: '{faction}' → {phase}",
                        "medium",
                    )

        # 使用语音行内容聚类
        voice_texts = [vl.get("text", "") for vl in operator_data.get("voice_lines", [])]
        if voice_texts:
            result = infer_phase_from_content_cluster(voice_texts)
            if result:
                return result

    # 如果 PRTS 分类给了 low confidence 结果，仍然返回
    if result:
        return result

    return PhaseInferenceResult("unknown", f"无法推断 {operator_name} 的默认时期", "low")


def _interactive_fallback(
    text: str, chapter: str, operator_name: str
) -> PhaseInferenceResult | None:
    """交互式 CLI fallback — 当自动推断全部失败时提示用户"""
    if not sys.stdin.isatty():
        return None

    print(f"\n[时期推断] 无法自动推断时期:")
    print(f"  对话: {text[:50]}...")
    if chapter:
        print(f"  章节: {chapter}")
    if operator_name:
        print(f"  干员: {operator_name}")
    print(f"  可选时期: {', '.join(PHASE_ORDER)}")

    try:
        user_input = input("  请输入时期 (留空=unknown): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if user_input in PHASE_ORDER:
        return PhaseInferenceResult(user_input, "用户手动指定", "high")

    return None


# ──────────────────────────────────────────────
# 推断报告
# ──────────────────────────────────────────────

def generate_inference_report(
    results: list[dict],
) -> dict:
    """生成时期推断报告

    Args:
        results: 推断结果列表，每条包含 phase, source, confidence

    Returns:
        报告 dict，包含统计和建议
    """
    total = len(results)
    by_phase = {}
    by_source = {}
    by_confidence = {}
    unknown_count = 0

    for r in results:
        phase = r.get("phase", "unknown")
        source = r.get("source", "unknown")
        confidence = r.get("confidence", "unknown")

        by_phase[phase] = by_phase.get(phase, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        by_confidence[confidence] = by_confidence.get(confidence, 0) + 1

        if phase == "unknown":
            unknown_count += 1

    unknown_pct = (unknown_count / total * 100) if total > 0 else 0

    # 建议
    suggestions = []
    if unknown_pct > 50:
        suggestions.append(
            f"⚠️  {unknown_pct:.0f}% 的数据时期为 unknown，建议：\n"
            "   1. 检查角色相关活动是否在 CHAPTER_PHASE_MAP 中\n"
            "   2. 运行 context_annotator.py --interactive 启用交互式推断\n"
            "   3. 在 knowledge.md 中补充更详细的时间线"
        )
    if by_confidence.get("low", 0) > total * 0.3:
        suggestions.append(
            f"⚠️  {by_confidence.get('low', 0)} 条推断置信度为 low，"
            "建议审查推断结果"
        )

    return {
        "total_lines": total,
        "phase_distribution": by_phase,
        "source_distribution": by_source,
        "confidence_distribution": by_confidence,
        "unknown_pct": round(unknown_pct, 1),
        "suggestions": suggestions,
    }


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="时期自动推断引擎")
    parser.add_argument(
        "--operator", help="干员名（查询 PRTS 分类推断默认时期）"
    )
    parser.add_argument("--chapter", help="章节名（推断章节时期）")
    parser.add_argument("--text", help="对话文本（推断单条时期）")
    parser.add_argument(
        "--interactive", action="store_true",
        help="启用交互式 fallback"
    )
    parser.add_argument(
        "--context-json", help="context.json 路径（生成推断报告）"
    )
    args = parser.parse_args()

    if args.operator:
        print(f"推断干员 '{args.operator}' 的默认时期...")
        result = infer_default_phase_for_operator(args.operator)
        print(f"  时期: {result.phase}")
        print(f"  来源: {result.source}")
        print(f"  置信度: {result.confidence}")

    if args.chapter:
        print(f"推断章节 '{args.chapter}' 的时期...")
        result = infer_phase("", chapter=args.chapter)
        print(f"  时期: {result.phase}")
        print(f"  来源: {result.source}")
        print(f"  置信度: {result.confidence}")

    if args.text:
        print(f"推断对话时期: '{args.text[:30]}...'")
        result = infer_phase(args.text, chapter=args.chapter or "")
        print(f"  时期: {result.phase}")
        print(f"  来源: {result.source}")
        print(f"  置信度: {result.confidence}")

    if args.context_json:
        with open(args.context_json, encoding="utf-8") as f:
            ctx = json.load(f)
        results = []
        for line in ctx.get("annotated_lines", []):
            results.append({
                "phase": line.get("context", {}).get("phase", "unknown"),
                "source": "existing",
                "confidence": "unknown",
            })
        report = generate_inference_report(results)
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
