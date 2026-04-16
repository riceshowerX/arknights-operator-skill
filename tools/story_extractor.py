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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

PRTS_API_URL = "https://prts.wiki/api.php"
PRTS_USER_AGENT = "arknights-operator-skill/2.0 (https://github.com/riceshowerX/arknights-operator-skill)"
REQUEST_TIMEOUT = 20

# 章节名 → 时间阶段映射
# 注意：此映射以特蕾西娅的视角为主，其他角色可能需要调整
CHAPTER_PHASE_MAP = {
    "第0章": "early",
    "第1章": "early",
    "第2章": "early",
    "第3章": "early",
    "第4章": "early",
    "第5章": "early",
    "第6章": "early",
    "第7章": "early",       # 苦难摇篮：切尔诺伯格/整合运动
    "第8章": "babel",       # 怒号光明：巴别塔回忆
    "第9章": "babel",       # 风暴瞭望：巴别塔末期
    "第10章": "resurrected", # 碎鳞：复活后
    "第11章": "resurrected",
    "第12章": "resurrected",
    "第13章": "resurrected",
    "第14章": "resurrected", # 慈悲灯塔
    # 巴别塔活动（BB 系列）
    "BB-": "babel",
    # 伦蒂尼姆/第 10-14 章相关
    "LT-": "resurrected",
    "H10-": "resurrected",
    "H11-": "resurrected",
    "H12-": "resurrected",
    "H14-": "resurrected",
    # 生于黑夜（W 的活动，切尔诺伯格/早期回忆）
    "DM-": "early",
    # 遗尘漫步（凯尔希回忆，跨越多时期，归为 early）
    "WD-": "early",
    # 危机合约等
    "CC-": "unknown",
}

# 活动关键词 → 时期
ACTIVITY_PHASE_MAP = {
    "巴别塔": "babel",
    "慈悲灯塔": "resurrected",
    "伦蒂尼姆": "resurrected",
    "生于黑夜": "early",
    "切尔诺伯格": "early",
    "遗尘漫步": "early",
}

# 场景类型关键词
SITUATION_KEYWORDS = {
    "confront": ["战斗", "敌", "进攻", "撤退", "交战", "对峙", "冲突", "攻击", "防线"],
    "comfort": ["安慰", "不必", "没关系", "不是你的错", "不要紧", "已经足够"],
    "decide": ["决定", "必须", "只能如此", "没有选择", "别无选择", "这是我的选择"],
    "reminisce": ["回忆", "过去", "曾经", "记得", "那时候", "还记得", "从前"],
    "command": ["命令", "执行", "立刻", "全员", "出发", "集合"],
}

# 场景标题正则（wikitext 中 === 标题 === 或 == 标题 ==）
SCENE_HEADER_RE = re.compile(r'^={2,4}\s*(.+?)\s*={2,4}', re.MULTILINE)

# Wikitext 对话行正则（'''角色名'''：台词）
WIKITEXT_DIALOGUE_RE = re.compile(
    r"""[''\u2018\u2019]{2,3}(.+?)[''\u2018\u2019]{2,3}[：:]\s*(.+?)(?:\n|$)"""
)

# 剧情模拟器脚本对话行正则：[name="角色名"]对话内容
SCRIPT_DIALOGUE_RE = re.compile(r'\[name="([^"]+)"\]([\s\S]*?)(?=\[name=|\[dialog\]|\[Decision\]|\[HEADER\]|\[Blocker\]|\[stopmusic\]|\[playMusic\]|$)')

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
# PRTS API
# ──────────────────────────────────────────────

def fetch_chapter_wikitext(chapter: str) -> str:
    """获取剧情页面的 wikitext 原文，自动跟随 redirect"""
    # 先尝试用 action=parse（自动跟随 redirect）
    params = urlencode({
        'action': 'parse',
        'page': chapter,
        'prop': 'wikitext',
        'format': 'json',
        'redirects': 'true',
    })
    url = f"{PRTS_API_URL}?{params}"
    req = Request(url, headers={'User-Agent': PRTS_USER_AGENT})

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (HTTPError, URLError) as e:
        print(json.dumps({
            "error": f"无法获取剧情页面 '{chapter}': {e}",
            "chapter": chapter
        }, ensure_ascii=False), file=sys.stderr)
        return ""

    wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')

    # 如果是 redirect，手动跟随
    if wikitext.startswith('#REDIRECT') or wikitext.startswith('#redirect'):
        redirect_match = re.search(r'\[\[([^\]]+)\]\]', wikitext)
        if redirect_match:
            target = redirect_match.group(1)
            print(json.dumps({
                "info": f"跟随重定向: '{chapter}' → '{target}'",
                "chapter": chapter
            }, ensure_ascii=False), file=sys.stderr)
            return fetch_chapter_wikitext(target)

    # 如果内容为空，尝试查找 /NBT 子页面
    if not wikitext:
        # 尝试 chapter/NBT
        nbt_page = f"{chapter}/NBT"
        nbt_wikitext = _fetch_raw_wikitext(nbt_page)
        if nbt_wikitext:
            print(json.dumps({
                "info": f"自动切换到 NBT 子页面: '{nbt_page}'",
                "chapter": chapter
            }, ensure_ascii=False), file=sys.stderr)
            return nbt_wikitext

        print(json.dumps({
            "warning": f"页面 '{chapter}' 内容为空或不存在（也尝试了 /NBT 子页面）",
            "chapter": chapter
        }, ensure_ascii=False), file=sys.stderr)

    return wikitext


def _fetch_raw_wikitext(page: str) -> str:
    """直接获取页面 wikitext，不跟随 redirect"""
    params = urlencode({
        'action': 'parse',
        'page': page,
        'prop': 'wikitext',
        'format': 'json',
        'redirects': 'true',
    })
    url = f"{PRTS_API_URL}?{params}"
    req = Request(url, headers={'User-Agent': PRTS_USER_AGENT})

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (HTTPError, URLError):
        return ""

    return data.get('parse', {}).get('wikitext', {}).get('*', '')


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
        if not re.match(r'^[=\s]+$', title):
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
            # 跳过纯格式标题
            if re.match(r'^[=\s]+$', current_scene):
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


def infer_phase(scene: str, chapter: str) -> str:
    """基于章节名和场景关键词推断时间阶段"""
    # 优先用章节名映射
    for ch_key, phase in CHAPTER_PHASE_MAP.items():
        if ch_key in chapter:
            return phase

    # 活动名映射
    for activity, phase in ACTIVITY_PHASE_MAP.items():
        if activity in chapter:
            return phase

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


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PRTS 剧情对话提取器")
    parser.add_argument(
        "--chapter", action="append", required=True,
        help="章节/剧情页面名（可多次指定），如 'BB-ST-3 灵魂尽头/NBT' 或 '第8章/怒号光明'"
    )
    parser.add_argument("--character", required=True, help="角色名")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    all_dialogues = []

    for chapter in args.chapter:
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

        print(json.dumps({
            "chapter": chapter,
            "target_lines": target_count,
            "total_lines": len(dialogues),
        }, ensure_ascii=False), file=sys.stderr)

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
