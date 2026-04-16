#!/usr/bin/env python3
"""
对话指纹分析器 —— 从角色语音/对话文本中自动提取语言指纹

这是 arknights-operator-skill 相比 ex-skill / colleague-skill 的核心差异：
不做主观描述，而是从角色的实际对话中提取可量化的语言特征。

用法:
    # 分析单条对话文件
    python dialogue_fingerprint.py --input ./theresa_lines.txt --format plain

    # 分析 PRTS Wiki 导出的语音数据 JSON
    python dialogue_fingerprint.py --input ./theresa_voices.json --format prts-json

    # 分析后输出到文件
    python dialogue_fingerprint.py --input ./theresa_lines.txt --output ./fingerprint.json

输出:
    JSON 格式的语言指纹报告，包含 7 个维度的量化指标
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 中文情感词典（精简版，覆盖明日方舟角色常见情感表达）
# ──────────────────────────────────────────────

EMOTION_LEXICON = {
    "温柔": ["温柔", "轻声", "微笑", "柔和", "温暖", "关怀", "呵护", "怜惜"],
    "悲伤": ["悲伤", "哀伤", "沉默", "叹息", "泪水", "遗憾", "失去", "怀念", "痛"],
    "愤怒": ["愤怒", "不可饶恕", "绝不允许", "休想", "愚蠢", "可恶", "不可原谅"],
    "坚定": ["坚定", "决不", "一定", "必须", "绝不", "无论如何", "必然", "必将"],
    "恐惧": ["恐惧", "害怕", "可怕", "战栗", "颤抖", "不安", "危险"],
    "希望": ["希望", "未来", "黎明", "明天", "一定会", "终将"],
    "孤独": ["孤独", "独自", "一个人", "无人", "寂寞", "空旷", "遥远"],
    "信任": ["信任", "相信", "托付", "交付", "依靠", "在一起", "同行"],
}

# 中文第一人称代词
FIRST_PERSON = ["我", "吾", "本王", "吾辈", "在下", "朕", "本人", "咱"]

# 中文语气标记
PAUSE_MARKERS = ["……", "…", "——", "—", "···"]
EXCLAMATION = ["！", "!", "？！", "!?"]
QUESTION = ["？", "?"]


# ──────────────────────────────────────────────
# 核心分析函数
# ──────────────────────────────────────────────

def load_dialogues(filepath: str, fmt: str = "plain") -> list[dict]:
    """
    加载对话数据

    返回格式: [{"label": "xxx", "text": "xxx"}, ...]
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    if fmt == "prts-json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # PRTS JSON 格式: {"voice_lines": [...]} 或直接 [...]
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "voice_lines" in data:
                return data["voice_lines"]
            # 尝试从 game_data_parser 输出格式提取
            if "archives" in data:
                return [
                    {"label": a.get("index", ""), "text": a.get("text", "")}
                    for a in data["archives"]
                    if a.get("text")
                ]
        return []

    elif fmt == "plain":
        # 纯文本格式，每行一条对话
        content = path.read_text(encoding="utf-8")
        lines = []
        for i, line in enumerate(content.strip().split("\n")):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持 "标签: 内容" 或 "标签|内容" 格式
            for sep in [":", "：", "|"]:
                if sep in line:
                    label, _, text = line.partition(sep)
                    lines.append({"label": label.strip(), "text": text.strip()})
                    break
            else:
                lines.append({"label": f"line_{i+1}", "text": line})
        return lines

    elif fmt == "csv":
        # 简易 CSV: label,text
        content = path.read_text(encoding="utf-8")
        lines = []
        for i, row in enumerate(content.strip().split("\n")):
            if i == 0 and "label" in row.lower():
                continue  # skip header
            parts = row.split(",", 1)
            if len(parts) == 2:
                lines.append({"label": parts[0].strip(), "text": parts[1].strip()})
            elif len(parts) == 1 and parts[0].strip():
                lines.append({"label": f"line_{i+1}", "text": parts[0].strip()})
        return lines

    else:
        raise ValueError(f"不支持的格式: {fmt}")


