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


def load_operator_db(filepath: Optional[str] = None) -> tuple[dict, dict]:
    """
    加载角色名库和别名映射

    支持从外部 JSON 文件加载自定义角色名库，
    与内置名库合并（外部覆盖内置同名项）
    """
    db = dict(OPERATOR_DB)
    aliases = dict(ALIAS_MAP)

    if not filepath:
        return db, aliases

    path = Path(filepath)
    if not path.exists():
        print(f"警告：角色名库文件不存在 {filepath}，使用内置名库", file=sys.stderr)
        return db, aliases

    try:
        custom = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"警告：角色名库文件格式错误 {filepath}：{e}，使用内置名库", file=sys.stderr)
        return db, aliases

    if not isinstance(custom, dict):
        print(f"警告：角色名库文件应为 JSON 对象，使用内置名库", file=sys.stderr)
        return db, aliases

    custom_ops = custom.get("operators", {})
    if isinstance(custom_ops, dict):
        db.update(custom_ops)

    custom_aliases = custom.get("aliases", {})
    if isinstance(custom_aliases, dict):
        aliases.update(custom_aliases)

    return db, aliases


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


def normalize_name(name: str, operator_db: Optional[dict] = None, alias_map: Optional[dict] = None) -> Optional[str]:
    """将名称标准化为中文名"""
    db = operator_db or OPERATOR_DB
    aliases = alias_map or ALIAS_MAP

    name = name.strip()
    if name in db:
        return name
    if name in aliases:
        return aliases[name]
    for cn, info in db.items():
        if info.get("en", "").lower() == name.lower():
            return cn
    return None


def extract_entities(text: str, operator_db: Optional[dict] = None, alias_map: Optional[dict] = None) -> list[str]:
    """从文本中提取出现的角色名"""
    db = operator_db or OPERATOR_DB
    aliases = alias_map or ALIAS_MAP

    found = []
    for name in db:
        if name in text:
            found.append(name)
    for alias, cn_name in aliases.items():
        if alias in text and cn_name not in found:
            found.append(cn_name)
    return found


def extract_relationships_from_text(
    text: str,
    source_label: str = "",
    operator_db: Optional[dict] = None,
    alias_map: Optional[dict] = None,
) -> list[dict]:
    """
    从一段文本中提取关系

    策略：
    1. 识别文本中出现的所有角色名
    2. 对每对共现的角色，检查关系关键词
    3. 对每个识别出的关系，标注来源和可信度
    """
    entities = extract_entities(text, operator_db, alias_map)
    if len(entities) < 2:
        return []

    relationships = []

    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            e1, e2 = entities[i], entities[j]

            relevant_segments = _find_relevant_segments(text, e1, e2)

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


