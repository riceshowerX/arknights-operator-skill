#!/usr/bin/env python3
"""
关系图谱构建器 —— 从文本中自动提取角色关系网络

这是 arknights-operator-skill 的核心差异化工具之一：
不依赖手动填写关系，而是从角色资料/剧情文本中自动识别关系模式。

升级版：支持语境化模式，从 context.json 提取时序关系。
  - 传统模式：--input/--format（分析原始文本文件）
  - 语境化模式：--context-json（消费 context.json，按时期分片提取关系）

语境化模式会输出 per-phase 的关系切片，以及跨时期的关系演变轨迹，
直接写入 context.json 的 annotated_relations 字段。

用法:
    # 传统模式
    python relationship_graph.py --input ./knowledge.md --format markdown

    # 语境化模式
    python relationship_graph.py --context-json operators/te-lei-xi-ya/context.json

    # 语境化 + 自定义角色名库
    python relationship_graph.py --context-json context.json --operator-db custom_db.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import assets
import cli
from constants import PHASE_ORDER
from shared_utils import atomic_write_json, atomic_write_text, read_text_utf8, setup_logging
from shared_utils import split_sentences as _shared_split_sentences

logger = setup_logging("relationship_graph")


# ──────────────────────────────────────────────
# 明日方舟角色名库（用于文本中的实体识别）
# ──────────────────────────────────────────────

# 内建默认角色名库（仅作 fallback，优先从资产目录的 operator_db.json 加载）
# 要扩展名库，编辑 tools/_data/operator_db.json 或使用 --operator-db 指定自定义文件。

_OPERATOR_DB_BUILTIN = {
    # 巴别塔/罗德岛核心
    "特蕾西娅": {"en": "Theresa", "race": "萨卡兹", "faction": "巴别塔"},
    "特雷西斯": {"en": "Theresis", "race": "萨卡兹", "faction": "卡兹戴尔"},
    "阿米娅": {"en": "Amiya", "race": "卡特斯", "faction": "罗德岛"},
    "博士": {"en": "Doctor", "race": "未知", "faction": "罗德岛"},
    "凯尔希": {"en": "Kal'tsit", "race": "菲林", "faction": "罗德岛"},
    "可露希尔": {"en": "Closure", "race": "吸血鬼", "faction": "罗德岛"},
    "W": {"en": "Wiš'adel", "race": "萨卡兹", "faction": "罗德岛"},
    "维什戴尔": {"en": "Wiš'adel", "race": "萨卡兹", "faction": "罗德岛"},
    # 整合运动
    "塔露拉": {"en": "Talulah", "race": "德拉克", "faction": "整合运动"},
    "爱国者": {"en": "Patriot", "race": "萨卡兹", "faction": "整合运动"},
    "霜星": {"en": "FrostNova", "race": "萨卡兹", "faction": "整合运动"},
    "梅菲斯特": {"en": "Mephisto", "race": "里拉", "faction": "整合运动"},
    "浮士德": {"en": "Faust", "race": "萨卡兹", "faction": "整合运动"},
    # 龙门
    "陈": {"en": "Ch'en", "race": "德拉克", "faction": "龙门"},
    "星熊": {"en": "Hoshiguma", "race": "鬼", "faction": "龙门"},
    # 莱茵生命
    "塞雷娅": {"en": "Saria", "race": "瓦伊凡", "faction": "莱茵生命"},
    "伊芙利特": {"en": "Ifrit", "race": "萨卡兹", "faction": "莱茵生命"},
    "赫默": {"en": "Silence", "race": "里拉", "faction": "莱茵生命"},
    # 维多利亚/伦蒂尼姆
    "推进之王": {"en": "Siege", "race": "阿斯兰", "faction": "维多利亚"},
    "因陀罗": {"en": "Indra", "race": "维多利亚", "faction": "维多利亚"},
    "达格达": {"en": "Dagda", "race": "阿斯兰", "faction": "维多利亚"},
    "号角": {"en": "Horn", "race": "鲁珀", "faction": "维多利亚"},
    "风笛": {"en": "Bagpipe", "race": "瑞柏巴", "faction": "维多利亚"},
    # 卡兹戴尔/萨卡兹佣兵
    "赫德雷": {"en": "Hoederer", "race": "萨卡兹", "faction": "卡兹戴尔"},
    "伊内丝": {"en": "Ines", "race": "卡普里尼", "faction": "卡兹戴尔"},
    "罗德岛精英干员Scout": {"en": "Scout", "race": "萨卡兹", "faction": "罗德岛"},
    "迷迭香": {"en": "Rosa", "race": "斐迪亚", "faction": "罗德岛"},
    "Logos": {"en": "Logos", "race": "萨卡兹", "faction": "罗德岛"},
    "赦罪师": {"en": "Confessor", "race": "萨卡兹", "faction": "卡兹戴尔"},
    "军事委员会": {"en": "Military Commission", "race": "萨卡兹", "faction": "卡兹戴尔"},
    # 其他
    "银灰": {"en": "SilverAsh", "race": "菲林", "faction": "喀兰贸易"},
    "煌": {"en": "Blaze", "race": "萨卡兹", "faction": "罗德岛"},
}

# 内建别名映射（仅作 fallback）
_ALIAS_MAP_BUILTIN = {
    "Theresa": "特蕾西娅",
    "Theresis": "特雷西斯",
    "Amiya": "阿米娅",
    "Doctor": "博士",
    "Kal'tsit": "凯尔希",
    "Closure": "可露希尔",
    "Wiš'adel": "W",
    "W": "W",
    "维什戴尔": "维什戴尔",
    "Talulah": "塔露拉",
    "Ch'en": "陈",
    "Saria": "塞雷娅",
    "Ifrit": "伊芙利特",
    "SilverAsh": "银灰",
    "Blaze": "煌",
    "爱国者": "爱国者",
    "Patriot": "爱国者",
    "FrostNova": "霜星",
    # 维多利亚/伦蒂尼姆
    "Siege": "推进之王",
    "维娜": "推进之王",
    "Horn": "号角",
    "Bagpipe": "风笛",
    # 卡兹戴尔/萨卡兹佣兵
    "Hoederer": "赫德雷",
    "Ines": "伊内丝",
    "Scout": "罗德岛精英干员Scout",
    "Rosa": "迷迭香",
    "Logos": "Logos",
    "Mephisto": "梅菲斯特",
    "Faust": "浮士德",
    "Hoshiguma": "星熊",
    "Silence": "赫默",
    "Indra": "因陀罗",
    "Dagda": "达格达",
    "Confessor": "赦罪师",
    "Military Commission": "军事委员会",
    # 中文别称
    "魔王": "特蕾西娅",
    "兄长": "特雷西斯",
    "小兔子": "阿米娅",
    "老女人": "凯尔希",
    "凯太后": "凯尔希",
    "赫总": "赫德雷",
    "伊内丝小姐": "伊内丝",
}


# 角色名库「读不出来」的哨兵值（用于区分「解析失败」与「合法空对象」）
_OPERATOR_DB_PAIR_SENTINEL: object = object()


def _load_operator_db_from_json(json_path: Path) -> tuple[dict, dict]:
    """从 JSON 文件加载角色名库和别名映射。

    JSON 格式:
    {
        "operators": {"特蕾西娅": {"en": "Theresa", ...}, ...},
        "aliases": {"Theresa": "特蕾西娅", ...}
    }
    """
    # 读 + 解析（失败回退内建名库）统一走 assets.load_json_or
    raw = assets.load_json_or(json_path, _OPERATOR_DB_PAIR_SENTINEL, kind="角色名库")
    if raw is _OPERATOR_DB_PAIR_SENTINEL:
        # 文件不存在（无告警）或解析失败（已告警）：直接使用内建名库
        return _OPERATOR_DB_BUILTIN, _ALIAS_MAP_BUILTIN

    if not isinstance(raw, dict):
        logger.warning("角色名库文件格式错误（应为对象）%s，使用内建名库", json_path)
        return _OPERATOR_DB_BUILTIN, _ALIAS_MAP_BUILTIN

    db = dict(_OPERATOR_DB_BUILTIN)
    aliases = dict(_ALIAS_MAP_BUILTIN)

    # 合并 JSON 中的 operators（覆盖内建同名项）
    custom_ops = raw.get("operators", {})
    if isinstance(custom_ops, dict):
        db.update(custom_ops)

    # 合并别名
    custom_aliases = raw.get("aliases", {})
    if isinstance(custom_aliases, dict):
        aliases.update(custom_aliases)

    return db, aliases


def _fetch_operators_from_prts() -> dict | None:
    """从 PRTS API 动态拉取角色列表，用于扩展名库覆盖率。

    仅在名库未通过 --operator-db 指定时尝试拉取。
    拉取失败不影响功能（使用内建名库 fallback）。

    Returns:
        角色信息 dict，或 None（拉取失败时）
    """
    try:
        from prts_client import fetch_page_wikitext
        # 拉取干员列表页（分类页面包含所有干员链接）
        wikitext = fetch_page_wikitext("干员一览")
        if not wikitext:
            return None

        # 从 wikitext 提取角色名（[[角色名]] 或 [[角色名|显示名]] 链接）
        names = re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', wikitext)
        operators: dict[str, dict] = {}
        for name in names:
            name = name.strip()
            # 过滤非角色页面
            if len(name) < 2 or name.startswith("模板") or name.startswith("分类"):
                continue
            if name not in operators:
                operators[name] = {}  # 仅名称，详细字段由后续按需查询填充
        return operators if operators else None

    except Exception as e:
        print(f"提示：PRTS 动态拉取角色列表失败: {e}，使用本地名库", file=sys.stderr)
        return None


def load_operator_db(filepath: str | None = None) -> tuple[dict, dict]:
    """
    加载角色名库和别名映射

    加载优先级：
    1. --operator-db 指定的自定义 JSON 文件
    2. 资产目录下的 operator_db.json（包内 tools/_data/，或仓库根 data/ 覆盖位）
    3. 尝试从 PRTS API 动态拉取（仅补充名称，不覆盖内建详情）
    4. 内建硬编码名库（最终 fallback）

    外部文件与内建名库合并（外部覆盖内置同名项）
    """
    # 优先级 1：自定义文件
    if filepath:
        path = Path(filepath)
        if path.exists():
            return _load_operator_db_from_json(path)
        print(f"警告：角色名库文件不存在 {filepath}，使用内置名库", file=sys.stderr)
        return _OPERATOR_DB_BUILTIN, _ALIAS_MAP_BUILTIN

    # 优先级 2：默认资产目录下的 operator_db.json（tools/_data，或仓库根 data/ 覆盖位）
    default_path = assets.data_file("operator_db.json")
    if default_path.exists():
        return _load_operator_db_from_json(default_path)

    # 优先级 3：尝试 PRTS 动态拉取
    prts_ops = _fetch_operators_from_prts()
    if prts_ops:
        db = dict(_OPERATOR_DB_BUILTIN)
        # 动态拉取仅补充名称，不覆盖内建的详细字段
        for name, info in prts_ops.items():
            if name not in db:
                db[name] = info
        return db, _ALIAS_MAP_BUILTIN

    # 优先级 4：内建 fallback
    return _OPERATOR_DB_BUILTIN, _ALIAS_MAP_BUILTIN


# ──────────────────────────────────────────────
# 关系模式识别
# ──────────────────────────────────────────────

RELATIONSHIP_PATTERNS = [
    # 亲属关系
    (r"胞兄|哥哥|兄长|亲兄", "sibling"),
    (r"胞妹|妹妹|亲妹|姐姐", "sibling"),
    (r"父亲|母亲|父|母|养育|抚养", "parent_child"),
    (r"女儿|儿子|孩子|继承者|传人", "parent_child"),

    # 战友关系
    (r"战友|同袍|并肩|一起战斗|共同", "comrade"),
    (r"部下|追随者|手下|部属", "subordinate"),
    (r"上级|长官|领袖|领导", "superior"),

    # 对抗关系
    (r"敌人|对手|对抗|对立|敌对|反对", "opponent"),
    (r"内战|交战|战斗|战争", "opponent"),

    # 信任关系
    (r"信任|相信|托付|依赖|依靠|信赖", "trust"),
    (r"背叛|出卖|欺骗", "betrayal"),

    # 师徒/教导
    (r"教导|教授|培养|训练|指导|师父|师傅", "mentor"),
    (r"学生|徒弟|学到了|教会", "student"),

    # 情感
    (r"温柔|关怀|呵护|珍视|在乎|牵挂", "affection"),
    (r"恨|愤怒|厌恶|憎恨", "hatred"),
]


def normalize_name(name: str, operator_db: dict | None = None, alias_map: dict | None = None) -> str | None:
    """将名称标准化为中文名"""
    db = operator_db or _OPERATOR_DB_BUILTIN
    aliases = alias_map or _ALIAS_MAP_BUILTIN

    name = name.strip()
    if name in db:
        return name
    if name in aliases:
        return aliases[name]
    for cn, info in db.items():
        if info.get("en", "").lower() == name.lower():
            return cn
    return None


def _is_name_in_text(name: str, text: str) -> bool:
    """检查角色名是否出现在文本中，对单字名做词边界检查。

    规则：
    - 多字中文名：直接用子串匹配（足够精确）
    - 单字中文名：要求两侧都不是CJK字符或边界（防止"陈旧"误匹配"陈"）
    - 英文单字名：要求前后不是英文字母或数字（防止"WT"误匹配"W"）
    """
    if len(name) >= 2:
        return name in text

    ch = name
    if re.match(r'[a-zA-Z]', ch):
        return bool(re.search(r'(?<![a-zA-Z0-9])' + re.escape(ch) + r'(?![a-zA-Z0-9])', text))
    else:
        for m in re.finditer(re.escape(ch), text):
            start, end = m.start(), m.end()
            has_cjk_before = start > 0 and bool(re.match(r'[\u4e00-\u9fff]', text[start - 1]))
            has_cjk_after = end < len(text) and bool(re.match(r'[\u4e00-\u9fff]', text[end]))
            if not has_cjk_before and not has_cjk_after:
                return True
        return False


class _AhoCorasick:
    """轻量级 Aho-Corasick 多模式匹配自动机

    用于在单次遍历中检测文本中是否包含多个模式字符串，
    替代逐个遍历的 O(n×m) 方案。
    """

    __slots__ = ("_goto", "_fail", "_output", "_built")

    def __init__(self) -> None:
        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._output: list[list[str]] = [[]]
        self._built = False

    def add_pattern(self, pattern: str, label: str) -> None:
        """添加一个模式字符串及其关联标签"""
        state = 0
        for ch in pattern:
            if ch not in self._goto[state]:
                self._goto[state][ch] = len(self._goto)
                self._goto.append({})
                self._fail.append(0)
                self._output.append([])
            state = self._goto[state][ch]
        self._output[state].append(label)
        self._built = False

    def build(self) -> None:
        """构建失败链接（BFS）"""
        from collections import deque
        queue: deque[int] = deque()
        for _ch, s in self._goto[0].items():
            self._fail[s] = 0
            queue.append(s)
        while queue:
            r = queue.popleft()
            for ch, s in self._goto[r].items():
                queue.append(s)
                state = self._fail[r]
                while state != 0 and ch not in self._goto[state]:
                    state = self._fail[state]
                self._fail[s] = self._goto[state].get(ch, 0)
                if self._fail[s] == s:
                    self._fail[s] = 0
                self._output[s] = self._output[s] + self._output[self._fail[s]]
        self._built = True

    def search(self, text: str) -> set[str]:
        """在文本中搜索所有匹配的模式标签"""
        if not self._built:
            self.build()
        found: set[str] = set()
        state = 0
        for ch in text:
            while state != 0 and ch not in self._goto[state]:
                state = self._fail[state]
            state = self._goto[state].get(ch, 0)
            for label in self._output[state]:
                found.add(label)
        return found


# 公共别名（供测试和外部使用）
AhoCorasickMatcher = _AhoCorasick

# 全局 Aho-Corasick 自动机缓存（按 operator_db + alias_map 的 key 集合构建）
_ac_cache: dict[frozenset, _AhoCorasick] = {}


def _build_ac_automaton(db: dict, aliases: dict) -> _AhoCorasick:
    """构建或获取缓存的 Aho-Corasick 自动机"""
    cache_key = frozenset(db.keys()) | frozenset(aliases.keys())
    if cache_key not in _ac_cache:
        ac = _AhoCorasick()
        for name in db:
            ac.add_pattern(name, name)
        for alias in aliases:
            ac.add_pattern(alias, f"alias:{alias}")
        ac.build()
        _ac_cache[cache_key] = ac
    return _ac_cache[cache_key]


def extract_entities(text: str, operator_db: dict | None = None, alias_map: dict | None = None) -> list[str]:
    """从文本中提取出现的角色名

    使用 Aho-Corasick 多模式匹配，单次遍历文本即可检测所有角色名，
    时间复杂度从 O(n×m) 降为 O(n + m + 匹配数)。
    匹配后仍应用边界检查（CJK/英文边界）过滤误匹配。

    确定性：Aho-Corasick 的 `search()` 返回 ``set[str]``，直接迭代会让实体顺序
    随 ``PYTHONHASHSEED`` 变化（v3.5.1 起的既存缺陷）。此处按**模式标签字典序**
    迭代，使同一输入在任何进程/任何 seed 下返回完全相同的实体顺序。

    Returns:
        去重后的角色名列表（顺序由模式标签字典序决定，稳定可复现）。
    """
    db = operator_db or _OPERATOR_DB_BUILTIN
    aliases = alias_map or _ALIAS_MAP_BUILTIN

    ac = _build_ac_automaton(db, aliases)
    candidates = ac.search(text)

    found: list[str] = []
    seen: set[str] = set()

    # sorted()：消除 set 迭代顺序对实体顺序（进而对关系列表顺序）的影响
    for candidate in sorted(candidates):
        if candidate.startswith("alias:"):
            alias = candidate[6:]
            cn_name = aliases[alias]
            if cn_name not in seen and _is_name_in_text(alias, text):
                found.append(cn_name)
                seen.add(cn_name)
        else:
            name = candidate
            if name not in seen and _is_name_in_text(name, text):
                found.append(name)
                seen.add(name)

    return found


def extract_relationships_from_text(
    text: str,
    source_label: str = "",
    operator_db: dict | None = None,
    alias_map: dict | None = None,
) -> list[dict]:
    """
    从一段文本中提取关系

    策略：
    1. 识别文本中出现的所有角色名
    2. 对每对共现的角色，检查关系关键词
    3. 对每个识别出的关系，标注来源和可信度

    性能：全文分句 **1 次** + 「实体 → 句号集合」倒排索引 **1 次**，
    之后每对实体只做 O(1) 集合运算，不再重复全文 split
    （原实现为 O(E²·N)，E=30 时 10k 字约 480 ms；现为 O(N·E)）。
    分句标点集、共现谓词、关系模式匹配、方向判定、可信度计算**全部保持原样**。
    """
    entities = extract_entities(text, operator_db, alias_map)
    if len(entities) < 2:
        return []

    sentences = _split_sentences(text)
    index = _build_sentence_index(sentences, entities)

    relationships = []

    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            e1, e2 = entities[i], entities[j]

            relevant_segments = _segments_from_index(sentences, index, e1, e2)

            for rel_pattern, rel_type in RELATIONSHIP_PATTERNS:
                matched_in_segment = False
                best_segment = ""
                for seg in relevant_segments:
                    if re.search(rel_pattern, seg):
                        matched_in_segment = True
                        best_segment = seg
                        break

                if not matched_in_segment:
                    continue

                direction = _detect_direction(best_segment, e1, e2, rel_pattern)

                rel = {
                    "from": e1 if direction == "forward" else e2,
                    "to": e2 if direction == "forward" else e1,
                    "type": rel_type,
                    "confidence": _calc_confidence(best_segment, rel_pattern),
                    "source": source_label,
                    "context": _extract_context(best_segment, e1, e2, rel_pattern),
                }
                relationships.append(rel)

    return relationships


# 本模块的分句符集合（与 3.x 的 `re.split(r"[。！？\n]+", text)` 完全一致）
_SENTENCE_DELIMITERS = "。！？\n"

# 预编译分句正则（供 `_extract_context` 保留「不 strip、不过滤空串」的旧行为）
_SENTENCE_SPLIT_RE = re.compile("[" + _SENTENCE_DELIMITERS + "]+")

_NEGATION_MARKERS = frozenset(["≠", "不是", "并非", "不等于", "误解", "错误", "没有", "不曾", "未尝", "并不"])


def _is_negation_context(s: str) -> bool:
    return any(marker in s for marker in _NEGATION_MARKERS)


def _split_sentences(text: str) -> list[str]:
    """按本模块原有标点集分句（委托 `shared_utils.split_sentences`，标点集不变）"""
    sentences: list[str] = _shared_split_sentences(text, keep=_SENTENCE_DELIMITERS)
    return sentences


def _build_sentence_index(sentences: list[str], entities: list[str] | tuple[str, ...]) -> dict[str, set[int]]:
    """构建倒排索引：实体名 → 包含该实体的句子下标集合（每个实体只扫一遍全文）"""
    return {entity: {i for i, s in enumerate(sentences) if entity in s} for entity in entities}


def _segments_from_index(
    sentences: list[str],
    index: dict[str, set[int]],
    e1: str,
    e2: str,
    max_gap: int = 80,
) -> list[str]:
    """用预计算的句子列表与倒排索引，取出与实体对相关的句子/段落。

    谓词与遍历顺序与旧实现 `_find_relevant_segments` 完全一致
    （`e1_indices` / `e2_indices` 仍是按句子顺序插入的整数集合），
    因此返回列表的内容与顺序逐项相同。
    """
    e1_indices = index.get(e1, set())
    e2_indices = index.get(e2, set())

    joint = e1_indices & e2_indices
    joint_sentences = [s for i, s in enumerate(sentences) if i in joint and not _is_negation_context(s)]
    if joint_sentences:
        return joint_sentences

    merged = []
    for i1 in e1_indices:
        for i2 in e2_indices:
            if abs(i1 - i2) <= 2:
                start = min(i1, i2)
                end = max(i1, i2)
                segment = "。".join(sentences[start:end + 1])
                if _is_negation_context(segment):
                    continue
                if len(segment) <= max_gap * 3:
                    merged.append(segment)

    return merged


def _find_relevant_segments(text: str, e1: str, e2: str, max_gap: int = 80) -> list[str]:
    """从文本中提取同时包含两个角色名的句子/段落（兼容包装）

    保留给外部与测试调用；批量场景请改用
    :func:`_build_sentence_index` + :func:`_segments_from_index`，避免重复全文分句。
    """
    sentences = _split_sentences(text)
    index = _build_sentence_index(sentences, (e1, e2))
    return _segments_from_index(sentences, index, e1, e2, max_gap)


def _detect_direction(text: str, e1: str, e2: str, rel_pattern: str) -> str:
    """尝试判断关系方向"""
    pos1 = text.find(e1)
    pos2 = text.find(e2)

    if pos1 < 0 or pos2 < 0:
        return "forward"

    after_e1 = text[pos1 + len(e1):]
    after_e2 = text[pos2 + len(e2):]

    if pos1 < pos2:
        between = text[pos1 + len(e1):pos2]
        if "的" in between and len(between) < 15:
            return "reverse"
        if "是" in between and re.search(r"的", after_e2[:10]):
            return "forward"
    else:
        between = text[pos2 + len(e2):pos1]
        if "的" in between and len(between) < 15:
            return "forward"
        if "是" in between and re.search(r"的", after_e1[:10]):
            return "reverse"

    keyword_pos = -1
    for match in re.finditer(rel_pattern, text):
        keyword_pos = match.start()
        break

    if keyword_pos >= 0:
        dist1 = abs(keyword_pos - pos1)
        dist2 = abs(keyword_pos - pos2)
        if dist1 < dist2:
            return "forward"
        else:
            return "reverse"

    if pos1 < pos2:
        return "forward"
    return "reverse"


def _calc_confidence(text: str, rel_pattern: str) -> str:
    """计算关系识别的可信度"""
    match_count = len(re.findall(rel_pattern, text))
    if match_count >= 3:
        return "high"
    elif match_count >= 2:
        return "medium"
    else:
        return "low"


def _extract_context(text: str, e1: str, e2: str, rel_pattern: str) -> str:
    """提取关系出现的上下文"""
    compiled = re.compile(rel_pattern)
    for s in _SENTENCE_SPLIT_RE.split(text):
        if (e1 in s or e2 in s) and compiled.search(s):
            return s.strip()[:200]
    return ""


# ──────────────────────────────────────────────
# 关系图谱合并与去重
# ──────────────────────────────────────────────

def merge_relationships(all_rels: list[dict], operator_db: dict | None = None) -> dict:
    """
    合并来自多个来源的关系，去重并计算综合可信度

    返回图谱结构：
    {
        "nodes": [...],
        "edges": [...]
    }
    """
    edge_map: defaultdict = defaultdict(lambda: {"sources": [], "contexts": [], "confidences": []})

    for rel in all_rels:
        key = (rel["from"], rel["to"], rel["type"])
        entry = edge_map[key]
        if rel["source"] not in entry["sources"]:
            entry["sources"].append(rel["source"])
        if rel.get("context") and rel["context"] not in entry["contexts"]:
            entry["contexts"].append(rel["context"])
        entry["confidences"].append(rel["confidence"])

    node_names = set()
    for key in edge_map:
        node_names.add(key[0])
        node_names.add(key[1])

    nodes = []
    db = operator_db or _OPERATOR_DB_BUILTIN
    for name in sorted(node_names):
        info = db.get(name, {})
        nodes.append({
            "name": name,
            "name_en": info.get("en", ""),
            "race": info.get("race", "unknown"),
            "faction": info.get("faction", "unknown"),
        })

    edges = []
    for (from_name, to_name, rel_type), data in sorted(edge_map.items()):
        confidences = data["confidences"]
        if "high" in confidences:
            combined_confidence = "high"
        elif "medium" in confidences:
            combined_confidence = "medium"
        else:
            combined_confidence = "low"

        if len(data["sources"]) >= 3:
            combined_confidence = "high"
        elif len(data["sources"]) >= 2 and combined_confidence != "high":
            combined_confidence = "medium"

        edges.append({
            "from": from_name,
            "to": to_name,
            "type": rel_type,
            "confidence": combined_confidence,
            "source_count": len(data["sources"]),
            "sources": data["sources"],
            "contexts": data["contexts"][:3],
        })

    return {"nodes": nodes, "edges": edges}


# ──────────────────────────────────────────────
# 关系强度量化（升级新增）
# ──────────────────────────────────────────────

def compute_relationship_strength(
    co_occurrence: int,
    total_lines: int,
    sentiment_words: list[str],
    dialogue_count: int,
) -> float:
    """量化关系强度 (0.0 ~ 1.0)

    综合考虑：
    - 共现频率（归一化）
    - 情感词密度（共现段落中的情感词数）
    - 直接对话次数
    """
    if total_lines <= 0 or co_occurrence <= 0:
        return 0.0

    co_freq = co_occurrence / total_lines
    sentiment_density = len(sentiment_words) / co_occurrence
    dialogue_ratio = dialogue_count / co_occurrence

    # 加权综合
    strength = (
        0.3 * min(co_freq * 10, 1.0)
        + 0.3 * min(sentiment_density, 1.0)
        + 0.4 * min(dialogue_ratio, 1.0)
    )
    return round(strength, 3)


def enrich_edges_with_strength(
    graph: dict,
    all_texts: list[str],
    operator_db: dict | None = None,
) -> dict:
    """为图谱中的每条边计算关系强度

    在 merge_relationships 的输出基础上，为每条边添加 strength 字段。
    """
    total_lines = len(all_texts)

    # 情感词集合（用于检测共现段落中的情感密度）
    _sentiment_words = {
        "信任", "相信", "托付", "关怀", "温柔", "珍视", "在乎",
        "恨", "愤怒", "厌恶", "憎恨", "背叛", "敌人", "对手",
        "战友", "并肩", "共同", "教导", "培养", "依赖",
    }

    for edge in graph.get("edges", []):
        # 推断边（dialogue/mention）已带按证据条数计算的 strength，
        # 文本共现口径对它们不适用（对话对象常是元数据，不在行文本里）
        if "strength" in edge:
            continue
        from_name = edge["from"]
        to_name = edge["to"]

        # 统计共现次数和情感词
        co_count = 0
        sentiment_found: list[str] = []
        dialogue_count = 0

        for text in all_texts:
            has_from = from_name in text
            has_to = to_name in text
            if has_from and has_to:
                co_count += 1
                for sw in _sentiment_words:
                    if sw in text:
                        sentiment_found.append(sw)
                # 检测是否有直接对话（引号内的交互）
                # 注意：原实现两个操作数相同（'"' in text 判断两次），
                # 中文弯引号/书名号永远不命中 → dialogue_count 恒 0 → 强度偏低。
                if any(q in text for q in ('"', '\u201c', '\u201d', '\u300c', '\u300e')):
                    dialogue_count += 1

        edge["strength"] = compute_relationship_strength(
            co_count, total_lines, sentiment_found, dialogue_count
        )

    return graph


def detect_relationship_evolution(
    phase_graphs: dict[str, dict],
    phase_order: list[str] | None = None,
) -> list[dict]:
    """检测关系的跨期演变（量化版）

    输出每条关系的强度变化轨迹：
    - 方向：加深/疏远/稳定
    - delta：强度变化量
    - 各时期强度值
    """
    if len(phase_graphs) < 2:
        return []

    # 按时序排列时期
    phases_sorted = (
        [p for p in phase_order if p in phase_graphs] if phase_order else sorted(phase_graphs.keys())
    )

    # 收集所有边
    all_edge_keys: set[tuple[str, str, str]] = set()
    for graph in phase_graphs.values():
        for edge in graph.get("edges", []):
            all_edge_keys.add((edge["from"], edge["to"], edge["type"]))

    evolutions: list[dict] = []

    for from_name, to_name, rel_type in sorted(all_edge_keys):
        phase_strengths: dict[str, float] = {}
        for phase in phases_sorted:
            graph = phase_graphs[phase]
            for edge in graph.get("edges", []):
                if (edge["from"] == from_name and
                    edge["to"] == to_name and
                    edge["type"] == rel_type):
                    phase_strengths[phase] = edge.get("strength", 0.0)
                    break

        if len(phase_strengths) < 2:
            continue

        present_phases = list(phase_strengths.keys())
        first_strength = phase_strengths[present_phases[0]]
        last_strength = phase_strengths[present_phases[-1]]
        delta = last_strength - first_strength

        if abs(delta) < 0.05:
            direction = "稳定"
        elif delta > 0:
            direction = "加深"
        else:
            direction = "疏远"

        evolutions.append({
            "from": from_name,
            "to": to_name,
            "type": rel_type,
            "direction": direction,
            "delta": round(delta, 3),
            "phase_strengths": phase_strengths,
            "description": (
                f"与{to_name}的{rel_type}关系从{present_phases[0]}时期"
                f"({first_strength:.2f})到{present_phases[-1]}时期"
                f"({last_strength:.2f})，趋势：{direction}"
            ),
        })

    return evolutions


# ──────────────────────────────────────────────
# 文件读取
# ──────────────────────────────────────────────

def load_text(filepath: str, fmt: str = "markdown") -> list[tuple[str, str]]:
    """加载文本并按段落拆分"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    content = read_text_utf8(path)
    source_label = path.name

    if fmt == "markdown":
        sections = re.split(r"^#+\s+", content, flags=re.MULTILINE)
        parts = []
        for s in sections:
            s = s.strip()
            if s and len(s) > 20:
                parts.append((s, source_label))
        return parts if parts else [(content, source_label)]

    else:  # plain
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip() and len(p.strip()) > 20]
        return [(p, source_label) for p in paragraphs] if paragraphs else [(content, source_label)]