def analyze_sentence_length_distribution(dialogues: list[dict]) -> dict:
    """
    维度 1：句式长度分布

    分析角色对话的句子长度模式，量化"短句型/长句型/混合型"
    """
    lengths = []
    for d in dialogues:
        text = d.get("text", "")
        # 按中文标点分句
        sentences = re.split(r"[。！？；…—]+", text)
        for s in sentences:
            s = s.strip()
            if len(s) > 0:
                lengths.append(len(s))

    if not lengths:
        return {"type": "unknown", "avg": 0, "distribution": {}}

    avg_len = sum(lengths) / len(lengths)

    # 按长度区间统计
    short = sum(1 for l in lengths if l <= 5)    # 短句 ≤5字
    medium = sum(1 for l in lengths if 5 < l <= 15)  # 中句 6-15字
    long = sum(1 for l in lengths if l > 15)       # 长句 >15字
    total = len(lengths)

    distribution = {
        "short_le5": round(short / total * 100, 1),
        "medium_6_15": round(medium / total * 100, 1),
        "long_gt15": round(long / total * 100, 1),
    }

    # 判断类型
    if distribution["short_le5"] > 50:
        stype = "短句型"
    elif distribution["long_gt15"] > 40:
        stype = "长句型"
    elif distribution["short_le5"] > 25 and distribution["long_gt15"] > 25:
        stype = "长短交替型"
    else:
        stype = "中句型"

    return {
        "type": stype,
        "avg_length": round(avg_len, 1),
        "min": min(lengths),
        "max": max(lengths),
        "distribution_pct": distribution,
        "sample_count": total,
    }


def analyze_pause_markers(dialogues: list[dict]) -> dict:
    """
    维度 2：停顿与语气标记

    量化角色的停顿习惯（省略号频率、破折号频率）
    """
    total_lines = len(dialogues)
    ellipsis_count = 0  # 省略号
    dash_count = 0      # 破折号
    exclamation_count = 0  # 感叹号
    question_count = 0     # 问号
    ellipsis_start = 0     # 以省略号开头

    for d in dialogues:
        text = d.get("text", "")
        if "…" in text or "..." in text:
            ellipsis_count += 1
        if text.startswith("…") or text.startswith("...") or text.startswith("……"):
            ellipsis_start += 1
        if "——" in text or "—" in text:
            dash_count += 1
        if any(e in text for e in EXCLAMATION):
            exclamation_count += 1
        if any(q in text for q in QUESTION):
            question_count += 1

    if total_lines == 0:
        return {"ellipsis_freq": 0, "exclamation_freq": 0}

    return {
        "ellipsis_pct": round(ellipsis_count / total_lines * 100, 1),
        "ellipsis_start_pct": round(ellipsis_start / total_lines * 100, 1),
        "dash_pct": round(dash_count / total_lines * 100, 1),
        "exclamation_pct": round(exclamation_count / total_lines * 100, 1),
        "question_pct": round(question_count / total_lines * 100, 1),
        "interpretation": _interpret_pause(
            ellipsis_count / total_lines,
            exclamation_count / total_lines,
            ellipsis_start / total_lines,
        ),
    }


def _interpret_pause(ellipsis_ratio, exclamation_ratio, ellipsis_start_ratio):
    """生成停顿模式的自然语言解读"""
    traits = []
    if ellipsis_ratio > 0.3:
        traits.append("频繁停顿，善于沉默")
    if ellipsis_start_ratio > 0.15:
        traits.append("常以沉默开头，话语经过深思熟虑")
    if exclamation_ratio < 0.05:
        traits.append("几乎不用感叹号，语气极度克制")
    elif exclamation_ratio > 0.3:
        traits.append("常用感叹号，表达直接热烈")
    if not traits:
        traits.append("语气平稳，无明显极端标记")
    return "；".join(traits)


