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
    ("晋升后交谈", "casual"),
    ("精二晋升后交谈", "casual"),
    ("晋升", "casual"),
    ("助理", "casual"),
    ("交谈", "casual"),
    ("进驻", "casual"),
    ("编入", "casual"),
    ("精英化", "casual"),
]

# 语音内容 → 时期推断关键词
# 注意：使用更精确的词组避免误匹配（"和平"→"和平协议"，"魔王"→需同时含卡兹戴尔语境）
PHASE_KEYWORDS = {
    "babel": ["巴别塔", "内战", "卡兹戴尔重建", "和平协议", "卡兹戴尔的和平"],
    "resurrected": ["黑冠", "赦罪师", "巫术"],
}

# 语音内容 → 时期推断（精确匹配模式，优先级高于关键词包含）
PHASE_PATTERNS = [
    (re.compile(r"魔王.{0,10}(?:卡兹戴尔|回归|归来)"), "babel"),
    (re.compile(r"(?:复活|苏醒|重获).{0,10}(?:身体|力量|记忆)"), "resurrected"),
]

# 时间线正则（从 knowledge.md 提取）
TIMELINE_RE = re.compile(r'###\s*(\d{3,4})\s*[-–—]\s*(\d{3,4})\s*(.+)')


# ──────────────────────────────────────────────
# 加载函数
# ──────────────────────────────────────────────

def load_operator_data(path: str) -> dict:
    """加载 game_data_parser 的输出"""
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_story_data(path: str) -> list[dict]:
    """加载 story_extractor 的输出"""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get("dialogues", [])


def load_timeline(knowledge_path: str) -> list[dict]:
    """从 knowledge.md 中提取时间线定义"""
    try:
        text = Path(knowledge_path).read_text(encoding='utf-8')
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

def annotate_voice_line(line: dict, index: int) -> dict:
    """标注单条语音行"""
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

    # 推断时期
    phase = "unknown"
    # 优先使用精确模式匹配
    for pattern, phase_id in PHASE_PATTERNS:
        if pattern.search(text):
            phase = phase_id
            break
    # 退而使用关键词包含
    if phase == "unknown":
        for phase_id, keywords in PHASE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                phase = phase_id
                break

    return {
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

def build_context_json(
    operator_data: dict,
    story_data_list: list[list[dict]],
    timeline: list[dict],
) -> dict:
    """构建完整的 context.json"""
    annotated_lines = []

    # 1. 标注语音
    for i, vl in enumerate(operator_data.get("voice_lines", [])):
        annotated_lines.append(annotate_voice_line(vl, i))

    # 2. 标注剧情对话
    story_idx = 0
    for story_data in story_data_list:
        for line in story_data:
            if line.get("is_target"):
                annotated_lines.append(annotate_story_line(line, story_idx))
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

    return {
        "character": operator_data.get("name_zh") or operator_data.get("name", ""),
        "slug": operator_data.get("slug", ""),
        "source_url": operator_data.get("source_url", ""),
        "page_type": operator_data.get("page_type", ""),
        "timeline": timeline,
        "annotated_lines": annotated_lines,
        "annotated_relations": [],  # 由升级后的 relationship_graph 填充
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
    args = parser.parse_args()

    operator_data = load_operator_data(args.operator_json)
    story_data_list = [load_story_data(p) for p in args.story_json]
    timeline = load_timeline(args.knowledge_md)

    context = build_context_json(operator_data, story_data_list, timeline)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(context, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "success": True,
        "total_lines": context["stats"]["total_lines"],
        "source_distribution": context["stats"]["source_distribution"],
        "phase_distribution": context["stats"]["phase_distribution"],
        "timeline_phases": len(context["timeline"]),
        "output": args.output,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
