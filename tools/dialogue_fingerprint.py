#!/usr/bin/env python3
"""
对话指纹分析器 —— 从角色语音/对话文本中自动提取语言指纹

这是 arknights-operator-skill 相比 ex-skill / colleague-skill 的核心差异：
不做主观描述，而是从角色的实际对话中提取可量化的语言特征。

升级版：支持语境化分析模式。
  - 传统模式：--input/--format（分析原始对话文件）
  - 语境化模式：--context-json（消费 context.json，按场景/对象/时期分片分析）

语境化模式会输出 per-situation / per-interlocutor / per-phase 的分片指纹，
以及各分片之间的差异（shifts），可直接写入 Persona Layer 2-4。

用法:
    # 传统模式
    python dialogue_fingerprint.py --input ./theresa_lines.txt --format plain
    python dialogue_fingerprint.py --input ./theresa_voices.json --format prts-json

    # 语境化模式
    python dialogue_fingerprint.py --context-json operators/te-lei-xi-ya/context.json

    # 语境化 + 输出到文件
    python dialogue_fingerprint.py --context-json context.json --output fingerprint.json
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# ──────────────────────────────────────────────
# 中文情感词典（精简版，覆盖明日方舟角色常见情感表达）
# ──────────────────────────────────────────────

# 情感词典（中文）— 带权重版本
# 每个词条为 (词, 权重) 元组，权重范围 0.5~1.5
# 权重反映情感强度：高权重 = 强烈情感，低权重 = 轻微暗示
#
# 词典从 data/emotion_lexicon.json 加载；如文件不存在则使用以下内建默认值。
# 要扩展词典，编辑 data/emotion_lexicon.json 即可，无需修改源码。

_EMOTION_LEXICON_BUILTIN: dict[str, list[tuple[str, float]]] = {
    "温柔": [
        ("温柔", 1.0), ("轻声", 0.8), ("微笑", 0.9), ("柔和", 0.7),
        ("温暖", 0.8), ("关怀", 1.0), ("呵护", 1.2), ("怜惜", 1.1),
        ("注视", 0.5), ("轻抚", 1.0), ("低声", 0.6), ("柔声", 0.9),
        ("安抚", 1.0), ("慈爱", 1.2),
    ],
    "悲伤": [
        ("悲伤", 1.2), ("哀伤", 1.2), ("沉默", 0.6), ("叹息", 0.9),
        ("泪水", 1.0), ("遗憾", 0.8), ("失去", 1.0), ("怀念", 0.9),
        ("痛", 1.0), ("消逝", 1.0), ("陨落", 1.3), ("永别", 1.5),
        ("哀悼", 1.2), ("沉痛", 1.3),
    ],
    "愤怒": [
        ("愤怒", 1.2), ("不可饶恕", 1.5), ("绝不允许", 1.4), ("休想", 1.0),
        ("愚蠢", 0.8), ("可恶", 1.0), ("不可原谅", 1.5), ("暴怒", 1.4),
        ("愤慨", 1.2), ("痛恨", 1.4), ("怒斥", 1.3),
    ],
    "坚定": [
        ("坚定", 1.0), ("决不", 1.1), ("一定", 0.7), ("必须", 0.7),
        ("绝不", 1.1), ("无论如何", 1.0), ("必然", 0.9), ("必将", 1.0),
        ("誓言", 1.2), ("誓约", 1.3), ("不动摇", 1.2), ("义无反顾", 1.3),
        ("矢志", 1.4),
    ],
    "恐惧": [
        ("恐惧", 1.2), ("害怕", 1.0), ("可怕", 0.9), ("战栗", 1.3),
        ("颤抖", 1.0), ("不安", 0.8), ("危险", 0.7), ("惊惧", 1.2),
        ("惶恐", 1.1),
    ],
    "希望": [
        ("希望", 1.0), ("未来", 0.7), ("黎明", 0.9), ("明天", 0.6),
        ("一定会", 1.0), ("终将", 0.9), ("曙光", 1.2), ("期盼", 1.0),
        ("憧憬", 0.9), ("祈愿", 1.1), ("信念", 1.1), ("勇气", 1.0),
    ],
    "孤独": [
        ("孤独", 1.2), ("独自", 0.8), ("一个人", 0.7), ("无人", 0.7),
        ("寂寞", 1.0), ("空旷", 0.6), ("遥远", 0.5), ("漂泊", 0.9),
        ("流浪", 0.9), ("形单影只", 1.3), ("孑然", 1.2),
    ],
    "信任": [
        ("信任", 1.0), ("相信", 0.9), ("托付", 1.2), ("交付", 0.9),
        ("依靠", 0.8), ("在一起", 0.7), ("同行", 0.8), ("深信", 1.2),
        ("依赖", 0.8), ("无条件", 1.0),
    ],
    "嘲讽": [
        ("呵", 0.8), ("可笑", 1.0), ("有趣", 0.6), ("愚蠢", 1.2),
        ("天真", 0.9), ("不自量力", 1.3), ("滑稽", 1.0), ("嗤笑", 1.2),
        ("嘲讽", 1.2), ("讥讽", 1.2), ("轻蔑", 1.1),
    ],
    "绝望": [
        ("无望", 1.5), ("徒劳", 1.2), ("终焉", 1.3), ("末日", 1.3),
        ("注定", 0.9), ("无法改变", 1.2), ("深渊", 1.1), ("绝望", 1.5),
        ("万劫不复", 1.5),
    ],
    "自豪": [
        ("骄傲", 1.0), ("荣耀", 1.1), ("自豪", 1.2), ("无愧", 0.9),
        ("辉煌", 1.0), ("伟大", 0.8), ("传承", 0.7), ("使命", 0.8),
    ],
    "眷恋": [
        ("眷恋", 1.2), ("不舍", 1.0), ("留恋", 1.0), ("牵挂", 0.9),
        ("思念", 1.0), ("故乡", 0.7), ("家园", 0.8), ("归处", 1.0),
        ("依恋", 1.1), ("难舍", 1.2),
    ],
}


def _load_emotion_lexicon(filepath: str | None = None) -> dict[str, list[tuple[str, float]]]:
    """加载情感词典。优先从 JSON 文件加载，失败则使用内建默认值。

    JSON 文件格式: {"温柔": [{"word": "温柔", "weight": 1.0}, ...], ...}

    Args:
        filepath: 自定义词典路径。None 时使用默认 data/emotion_lexicon.json

    Returns:
        情感 → [(词, 权重), ...] 映射
    """
    json_path = Path(filepath) if filepath else Path(__file__).parent.parent / "data" / "emotion_lexicon.json"

    if not json_path.exists():
        return _EMOTION_LEXICON_BUILTIN

    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"警告：情感词典文件解析失败 {json_path}: {e}，使用内建词典", file=sys.stderr)
        return _EMOTION_LEXICON_BUILTIN

    if not isinstance(raw, dict):
        print("警告：情感词典文件格式错误（应为对象），使用内建词典", file=sys.stderr)
        return _EMOTION_LEXICON_BUILTIN

    result: dict[str, list[tuple[str, float]]] = {}
    for emotion, entries in raw.items():
        if not isinstance(entries, list):
            continue
        converted = []
        for entry in entries:
            if isinstance(entry, dict) and "word" in entry and "weight" in entry:
                converted.append((entry["word"], float(entry["weight"])))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                converted.append((str(entry[0]), float(entry[1])))
        if converted:
            result[emotion] = converted

    return result if result else _EMOTION_LEXICON_BUILTIN


# 模块级初始化：从 JSON 文件加载（如存在），否则用内建值
EMOTION_LEXICON: dict[str, list[tuple[str, float]]] = _load_emotion_lexicon()

# 通用中文字频基线（用于口头禅检测的显著性对比）
_CN_CHAR_FREQ_BASELINE = 0.003  # 约 0.3%

# 中文第一人称代词
FIRST_PERSON = ["我", "吾", "本王", "吾辈", "在下", "朕", "本人", "咱"]

# 中文语气标记
EXCLAMATION = ["！", "!", "？！", "!?"]
QUESTION = ["？", "?"]


# ──────────────────────────────────────────────
# 核心分析函数（7 维度）
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
        with open(path, encoding="utf-8") as f:
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


def split_sentences(text: str) -> list[str]:
    """
    按中文标点将文本分句，返回非空句子列表。

    被 temporal_slicer.py 共享使用，避免代码重复。
    """
    sentences = re.split(r"[。！？；…—]+", text)
    return [s.strip() for s in sentences if s.strip()]


def analyze_sentence_length_distribution(dialogues: list[dict]) -> dict:
    """
    维度 1：句式长度分布（统计分布升级版）

    分析角色对话的句子长度模式，使用统计分布而非硬阈值。
    输出百分位数、变异系数（CV）、节奏稳定性等指标。
    """
    lengths: list[int] = []
    for d in dialogues:
        text = d.get("text", "")
        # 按中文标点分句
        for s in split_sentences(text):
            lengths.append(len(s))

    if not lengths:
        return {"type": "unknown", "avg": 0, "distribution": {}}

    avg_len = sum(lengths) / len(lengths)
    total = len(lengths)

    # ── 统计分布指标 ──
    median_len = statistics.median(lengths)
    stdev_len = statistics.stdev(lengths) if total > 1 else 0
    cv = stdev_len / median_len if median_len > 0 else 0  # 变异系数

    # 百分位数（使用 statistics.quantiles）
    if total >= 4:
        q1, q2, q3 = statistics.quantiles(lengths, n=4)
    else:
        q1 = min(lengths)
        q2 = median_len
        q3 = max(lengths)

    # 自适应分界（基于百分位数而非硬编码阈值）
    short = sum(1 for ln in lengths if ln <= q1)
    medium = sum(1 for ln in lengths if q1 < ln <= q3)
    long = sum(1 for ln in lengths if ln > q3)

    distribution = {
        "short_pct": round(short / total * 100, 1),
        "medium_pct": round(medium / total * 100, 1),
        "long_pct": round(long / total * 100, 1),
    }

    # 节奏稳定性判断（基于 CV）
    if cv < 0.4:
        rhythm = "稳定"
    elif cv < 0.7:
        rhythm = "多变"
    else:
        rhythm = "极端交替"

    # 类型判断（结合分布和 CV）
    if distribution["short_pct"] > 50:
        stype = "短句型"
    elif distribution["long_pct"] > 40:
        stype = "长句型"
    elif distribution["short_pct"] > 25 and distribution["long_pct"] > 25:
        stype = "长短交替型"
    else:
        stype = "中句型"

    return {
        "type": stype,
        "avg_length": round(avg_len, 1),
        "median": round(median_len, 1),
        "stdev": round(stdev_len, 1),
        "cv": round(cv, 2),
        "rhythm": rhythm,
        "percentiles": {"p25": round(q1, 1), "p50": round(q2, 1), "p75": round(q3, 1)},
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
    emotion_counts: Counter = Counter()
    total_emotion_words = 0
    emotion_examples: dict[str, list[str]] = {}

    for d in dialogues:
        text = d.get("text", "")
        for emotion, word_entries in EMOTION_LEXICON.items():
            for word, weight in word_entries:
                count = text.count(word)
                if count > 0:
                    weighted = count * weight
                    emotion_counts[emotion] += weighted
                    total_emotion_words += weighted
                    if emotion not in emotion_examples:
                        emotion_examples[emotion] = []
                    if len(emotion_examples[emotion]) < 3:
                        emotion_examples[emotion].append(word)

    if total_emotion_words == 0:
        return {"dominant": "unknown", "spectrum": {}, "interpretation": "未检测到明显情感词汇"}

    # 按加权频率排序
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

        # 比喻检测（扩展版：明喻 + 暗喻 + 借喻）
        # 明喻：像/如同/仿佛/似/宛如/犹如/好比
        # 暗喻：是/成了/化作/变为 + 自然意象
        # 转化式：化作/变成/融为
        metaphor_keywords = ["像", "如同", "仿佛", "似", "宛如", "犹如", "好比"]
        dark_metaphor_patterns = [
            r"(?:是|成了|化作|变为|变成).{1,8}(?:光|影|风|花|火|星|梦|尘|灰|夜|雨|雪|霜|露)",
            r"(?:化作|变成|融为|化为).{0,6}(?:一|的)",
        ]
        if any(w in text for w in metaphor_keywords) or any(
            re.search(pat, text) for pat in dark_metaphor_patterns
        ):
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
        negation_patterns = [
            r"(不|未|莫|别)\s*[是能为会有在到想需该]",
            r"(不|未|莫|别)\s*[让叫使把给向对]",
            r"没有",
            r"无法",
            r"并非",
            r"从不",
            r"绝不|决不",
            r"无人|无物|无端|无从",
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
    honorific = ["大人", "阁下", "殿下", "陛下", "先生", "小姐", "长官", "指挥官"]
    # 使用 2 字词组避免单字误报（"小"→"小心", "老"→"老师", "姐"→"姐姐"）
    intimate = ["亲爱的", "小家伙", "小可爱", "老朋友", "阿米娅", "姐姐", "哥哥", "妹妹", "弟弟", "姐", "哥"]

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
# 维度 8：口头禅与标志性短语检测
# ──────────────────────────────────────────────

def analyze_catchphrases(dialogues: list[dict], min_count: int = 3) -> dict:
    """
    维度 8：口头禅与标志性短语

    使用 n-gram 频率分析，找出角色特有的高频短语。
    与基线频率对比，筛选出显著高于基线的短语。

    Args:
        dialogues: 对话列表
        min_count: 最小出现次数阈值（默认 3 次）
    """
    if not dialogues:
        return {"signature_phrases": [], "interpretation": "无对话数据"}

    ngram_counter: Counter = Counter()
    total_chars = 0

    for d in dialogues:
        text = d.get("text", "")
        total_chars += len(text)
        # 提取 2~5 gram
        for n in range(2, 6):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                # 过滤纯标点、纯空格、纯数字
                if re.match(r'^[\s\d。！？…，、；：\u201c\u201d\u2018\u2019（）\u002d\u3000]+$', gram):
                    continue
                # 过滤以标点开头或结尾的 n-gram
                if gram[0] in "。！？…，、；：" or gram[-1] in "。！？…，、；：":
                    continue
                ngram_counter[gram] += 1

    total_lines = len(dialogues)
    signature_phrases: list[dict] = []

    for gram, count in ngram_counter.most_common(100):
        if count < min_count:
            break
        # 计算频率（每句出现次数）
        freq = count / total_lines
        # 显著性：频率 / 基线
        significance = freq / _CN_CHAR_FREQ_BASELINE if _CN_CHAR_FREQ_BASELINE > 0 else 0

        if significance > 2.0:  # 至少是基线的 2 倍
            signature_phrases.append({
                "phrase": gram,
                "count": count,
                "frequency_per_line": round(freq, 3),
                "significance": round(significance, 1),
            })

        # 最多保留 20 个
        if len(signature_phrases) >= 20:
            break

    # 去重：如果 "ABC" 和 "AB" 都出现，且 "AB" 的频率与 "ABC" 相近，保留更长的
    filtered: list[dict] = []
    seen_prefixes: set[str] = set()
    for sp in sorted(signature_phrases, key=lambda x: -len(x["phrase"])):
        phrase = sp["phrase"]
        # 检查是否是已保留短语的子串
        is_sub = False
        for prefix in seen_prefixes:
            if phrase in prefix:
                is_sub = True
                break
        if not is_sub:
            filtered.append(sp)
            seen_prefixes.add(phrase)

    # 按频率排序
    filtered.sort(key=lambda x: -x["count"])
    top_phrases = filtered[:15]

    if top_phrases:
        top3 = "、".join(f'"{p["phrase"]}"({p["count"]}次)' for p in top_phrases[:3])
        interp = f"标志性短语：{top3}"
    else:
        interp = "未检测到显著口头禅"

    return {
        "signature_phrases": top_phrases,
        "total_unique_ngrams": len(ngram_counter),
        "interpretation": interp,
    }


# ──────────────────────────────────────────────
# 单次遍历收集器（性能优化：将 7 次遍历合并为 1 次）
# ──────────────────────────────────────────────

# 预编译否定句正则（避免每次循环重复编译）
_NEGATION_PATTERNS = [
    re.compile(r"(不|未|莫|别)\s*[是能为会有在到想需该]"),
    re.compile(r"(不|未|莫|别)\s*[让叫使把给向对]"),
    re.compile(r"没有"),
    re.compile(r"无法"),
    re.compile(r"并非"),
    re.compile(r"从不"),
    re.compile(r"绝不|决不"),
    re.compile(r"无人|无物|无端|无从"),
]

# 预编译修辞关键词
_RHETORICAL_WORDS = ["难道", "岂", "何不", "又怎么", "又如何", "不是吗"]
_METAPHOR_WORDS = ["像", "如同", "仿佛", "似", "宛如", "犹如", "好比"]
# 暗喻检测正则（扩展版）
_DARK_METAPHOR_PATTERNS = [
    re.compile(r"(?:是|成了|化作|变为|变成).{1,8}(?:光|影|风|花|火|星|梦|尘|灰|夜|雨|雪|霜|露)"),
    re.compile(r"(?:化作|变成|融为|化为).{0,6}(?:一|的)"),
]

# 称呼词
_HONORIFIC = ["大人", "阁下", "殿下", "陛下", "先生", "小姐", "长官", "指挥官"]
_INTIMATE = ["亲爱的", "小家伙", "小可爱", "老朋友", "阿米娅", "姐姐", "哥哥", "妹妹", "弟弟", "姐", "哥"]

# 自然意象词典
_NATURE_WORDS = {
    "植物": ["花朵", "花瓣", "花开", "花落", "草木", "树叶", "枝头", "藤蔓", "森林", "丛林", "花草"],
    "天文": ["星空", "星辰", "月光", "阳光", "光影", "天空", "云霞", "彩虹", "星光", "夜空", "日光"],
    "气象": ["风雨", "风声", "微风", "暴风", "雨幕", "雪花", "霜降", "雾气", "雷鸣", "露水", "晨露"],
    "大地": ["山河", "大海", "大地", "土地", "岩石", "沙漠", "泉水", "山峦", "河川", "海洋", "山巅"],
    "时间": ["清晨", "日暮", "夜晚", "白昼", "春天", "夏日", "秋色", "冬雪", "黄昏", "黎明", "破晓"],
}


def _collect_all_metrics(dialogues: list[dict]) -> dict:
    """
    单次遍历收集所有 7 个维度的原始指标数据。

    返回一个 dict，包含各维度所需的原始计数/列表，
    后续由各维度的结果函数分别处理。
    """
    # 维度 1: 句式长度
    sentence_lengths: list[int] = []

    # 维度 2: 停顿标记
    ellipsis_count = 0
    ellipsis_start = 0
    dash_count = 0
    exclamation_count = 0
    question_count = 0

    # 维度 3: 自称
    pronoun_counter: Counter = Counter()
    total_first_person = 0

    # 维度 4: 情感词汇
    emotion_counts: Counter = Counter()
    total_emotion_words = 0
    emotion_examples: dict[str, list[str]] = {}

    # 维度 5: 修辞
    rhetorical_question = 0
    metaphor = 0
    parallelism = 0
    negation = 0

    # 维度 6: 称呼
    honorific_count = 0
    intimate_count = 0
    address_examples: dict[str, list[str]] = {"honorific": [], "intimate": []}

    # 维度 7: 自然意象
    nature_category_counts: Counter = Counter()
    total_nature = 0
    nature_top_words: Counter = Counter()

    total_lines = len(dialogues)

    for d in dialogues:
        text = d.get("text", "")

        # ── 维度 1: 句式长度 ──
        for s in split_sentences(text):
            sentence_lengths.append(len(s))

        # ── 维度 2: 停顿标记 ──
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

        # ── 维度 3: 自称 ──
        for pronoun in FIRST_PERSON:
            count = text.count(pronoun)
            if count > 0:
                pronoun_counter[pronoun] += count
                total_first_person += count

        # ── 维度 4: 情感词汇（带权重） ──
        for emotion, word_entries in EMOTION_LEXICON.items():
            for word, weight in word_entries:
                count = text.count(word)
                if count > 0:
                    weighted = count * weight
                    emotion_counts[emotion] += weighted
                    total_emotion_words += weighted
                    if emotion not in emotion_examples:
                        emotion_examples[emotion] = []
                    if len(emotion_examples[emotion]) < 3:
                        emotion_examples[emotion].append(word)

        # ── 维度 5: 修辞 ──
        has_question = any(q in text for q in QUESTION)
        has_rhetorical = any(w in text for w in _RHETORICAL_WORDS)
        if has_question and has_rhetorical:
            rhetorical_question += 1

        if any(w in text for w in _METAPHOR_WORDS) or any(
            pat.search(text) for pat in _DARK_METAPHOR_PATTERNS
        ):
            metaphor += 1

        comma_phrases = re.split(r"[，、；]", text)
        if len(comma_phrases) >= 3:
            starts = [p.strip()[:2] for p in comma_phrases if len(p.strip()) >= 2]
            if len(starts) >= 3:
                start_counter = Counter(starts)
                if start_counter.most_common(1)[0][1] >= 3:
                    parallelism += 1

        if any(pat.search(text) for pat in _NEGATION_PATTERNS):
            negation += 1

        # ── 维度 6: 称呼 ──
        for h in _HONORIFIC:
            if h in text:
                honorific_count += 1
                if len(address_examples["honorific"]) < 5:
                    address_examples["honorific"].append(text[:50])
                break
        for i in _INTIMATE:
            if i in text:
                intimate_count += 1
                if len(address_examples["intimate"]) < 5:
                    address_examples["intimate"].append(text[:50])
                break

        # ── 维度 7: 自然意象 ──
        for category, words in _NATURE_WORDS.items():
            for word in words:
                count = text.count(word)
                if count > 0:
                    nature_category_counts[category] += count
                    total_nature += count
                    nature_top_words[word] += count

    return {
        "total_lines": total_lines,
        # 维度 1
        "sentence_lengths": sentence_lengths,
        # 维度 2
        "ellipsis_count": ellipsis_count,
        "ellipsis_start": ellipsis_start,
        "dash_count": dash_count,
        "exclamation_count": exclamation_count,
        "question_count": question_count,
        # 维度 3
        "pronoun_counter": pronoun_counter,
        "total_first_person": total_first_person,
        # 维度 4
        "emotion_counts": emotion_counts,
        "total_emotion_words": total_emotion_words,
        "emotion_examples": emotion_examples,
        # 维度 5
        "rhetorical_question": rhetorical_question,
        "metaphor": metaphor,
        "parallelism": parallelism,
        "negation": negation,
        # 维度 6
        "honorific_count": honorific_count,
        "intimate_count": intimate_count,
        "address_examples": address_examples,
        # 维度 7
        "nature_category_counts": nature_category_counts,
        "total_nature": total_nature,
        "nature_top_words": nature_top_words,
    }


def _result_sentence_length(m: dict) -> dict:
    """从收集器数据生成维度 1 结果（统计分布升级版）"""
    lengths = m["sentence_lengths"]
    if not lengths:
        return {"type": "unknown", "avg": 0, "distribution": {}}

    avg_len = sum(lengths) / len(lengths)
    total = len(lengths)

    # 统计分布指标
    median_len = statistics.median(lengths)
    stdev_len = statistics.stdev(lengths) if total > 1 else 0
    cv = stdev_len / median_len if median_len > 0 else 0

    if total >= 4:
        q1, q2, q3 = statistics.quantiles(lengths, n=4)
    else:
        q1 = min(lengths)
        q2 = median_len
        q3 = max(lengths)

    # 自适应分界
    short = sum(1 for ln in lengths if ln <= q1)
    medium = sum(1 for ln in lengths if q1 < ln <= q3)
    long = sum(1 for ln in lengths if ln > q3)

    distribution = {
        "short_pct": round(short / total * 100, 1),
        "medium_pct": round(medium / total * 100, 1),
        "long_pct": round(long / total * 100, 1),
    }

    # 节奏稳定性
    if cv < 0.4:
        rhythm = "稳定"
    elif cv < 0.7:
        rhythm = "多变"
    else:
        rhythm = "极端交替"

    if distribution["short_pct"] > 50:
        stype = "短句型"
    elif distribution["long_pct"] > 40:
        stype = "长句型"
    elif distribution["short_pct"] > 25 and distribution["long_pct"] > 25:
        stype = "长短交替型"
    else:
        stype = "中句型"

    return {
        "type": stype,
        "avg_length": round(avg_len, 1),
        "median": round(median_len, 1),
        "stdev": round(stdev_len, 1),
        "cv": round(cv, 2),
        "rhythm": rhythm,
        "percentiles": {"p25": round(q1, 1), "p50": round(q2, 1), "p75": round(q3, 1)},
        "min": min(lengths),
        "max": max(lengths),
        "distribution_pct": distribution,
        "sample_count": total,
    }


def _result_pause_markers(m: dict) -> dict:
    """从收集器数据生成维度 2 结果"""
    total = m["total_lines"]
    if total == 0:
        return {"ellipsis_freq": 0, "exclamation_freq": 0}

    return {
        "ellipsis_pct": round(m["ellipsis_count"] / total * 100, 1),
        "ellipsis_start_pct": round(m["ellipsis_start"] / total * 100, 1),
        "dash_pct": round(m["dash_count"] / total * 100, 1),
        "exclamation_pct": round(m["exclamation_count"] / total * 100, 1),
        "question_pct": round(m["question_count"] / total * 100, 1),
        "interpretation": _interpret_pause(
            m["ellipsis_count"] / total,
            m["exclamation_count"] / total,
            m["ellipsis_start"] / total,
        ),
    }


def _result_self_reference(m: dict) -> dict:
    """从收集器数据生成维度 3 结果"""
    counter = m["pronoun_counter"]
    total_fp = m["total_first_person"]
    total_lines = m["total_lines"]

    if total_fp == 0:
        return {
            "primary": "省略自称",
            "frequency_per_line": 0,
            "distribution": {},
            "interpretation": "极少使用第一人称，倾向省略主语或使用'我们'",
        }

    primary = counter.most_common(1)[0][0]
    freq = round(total_fp / total_lines, 2) if total_lines > 0 else 0
    distribution = {k: round(v / total_fp * 100, 1) for k, v in counter.most_common()}

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


def _result_emotion_vocabulary(m: dict) -> dict:
    """从收集器数据生成维度 4 结果"""
    emotion_counts = m["emotion_counts"]
    total_ew = m["total_emotion_words"]
    emotion_examples = m["emotion_examples"]

    if total_ew == 0:
        return {"dominant": "unknown", "spectrum": {}, "interpretation": "未检测到明显情感词汇"}

    sorted_emotions = emotion_counts.most_common()
    dominant = sorted_emotions[0][0] if sorted_emotions else "unknown"
    spectrum = {k: round(v / total_ew * 100, 1) for k, v in sorted_emotions}

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


def _result_rhetoric_patterns(m: dict) -> dict:
    """从收集器数据生成维度 5 结果"""
    total = m["total_lines"]
    if total == 0:
        return {"rhetorical_question_freq": 0}

    return {
        "rhetorical_question_pct": round(m["rhetorical_question"] / total * 100, 1),
        "metaphor_pct": round(m["metaphor"] / total * 100, 1),
        "parallelism_pct": round(m["parallelism"] / total * 100, 1),
        "negation_pct": round(m["negation"] / total * 100, 1),
        "interpretation": _interpret_rhetoric(
            m["rhetorical_question"] / total,
            m["metaphor"] / total,
            m["negation"] / total,
        ),
    }


def _result_address_pattern(m: dict) -> dict:
    """从收集器数据生成维度 6 结果"""
    total = m["total_lines"]
    hc = m["honorific_count"]
    ic = m["intimate_count"]

    if total == 0:
        return {"pattern": "unknown"}

    if hc > ic * 2:
        pattern = "尊称型"
    elif ic > hc * 2:
        pattern = "亲昵型"
    elif hc > 0 and ic > 0:
        pattern = "切换型"
    else:
        pattern = "省略称呼型"

    return {
        "pattern": pattern,
        "honorific_pct": round(hc / total * 100, 1),
        "intimate_pct": round(ic / total * 100, 1),
        "examples": m["address_examples"],
    }


def _result_natural_imagery(m: dict) -> dict:
    """从收集器数据生成维度 7 结果"""
    total_nature = m["total_nature"]
    if total_nature == 0:
        return {"density": 0, "interpretation": "极少使用自然意象"}

    total_lines = m["total_lines"]
    density = round(total_nature / total_lines, 2) if total_lines > 0 else 0

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
            for k, v in m["nature_category_counts"].most_common()
        },
        "top_5_words": dict(m["nature_top_words"].most_common(5)),
        "interpretation": f"自然意象密度{density_level}（{density}个/句），偏好{_top_category(m['nature_category_counts'])}意象",  # noqa: E501  (中文消息折行破坏可读性)
    }


# ──────────────────────────────────────────────
# 主分析流程
# ──────────────────────────────────────────────

def generate_fingerprint(dialogues: list[dict], operator_name: str = "unknown") -> dict:
    """
    生成完整的语言指纹报告（单次遍历优化版 + 维度8口头禅）
    """
    metrics = _collect_all_metrics(dialogues)

    report = {
        "operator": operator_name,
        "dialogue_count": len(dialogues),
        "dimensions": {
            "1_sentence_length": _result_sentence_length(metrics),
            "2_pause_markers": _result_pause_markers(metrics),
            "3_self_reference": _result_self_reference(metrics),
            "4_emotion_vocabulary": _result_emotion_vocabulary(metrics),
            "5_rhetoric_patterns": _result_rhetoric_patterns(metrics),
            "6_address_pattern": _result_address_pattern(metrics),
            "7_natural_imagery": _result_natural_imagery(metrics),
            "8_catchphrases": analyze_catchphrases(dialogues),
        },
    }

    # 生成综合画像摘要
    report["summary"] = _generate_summary(report["dimensions"])

    return report


def _generate_summary(dimensions: dict) -> str:
    """
    从 8 个维度生成一段自然语言的角色语言画像摘要
    """
    parts = []

    d1 = dimensions["1_sentence_length"]
    rhythm_note = f"，节奏{d1['rhythm']}" if d1.get("rhythm") else ""
    parts.append(f"句式{d1.get('type', '未知')}，平均{d1.get('avg_length', 0)}字{rhythm_note}")

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

    d8 = dimensions.get("8_catchphrases", {})
    if d8.get("signature_phrases"):
        parts.append(d8.get("interpretation", ""))

    return "；".join(p for p in parts if p)


# ──────────────────────────────────────────────
# 语境化分析（升级新增）
# ──────────────────────────────────────────────

def _lines_to_dialogues(annotated_lines: list[dict], source_filter: str = None) -> list[dict]:
    """将 context.json 的 annotated_lines 转为 fingerprint 兼容的 dialogues 格式"""
    result = []
    for line in annotated_lines:
        if source_filter and line.get("source") != source_filter:
            continue
        if line.get("source") == "archive":
            continue
        text = line.get("text", "")
        if not text or not text.strip():  # 跳过空文本
            continue
        result.append({"label": line.get("source_detail", ""), "text": text})
    return result


def generate_contextual_fingerprint(context: dict) -> dict:
    """
    语境化指纹分析：在全局指纹基础上，按场景/对象/时期分片分析
    """
    lines = context.get("annotated_lines", [])
    operator_name = context.get("character", "unknown")

    # 全局指纹
    all_dialogues = _lines_to_dialogues(lines)
    global_fp = generate_fingerprint(all_dialogues, operator_name)

    result = {
        "operator": operator_name,
        "mode": "contextual",
        "global": global_fp,
        "slices": {},
        "shifts": {},
    }

    # ── 按场景分片 ──
    by_situation = {}
    for line in lines:
        if line.get("source") == "archive":
            continue
        sit = line.get("context", {}).get("situation_type", "unknown")
        by_situation.setdefault(sit, []).append(line)

    for sit, sit_lines in by_situation.items():
        if len(sit_lines) < 2:
            continue
        dialogues = _lines_to_dialogues(sit_lines)
        result["slices"][f"situation:{sit}"] = generate_fingerprint(dialogues, operator_name)

    # ── 按对话对象分片 ──
    by_interlocutor = {}
    for line in lines:
        if line.get("source") == "archive":
            continue
        person = line.get("context", {}).get("interlocutor") or "unknown"
        by_interlocutor.setdefault(person, []).append(line)

    for person, person_lines in by_interlocutor.items():
        if len(person_lines) < 2:
            continue
        dialogues = _lines_to_dialogues(person_lines)
        result["slices"][f"interlocutor:{person}"] = generate_fingerprint(dialogues, operator_name)

    # ── 按时期分片 ──
    by_phase = {}
    for line in lines:
        if line.get("source") == "archive":
            continue
        phase = line.get("context", {}).get("phase", "unknown")
        if phase == "unknown":
            continue
        by_phase.setdefault(phase, []).append(line)

    for phase, phase_lines in by_phase.items():
        if len(phase_lines) < 2:
            continue
        dialogues = _lines_to_dialogues(phase_lines)
        result["slices"][f"phase:{phase}"] = generate_fingerprint(dialogues, operator_name)

    # ── 计算分片偏移（shifts） ──
    result["shifts"] = compute_shifts(global_fp, result["slices"])

    return result


def compute_shifts(global_fp: dict, slices: dict) -> dict:
    """
    计算各分片与全局指纹的差异（shifts）
    输出可直接写入 Persona Layer 的行为偏移规则
    """
    shifts = {}
    global_dims = global_fp.get("dimensions", {})

    for slice_key, slice_fp in slices.items():
        slice_dims = slice_fp.get("dimensions", {})
        diff_items = []

        # 句式长度偏移
        g_avg = global_dims.get("1_sentence_length", {}).get("avg_length", 0)
        s_avg = slice_dims.get("1_sentence_length", {}).get("avg_length", 0)
        if g_avg > 0 and abs(s_avg - g_avg) / g_avg > 0.3:
            direction = "偏短" if s_avg < g_avg else "偏长"
            diff_items.append({
                "dimension": "sentence_length",
                "global_avg": g_avg,
                "slice_avg": s_avg,
                "shift": direction,
                "magnitude": round(abs(s_avg - g_avg) / g_avg, 2),
            })

        # 省略号频率偏移
        g_ell = global_dims.get("2_pause_markers", {}).get("ellipsis_pct", 0)
        s_ell = slice_dims.get("2_pause_markers", {}).get("ellipsis_pct", 0)
        if g_ell > 0 and abs(s_ell - g_ell) / g_ell > 0.4:
            direction = "更多沉默" if s_ell > g_ell else "更少沉默"
            diff_items.append({
                "dimension": "ellipsis",
                "global_pct": g_ell,
                "slice_pct": s_ell,
                "shift": direction,
                "magnitude": round(abs(s_ell - g_ell) / g_ell, 2),
            })
        elif g_ell == 0 and s_ell > 20:
            # 全局无省略号但切片有明显省略号使用
            diff_items.append({
                "dimension": "ellipsis",
                "global_pct": g_ell,
                "slice_pct": s_ell,
                "shift": "出现沉默标记（全局无）",
                "magnitude": round(s_ell / 100, 2),
            })

        # 情感主导偏移
        g_dom = global_dims.get("4_emotion_vocabulary", {}).get("dominant", "")
        s_dom = slice_dims.get("4_emotion_vocabulary", {}).get("dominant", "")
        if g_dom and s_dom and g_dom != s_dom:
            diff_items.append({
                "dimension": "emotion_dominant",
                "global_dominant": g_dom,
                "slice_dominant": s_dom,
                "shift": f"从'{g_dom}'偏移到'{s_dom}'",
            })

        # 否定句频率偏移
        g_neg = global_dims.get("5_rhetoric_patterns", {}).get("negation_pct", 0)
        s_neg = slice_dims.get("5_rhetoric_patterns", {}).get("negation_pct", 0)
        if g_neg > 0 and abs(s_neg - g_neg) / g_neg > 0.4:
            direction = "更多否定" if s_neg > g_neg else "更少否定"
            diff_items.append({
                "dimension": "negation",
                "global_pct": g_neg,
                "slice_pct": s_neg,
                "shift": direction,
                "magnitude": round(abs(s_neg - g_neg) / g_neg, 2),
            })
        elif g_neg == 0 and s_neg > 20:
            # 全局无否定句但切片有显著否定句使用
            diff_items.append({
                "dimension": "negation",
                "global_pct": g_neg,
                "slice_pct": s_neg,
                "shift": "出现否定表达（全局无）",
                "magnitude": round(s_neg / 100, 2),
            })

        if diff_items:
            shifts[slice_key] = diff_items

    return shifts


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="对话指纹分析器 — 从角色对话中提取量化语言特征（支持语境化分析）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 传统模式
  python dialogue_fingerprint.py --input ./theresa_lines.txt --format plain
  python dialogue_fingerprint.py --input ./theresa_voices.json --format prts-json

  # 语境化模式
  python dialogue_fingerprint.py --context-json operators/te-lei-xi-ya/context.json
        """,
    )

    # 传统模式参数
    parser.add_argument("--input", help="对话数据文件路径（传统模式）")
    parser.add_argument("--format", choices=["plain", "prts-json", "csv"], default="plain", help="数据格式")
    parser.add_argument("--name", default="unknown", help="角色名称")

    # 语境化模式参数
    parser.add_argument("--context-json", help="context.json 路径（语境化模式）")

    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    # 互斥校验
    if args.context_json and args.input:
        print("错误：--context-json 和 --input 互斥，请选择一种模式", file=sys.stderr)
        sys.exit(1)

    if not args.context_json and not args.input:
        print("错误：请指定 --context-json（语境化模式）或 --input（传统模式）", file=sys.stderr)
        sys.exit(1)

    if args.context_json:
        # 语境化模式
        with open(args.context_json, encoding='utf-8') as f:
            context = json.load(f)
        report = generate_contextual_fingerprint(context)
    else:
        # 传统模式
        dialogues = load_dialogues(args.input, args.format)
        if not dialogues:
            print("错误：未找到任何对话数据", file=sys.stderr)
            sys.exit(1)
        report = generate_fingerprint(dialogues, args.name)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"指纹报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
