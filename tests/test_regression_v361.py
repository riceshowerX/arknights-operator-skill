#!/usr/bin/env python3
"""v3.6.1 回归用例 —— 关系抽取召回修复（QA 报告遗留项 R1）

背景：v3.6.0 及之前，generate_contextual_relationships 只消费
context["annotated_relations"]（而标注器从不填充该字段），且
context["character"] 读了即丢、行内 interlocutor 完全未用——
真实数据永远是 0 边（166 字节空图却通过「存在且非空」校验）。

修复：按两类可回溯证据补链
    dialogue —— 行内对话对象（语音行的元数据级证据）
    mention  —— 同行文本提及的已知角色（共现证据，无关键词才产出）

本文件每条用例都对「能独立暴露旧缺陷」的具体值断言。
"""

import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
PROJECT_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import relationship_graph  # noqa: E402
from data_injector import format_relationships  # noqa: E402
from shared_utils import load_json_safe  # noqa: E402

# ──────────────────────────────────────────────
# 构造工具
# ──────────────────────────────────────────────

def _voice(idx: int, text: str, interlocutor: str | None, phase: str = "babel") -> dict:
    return {
        "id": f"V{idx:03d}",
        "text": text,
        "source": "voice",
        "source_detail": "",
        "context": {
            "phase": phase,
            "scene": "",
            "interlocutor": interlocutor,
            "preceding_event": "",
            "situation_type": "casual",
        },
        "speech_acts": [],
        "emotion": {},
    }


def _context(lines: list[dict], character: str = "特蕾西娅") -> dict:
    return {"character": character, "annotated_lines": lines}


def _edges(result: dict) -> list[dict]:
    return result["global_graph"]["edges"]


def _find(result: dict, to: str, rel_type: str) -> dict | None:
    for e in _edges(result):
        if e["to"] == to and e["type"] == rel_type:
            return e
    return None


# ──────────────────────────────────────────────
# T1 dialogue 边：interlocutor 是元数据级证据
# ──────────────────────────────────────────────

class TestDialogueEdges:
    def test_interlocutor_produces_dialogue_edge(self):
        lines = [_voice(i, "台词内容。", "博士") for i in range(3)]
        result = relationship_graph.generate_contextual_relationships(_context(lines))

        edge = _find(result, "博士", "dialogue")
        assert edge is not None, f"interlocutor 未生成 dialogue 边: {_edges(result)}"
        # 证据必须可回溯到具体台词行
        assert edge["sources"] == ["V000", "V001", "V002"]

        # annotated_relations 是 data_injector 的消费入口，必须同步产出
        rel = next(r for r in result["annotated_relations"] if r["type"] == "dialogue")
        assert rel["to"] == "博士"
        assert len(rel["sources"]) == 3
        assert rel["strength"] is not None

    def test_placeholder_interlocutor_ignored(self):
        for placeholder in ("未知", "无", "独白", "", None):
            lines = [_voice(i, "自言自语的内容。", placeholder) for i in range(3)]
            result = relationship_graph.generate_contextual_relationships(_context(lines))
            assert _edges(result) == [], f"占位对话对象 {placeholder!r} 不应产出任何边"
            assert result["inferred_edges"] == 0

    def test_unresolved_interlocutor_kept_as_node(self):
        """剧情里的「坚强的孩子」不在名库中，但它是真实对话对象，不能丢"""
        lines = [_voice(i, "台词。", "坚强的孩子") for i in range(4)]
        result = relationship_graph.generate_contextual_relationships(
            _context(lines, character="W")
        )
        edge = _find(result, "坚强的孩子", "dialogue")
        assert edge is not None, "非名库对话对象被错误丢弃（召回缺口）"
        assert len(edge["sources"]) == 4


# ──────────────────────────────────────────────
# T2 mention 边：同行文本提及已知角色
# ──────────────────────────────────────────────

class TestMentionEdges:
    def test_text_mention_produces_mention_edge(self):
        lines = [_voice(0, "阿米娅还在等我的答复。", "博士")]
        result = relationship_graph.generate_contextual_relationships(_context(lines))
        assert _find(result, "阿米娅", "mention") is not None

    def test_speaker_pattern_types_mentioned_entity(self):
        """说话人不出现在行文本时，通用关键词分类够不着（需双名共现）；
        第一人称限定模式补上这个缺口：'我最信任' → trust"""
        lines = [_voice(0, "凯尔希是我最信任的战友。", "博士")]
        result = relationship_graph.generate_contextual_relationships(_context(lines))
        pairs = {(e["to"], e["type"]) for e in _edges(result)}
        assert ("凯尔希", "trust") in pairs, "说话人限定模式未生效（召回缺口）"
        assert ("凯尔希", "mention") not in pairs, "已有语义边的对不应重复产 mention"

    def test_speaker_pattern_not_inherited_by_interlocutor(self):
        """句子的关系表述只关乎句内出现的名字：
        对话对象（元数据）不在句内，不得继承 trust 语义"""
        lines = [_voice(0, "凯尔希是我最信任的战友。", "博士")]
        result = relationship_graph.generate_contextual_relationships(_context(lines))
        doctor = [e for e in _edges(result) if e["to"] == "博士"]
        assert doctor and all(e["type"] == "dialogue" for e in doctor), \
            f"对话对象被错误赋予句内语义词: {doctor}"

    def test_character_self_mention_not_an_edge(self):
        """角色在台词里提到自己不构成关系"""
        lines = [_voice(0, "这是专门为特蕾西娅空着的位置吗？", "博士")]
        result = relationship_graph.generate_contextual_relationships(_context(lines))
        assert all(e["to"] != "特蕾西娅" for e in _edges(result))