# ──────────────────────────────────────────────
# 语境化分析（升级新增）
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# 行级关系推断（v3.6.1 新增：修复真实数据召回 0 的能力缺口）
# ──────────────────────────────────────────────

# 这些「对话对象」值不指向具体身份，不能作为关系节点
_PLACEHOLDER_INTERLOCUTORS = frozenset({
    "", "未知", "无", "独白", "未标注", "未标注场景", "旁白", "自言自语",
    "-", "—", "N/A", "n/a", "none", "null",
})


def _resolve_interlocutor(raw: object, db: dict, aliases: dict) -> str | None:
    """把行内 interlocutor 解析成可作节点的关系对象。

    能经由名库/别名归一化的（如「博士」）归一化；解析不出但也不是占位符的
    （如剧情里的「坚强的孩子」）保留原文——它是标注器给出的真实对话对象，
    只是名库未收录，丢弃会损失真实证据。
    """
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name or name in _PLACEHOLDER_INTERLOCUTORS:
        return None
    return normalize_name(name, db, aliases) or name


# 说话人限定模式：只匹配**第一人称**关系表述。
# 非归档行都是目标角色本人的话，所以「我的战友」「教导我」里的关系
# 主语就是角色本人——这让我们能在说话人名字不出现在行文本时
# （角色极少自称）也给出语义分类，且不会把「战争结束了」这类
# 第三人称叙事误判成角色间关系（那是通用 RELATIONSHIP_PATTERNS 的风险）。
_SPEAKER_PATTERNS: list[tuple[str, str]] = [
    (r"我最信任|我信任|信任我|依赖我|依靠我", "trust"),
    (r"背叛了我|出卖了我|欺骗我", "betrayal"),
    (r"我的战友|与我并肩|和我并肩", "comrade"),
    (r"教导我|教会我|我的老师|我的师父|我的师傅", "mentor"),
    (r"我最珍视|我最在乎|我牵挂", "affection"),
    (r"我的敌人|我的对手|与我为敌", "opponent"),
]