def analyze_self_reference(dialogues: list[dict]) -> dict:
    """
    维度 3：自称模式

    量化角色的第一人称使用偏好
    """
    counter = Counter()
    total_first_person = 0
    total_lines = len(dialogues)

    for d in dialogues:
        text = d.get("text", "")
        for pronoun in FIRST_PERSON:
            count = text.count(pronoun)
            if count > 0:
                counter[pronoun] += count
                total_first_person += count

    if total_first_person == 0:
        return {
            "primary": "省略自称",
            "frequency_per_line": 0,
            "distribution": {},
            "interpretation": "极少使用第一人称，倾向省略主语或使用'我们'",
        }

    primary = counter.most_common(1)[0][0]
    freq = round(total_first_person / total_lines, 2) if total_lines > 0 else 0

    distribution = {
        k: round(v / total_first_person * 100, 1)
        for k, v in counter.most_common()
    }

    # 解读
    if freq < 0.3:
        interp = "极少自称，倾向省略主语"
    elif primary == "我":
        interp = "常用'我'，表达直接"
    elif primary in ["吾", "本王", "朕"]:
        interp = f"使用'{primary}'自称，体现特殊身份地位"
    else:
        interp = f"自称'{primary}'，有独特表达习惯"

    return {
        "primary": primary,
        "frequency_per_line": freq,
        "distribution_pct": distribution,
        "interpretation": interp,
    }


def analyze_emotion_vocabulary(dialogues: list[dict]) -> dict:
    """
    维度 4：情感词汇分布

    量化角色的情感表达范围和偏好
    """
    emotion_counts = Counter()
    total_emotion_words = 0
    emotion_examples = {}

    for d in dialogues:
        text = d.get("text", "")
        for emotion, words in EMOTION_LEXICON.items():
            for word in words:
                count = text.count(word)
                if count > 0:
                    emotion_counts[emotion] += count
                    total_emotion_words += count
                    if emotion not in emotion_examples:
                        emotion_examples[emotion] = []
                    if len(emotion_examples[emotion]) < 3:
                        emotion_examples[emotion].append(word)

    if total_emotion_words == 0:
        return {"dominant": "unknown", "spectrum": {}, "interpretation": "未检测到明显情感词汇"}

    # 按频率排序
    sorted_emotions = emotion_counts.most_common()
    dominant = sorted_emotions[0][0] if sorted_emotions else "unknown"

    spectrum = {
        k: round(v / total_emotion_words * 100, 1)
        for k, v in sorted_emotions
    }

    # 判断情感宽度
    active_emotions = sum(1 for k, v in sorted_emotions if v >= 2)
    if active_emotions >= 5:
        breadth = "宽谱"
    elif active_emotions >= 3:
        breadth = "中谱"
    else:
        breadth = "窄谱"

    return {
        "dominant": dominant,
        "breadth": breadth,
        "active_emotion_count": active_emotions,
        "spectrum_pct": spectrum,
        "examples": emotion_examples,
        "interpretation": f"主导情感为'{dominant}'，情感谱系{breadth}（活跃情感{active_emotions}种）",
    }


def analyze_rhetoric_patterns(dialogues: list[dict]) -> dict:
    """
    维度 5：修辞模式

    量化反问、比喻、排比等修辞手法的使用频率
    """
    total_lines = len(dialogues)
    rhetorical_question = 0  # 反问
    metaphor = 0             # 比喻（含"像""如同""仿佛""似"）
    parallelism = 0          # 排比（连续3个以上相似结构）
    negation = 0             # 否定句

    for d in dialogues:
        text = d.get("text", "")

        # 反问检测：含问号 + 否定词/反问词
        has_question = any(q in text for q in QUESTION)
        has_rhetorical = any(w in text for w in ["难道", "岂", "何不", "又怎么", "又如何", "不是吗"])
        if has_question and has_rhetorical:
            rhetorical_question += 1

        # 比喻检测
        if any(w in text for w in ["像", "如同", "仿佛", "似", "宛如", "犹如", "好比"]):
            metaphor += 1

        # 排比检测：重复的逗号分隔短语
        comma_phrases = re.split(r"[，、；]", text)
        if len(comma_phrases) >= 3:
            # 检查是否有相似的起始字
            starts = [p.strip()[:2] for p in comma_phrases if len(p.strip()) >= 2]
            if len(starts) >= 3:
                start_counter = Counter(starts)
                if start_counter.most_common(1)[0][1] >= 3:
                    parallelism += 1

        # 否定句检测：匹配否定词 + 动词/形容词的典型否定句式
        # 避免误匹配含"不"但非否定句的文本（如"不同""不断"等）
        negation_patterns = [
            r"(不|未|莫|别)\s*[是能为会有在到想需该]",   # 不是/不能/不会/未有...
            r"(不|未|莫|别)\s*[让叫使把给向对]",       # 不让/别叫...
            r"没有",                                    # 没有
            r"无法",                                    # 无法
            r"并非",                                    # 并非
            r"从不|从不",                               # 从不
            r"绝不|决不",                               # 绝不
            r"无人|无物|无端|无从",                     # 无+名词性成分
        ]
        if any(re.search(pat, text) for pat in negation_patterns):
            negation += 1

    if total_lines == 0:
        return {"rhetorical_question_freq": 0}

    return {
        "rhetorical_question_pct": round(rhetorical_question / total_lines * 100, 1),
        "metaphor_pct": round(metaphor / total_lines * 100, 1),
        "parallelism_pct": round(parallelism / total_lines * 100, 1),
        "negation_pct": round(negation / total_lines * 100, 1),
        "interpretation": _interpret_rhetoric(
            rhetorical_question / total_lines,
            metaphor / total_lines,
            negation / total_lines,
        ),
    }