def _find_relevant_segments(text: str, e1: str, e2: str, max_gap: int = 80) -> list[str]:
    """从文本中提取同时包含两个角色名的句子/段落"""
    sentences = re.split(r"[。！？\n]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    negation_markers = ["≠", "不是", "并非", "不等于", "误解", "错误"]

    def _is_negation_context(s: str) -> bool:
        return any(marker in s for marker in negation_markers)

    joint_sentences = []
    for s in sentences:
        if e1 in s and e2 in s and not _is_negation_context(s):
            joint_sentences.append(s)

    if joint_sentences:
        return joint_sentences

    e1_indices = set()
    e2_indices = set()
    for i, s in enumerate(sentences):
        if e1 in s:
            e1_indices.add(i)
        if e2 in s:
            e2_indices.add(i)

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

    return merged if merged else []


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
    sentences = re.split(r"[。！？\n]", text)
    for s in sentences:
        if (e1 in s or e2 in s) and re.search(rel_pattern, s):
            return s.strip()[:200]
    return ""


# ──────────────────────────────────────────────
# 关系图谱合并与去重
# ──────────────────────────────────────────────

def merge_relationships(all_rels: list[dict], operator_db: Optional[dict] = None) -> dict:
    """
    合并来自多个来源的关系，去重并计算综合可信度

    返回图谱结构：
    {
        "nodes": [...],
        "edges": [...]
    }
    """
    edge_map = defaultdict(lambda: {"sources": [], "contexts": [], "confidences": []})

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
    db = operator_db or OPERATOR_DB
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
# 文件读取
# ──────────────────────────────────────────────

def load_text(filepath: str, fmt: str = "markdown") -> list[tuple[str, str]]:
    """加载文本并按段落拆分"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    content = path.read_text(encoding="utf-8")
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

def generate_contextual_relationships(
    context: dict,
    operator_db: Optional[dict] = None,
    alias_map: Optional[dict] = None,
) -> dict:
    """
    从 context.json 提取时序关系图谱

    按 period 分片提取关系，计算跨时期关系演变，
    结果回写 context.json 的 annotated_relations。
    """
    db = operator_db or OPERATOR_DB
    aliases = alias_map or ALIAS_MAP

    lines = context.get("annotated_lines", [])
    character = context.get("character", "unknown")

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

    # 提取全局关系
    global_text = "\n".join(all_texts)
    global_rels = extract_relationships_from_text(
        global_text, "context:global", db, aliases
    )
    global_graph = merge_relationships(global_rels, db)

    # 按 period 提取关系
    phase_graphs = {}
    for phase, texts in phase_texts.items():
        if phase == "unknown" or len(texts) < 3:
            continue
        phase_text = "\n".join(texts)
        phase_rels = extract_relationships_from_text(
            phase_text, f"context:phase:{phase}", db, aliases
        )
        if phase_rels:
            phase_graphs[phase] = merge_relationships(phase_rels, db)

    # 计算关系演变轨迹
    trajectories = compute_relation_trajectories(global_graph, phase_graphs)

    # 构建 annotated_relations
    annotated_relations = []
    for edge in global_graph.get("edges", []):
        entry = {
            "from": edge["from"],
            "to": edge["to"],
            "type": edge["type"],
            "confidence": edge["confidence"],
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
        "annotated_relations": annotated_relations,
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
    # 使用预定义的时间顺序，未知时期排在最后
    PHASE_ORDER = ["early", "babel", "resurrected"]
    phases_sorted = []
    for p in PHASE_ORDER:
        if p in phase_graphs:
            phases_sorted.append(p)
    # 添加未在预定义顺序中的时期
    for p in sorted(phase_graphs.keys()):
        if p not in phases_sorted:
            phases_sorted.append(p)

    # 收集所有边的全局信息
    global_edges = {}
    for edge in global_graph.get("edges", []):
        key = (edge["from"], edge["to"], edge["type"])
        global_edges[key] = edge

    # 对每条全局边，检查在各时期的表现
    for key, global_edge in global_edges.items():
        from_name, to_name, rel_type = key

        # 收集该关系在各时期的出现情况
        phase_presence = {}
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
            if phases_sorted.index(only_phase) > 0:
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
        with open(args.context_json, encoding='utf-8') as f:
            context = json.load(f)

        result = generate_contextual_relationships(context, operator_db, alias_map)

        # 回写 annotated_relations 到 context.json
        context["annotated_relations"] = result["annotated_relations"]
        with open(args.context_json, 'w', encoding='utf-8') as f:
            json.dump(context, f, ensure_ascii=False, indent=2)

        report = {
            "mode": "contextual",
            "character": context.get("character", "unknown"),
            "global_edges": len(result["global_graph"].get("edges", [])),
            "global_nodes": len(result["global_graph"].get("nodes", [])),
            "phase_graphs": {
                phase: len(graph.get("edges", []))
                for phase, graph in result["phase_graphs"].items()
            },
            "trajectories": result["trajectories"],
            "annotated_relations_count": len(result["annotated_relations"]),
        }

        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text, encoding="utf-8")
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
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"关系图谱已写入 {args.output}", file=sys.stderr)
        else:
            print(text)


if __name__ == "__main__":
    main()