def _infer_line_relations(
    lines: list[dict],
    character: str,
    db: dict,
    aliases: dict,
) -> list[tuple[str, dict]]:
    """逐行推断角色关系（recall 修复的主体）。

    旧实现只消费 context["annotated_relations"]，而标注器从不填充该字段，
    且 ``context["character"]`` 读了即丢——于是真实数据永远是 0 边。

    按可信度递减的三类证据补链（都可回溯到具体台词行）：
    1. 关键词语义边 —— 行文本命中说话人限定模式（第一人称关系表述）
    2. dialogue    —— 该行的对话对象：说话人直接对谁说话（元数据级证据）
    3. mention     —— 同一行文本中提及的已知角色（纯共现，无任何语义词）

    由通用 RELATIONSHIP_PATTERNS 在全文分类出的 typed 对不产 mention
    （信息重复）；dialogue 保留——直接对话是独立证据。

    Returns:
        (phase, rel) 列表；rel 形如 merge_relationships 的输入，
        ``source`` 为证据行 id（可在 persona 文档中回溯到具体台词）。
    """
    inferred: list[tuple[str, dict]] = []
    char_key = normalize_name(character, db, aliases) or character

    # 预扫描：每个非归档行的提及实体、参与方、对话对象
    # 元素：(line_id, phase, text, mentioned, others, interlocutor)
    line_infos: list[tuple[str, str, str, set[str], set[str], str | None]] = []
    for idx, line in enumerate(lines):
        if line.get("source") == "archive":
            continue
        text = line.get("text", "")
        if not text:
            continue
        phase = line.get("context", {}).get("phase", "unknown")
        line_id = line.get("id") or f"L{idx:03d}"

        mentioned = set(extract_entities(text, db, aliases))
        interlocutor = _resolve_interlocutor(
            line.get("context", {}).get("interlocutor"), db, aliases
        )

        others: set[str] = set(mentioned)
        if interlocutor:
            others.add(interlocutor)
        others.discard(char_key)
        others.discard(character)

        line_infos.append((line_id, phase, text, mentioned, others, interlocutor))

    # 第一遍：说话人限定模式 → 语义边（最高优先，存在即压制 mention）。
    # 只作用于**行文本中实际提及**的实体——句子的语义只关乎句内出现的名字；
    # 对话对象是元数据，不在句内，不应继承句子的关系表述。
    semantic_pairs: set[tuple[str, str]] = set()
    for line_id, phase, text, mentioned, _others, _interlocutor in line_infos:
        for other in sorted(mentioned):
            for pat, rel_type in _SPEAKER_PATTERNS:
                if re.search(pat, text):
                    semantic_pairs.add((character, other))
                    inferred.append((phase, {
                        "from": character,
                        "to": other,
                        "type": rel_type,
                        "confidence": _calc_confidence(text, pat),
                        "source": line_id,
                        "context": text[:100],
                    }))

    # 第二遍：dialogue / mention
    for line_id, phase, text, _mentioned, others, interlocutor in line_infos:
        for other in sorted(others):
            if (character, other) in semantic_pairs:
                continue
            is_dialogue = other == interlocutor
            inferred.append((phase, {
                "from": character,
                "to": other,
                "type": "dialogue" if is_dialogue else "mention",
                # 单行证据置 low，由 merge_relationships 按证据条数升级
                "confidence": "low",
                "source": line_id,
                "context": text[:100],
            }))

    return inferred


