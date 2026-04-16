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

# 导入自动推断引擎
try:
    from phase_inferrer import (
        infer_phase_from_content,
        infer_default_phase_for_operator,
        infer_phase_from_content_cluster,
        generate_inference_report,
        PhaseInferenceResult,
    )
    HAS_PHASE_INFERRER = True
except ImportError:
    HAS_PHASE_INFERRER = False


# ──────────────────────────────────────────────
# 语音行对话对象推断
# ──────────────────────────────────────────────

VOICE_INTERLOCUTOR_MAP = {
    "信赖触摸": "博士",
    "晋升后交谈1": "博士",
    "晋升后交谈2": "博士",
    "精二晋升后交谈": "博士",
    "任命助理": "博士",
    "4星结束": None,
    "3星结束": None,
}

# 语音标题 → 场景类型
# 注意：按特异性从高到低排列，首次匹配即停止
# 例如 "晋升后交谈1" 应匹配 "晋升"→casual 而非 "交谈"→casual
VOICE_SITUATION_MAP = [
    ("信赖触摸", "comfort"),
    ("信赖", "comfort"),
    ("战斗开始", "confront"),
    ("战斗失败", "confront"),
    ("精二晋升后交谈", "casual"),   # 必须在"晋升后交谈"之前，否则"精二晋升后交谈1"被误匹配
    ("晋升后交谈", "casual"),
    ("晋升", "casual"),
    ("助理", "casual"),
    ("交谈", "casual"),
    ("进驻", "casual"),
    ("编入", "casual"),
    ("精英化", "casual"),
]

# 语音内容 → 时期推断关键词
# 注意：使用更精确的词组避免误匹配（"和平"→"和平协议"，"魔王"→需同时含卡兹戴尔语境）
# 优先从 phase_inferrer import，本地定义仅作离线 fallback
if HAS_PHASE_INFERRER:
    from phase_inferrer import PHASE_KEYWORDS, PHASE_PATTERNS
else:
    PHASE_KEYWORDS = {
        "babel": ["巴别塔", "内战", "卡兹戴尔重建", "和平协议", "卡兹戴尔的和平"],
        "resurrected": ["黑冠", "赦罪师", "巫术"],
    }

    PHASE_PATTERNS = [
        (re.compile(r"魔王.{0,10}(?:卡兹戴尔|回归|归来)"), "babel"),
        (re.compile(r"(?:复活|苏醒|重获).{0,10}(?:身体|力量|记忆)"), "resurrected"),
    ]

# 干员页面名 → 语音行默认时期（快速路径 / 离线缓存）
# 优先使用 phase_inferrer 自动推断；此表仅作为离线 fallback 和已知结果的缓存
# 新增角色时无需手动添加 — phase_inferrer 会从 PRTS 分类标签自动推断
OPERATOR_DEFAULT_PHASE = {
    "魔王": "resurrected",    # Civilight Eterna = 复活后特蕾西娅
    "W": "early",            # W 的语音行默认为早期（切尔诺伯格/整合运动时期）
}

# 自动推断缓存（运行时填充，避免重复查询 PRTS）
_auto_inferred_phases: dict[str, PhaseInferenceResult] = {}

# 时间线正则（从 knowledge.md 提取）
TIMELINE_RE = re.compile(r'###\s*(\d{3,4})\s*[-–—]\s*(\d{3,4})\s*(.+)')


# ──────────────────────────────────────────────
# 安全工具
# ──────────────────────────────────────────────

# 允许读取的目录前缀（白名单）
_ALLOWED_PATH_PREFIXES = [
    str(Path.cwd()),
    str(Path.home()),
    "/tmp",
]


def _validate_path(path: str) -> str:
    """验证文件路径是否在允许范围内，防止路径遍历攻击"""
    resolved = Path(path).resolve()
    # 检查路径是否在允许的目录内
    for prefix in _ALLOWED_PATH_PREFIXES:
        if str(resolved).startswith(prefix):
            return str(resolved)
    raise ValueError(
        f"安全限制：路径 '{path}' 不在允许的目录内。"
        f"允许的目录: {', '.join(_ALLOWED_PATH_PREFIXES)}"
    )


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
    """从 knowledge.md 中提取时间线定义"""
    try:
        safe_path = _validate_path(knowledge_path)
        text = Path(safe_path).read_text(encoding='utf-8')
    except FileNotFoundError:
        return []

    timeline = []
    for match in TIMELINE_RE.finditer(text):
        timeline.append({
            "id": match.group(3).strip().replace(" ", "_").lower(),
            "label": match.group(3).strip(),
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
# 构建语境化数据
# ──────────────────────────────────────────────

def _get_default_phase(operator_name: str, operator_data: dict = None) -> str:
    """获取干员的默认时期

    推断优先级：
    1. OPERATOR_DEFAULT_PHASE 缓存（快速路径，离线可用）
    2. phase_inferrer 自动推断（PRTS 分类标签 + 阵营信息 + 内容聚类）
    """
    # 快速路径：已有缓存
    if operator_name in OPERATOR_DEFAULT_PHASE:
        return OPERATOR_DEFAULT_PHASE[operator_name]

    # 自动推断
    if HAS_PHASE_INFERRER:
        if operator_name not in _auto_inferred_phases:
            result = infer_default_phase_for_operator(operator_name, operator_data)
            _auto_inferred_phases[operator_name] = result
            # 缓存到 OPERATOR_DEFAULT_PHASE 供后续使用
            if result.phase != "unknown":
                OPERATOR_DEFAULT_PHASE[operator_name] = result.phase
                print(f"[context_annotator] 自动推断: {operator_name} → {result.phase} "
                      f"(来源: {result.source}, 置信度: {result.confidence})",
                      file=sys.stderr)
        return _auto_inferred_phases[operator_name].phase

    return "unknown"


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
        if isinstance(archive, dict):
            text = archive.get("text", "")
        else:
            text = str(archive)
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

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

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