def _interpret_rhetoric(rq_ratio, meta_ratio, neg_ratio):
    traits = []
    if rq_ratio > 0.1:
        traits.append("善用反问引导思考")
    if meta_ratio > 0.1:
        traits.append("偏好意象化表达")
    if neg_ratio > 0.4:
        traits.append("频繁使用否定句式，倾向从反面界定")
    if neg_ratio < 0.1:
        traits.append("极少使用否定句，表达积极正向")
    if not traits:
        traits.append("修辞风格平实直白")
    return "；".join(traits)


def analyze_address_pattern(dialogues: list[dict]) -> dict:
    """
    维度 6：称呼模式

    量化角色如何称呼他人（尊称/昵称/省略称呼）
    """
    # 中文尊称/亲昵称呼标记
    honorific = ["大人", "阁下", "殿下", "陛下", "先生", "小姐", "长官", "指挥官"]
    intimate = ["亲爱的", "小", "老", "阿", "姐", "哥", "妹", "弟"]

    honorific_count = 0
    intimate_count = 0
    address_examples = {"honorific": [], "intimate": []}

    for d in dialogues:
        text = d.get("text", "")
        for h in honorific:
            if h in text:
                honorific_count += 1
                if len(address_examples["honorific"]) < 5:
                    address_examples["honorific"].append(text[:50])
                break
        for i in intimate:
            if i in text:
                intimate_count += 1
                if len(address_examples["intimate"]) < 5:
                    address_examples["intimate"].append(text[:50])
                break

    total = len(dialogues)
    if total == 0:
        return {"pattern": "unknown"}

    if honorific_count > intimate_count * 2:
        pattern = "尊称型"
    elif intimate_count > honorific_count * 2:
        pattern = "亲昵型"
    elif honorific_count > 0 and intimate_count > 0:
        pattern = "切换型"
    else:
        pattern = "省略称呼型"

    return {
        "pattern": pattern,
        "honorific_pct": round(honorific_count / total * 100, 1),
        "intimate_pct": round(intimate_count / total * 100, 1),
        "examples": address_examples,
    }