# 推断边的强度曲线与置信度阈值：证据越多越强，但同一证据量下
# 共现（mention）比直接对话（dialogue）更弱，两者都应比关键词分类保守
_INFERRED_STRENGTH = {
    # type: (strength_base, strength_step, strength_cap, high_n, medium_n)
    "dialogue": (0.35, 0.04, 0.90, 4, 2),
    "mention": (0.20, 0.08, 0.80, 6, 3),
}


def _apply_inferred_strength(graph: dict) -> dict:
    """给 dialogue/mention 边按证据条数写 strength 与 confidence。

    与 enrich_edges_with_strength 的文本共现口径不同：这两类边的「对话对象/
    提及」本身不要求出现在行文本里（如语音行的对话对象是元数据），共现
    统计会恒为 0，所以直接用 sources（证据行）计数。

    置信度阈值比 merge_relationships 的通用规则（>=3 条即 high）更严：
    关键词命中是语义证据，共现只是统计证据，不应享受同一升级曲线。
    """
    for edge in graph.get("edges", []):
        params = _INFERRED_STRENGTH.get(edge.get("type", ""))
        if params is None:
            continue
        base, step, cap, high_n, medium_n = params
        n = len(edge.get("sources", []))
        edge["strength"] = round(min(base + step * max(0, n - 1), cap), 3)
        edge["confidence"] = "high" if n >= high_n else ("medium" if n >= medium_n else "low")
    return graph


