#!/usr/bin/env python3
"""
语境标注器 — 将所有原始数据统一标注为语境化数据模型

这是整个升级架构的枢纽组件。它把 game_data_parser 的档案数据、
story_extractor 的剧情数据、语音数据合并，统一标注后输出 context.json。

下游所有工具（fingerprint / relationship / speech_act / temporal_slicer）
都消费这一份标注数据，不再各自处理原始文本。

用法：
    # 基本用法：合并 PRTS 数据 + 剧情数据
    python3 context_annotator.py \
      --operator-json /tmp/operator_data.json \
      --knowledge-md operators/te-lei-xi-ya/knowledge.md \
      --output operators/te-lei-xi-ya/context.json

    # 加入剧情数据
    python3 context_annotator.py \
      --operator-json /tmp/operator_data.json \
      --story-json /tmp/story_ch8.json --story-json /tmp/story_ch10.json \
      --knowledge-md operators/te-lei-xi-ya/knowledge.md \
      --output operators/te-lei-xi-ya/context.json

输出：context.json（语境化数据模型，详见文档）
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

from constants import (
    OPERATOR_DEFAULT_PHASE,
    PHASE_KEYWORDS,
    PHASE_LABEL_MAP,
    PHASE_PATTERNS,
    TIMELINE_RE,
    VOICE_INTERLOCUTOR_MAP,
    VOICE_SITUATION_MAP,
)
from shared_utils import (
    atomic_write_json,
    setup_logging,
    validate_context,
    validate_path,
)

logger = setup_logging("context_annotator")

# 导入自动推断引擎（可选依赖：缺失时退化为基础时期推断）
try:
    from phase_inferrer import (
        PhaseInferenceResult,  # noqa: F401  (re-exported for downstream consumers)
        generate_inference_report,
        infer_default_phase_for_operator,
        infer_phase_from_content,
        infer_phase_from_content_cluster,
    )
    HAS_PHASE_INFERRER = True
except ImportError:
    HAS_PHASE_INFERRER = False

# 自动推断缓存（使用 lru_cache 限制大小，避免重复查询 PRTS）
from functools import lru_cache as _lru_cache

# ──────────────────────────────────────────────
# 安全工具（委托给 shared_utils）
# ──────────────────────────────────────────────


def _validate_path(path: str) -> str:
    """验证文件路径是否在允许范围内，防止路径遍历攻击"""
    return validate_path(path)


# ──────────────────────────────────────────────
# 加载函数
# ──────────────────────────────────────────────

def load_operator_data(path: str) -> dict:
    """加载 game_data_parser 的输出"""
    safe_path = _validate_path(path)
    with open(safe_path, encoding='utf-8') as f:
        return json.load(f)


def load_story_data(path: str) -> list[dict]:
    """加载 story_extractor 的输出"""
    safe_path = _validate_path(path)
    with open(safe_path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get("dialogues", [])


def load_timeline(knowledge_path: str) -> list[dict]:
    """从 knowledge.md 中提取时间线定义

    使用 PHASE_LABEL_MAP 将中文时期标签（如"早期"、"巴别塔时期"）映射为
    规范化英文 id（如 "early"、"babel"），确保 timeline[].id 与
    annotated_lines[].context.phase 值一致，使下游 temporal_slicer 的
    跨期比较能正确匹配。
    """
    try:
        safe_path = _validate_path(knowledge_path)
        text = Path(safe_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return []

    timeline = []
    for match in TIMELINE_RE.finditer(text):
        label = match.group(3).strip()
        # 通过 PHASE_LABEL_MAP 将中文标签映射为英文 id
        phase_id = PHASE_LABEL_MAP.get(label, label.replace(" ", "_").lower())
        timeline.append({
            "id": phase_id,
            "label": label,
            "range": f"{match.group(1)}-{match.group(2)}",
            "summary": ""
        })

    # 如果 knowledge.md 没有标准时间线格式，提供默认分期
    if not timeline:
        timeline = [
            {"id": "early", "label": "早期", "range": "893-1072", "summary": "成长与加冕"},
            {"id": "babel", "label": "巴别塔时期", "range": "1072-1094", "summary": "巴别塔创建与内战"},
            {"id": "resurrected", "label": "复活后", "range": "1094后", "summary": "被赦罪师复活"},
        ]

    return timeline


# ──────────────────────────────────────────────
# 标注函数
# ──────────────────────────────────────────────

def annotate_voice_line(line: dict, index: int, default_phase: str = "unknown",
                        all_voice_texts: list[str] | None = None) -> dict:
    """标注单条语音行

    Args:
        default_phase: 当内容无法推断时期时使用的默认时期
            优先使用 phase_inferrer 自动推断
        all_voice_texts: 所有语音行文本（用于内容聚类 fallback）
    """
    # game_data_parser 输出字段名为 "label"，兼容旧格式 "title"
    title = line.get("label") or line.get("title", "")
    text = line.get("text", "")

    # 推断对话对象
    interlocutor = None
    for key, val in VOICE_INTERLOCUTOR_MAP.items():
        if key in title:
            interlocutor = val
            break

    # 推断场景类型（按特异性从高到低匹配）
    situation = "casual"
    for key, sit_type in VOICE_SITUATION_MAP:
        if key in title:
            situation = sit_type
            break

    # 推断时期 — 多层级推断链
    phase = "unknown"
    inference_source = "unknown"
    inference_confidence = "low"

    # 层级 1-2：内容匹配（正则 → 关键词）
    if HAS_PHASE_INFERRER:
        result = infer_phase_from_content(text)
        if result:
            phase = result.phase
            inference_source = result.source
            inference_confidence = result.confidence

    # fallback：使用原有逻辑（兼容无 phase_inferrer 的场景）
    if phase == "unknown":
        for pattern, phase_id in PHASE_PATTERNS:
            if pattern.search(text):
                phase = phase_id
                inference_source = "本地正则匹配"
                inference_confidence = "high"
                break
    if phase == "unknown":
        for phase_id, keywords in PHASE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                phase = phase_id
                inference_source = "本地关键词匹配"
                inference_confidence = "medium"
                break

    # 层级 6：内容聚类 fallback（仅当内容匹配和默认时期都失败时）
    if phase == "unknown" and HAS_PHASE_INFERRER and all_voice_texts:
        result = infer_phase_from_content_cluster(all_voice_texts)
        if result:
            phase = result.phase
            inference_source = result.source
            inference_confidence = result.confidence

    # 最终回退到默认时期
    if phase == "unknown" and default_phase != "unknown":
        phase = default_phase
        inference_source = f"默认时期({default_phase})"
        inference_confidence = "medium"

    result = {
        "id": f"V{index:03d}",
        "text": text,
        "source": "voice",
        "source_detail": title,
        "context": {
            "phase": phase,
            "scene": title,
            "interlocutor": interlocutor,
            "preceding_event": "",
            "situation_type": situation,
        },
        "speech_acts": [],    # 由 speech_act_analyzer 填充
        "emotion": {},        # 由情感分析填充
    }
    # 内部字段：推断记录（不输出到最终 JSON，仅用于报告）
    result["_inference_source"] = inference_source
    result["_inference_confidence"] = inference_confidence
    return result


def annotate_story_line(line: dict, index: int) -> dict:
    """标注单条剧情对话行"""
    return {
        "id": f"S{index:03d}",
        "text": line.get("text", ""),
        "source": "story",
        "source_detail": line.get("scene", ""),
        "context": {
            "phase": line.get("phase", "unknown"),
            "scene": line.get("scene", ""),
            "interlocutor": line.get("reply_to"),
            "preceding_event": "",
            "situation_type": line.get("situation_type", "casual"),
        },
        "narration": line.get("narration", []),
        "speech_acts": [],
        "emotion": {},
    }


def annotate_archive_text(archive_text: str, index: int) -> dict:
    """标注档案段落（作为背景知识，不参与对话分析）"""
    return {
        "id": f"A{index:03d}",
        "text": archive_text,
        "source": "archive",
        "source_detail": f"档案#{index + 1}",
        "context": {
            "phase": "unknown",
            "scene": "档案",
            "interlocutor": None,
            "preceding_event": "",
            "situation_type": "casual",
        },
        "speech_acts": [],
        "emotion": {},
    }


# ──────────────────────────────────────────────
# 场景分类增强（升级新增）
# ──────────────────────────────────────────────

# 内容级场景关键词
_CONTENT_SITUATION_KEYWORDS = {
    "battle": ["战斗", "出击", "敌人", "进攻", "防守", "战场", "武器", "源石技艺"],
    "intimate": ["休息", "夜晚", "安静", "星空", "月光", "独处", "私密"],
    "farewell": ["告别", "再见", "离开", "永别", "最后一面", "送别"],
    "confrontation": ["对峙", "质问", "背叛", "敌人", "对立", "冲突"],
    "comfort": ["安慰", "别怕", "没事", "我在", "陪伴", "守护"],
    "reflection": ["回忆", "过去", "曾经", "记忆", "往事", "思考"],
}


def classify_situation_v2(
    title: str,
    text: str,
    interlocutor: str | None = None,
) -> str:
    """多信号场景分类

    信号源：
    1. 语音标题关键词（现有 VOICE_SITUATION_MAP）
    2. 对话内容情感（新增）
    3. 对话对象（新增）

    使用多数投票融合多信号。

    Args:
        title: 语音标题
        text: 对话文本
        interlocutor: 对话对象

    Returns:
        场景类型字符串
    """
    signals: dict[str, str] = {}

    # 信号 1：标题匹配（现有逻辑）
    for key, sit_type in VOICE_SITUATION_MAP:
        if key in title:
            signals["title"] = sit_type
            break

    # 信号 2：内容关键词
    content_scores: dict[str, int] = {}
    for sit_type, keywords in _CONTENT_SITUATION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            content_scores[sit_type] = score

    if content_scores:
        best_content_sit = max(content_scores, key=content_scores.get)
        signals["content"] = best_content_sit

    # 信号 3：对话对象
    if interlocutor:
        if interlocutor in ["博士", "Doctor"]:
            signals["interlocutor"] = "trust"  # 对博士通常是信任场景
        elif interlocutor in ["敌人", "整合运动"]:
            signals["interlocutor"] = "confrontation"

    # 融合：多数投票
    if signals:
        from collections import Counter
        vote_counts = Counter(signals.values())
        # 标题信号权重更高
        if "title" in signals:
            return signals["title"]
        return vote_counts.most_common(1)[0][0]

    return "casual"


# ──────────────────────────────────────────────
# 对话对象内容推断（升级新增）
# ──────────────────────────────────────────────

def infer_interlocutor_from_content(
    text: str,
    known_characters: list[str] | None = None,
) -> str | None:
    """从对话内容推断说话对象

    线索：
    - 直接称呼："博士，你来了" → 对象是博士
    - 第二人称 + 已知角色名

    Args:
        text: 对话文本
        known_characters: 已知角色名列表

    Returns:
        推断的对话对象，或 None
    """
    if known_characters is None:
        known_characters = ["博士", "Doctor", "凯尔希", "阿米娅", "W", "特雷西斯"]

    for char in known_characters:
        if char in text and len(char) >= 2:
            # 检查是否是称呼而非提及
            patterns = [
                rf"^{char}[，,]",          # "博士，..."
                rf"{char}[。！？]",         # "...博士。"
                rf"(你|您).{{0,5}}{char}",  # "你就是博士"
                rf"{char}[,，]\s*",         # "博士，"
            ]
            if any(re.search(p, text) for p in patterns):
                return char

    return None


# ──────────────────────────────────────────────
# 构建语境化数据
# ──────────────────────────────────────────────

@_lru_cache(maxsize=128)
def _infer_phase_cached(operator_name: str) -> str:
    """通过 phase_inferrer 推断干员默认时期（带 LRU 缓存）

    仅缓存 operator_name → phase 字符串，避免存储完整 PhaseInferenceResult。
    缓存上限 128 条，超出时淘汰最久未使用的条目。
    """
    if not HAS_PHASE_INFERRER:
        return "unknown"
    result = infer_default_phase_for_operator(operator_name)
    if result.phase != "unknown":
        OPERATOR_DEFAULT_PHASE[operator_name] = result.phase
        logger.info("自动推断: %s → %s (来源: %s, 置信度: %s)",
                     operator_name, result.phase, result.source, result.confidence)
    return result.phase


def _get_default_phase(operator_name: str, operator_data: dict = None) -> str:
    """获取干员的默认时期

    推断优先级：
    1. OPERATOR_DEFAULT_PHASE 缓存（快速路径，离线可用）
    2. phase_inferrer 自动推断（PRTS 分类标签 + 阵营信息 + 内容聚类，带 lru_cache）
    """
    # 快速路径：已有缓存
    if operator_name in OPERATOR_DEFAULT_PHASE:
        return OPERATOR_DEFAULT_PHASE[operator_name]

    # 自动推断（带 lru_cache，上限 128 条）
    return _infer_phase_cached(operator_name)


def build_context_json(
    operator_data: dict,
    story_data_list: list[list[dict]],
    timeline: list[dict],
    interactive: bool = False,
) -> dict:
    """构建完整的 context.json"""
    annotated_lines = []
    inference_results = []  # 推断记录，用于生成报告

    # 确定语音行的默认时期（自动推断）
    operator_name = operator_data.get("name_zh") or operator_data.get("name", "")
    default_phase = _get_default_phase(operator_name, operator_data)

    # 收集所有语音行文本，用于内容聚类 fallback
    voice_texts = [vl.get("text", "") for vl in operator_data.get("voice_lines", [])]

    # 1. 标注语音
    for i, vl in enumerate(operator_data.get("voice_lines", [])):
        result = annotate_voice_line(vl, i, default_phase, voice_texts)
        annotated_lines.append(result)
        inference_results.append({
            "id": result["id"],
            "phase": result["context"]["phase"],
            "source": result.get("_inference_source", "default"),
            "confidence": result.get("_inference_confidence", "unknown"),
        })

    # 2. 标注剧情对话
    story_idx = 0
    for story_data in story_data_list:
        for line in story_data:
            if line.get("is_target"):
                result = annotate_story_line(line, story_idx)
                annotated_lines.append(result)
                story_idx += 1

    # 3. 标注档案段落
    for i, archive in enumerate(operator_data.get("archives", [])):
        text = archive.get("text", "") if isinstance(archive, dict) else str(archive)
        if text:
            annotated_lines.append(annotate_archive_text(text, i))

    # 统计
    source_dist = {}
    phase_dist = {}
    situation_dist = {}
    for line in annotated_lines:
        src = line["source"]
        source_dist[src] = source_dist.get(src, 0) + 1

        phase = line["context"]["phase"]
        if line["source"] != "archive":  # 档案不参与时期统计
            phase_dist[phase] = phase_dist.get(phase, 0) + 1

        sit = line["context"]["situation_type"]
        situation_dist[sit] = situation_dist.get(sit, 0) + 1

    # 生成推断报告
    inference_report = generate_inference_report(inference_results) if HAS_PHASE_INFERRER else None

    return {
        "character": operator_data.get("name_zh") or operator_data.get("name", ""),
        "slug": operator_data.get("slug", ""),
        "source_url": operator_data.get("source_url", ""),
        "page_type": operator_data.get("page_type", ""),
        "timeline": timeline,
        "annotated_lines": annotated_lines,
        "annotated_relations": [],  # 由升级后的 relationship_graph 填充
        "inference_report": inference_report,
        "stats": {
            "total_lines": len(annotated_lines),
            "source_distribution": source_dist,
            "phase_distribution": phase_dist,
            "situation_distribution": situation_dist,
        },
    }


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="语境标注器")
    parser.add_argument(
        "--operator-json", required=True,
        help="game_data_parser 的输出 JSON 路径"
    )
    parser.add_argument(
        "--story-json", action="append", default=[],
        help="story_extractor 的输出 JSON 路径（可多次指定）"
    )
    parser.add_argument(
        "--knowledge-md", required=True,
        help="knowledge.md 路径（用于提取时间线）"
    )
    parser.add_argument("--output", required=True, help="输出 context.json 路径")
    parser.add_argument(
        "--interactive", action="store_true",
        help="启用交互式时期推断（当自动推断失败时提示用户）"
    )
    args = parser.parse_args()

    operator_data = load_operator_data(args.operator_json)
    story_data_list = [load_story_data(p) for p in args.story_json]
    timeline = load_timeline(args.knowledge_md)

    context = build_context_json(operator_data, story_data_list, timeline,
                                interactive=args.interactive)

    # 清理内部字段（不输出到最终 JSON）
    for line in context["annotated_lines"]:
        line.pop("_inference_source", None)
        line.pop("_inference_confidence", None)

    # 添加 schema 版本号
    context["schema_version"] = "1.0.0"

    # 写入前进行 schema 校验
    validation_errors = validate_context(context)
    if validation_errors:
        for err in validation_errors:
            print(f"schema 验证错误: {err}", file=sys.stderr)
        print(f"警告：context.json 存在 {len(validation_errors)} 项 schema 验证错误", file=sys.stderr)

    atomic_write_json(args.output, context)

    output_summary = {
        "success": True,
        "total_lines": context["stats"]["total_lines"],
        "source_distribution": context["stats"]["source_distribution"],
        "phase_distribution": context["stats"]["phase_distribution"],
        "timeline_phases": len(context["timeline"]),
        "output": args.output,
    }

    # 添加推断报告摘要
    if context.get("inference_report"):
        report = context["inference_report"]
        output_summary["inference_report"] = {
            "unknown_pct": report["unknown_pct"],
            "confidence_distribution": report["confidence_distribution"],
        }
        if report["suggestions"]:
            output_summary["inference_suggestions"] = report["suggestions"]

    print(json.dumps(output_summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
