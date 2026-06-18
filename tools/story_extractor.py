#!/usr/bin/env python3
"""
剧情提取器 — 从 PRTS Wiki 剧情页面提取结构化对话

当前 game_data_parser 只能拿到档案和语音，拿不到剧情对话。
这是还原度瓶颈的最大单一来源——角色最鲜活的展现就在剧情中。

PRTS 剧情页面有两种格式：
  1. Wikitext 对话格式：'''角色名'''：台词（旧版剧情）
  2. 剧情模拟器脚本格式：[name="角色名"]对话内容（新版活动如 BB/巴别塔）

剧情页面结构：
  - 活动页（如"巴别塔"）列出关卡链接
  - 关卡页（如"BB-ST-1"）→ redirect → "BB-ST-1 未完成的告别"
  - 剧情 NBT 子页面："BB-ST-1 未完成的告别/NBT" 包含对话脚本

用法：
    # 提取指定关卡/剧情页面中某角色的对话
    python3 story_extractor.py --chapter "BB-ST-3 灵魂尽头/NBT" --character 特蕾西娅

    # 提取多个页面
    python3 story_extractor.py --chapter "BB-ST-1 未完成的告别/NBT" --chapter "BB-ST-3 灵魂尽头/NBT" --character 特蕾西娅

    # 指定输出文件
    python3 story_extractor.py --chapter "BB-9/NBT" --character 特蕾西娅 --output /tmp/story.json

输出：JSON，包含该角色在指定章节中的所有对话，带场景与时期标注
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
    CHAPTER_PHASE_MAP,
    ACTIVITY_PHASE_MAP,
    SITUATION_KEYWORDS,
    SCENE_HEADER_RE,
    WIKITEXT_DIALOGUE_RE,
    SCRIPT_DIALOGUE_RE,
)
from prts_client import fetch_page_wikitext
from shared_utils import setup_logging

logger = setup_logging("story_extractor")

# 导入自动推断引擎
try:
    from phase_inferrer import (
        infer_phase as _infer_phase_auto,
        infer_phase_from_chapter_code,
        infer_phase_from_activity_meta,
    )
    HAS_PHASE_INFERRER = True
except ImportError:
    HAS_PHASE_INFERRER = False

# 剧情模拟器脚本中的叙述行（不带 name= 的纯文本行）
# 格式：直接在 [dialog] 或 [Delay] 之间出现的中文文本
SCRIPT_NARRATION_RE = re.compile(r'^[^\[\]{|}<>/]+$', re.MULTILINE)

# 括号内动作/神态
NARRATION_RE = re.compile(r'[（(](.+?)[）)]')

# 脚本中的舞台指令（需要跳过的行）
SCRIPT_DIRECTIVE_RE = re.compile(
    r'^\s*\['
    r'(?!name=)'
    r'|^\s*\{\{'
    r'|^\s*\|'
    r'|^\s*<'
    r'|^\s*$',
    re.MULTILINE,
)

# 需要从对话文本中清洗的脚本标记
SCRIPT_NOISE_RE = re.compile(
    r'\[charslot[^\]]*\]|\[Camera[^\]]*\]|\[Image[^\]]*\]|\[Background[^\]]*\]'
    r'|\[PlaySound[^\]]*\]|\[playsound[^\]]*\]|\[playMusic[^\]]*\]'
    r'|\[stopmusic\]|\[StopMusic[^\]]*\]|\[SoundVolume[^\]]*\]'
    r'|\[Blocker[^\]]*\]|\[Delay[^\]]*\]|\[dialog\]|\[Dialog\]'
    r'|\[Decision[^\]]*\]|\[Predicate[^\]]*\]|\[PredicateReferences[^\]]*\]'
    r'|\[HEADER[^\]]*\]|\[Sticker[^\]]*\]|\[subtitle[^\]]*\]'
    r'|\[showitem[^\]]*\]|\[Hideitem[^\]]*\]'
    r'|\[character[^\]]*\]|\[Character[^\]]*\]'
    r'|\[action[^\]]*\]|\[MoveScreen[^\]]*\]'
    r'|\[PlayMusic[^\]]*\]|\[StopMusic[^\]]*\]'
    r'|\[soundchannel[^\]]*\]|\[SoundChannel[^\]]*\]'
    r'|\[delay[^\]]*\]|\[Delay[^\]]*\]'
)


# ──────────────────────────────────────────────
# PRTS API（直接使用 prts_client 统一客户端）
# ──────────────────────────────────────────────

def fetch_chapter_wikitext(chapter: str, _depth: int = 0) -> str:
    """获取剧情页面的 wikitext 原文，自动跟随 redirect
    
    使用 prts_client.fetch_page_wikitext 统一处理重试和速率限制。
    """
    if _depth > 3:
        logger.error("重定向链太深: '%s'", chapter)
        return ""
    
    # 使用统一的 prts_client（含重试和速率限制）
    wikitext = fetch_page_wikitext(chapter, follow_redirects=True)

    # 如果内容为空，尝试查找 /NBT 子页面
    if not wikitext:
        # 尝试 chapter/NBT
        nbt_page = f"{chapter}/NBT"
        nbt_wikitext = fetch_page_wikitext(nbt_page, follow_redirects=True)
        if nbt_wikitext:
            logger.info("自动切换到 NBT 子页面: '%s'", nbt_page)
            return nbt_wikitext

        logger.warning("页面 '%s' 内容为空或不存在（也尝试了 /NBT 子页面）", chapter)

    return wikitext


# ──────────────────────────────────────────────
# 对话提取
# ──────────────────────────────────────────────

def extract_dialogues(wikitext: str, character: str) -> list[dict]:
    """
    从 wikitext 中提取指定角色的对话，带场景标注

    自动检测页面格式：
    - 优先尝试剧情模拟器脚本格式 [name="角色名"]对话内容
    - 回退到 wikitext 对话格式 '''角色名'''：台词

    返回结构：
    [
        {
            "speaker": "特蕾西娅",
            "text": "......我在。",
            "narration": ["目光柔和"],
            "scene": "罗德岛走廊",
            "is_target": True,
            "reply_to": "博士"
        },
        ...
    ]
    """
    # 检测页面格式
    has_script_format = '[name="' in wikitext
    has_wikitext_format = bool(WIKITEXT_DIALOGUE_RE.search(wikitext))

    if has_script_format:
        results = _extract_script_dialogues(wikitext, character)
    elif has_wikitext_format:
        results = _extract_wikitext_dialogues(wikitext, character)
    else:
        # 尝试两种格式
        results = _extract_script_dialogues(wikitext, character)
        if not results:
            results = _extract_wikitext_dialogues(wikitext, character)

    # 后处理：标注对话对象（相邻行关系）
    for i in range(1, len(results)):
        prev = results[i - 1]
        curr = results[i]
        # 如果上一行是目标角色，当前行是对别人的回复
        if prev["is_target"] and not curr["is_target"]:
            prev["reply_to"] = curr["speaker"]
        # 如果当前行是目标角色，上一行是对目标角色说话的人
        if curr["is_target"] and not prev["is_target"]:
            curr["reply_to"] = prev["speaker"]

    return results


def _extract_script_dialogues(wikitext: str, character: str) -> list[dict]:
    """
    从剧情模拟器脚本格式中提取对话

    格式: [name="角色名"]对话内容（直到下一个 [name= 或脚本指令）
    """
    results = []
    current_scene = "未标注场景"

    # 先提取场景标题（== 标题 == 格式）
    scene_map = {}
    for m in SCENE_HEADER_RE.finditer(wikitext):
        pos = m.start()
        title = m.group(1).strip()
        # 跳过空标题或仅含等号/空白的标题
        if not title or re.match(r'^[=\s]+$', title):
            continue
        scene_map[pos] = title

    # 提取 [name="xxx"] 对话行
    for m in SCRIPT_DIALOGUE_RE.finditer(wikitext):
        speaker = m.group(1).strip()
        raw_text = m.group(2).strip()

        # 清洗脚本噪声
        text = SCRIPT_NOISE_RE.sub('', raw_text)
        # 清洗换行和多余空白
        text = re.sub(r'\n+', '\n', text).strip()
        # 清洗括号内动作描写
        narrations = NARRATION_RE.findall(text)
        text = NARRATION_RE.sub('', text).strip()
        # 去除残留的脚本片段
        text = re.sub(r'\[.*?\]', '', text).strip()
        # 去除空行
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        if not text:
            continue

        # 确定当前场景
        pos = m.start()
        current_scene = "未标注场景"
        for scene_pos, scene_title in sorted(scene_map.items()):
            if scene_pos <= pos:
                current_scene = scene_title
            else:
                break

        results.append({
            "speaker": speaker,
            "text": text,
            "narration": narrations,
            "scene": current_scene,
            "is_target": speaker == character,
            "reply_to": None,
        })

    return results


def _extract_wikitext_dialogues(wikitext: str, character: str) -> list[dict]:
    """
    从 wikitext 对话格式中提取对话（旧版格式）

    格式: '''角色名'''：台词
    """
    results = []
    current_scene = "未标注场景"

    for line in wikitext.split('\n'):
        line_stripped = line.strip()

        # 检测场景标题
        scene_match = SCENE_HEADER_RE.match(line_stripped)
        if scene_match:
            current_scene = scene_match.group(1).strip()
            # 跳过空标题或仅含等号/空白的标题
            if not current_scene or re.match(r'^[=\s]+$', current_scene):
                continue
            continue

        # 检测对话行
        diag_match = WIKITEXT_DIALOGUE_RE.match(line_stripped)
        if diag_match:
            speaker = diag_match.group(1).strip()
            text = diag_match.group(2).strip()

            # 提取括号内动作描写
            narrations = NARRATION_RE.findall(text)
            clean_text = NARRATION_RE.sub('', text).strip()

            # 过滤空文本
            if not clean_text:
                continue

            results.append({
                "speaker": speaker,
                "text": clean_text,
                "narration": narrations,
                "scene": current_scene,
                "is_target": speaker == character,
                "reply_to": None,
            })

    return results


# ──────────────────────────────────────────────
# 场景与时期推断
# ──────────────────────────────────────────────

def detect_situation_type(scene: str, text: str, narration: list) -> str:
    """基于关键词推断场景类型"""
    combined = f"{scene} {text} {' '.join(narration)}"

    # 按优先级检查（confront 最特殊，优先匹配）
    for sit_type, keywords in SITUATION_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return sit_type

    return "casual"


# ──────────────────────────────────────────────
# 对话归属精确化（升级新增）
# ──────────────────────────────────────────────

# 常见角色别名映射
_SPEAKER_ALIAS_MAP = {
    "魔王": "特蕾西娅",
    "特雷西斯": "特雷西斯",
    "博士": "博士",
    "Doctor": "博士",
    "凯尔希": "凯尔希",
    "阿米娅": "阿米娅",
    "W": "W",
    "维什戴尔": "W",
}


def normalize_speaker_name(raw_name: str, target_character: str = "") -> str:
    """标准化说话者名称

    处理：
    - 括号注释：特蕾西娅(幼年) → 特蕾西娅
    - 别名：魔王 → 特蕾西娅
    - 去除多余空白

    Args:
        raw_name: 原始说话者名称
        target_character: 目标角色名（用于判断别名是否指向目标）

    Returns:
        标准化后的名称
    """
    # 去除括号注释
    clean = re.sub(r'[（(].+?[）)]', '', raw_name).strip()

    # 去除多余空白
    clean = re.sub(r'\s+', '', clean)

    # 别名映射
    if clean in _SPEAKER_ALIAS_MAP:
        return _SPEAKER_ALIAS_MAP[clean]

    # 如果目标角色有别名，检查是否匹配
    if target_character:
        for alias, canonical in _SPEAKER_ALIAS_MAP.items():
            if canonical == target_character and clean == alias:
                return canonical

    return clean


# ──────────────────────────────────────────────
# 情感标注（升级新增）
# ──────────────────────────────────────────────

# 舞台指示中的情感关键词
_EMOTION_STAGE_KEYWORDS = {
    "温柔": ["柔和", "微笑", "温暖", "轻声", "温柔", "柔声"],
    "悲伤": ["沉默", "低头", "叹息", "泪水", "悲伤", "哀伤", "哽咽"],
    "愤怒": ["愤怒", "厉声", "冷声", "目光锐利", "怒视", "咬牙"],
    "坚定": ["坚定", "直视", "平静", "沉稳", "决然"],
    "惊讶": ["惊讶", "震惊", "愣住", "意外"],
    "嘲讽": ["冷笑", "嗤笑", "嘲讽", "讥讽", "轻蔑"],
    "克制": ["克制", "压抑", "沉默片刻", "停顿"],
}


def extract_emotion_from_stage_direction(narration: list[str]) -> str | None:
    """从舞台指示中提取情感标注

    如：narration = ["目光柔和"] → emotion = "温柔"
        narration = ["沉默", "低头"] → emotion = "悲伤"

    Args:
        narration: 括号内的舞台指示列表

    Returns:
        情感标签，或 None（无法判断）
    """
    if not narration:
        return None

    combined = " ".join(narration)

    # 统计各情感类别的匹配数
    emotion_scores: dict[str, int] = {}
    for emotion, keywords in _EMOTION_STAGE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            emotion_scores[emotion] = score

    if not emotion_scores:
        return None

    # 返回得分最高的情感
    return max(emotion_scores, key=emotion_scores.get)


def infer_phase(scene: str, chapter: str) -> str:
    """基于章节名和场景关键词推断时间阶段

    推断优先级：
    1. 章节/活动代码快速映射（CHAPTER_PHASE_MAP）
    2. phase_inferrer 自动推断（活动元数据 + 内容聚类）
    3. 场景关键词匹配
    """
    # 优先用章节代码映射（快速路径）
    for ch_key, phase in CHAPTER_PHASE_MAP.items():
        if ch_key in chapter:
            return phase

    # 活动名映射
    for activity, phase in ACTIVITY_PHASE_MAP.items():
        if activity in chapter:
            return phase

    # phase_inferrer 自动推断（从 PRTS 获取元数据）
    if HAS_PHASE_INFERRER:
        result = infer_phase_from_activity_meta(chapter)
        if result and result.phase != "unknown":
            return result.phase

    # 退而用场景关键词（使用更精确的词组减少误判）
    scene_lower = scene.lower()
    if any(kw in scene_lower for kw in ["巴别塔", "内战", "卡兹戴尔"]):
        return "babel"
    if any(kw in scene_lower for kw in ["复活", "黑冠", "赦罪师"]):
        return "resurrected"
    # "魔王" 需结合卡兹戴尔语境才判定为 babel
    if "魔王" in scene_lower and "卡兹戴尔" in scene_lower:
        return "babel"

    return "unknown"


def discover_story_pages(activity_name: str) -> list[str]:
    """自动发现活动的剧情子页面

    PRTS Wiki 的剧情文本通常存储在子页面中，如：
    - "DM-1 埋藏/BEG"、"DM-1 埋藏/END"
    - "7-10 暗淡者之火/BEG"、"7-10 暗淡者之火/END"
    - "BB-ST-3 灵魂尽头/NBT"

    此函数通过搜索活动名，找到所有包含 /BEG、/END、/NBT 等后缀的剧情子页面。

    Args:
        activity_name: 活动名或章节前缀，如 "生于黑夜"、"DM"、"7-10"

    Returns:
        剧情子页面名列表，按页面名排序
    """
    from prts_client import prts_api_get

    # 搜索所有以活动名为前缀的页面
    pages = []
    for suffix in ["/BEG", "/END", "/NBT", "/BEG2", "/END2"]:
        search_term = f"{activity_name}{suffix}"
        data = prts_api_get({
            "action": "query",
            "list": "prefixsearch",
            "pssearch": search_term,
            "pslimit": "50",
        })
        for r in data.get("query", {}).get("prefixsearch", []):
            title = r.get("title", "")
            if title and title not in pages:
                pages.append(title)

    # 也搜索活动名本身（可能直接包含剧情）
    data = prts_api_get({
        "action": "query",
        "list": "prefixsearch",
        "pssearch": activity_name,
        "pslimit": "50",
    })
    for r in data.get("query", {}).get("prefixsearch", []):
        title = r.get("title", "")
        if title and title not in pages:
            # 只添加包含剧情后缀的页面
            if any(s in title for s in ["/BEG", "/END", "/NBT"]):
                pages.append(title)

    pages.sort()
    return pages


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRTS 剧情对话提取器")
    parser.add_argument(
        "--chapter", action="append",
        help="章节/剧情页面名（可多次指定），如 'DM-1 埋藏/BEG' 或 '7-10 暗淡者之火/BEG'"
    )
    parser.add_argument(
        "--discover",
        help="自动发现活动的剧情子页面（传入活动名或章节前缀，如 'DM'、'生于黑夜'）"
    )
    parser.add_argument("--character", required=True, help="角色名")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    # 确定要提取的章节列表
    chapters = list(args.chapter or [])
    if args.discover:
        discovered = discover_story_pages(args.discover)
        if discovered:
            logger.info("发现 %d 个剧情页面: %s", len(discovered), ", ".join(discovered[:5]))
            if len(discovered) > 5:
                logger.info("  ... 及其他 %d 个页面", len(discovered) - 5)
            chapters.extend(discovered)
        else:
            logger.warning("未发现 '%s' 的剧情子页面", args.discover)

    if not chapters:
        parser.error("请指定 --chapter 或 --discover 参数")

    all_dialogues = []

    for chapter in chapters:
        wikitext = fetch_chapter_wikitext(chapter)
        if not wikitext:
            continue

        dialogues = extract_dialogues(wikitext, args.character)

        # 标注场景类型和时期
        for d in dialogues:
            d["situation_type"] = detect_situation_type(
                d["scene"], d["text"], d.get("narration", [])
            )
            d["phase"] = infer_phase(d["scene"], chapter)

        # 统计
        target_count = sum(1 for d in dialogues if d["is_target"])
        all_dialogues.extend(dialogues)

        logger.info("章节 '%s': %d 目标台词 / %d 总台词", chapter, target_count, len(dialogues))

    # 统计各时期分布
    phase_dist = {}
    for d in all_dialogues:
        if d["is_target"]:
            phase = d.get("phase", "unknown")
            phase_dist[phase] = phase_dist.get(phase, 0) + 1

    result = {
        "character": args.character,
        "chapters": args.chapter,
        "total_target_lines": sum(1 for d in all_dialogues if d["is_target"]),
        "total_context_lines": len(all_dialogues),
        "phase_distribution": phase_dist,
        "dialogues": all_dialogues,
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding='utf-8')
        print(json.dumps({
            "success": True,
            "output": args.output,
            "target_lines": result["total_target_lines"],
        }, ensure_ascii=False))
    else:
        print(output_json)


if __name__ == "__main__":
    main()