def generate_contextual_relationships(
    context: dict,
    operator_db: dict | None = None,
    alias_map: dict | None = None,
) -> dict:
    """
    从 context.json 提取时序关系图谱

    按 period 分片提取关系，计算跨时期关系演变，
    结果回写 context.json 的 annotated_relations。
    """
    db = operator_db or _OPERATOR_DB_BUILTIN
    aliases = alias_map or _ALIAS_MAP_BUILTIN

    lines = context.get("annotated_lines", [])
    character = normalize_name(context.get("character", "unknown"), db, aliases) \
        or context.get("character", "unknown")

    # 按时期分组文本
    phase_texts: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        phase = line.get("context", {}).get("phase", "unknown")
        text = line.get("text", "")
        if text and line.get("source") != "archive":
            phase_texts[phase].append(text)

    # 全局文本（所有非档案行）
    all_texts = []
    for line in lines:
        if line.get("source") != "archive":
            all_texts.append(line.get("text", ""))

    # 行级推断（dialogue / mention）：修复「真实数据 0 召回」——
    # 旧实现只认关键词共现，而角色自己的台词极少同时包含两个名字和关系词
    inferred = _infer_line_relations(lines, character, db, aliases)

    # 提取全局关系（关键词分类，行为不变）
    global_text = "\n".join(all_texts)
    global_typed = extract_relationships_from_text(
        global_text, "context:global", db, aliases
    )

    # 已有分类关系的对不再产 mention（信息重复；dialogue 保留——直接对话
    # 是独立于关键词的证据）
    typed_pairs = {(r["from"], r["to"]) for r in global_typed}
    typed_pairs |= {(t, f) for t, f in typed_pairs}
    inferred_global = [
        rel
        for _phase, rel in inferred
        if rel["type"] != "mention" or (rel["from"], rel["to"]) not in typed_pairs
    ]

    global_rels = global_typed + inferred_global
    global_graph = merge_relationships(global_rels, db)

    # 推断边先按证据条数定 strength，再由 enrich 补 typed 边的文本共现强度
    global_graph = _apply_inferred_strength(global_graph)

    # 为全局图谱添加关系强度
    global_graph = enrich_edges_with_strength(global_graph, all_texts, db)

    # 按 period 提取关系
    phase_graphs = {}
    for phase, texts in phase_texts.items():
        if phase == "unknown" or len(texts) < 3:
            continue
        phase_text = "\n".join(texts)
        phase_rels = extract_relationships_from_text(
            phase_text, f"context:phase:{phase}", db, aliases
        )
        # 与全局口径一致：已有分类关系的对不重复产 mention
        phase_typed_pairs = {(r["from"], r["to"]) for r in phase_rels}
        phase_typed_pairs |= {(t, f) for t, f in phase_typed_pairs}
        phase_rels.extend(
            rel
            for ph, rel in inferred
            if ph == phase and (
                rel["type"] != "mention" or (rel["from"], rel["to"]) not in phase_typed_pairs
            )
        )
        if phase_rels:
            phase_graph = merge_relationships(phase_rels, db)
            phase_graph = _apply_inferred_strength(phase_graph)
            # 为分期图谱添加关系强度
            phase_graph = enrich_edges_with_strength(phase_graph, texts, db)
            phase_graphs[phase] = phase_graph

    # 计算关系演变轨迹（量化版）
    trajectories = compute_relation_trajectories(global_graph, phase_graphs)
    # 添加量化演变检测
    quantified_evolutions = detect_relationship_evolution(phase_graphs, PHASE_ORDER)

    # 构建 annotated_relations
    annotated_relations = []
    for edge in global_graph.get("edges", []):
        entry = {
            "from": edge["from"],
            "to": edge["to"],
            "type": edge["type"],
            "confidence": edge["confidence"],
            "strength": edge.get("strength"),
            "sources": edge.get("sources", []),
            "contexts": edge.get("contexts", [])[:2],
        }

        # 添加时序信息
        phase_info = {}
        for phase, graph in phase_graphs.items():
            for p_edge in graph.get("edges", []):
                if (p_edge["from"] == edge["from"] and
                    p_edge["to"] == edge["to"] and
                    p_edge["type"] == edge["type"]):
                    phase_info[phase] = {
                        "confidence": p_edge["confidence"],
                        "source_count": p_edge.get("source_count", 1),
                    }
        if phase_info:
            entry["phases"] = phase_info

        # 检查是否有演变
        for traj in trajectories:
            if (traj["from"] == edge["from"] and
                traj["to"] == edge["to"] and
                traj["type"] == edge["type"]):
                entry["trajectory"] = traj["evolution"]
                break

        annotated_relations.append(entry)

    return {
        "global_graph": global_graph,
        "phase_graphs": phase_graphs,
        "trajectories": trajectories,
        "quantified_evolutions": quantified_evolutions,
        "annotated_relations": annotated_relations,
        "inferred_edges": len(inferred_global),
    }


