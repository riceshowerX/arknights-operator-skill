#!/usr/bin/env python3
"""
关系图谱构建器 —— 从文本中自动提取角色关系网络

这是 arknights-operator-skill 的核心差异化工具之一：
不依赖手动填写关系，而是从角色资料/剧情文本中自动识别关系模式。

用法:
    # 从知识库文件中提取关系
    python relationship_graph.py --input ./knowledge.md --format markdown

    # 从 PRTS Wiki 文本中提取
    python relationship_graph.py --input ./prts_raw.txt --format plain

    # 从多个文件合并提取
    python relationship_graph.py --input ./f1.md ./f2.txt --format markdown

输出:
    JSON 格式的关系图谱，包含节点、边、关系类型和可信度
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 明日方舟角色名库（用于文本中的实体识别）
# ──────────────────────────────────────────────

OPERATOR_DB = {
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
    # 其他
    "银灰": {"en": "SilverAsh", "race": "菲林", "faction": "喀兰贸易"},
    "煌": {"en": "Blaze", "race": "萨卡兹", "faction": "罗德岛"},
}

# 别名映射
ALIAS_MAP = {
    "Theresa": "特蕾西娅",
    "Theresis": "特雷西斯",
    "Amiya": "阿米娅",
    "Doctor": "博士",
    "Kal'tsit": "凯尔希",
    "Closure": "可露希尔",
    "Wiš'adel": "W",
    "Talulah": "塔露拉",
    "Ch'en": "陈",
    "Saria": "塞雷娅",
    "Ifrit": "伊芙利特",
    "SilverAsh": "银灰",
    "Blaze": "煌",
    "爱国者": "爱国者",
    "Patriot": "爱国者",
    "FrostNova": "霜星",
}


# ──────────────────────────────────────────────
# 关系模式识别
# ──────────────────────────────────────────────

# 关系关键词模式：{(主语模式, 宾语模式): 关系类型}
RELATIONSHIP_PATTERNS = [
    # 亲属关系
    (r"胞兄|哥哥|兄长|亲兄", "sibling"),
    (r"胞妹|妹妹|亲妹|姐姐|姐姐", "sibling"),
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


def normalize_name(name: str) -> Optional[str]:
    """将名称标准化为中文名"""
    name = name.strip()
    if name in OPERATOR_DB:
        return name
    if name in ALIAS_MAP:
        return ALIAS_MAP[name]
    # 尝试从英文名匹配
    for cn, info in OPERATOR_DB.items():
        if info.get("en", "").lower() == name.lower():
            return cn
    return None


def extract_entities(text: str) -> list[str]:
    """从文本中提取出现的角色名"""
    found = []
    for name in OPERATOR_DB:
        if name in text:
            found.append(name)
    for alias, cn_name in ALIAS_MAP.items():
        if alias in text and cn_name not in found:
            found.append(cn_name)
    return found


def extract_relationships_from_text(text: str, source_label: str = "") -> list[dict]:
    """
    从一段文本中提取关系

    策略：
    1. 识别文本中出现的所有角色名
    2. 对每对共现的角色，检查关系关键词
    3. 对每个识别出的关系，标注来源和可信度
    """
    entities = extract_entities(text)
    if len(entities) < 2:
        return []

    relationships = []

    # 对每对共现实体检查关系模式
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            e1, e2 = entities[i], entities[j]

            # 提取两个角色名之间的上下文
            for rel_pattern, rel_type in RELATIONSHIP_PATTERNS:
                # 检查 "e1 ... 关键词 ... e2" 或 "e2 ... 关键词 ... e1"
                # 简化：在包含两者的段落中搜索关系关键词
                if re.search(rel_pattern, text):
                    # 尝试确定方向
                    direction = _detect_direction(text, e1, e2, rel_pattern)

                    rel = {
                        "from": e1 if direction == "forward" else e2,
                        "to": e2 if direction == "forward" else e1,
                        "type": rel_type,
                        "confidence": _calc_confidence(text, rel_pattern),
                        "source": source_label,
                        "context": _extract_context(text, e1, e2, rel_pattern),
                    }
                    relationships.append(rel)

    return relationships


def _detect_direction(text: str, e1: str, e2: str, rel_pattern: str) -> str:
    """
    尝试判断关系方向

    检查 e1 是否先于 e2 出现，且关系关键词在 e1 附近
    """
    pos1 = text.find(e1)
    pos2 = text.find(e2)

    if pos1 < 0 or pos2 < 0:
        return "forward"

    # 如果 e1 在 e2 前面，且关系关键词也在 e1 附近
    keyword_pos = -1
    for match in re.finditer(rel_pattern, text):
        keyword_pos = match.start()
        break

    if keyword_pos >= 0:
        # 关系关键词离谁更近
        dist1 = abs(keyword_pos - pos1)
        dist2 = abs(keyword_pos - pos2)
        if dist1 < dist2:
            return "forward"  # e1 → e2
        else:
            return "reverse"  # e2 → e1

    # 默认：先出现的为主体
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
    """提取关系出现的上下文（截取包含两者的句子）"""
    # 找到包含至少一个角色名和关系关键词的句子
    sentences = re.split(r"[。！？\n]", text)
    for s in sentences:
        if (e1 in s or e2 in s) and re.search(rel_pattern, s):
            return s.strip()[:200]
    return ""


# ──────────────────────────────────────────────
# 关系图谱合并与去重
# ──────────────────────────────────────────────

def merge_relationships(all_rels: list[dict]) -> dict:
    """
    合并来自多个来源的关系，去重并计算综合可信度

    返回图谱结构：
    {
        "nodes": [{"name": "xxx", "race": "xxx", "faction": "xxx"}],
        "edges": [{"from": "xxx", "to": "xxx", "type": "xxx", "confidence": "xxx", "sources": [...], "contexts": [...]}]
    }
    """
    # 用 (from, to, type) 作为唯一键合并
    edge_map = defaultdict(lambda: {"sources": [], "contexts": [], "confidences": []})

    for rel in all_rels:
        key = (rel["from"], rel["to"], rel["type"])
        entry = edge_map[key]
        if rel["source"] not in entry["sources"]:
            entry["sources"].append(rel["source"])
        if rel.get("context") and rel["context"] not in entry["contexts"]:
            entry["contexts"].append(rel["context"])
        entry["confidences"].append(rel["confidence"])

    # 构建节点集
    node_names = set()
    for key in edge_map:
        node_names.add(key[0])
        node_names.add(key[1])

    nodes = []
    for name in sorted(node_names):
        info = OPERATOR_DB.get(name, {})
        nodes.append({
            "name": name,
            "name_en": info.get("en", ""),
            "race": info.get("race", "unknown"),
            "faction": info.get("faction", "unknown"),
        })

    # 构建边
    edges = []
    for (from_name, to_name, rel_type), data in sorted(edge_map.items()):
        # 综合可信度
        confidences = data["confidences"]
        if "high" in confidences:
            combined_confidence = "high"
        elif "medium" in confidences:
            combined_confidence = "medium"
        else:
            combined_confidence = "low"

        # 多来源提升可信度
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
            "contexts": data["contexts"][:3],  # 最多保留3条上下文
        })

    return {"nodes": nodes, "edges": edges}


# ──────────────────────────────────────────────
# 文件读取
# ──────────────────────────────────────────────

def load_text(filepath: str, fmt: str = "markdown") -> list[tuple[str, str]]:
    """
    加载文本并按段落拆分

    返回: [(段落文本, 来源标签), ...]
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    content = path.read_text(encoding="utf-8")
    source_label = path.name

    if fmt == "markdown":
        # 按 Markdown 标题分段
        sections = re.split(r"^#+\s+", content, flags=re.MULTILINE)
        parts = []
        for s in sections:
            s = s.strip()
            if s and len(s) > 20:  # 忽略太短的段落
                parts.append((s, source_label))
        return parts if parts else [(content, source_label)]

    else:  # plain
        # 按空行分段
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip() and len(p.strip()) > 20]
        return [(p, source_label) for p in paragraphs] if paragraphs else [(content, source_label)]


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="关系图谱构建器 — 从文本中自动提取角色关系网络",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从知识库提取关系
  python relationship_graph.py --input ./knowledge.md --format markdown

  # 从多个文件合并提取
  python relationship_graph.py --input ./f1.md ./f2.txt --format markdown

  # 输出到文件
  python relationship_graph.py --input ./knowledge.md --output graph.json
        """,
    )

    parser.add_argument("--input", nargs="+", required=True, help="输入文件路径（支持多个）")
    parser.add_argument("--format", choices=["markdown", "plain"], default="markdown", help="文本格式")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")

    args = parser.parse_args()

    all_relationships = []

    for filepath in args.input:
        parts = load_text(filepath, args.format)
        for text, source in parts:
            rels = extract_relationships_from_text(text, source)
            all_relationships.extend(rels)

    if not all_relationships:
        print("警告：未识别到任何关系", file=sys.stderr)
        graph = {"nodes": [], "edges": []}
    else:
        graph = merge_relationships(all_relationships)

    # 统计摘要
    node_count = len(graph["nodes"])
    edge_count = len(graph["edges"])
    print(f"识别到 {node_count} 个角色、{edge_count} 条关系", file=sys.stderr)

    text = json.dumps(graph, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"关系图谱已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