def analyze_natural_imagery(dialogues: list[dict]) -> dict:
    """
    维度 7：自然意象偏好

    量化角色是否偏好使用自然意象（花、风、光、影等）
    使用 2 字词组匹配以减少误报（如"花费"不含"花"意象）
    """
    # 使用 2 字词组匹配，减少"花费""风格""光明"等误报
    nature_words = {
        "植物": ["花朵", "花瓣", "花开", "花落", "草木", "树叶", "枝头", "藤蔓", "森林", "丛林", "花草"],
        "天文": ["星空", "星辰", "月光", "阳光", "光影", "天空", "云霞", "彩虹", "星光", "夜空", "日光"],
        "气象": ["风雨", "风声", "微风", "暴风", "雨幕", "雪花", "霜降", "雾气", "雷鸣", "露水", "晨露"],
        "大地": ["山河", "大海", "大地", "土地", "岩石", "沙漠", "泉水", "山峦", "河川", "海洋", "山巅"],
        "时间": ["清晨", "日暮", "夜晚", "白昼", "春天", "夏日", "秋色", "冬雪", "黄昏", "黎明", "破晓"],
    }

    category_counts = Counter()
    total_nature = 0
    top_words = Counter()

    for d in dialogues:
        text = d.get("text", "")
        for category, words in nature_words.items():
            for word in words:
                count = text.count(word)
                if count > 0:
                    category_counts[category] += count
                    total_nature += count
                    top_words[word] += count

    if total_nature == 0:
        return {"density": 0, "interpretation": "极少使用自然意象"}

    total_lines = len(dialogues)
    density = round(total_nature / total_lines, 2) if total_lines > 0 else 0

    # 密度解读
    if density > 3:
        density_level = "高频"
    elif density > 1:
        density_level = "中频"
    else:
        density_level = "低频"

    return {
        "density_per_line": density,
        "density_level": density_level,
        "category_distribution": {
            k: round(v / total_nature * 100, 1)
            for k, v in category_counts.most_common()
        },
        "top_5_words": dict(top_words.most_common(5)),
        "interpretation": f"自然意象密度{density_level}（{density}个/句），偏好{_top_category(category_counts)}意象",
    }


def _top_category(counter: Counter) -> str:
    if not counter:
        return "无"
    return counter.most_common(1)[0][0]


# ──────────────────────────────────────────────
# 主分析流程
# ──────────────────────────────────────────────

def generate_fingerprint(dialogues: list[dict], operator_name: str = "unknown") -> dict:
    """
    生成完整的语言指纹报告
    """
    report = {
        "operator": operator_name,
        "dialogue_count": len(dialogues),
        "dimensions": {
            "1_sentence_length": analyze_sentence_length_distribution(dialogues),
            "2_pause_markers": analyze_pause_markers(dialogues),
            "3_self_reference": analyze_self_reference(dialogues),
            "4_emotion_vocabulary": analyze_emotion_vocabulary(dialogues),
            "5_rhetoric_patterns": analyze_rhetoric_patterns(dialogues),
            "6_address_pattern": analyze_address_pattern(dialogues),
            "7_natural_imagery": analyze_natural_imagery(dialogues),
        },
    }

    # 生成综合画像摘要
    report["summary"] = _generate_summary(report["dimensions"])

    return report


def _generate_summary(dimensions: dict) -> str:
    """
    从 7 个维度生成一段自然语言的角色语言画像摘要
    """
    parts = []

    d1 = dimensions["1_sentence_length"]
    parts.append(f"句式{d1.get('type', '未知')}，平均{d1.get('avg_length', 0)}字")

    d2 = dimensions["2_pause_markers"]
    parts.append(d2.get("interpretation", ""))

    d3 = dimensions["3_self_reference"]
    parts.append(d3.get("interpretation", ""))

    d4 = dimensions["4_emotion_vocabulary"]
    parts.append(d4.get("interpretation", ""))

    d5 = dimensions["5_rhetoric_patterns"]
    parts.append(d5.get("interpretation", ""))

    d7 = dimensions["7_natural_imagery"]
    parts.append(d7.get("interpretation", ""))

    return "；".join(p for p in parts if p)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="对话指纹分析器 — 从角色对话中提取量化语言特征",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析纯文本对话
  python dialogue_fingerprint.py --input ./theresa_lines.txt --format plain

  # 分析 PRTS 导出的语音 JSON
  python dialogue_fingerprint.py --input ./theresa_voices.json --format prts-json

  # 指定角色名并输出到文件
  python dialogue_fingerprint.py --input lines.txt --name 特蕾西娅 --output fingerprint.json
        """,
    )

    parser.add_argument("--input", required=True, help="对话数据文件路径")
    parser.add_argument("--format", choices=["plain", "prts-json", "csv"], default="plain", help="数据格式")
    parser.add_argument("--name", default="unknown", help="角色名称")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    dialogues = load_dialogues(args.input, args.format)
    if not dialogues:
        print("错误：未找到任何对话数据", file=sys.stderr)
        sys.exit(1)

    report = generate_fingerprint(dialogues, args.name)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"指纹报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