def compute_relation_trajectories(
    global_graph: dict,
    phase_graphs: dict[str, dict],
) -> list[dict]:
    """
    计算关系的时序演变轨迹

    识别同一对角色在不同时期的关系变化：
    - 新增：在后期出现但前期不存在
    - 消失：在前期出现但后期不存在
    - 强化：后期置信度提升
    - 转变：关系类型发生变化
    """
    if len(phase_graphs) < 2:
        return []

    trajectories = []

    # 按时序排列时期（而非字母序）
    # 使用 constants.PHASE_ORDER 的预定义时间顺序，未知时期排在最后
    phases_sorted = []
    for p in PHASE_ORDER:
        if p in phase_graphs:
            phases_sorted.append(p)
    # 添加未在预定义顺序中的时期
    for p in sorted(phase_graphs.keys()):
        if p not in phases_sorted:
            phases_sorted.append(p)

    # 时序最靠前的时期（用于判断「新出现」还是「出现后消失」）
    earliest_phase = phases_sorted[0] if phases_sorted else ""

    # 收集所有边的全局信息
    global_edges = {}
    for edge in global_graph.get("edges", []):
        key = (edge["from"], edge["to"], edge["type"])
        global_edges[key] = edge

    # 对每条全局边，检查在各时期的表现
    for key, _global_edge in global_edges.items():
        from_name, to_name, rel_type = key

        # 收集该关系在各时期的出现情况
        phase_presence: dict[str, dict[str, Any]] = {}
        for phase in phases_sorted:
            graph = phase_graphs[phase]
            found = False
            confidence = None
            for p_edge in graph.get("edges", []):
                if (p_edge["from"] == from_name and
                    p_edge["to"] == to_name and
                    p_edge["type"] == rel_type):
                    found = True
                    confidence = p_edge["confidence"]
                    break
            phase_presence[phase] = {"found": found, "confidence": confidence}

        # 检查演变模式
        present_phases = [p for p, info in phase_presence.items() if info["found"]]
        absent_phases = [p for p, info in phase_presence.items() if not info["found"]]

        evolution = None

        if len(present_phases) == 1 and len(absent_phases) >= 1:
            only_phase = present_phases[0]
            if only_phase != earliest_phase:
                evolution = f"在{only_phase}时期新出现"
            else:
                evolution = f"仅在{only_phase}时期出现后消失"

        elif len(present_phases) >= 2:
            # 检查置信度变化
            first_conf = phase_presence[present_phases[0]]["confidence"]
            last_conf = phase_presence[present_phases[-1]]["confidence"]
            conf_order = {"low": 1, "medium": 2, "high": 3}
            if conf_order.get(last_conf, 0) > conf_order.get(first_conf, 0):
                evolution = f"从{present_phases[0]}到{present_phases[-1]}逐步强化"
            elif conf_order.get(last_conf, 0) < conf_order.get(first_conf, 0):
                evolution = f"从{present_phases[0]}到{present_phases[-1]}逐步淡化"

        # 检查关系类型转变（同一对角色，不同关系类型）
        type_changes = []
        for phase in phases_sorted:
            graph = phase_graphs[phase]
            for p_edge in graph.get("edges", []):
                if (p_edge["from"] == from_name and
                    p_edge["to"] == to_name and
                    p_edge["type"] != rel_type):
                    type_changes.append((phase, p_edge["type"]))

        if type_changes:
            change_desc = "、".join(
                f"{phase}时期为{t}" for phase, t in type_changes
            )
            if evolution:
                evolution += f"；同时{change_desc}"
            else:
                evolution = f"关系类型存在变化：{change_desc}"

        if evolution:
            trajectories.append({
                "from": from_name,
                "to": to_name,
                "type": rel_type,
                "evolution": evolution,
            })

    return trajectories


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    cli.require_assets()

    parser = argparse.ArgumentParser(
        description="关系图谱构建器 — 从文本中自动提取角色关系网络（支持语境化模式）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 传统模式
  python relationship_graph.py --input ./knowledge.md --format markdown

  # 语境化模式
  python relationship_graph.py --context-json operators/te-lei-xi-ya/context.json
        """,
    )

    # 传统模式参数
    parser.add_argument("--input", nargs="+", help="输入文件路径（传统模式）")
    parser.add_argument("--format", choices=["markdown", "plain"], default="markdown", help="文本格式")

    # 语境化模式参数
    parser.add_argument("--context-json", help="context.json 路径（语境化模式）")

    # 通用参数
    parser.add_argument("--operator-db", help="自定义角色名库 JSON 文件路径")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    # 互斥校验
    if args.context_json and args.input:
        print("错误：--context-json 和 --input 互斥，请选择一种模式", file=sys.stderr)
        sys.exit(1)

    if not args.context_json and not args.input:
        print("错误：请指定 --context-json（语境化模式）或 --input（传统模式）", file=sys.stderr)
        sys.exit(1)

    # 加载角色名库
    operator_db, alias_map = load_operator_db(args.operator_db)

    if args.context_json:
        # 语境化模式
        context = json.loads(read_text_utf8(args.context_json))

        result = generate_contextual_relationships(context, operator_db, alias_map)

        # 回写 annotated_relations 到 context.json
        context["annotated_relations"] = result["annotated_relations"]
        atomic_write_json(args.context_json, context)

        report = {
            "mode": "contextual",
            "character": context.get("character", "unknown"),
            "global_edges": len(result["global_graph"].get("edges", [])),
            "global_nodes": len(result["global_graph"].get("nodes", [])),
            "inferred_edges": result["inferred_edges"],
            "phase_graphs": {
                phase: len(graph.get("edges", []))
                for phase, graph in result["phase_graphs"].items()
            },
            "trajectories": result["trajectories"],
            "annotated_relations_count": len(result["annotated_relations"]),
        }

        if report["global_edges"] == 0:
            logger.warning(
                "关系图谱为 0 边：所有行都未产生 dialogue/mention/关键词证据。"
                "常见原因：语料过少（非 archive 行 <3）、名库不覆盖文本中的称呼"
                "（可用 --operator-db 扩展）、或 interlocutor 全是占位值。"
            )

        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            atomic_write_text(args.output, text)
            print(f"语境化关系图谱已写入 {args.output}", file=sys.stderr)
            print(f"annotated_relations 已回写 {args.context_json}", file=sys.stderr)
        else:
            print(text)
    else:
        # 传统模式
        all_relationships = []

        for filepath in args.input:
            parts = load_text(filepath, args.format)
            for text, source in parts:
                rels = extract_relationships_from_text(text, source, operator_db, alias_map)
                all_relationships.extend(rels)

        if not all_relationships:
            print("警告：未识别到任何关系", file=sys.stderr)
            graph = {"nodes": [], "edges": []}
        else:
            graph = merge_relationships(all_relationships, operator_db)

        node_count = len(graph["nodes"])
        edge_count = len(graph["edges"])
        print(f"识别到 {node_count} 个角色、{edge_count} 条关系", file=sys.stderr)

        text = json.dumps(graph, ensure_ascii=False, indent=2)
        if args.output:
            atomic_write_text(args.output, text)
            print(f"关系图谱已写入 {args.output}", file=sys.stderr)
        else:
            print(text)


if __name__ == "__main__":
    main()