# ──────────────────────────────────────────────
# T3 置信度与强度：证据越多越强，但比关键词分类保守
# ──────────────────────────────────────────────

class TestConfidenceAndStrength:
    def test_confidence_scales_with_evidence(self):
        one = relationship_graph.generate_contextual_relationships(
            _context([_voice(0, "台词。", "博士")])
        )
        four = relationship_graph.generate_contextual_relationships(
            _context([_voice(i, "台词。", "博士") for i in range(4)])
        )
        e1 = _find(one, "博士", "dialogue")
        e4 = _find(four, "博士", "dialogue")
        assert e1["confidence"] == "low" and e1["strength"] == 0.35
        assert e4["confidence"] == "high"
        assert 0.35 < e4["strength"] <= 0.90

    def test_mention_needs_more_evidence_than_dialogue(self):
        """同一证据量下，共现（mention）不应比直接对话（dialogue）置信更高"""
        two_dialogue = relationship_graph.generate_contextual_relationships(
            _context([_voice(i, "台词。", "博士") for i in range(2)])
        )
        two_mention = relationship_graph.generate_contextual_relationships(
            _context([_voice(i, "阿米娅也在。", None) for i in range(2)])
        )
        d = _find(two_dialogue, "博士", "dialogue")["confidence"]
        m = _find(two_mention, "阿米娅", "mention")["confidence"]
        order = {"low": 0, "medium": 1, "high": 2}
        assert order[d] >= order[m]

    def test_enrich_respects_precomputed_strength(self):
        """enrich 的文本共现口径不得覆盖推断边已算好的 strength"""
        graph = {"edges": [{
            "from": "特蕾西娅", "to": "博士", "type": "dialogue",
            "sources": ["V000", "V001", "V002", "V003"], "strength": 0.47,
        }]}
        out = relationship_graph.enrich_edges_with_strength(
            graph, ["特蕾西娅对博士说话。"] * 5
        )
        assert out["edges"][0]["strength"] == 0.47

    def test_typed_edge_still_gets_cooccurrence_strength(self):
        """关键词分类边（无预置 strength）仍走原 enrich 口径，行为不回退"""
        graph = {"edges": [{
            "from": "特蕾西娅", "to": "阿米娅", "type": "trust",
            "sources": ["a"], "confidence": "low",
        }]}
        out = relationship_graph.enrich_edges_with_strength(graph, ["特蕾西娅信任阿米娅。"])
        assert isinstance(out["edges"][0]["strength"], float)


# ──────────────────────────────────────────────
# T4 真实样例端到端：本修复的最终验收口径
# ──────────────────────────────────────────────

class TestRealSampleRecall:
    def test_te_lei_xi_ya_has_doctor_dialogue_edge(self):
        """QA 报告 R1 的原始现场：真实 context.json 不得再产出 0 边"""
        context = load_json_safe(PROJECT_ROOT / "operators" / "te-lei-xi-ya" / "context.json")
        result = relationship_graph.generate_contextual_relationships(context)
        assert _edges(result), "真实样例仍为 0 边（R1 回归）"
        doctor = _find(result, "博士", "dialogue")
        assert doctor is not None and len(doctor["sources"]) >= 3

    def test_w_sample_graph_not_empty(self):
        context = load_json_safe(PROJECT_ROOT / "operators" / "w" / "context.json")
        result = relationship_graph.generate_contextual_relationships(context)
        assert len(_edges(result)) >= 3

    def test_injected_relationship_section_nonempty(self):
        """下游 data_injector 必须能从 context.json 格式化出非空关系段"""
        context = load_json_safe(PROJECT_ROOT / "operators" / "te-lei-xi-ya" / "context.json")
        section = format_relationships(context)
        assert "博士" in section
        assert "条证据" in section

    def test_report_has_inferred_edges_field(self, capsys):
        """relationship_graph.json 报告必须带 inferred_edges（QA R2：空图可观测性）"""
        context = load_json_safe(PROJECT_ROOT / "operators" / "te-lei-xi-ya" / "context.json")
        result = relationship_graph.generate_contextual_relationships(context)
        assert isinstance(result["inferred_edges"], int)


# ──────────────────────────────────────────────
# T5 确定性：同一输入在任何进程输出逐字节一致
# ──────────────────────────────────────────────

class TestDeterminism:
    def test_same_input_same_output(self):
        lines = [_voice(i, "阿米娅与凯尔希在会议室。", "博士") for i in range(5)]
        context = _context(lines)
        a = relationship_graph.generate_contextual_relationships(context)
        b = relationship_graph.generate_contextual_relationships(context)
        assert json.dumps(a, ensure_ascii=False, sort_keys=True) == \
            json.dumps(b, ensure_ascii=False, sort_keys=True)
