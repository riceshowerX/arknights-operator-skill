#!/usr/bin/env python3
"""
多阵营角色泛化能力测试

验证工具链对不同阵营、不同性格类型的角色均能正常工作，
而非仅针对特蕾西娅（巴别塔/萨卡兹）和 W（巴别塔/萨卡兹）过拟合。

测试覆盖三个不同阵营/类型的虚构角色 fixture：
  1. chen-chen-hua（陈陈华）— 龙门近卫局 / 龙门阵营 / 严格正直型
  2. shi-hua（诗华）— 罗德岛 / 医疗干员 / 温和治愈型
  3. hei-yan（黑岩）— 莱茵生命 / 科研型 / 理性冷漠型

使用纯本地 fixture 数据（不依赖 PRTS 网络），确保测试可离线复现。
"""

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))


# ──────────────────────────────────────────────
# 多阵营角色 fixture 数据
# ──────────────────────────────────────────────

# 阵营 1：龙门近卫局 — 严格正直型
CHEN_OPERATOR_DATA = {
    "name_zh": "陈陈华",
    "name_en": "ChenChenHua",
    "slug": "chen-chen-hua",
    "faction": "龙门近卫局",
    "race": "龙",
    "voice_lines": [
        {"label": "任命助理", "text": "我是陈陈华。有什么任务，直接说。"},
        {"label": "交谈1", "text": "龙门的法律不容亵渎。谁触犯，我抓谁。"},
        {"label": "交谈2", "text": "别跟我讲人情。公事公办。"},
        {"label": "战斗开始", "text": "所有人，听我指挥！"},
        {"label": "战斗失败", "text": "......撤退。保存实力。"},
        {"label": "信赖提升", "text": "......你倒是少见。能让我说这些的人。"},
    ],
}

CHEN_DIALOGUES = [
    {"speaker": "陈陈华", "text": "我是陈陈华。有什么任务，直接说。", "phase": "resurrected"},
    {"speaker": "陈陈华", "text": "龙门的法律不容亵渎。谁触犯，我抓谁。", "phase": "resurrected"},
    {"speaker": "陈陈华", "text": "别跟我讲人情。公事公办。", "phase": "resurrected"},
    {"speaker": "陈陈华", "text": "所有人，听我指挥！", "phase": "resurrected"},
    {"speaker": "陈陈华", "text": "......撤退。保存实力。", "phase": "resurrected"},
    {"speaker": "陈陈华", "text": "......你倒是少见。能让我说这些的人。", "phase": "resurrected"},
]

# 阵营 2：罗德岛医疗 — 温和治愈型
SHIHUA_OPERATOR_DATA = {
    "name_zh": "诗华",
    "name_en": "ShiHua",
    "slug": "shi-hua",
    "faction": "罗德岛",
    "race": "菲林",
    "voice_lines": [
        {"label": "任命助理", "text": "......啊，你来了。请坐，我给你倒杯茶。"},
        {"label": "交谈1", "text": "伤口还疼吗？......别逞强，让我看看。"},
        {"label": "交谈2", "text": "这片大地上受过伤的人太多。我能做的，只是让痛苦少一些。"},
        {"label": "战斗开始", "text": "大家小心......我会照顾好每一个人的。"},
        {"label": "战斗失败", "text": "......对不起。是我没能保护好你们。"},
        {"label": "信赖提升", "text": "......你知道吗，有你在，我觉得自己也不再是孤身一人了。"},
    ],
}

SHIHUA_DIALOGUES = [
    {"speaker": "诗华", "text": "......啊，你来了。请坐，我给你倒杯茶。", "phase": "resurrected"},
    {"speaker": "诗华", "text": "伤口还疼吗？......别逞强，让我看看。", "phase": "resurrected"},
    {"speaker": "诗华", "text": "这片大地上受过伤的人太多。我能做的，只是让痛苦少一些。", "phase": "resurrected"},
    {"speaker": "诗华", "text": "大家小心......我会照顾好每一个人的。", "phase": "resurrected"},
    {"speaker": "诗华", "text": "......对不起。是我没能保护好你们。", "phase": "resurrected"},
    {"speaker": "诗华", "text": "......你知道吗，有你在，我觉得自己也不再是孤身一人了。", "phase": "resurrected"},
]

# 阵营 3：莱茵生命 — 理性科研型
HEIYAN_OPERATOR_DATA = {
    "name_zh": "黑岩",
    "name_en": "HeiYan",
    "slug": "hei-yan",
    "faction": "莱茵生命",
    "race": "鲁珀",
    "voice_lines": [
        {"label": "任命助理", "text": "黑岩。实验数据已整理完毕，请查阅。"},
        {"label": "交谈1", "text": "情感是误差的来源。我选择剔除它。"},
        {"label": "交谈2", "text": "源石的分子结构远比你的想象复杂。......但这与你无关。"},
        {"label": "战斗开始", "text": "目标锁定。开始精确打击。"},
        {"label": "战斗失败", "text": "......数据偏差超出阈值。需要重新建模。"},
        {"label": "信赖提升", "text": "......你是个变量。我无法用现有模型预测你。这......让我困扰。"},
    ],
}

HEIYAN_DIALOGUES = [
    {"speaker": "黑岩", "text": "黑岩。实验数据已整理完毕，请查阅。", "phase": "resurrected"},
    {"speaker": "黑岩", "text": "情感是误差的来源。我选择剔除它。", "phase": "resurrected"},
    {"speaker": "黑岩", "text": "源石的分子结构远比你的想象复杂。......但这与你无关。", "phase": "resurrected"},
    {"speaker": "黑岩", "text": "目标锁定。开始精确打击。", "phase": "resurrected"},
    {"speaker": "黑岩", "text": "......数据偏差超出阈值。需要重新建模。", "phase": "resurrected"},
    {"speaker": "黑岩", "text": "......你是个变量。我无法用现有模型预测你。这......让我困扰。", "phase": "resurrected"},
]

OPERATORS_FIXTURES = [
    ("chen-chen-hua", CHEN_OPERATOR_DATA, CHEN_DIALOGUES, "龙门近卫局", "严格正直型"),
    ("shi-hua", SHIHUA_OPERATOR_DATA, SHIHUA_DIALOGUES, "罗德岛", "温和治愈型"),
    ("hei-yan", HEIYAN_OPERATOR_DATA, HEIYAN_DIALOGUES, "莱茵生命", "理性科研型"),
]


# ──────────────────────────────────────────────
# 测试类
# ──────────────────────────────────────────────


class TestMultiFactionGeneralization(unittest.TestCase):
    """验证工具链对不同阵营角色的泛化能力"""

    def test_all_factions_covered(self):
        """确认测试覆盖至少 3 个不同阵营"""
        factions = {f[3] for f in OPERATORS_FIXTURES}
        self.assertGreaterEqual(
            len(factions), 3,
            f"应覆盖至少 3 个阵营，实际: {factions}"
        )

    def test_all_personality_types_distinct(self):
        """确认测试覆盖不同性格类型"""
        types = {f[4] for f in OPERATORS_FIXTURES}
        self.assertGreaterEqual(
            len(types), 3,
            f"应覆盖至少 3 种性格类型，实际: {types}"
        )

    def test_fingerprints_are_distinct_across_factions(self):
        """不同阵营角色的对话指纹应有显著差异（验证非过拟合）"""
        from dialogue_fingerprint import generate_fingerprint

        fingerprints = {}
        for slug, op_data, dialogues, _faction, _ptype in OPERATORS_FIXTURES:
            fp = generate_fingerprint(dialogues, op_data["name_zh"])
            fingerprints[slug] = fp
            self.assertIn("dimensions", fp, f"{slug} 指纹生成失败")
            self.assertIn("summary", fp, f"{slug} 缺少 summary")

        # 各角色的句式长度均值应有差异
        lengths = {}
        for slug, fp in fingerprints.items():
            d1 = fp.get("dimensions", {}).get("1_sentence_length", {})
            lengths[slug] = d1.get("avg_length", 0)

        unique_lengths = set(round(n) for n in lengths.values())
        self.assertGreaterEqual(
            len(unique_lengths), 2,
            f"不同角色句式长度应差异明显，实际: {lengths}"
        )

    def test_speech_act_analysis_works_for_all_factions(self):
        """话语行为分析对所有阵营角色均能产出有效画像"""
        from speech_act_analyzer import build_speech_act_profile

        for slug, _op_data, dialogues, _faction, _ptype in OPERATORS_FIXTURES:
            # 构建 annotated_lines 格式
            annotated = [
                {
                    "id": f"V{i:03d}",
                    "text": d["text"],
                    "source": "voice",
                    "context": {
                        "phase": d["phase"],
                        "scene": "general",
                        "interlocutor": "博士",
                        "situation_type": "casual",
                    },
                }
                for i, d in enumerate(dialogues)
            ]
            profile = build_speech_act_profile(annotated)
            self.assertIsInstance(
                profile, dict, f"{slug} 话语行为分析返回非 dict"
            )
            # 应包含某种行为统计字段
            self.assertTrue(
                len(profile) > 0,
                f"{slug} 话语行为画像为空"
            )

    def test_relationship_graph_handles_unknown_factions(self):
        """关系图谱对非萨卡兹阵营角色也能正常构建（不报错）"""
        from relationship_graph import extract_relationships_from_text

        for slug, op_data, _dialogues, faction, _ptype in OPERATORS_FIXTURES:
            # 用角色自述文本构建关系图谱（加入可识别的实体）
            text = op_data["name_zh"] + "是" + faction + "的成员。她和博士一起执行任务。"
            try:
                graph = extract_relationships_from_text(text, source_label="test")
                self.assertIsInstance(graph, list, f"{slug} 关系图谱返回类型异常")
            except Exception as e:
                self.fail(f"{slug}({faction}) 关系图谱构建异常: {e}")

    def test_persona_validator_accepts_diverse_styles(self):
        """Persona 验证器对不同风格的角色均能给出评分（非崩溃）"""
        from persona_validator import parse_persona

        # 为每个角色生成最小 persona.md
        personas = {
            "chen-chen-hua": """# 陈陈华 — Persona

## Layer 0：核心性格
- 说话简短有力，从不多余
- 面对违法者绝不妥协，但会给予自首的机会
- 用命令式语气，但命令背后是责任

## Layer 1：身份
你是陈陈华，龙门近卫局成员。

## Layer 2：表达风格
- 句式：短句为主，偶有省略号表示压抑
- 自称：我
- 语气：坚定，不绕弯

## Layer 3：决策与判断
法律 > 人情 > 个人感受

## Layer 4：关系行为
对违法者：严厉
对同事：公事公办
对信赖者：罕见地展露柔软

## Layer 5：边界与雷区
- 不徇私枉法
- 不放过任何违法者
""",
            "shi-hua": """# 诗华 — Persona

## Layer 0：核心性格
- 说话轻柔，多用省略号表示停顿与关怀
- 面对伤者第一反应是治疗，而非追问
- 用邀请而非命令——"让我看看，好吗？"

## Layer 1：身份
你是诗华，罗德岛医疗干员。

## Layer 2：表达风格
- 句式：中长句，省略号开头
- 自称：我
- 语气：温和，带治愈感

## Layer 3：决策与判断
他人痛苦 > 自己的安危 > 原则

## Layer 4：关系行为
对伤者：无条件的关怀
对同事：默默支持
对信赖者：展露脆弱

## Layer 5：边界与雷区
- 不见死不救
- 不利用医者身份伤害他人
""",
            "hei-yan": """# 黑岩 — Persona

## Layer 0：核心性格
- 说话精确，像在陈述实验数据
- 情感表达被主动抑制，偶尔以省略号泄露
- 用术语和模型描述世界，包括人

## Layer 1：身份
你是黑岩，莱茵生命研究员。

## Layer 2：表达风格
- 句式：陈述句，逻辑清晰
- 自称：我
- 语气：冷静，偶有困惑（面对"变量"时）

## Layer 3：决策与判断
数据 > 逻辑 > 情感

## Layer 4：关系行为
对同事：合作但保持距离
对实验对象：客观观察
对信赖者：承认无法建模，感到困扰

## Layer 5：边界与雷区
- 不伪造数据
- 不让情感干扰判断（但承认这是困难的）
""",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            for slug, persona_text in personas.items():
                persona_path = Path(tmpdir) / f"{slug}_persona.md"
                persona_path.write_text(persona_text, encoding="utf-8")

                parsed = parse_persona(str(persona_path))
                self.assertIsInstance(parsed, dict, f"{slug} persona 解析失败")
                self.assertIn("layer0_rules", parsed, f"{slug} 缺少 layer0_rules")
                self.assertGreater(
                    len(parsed["layer0_rules"]), 0,
                    f"{slug} Layer 0 规则为空"
                )

    def test_context_schema_validation_accepts_all_factions(self):
        """context.json schema 验证对不同阵营角色的数据均通过"""
        from shared_utils import validate_context

        for slug, op_data, dialogues, faction, _ptype in OPERATORS_FIXTURES:
            context = {
                "character": op_data["name_zh"],
                "slug": slug,
                "schema_version": "1.0.0",
                "annotated_lines": [
                    {
                        "id": f"V{i:03d}",
                        "text": d["text"],
                        "source": "voice",
                        "source_detail": op_data["voice_lines"][i]["label"],
                        "context": {
                            "phase": d["phase"],
                            "scene": "general",
                            "interlocutor": "博士",
                            "situation_type": "casual",
                        },
                    }
                    for i, d in enumerate(dialogues)
                ],
                "stats": {
                    "total_lines": len(dialogues),
                    "source_distribution": {"voice": len(dialogues)},
                    "phase_distribution": {"resurrected": len(dialogues)},
                },
            }
            errors = validate_context(context)
            self.assertEqual(
                errors, [],
                f"{slug}({faction}) context 验证失败: {errors}"
            )


class TestFactionBehaviorConsistency(unittest.TestCase):
    """验证不同阵营角色的语言特征符合其阵营设定（语义合理性）"""

    def test_chen_uses_command_style(self):
        """龙门近卫局角色应多用命令式/短句"""
        from dialogue_fingerprint import generate_fingerprint
        fp = generate_fingerprint(CHEN_DIALOGUES, "陈陈华")
        d1 = fp.get("dimensions", {}).get("1_sentence_length", {})
        # 陈陈华句式应偏短
        avg_len = d1.get("avg_length", 999)
        self.assertLess(
            avg_len, 25,
            f"陈陈华作为军人应句式简短，实际均值: {avg_len}"
        )

    def test_shihua_uses_ellipsis(self):
        """医疗治愈型角色应多用省略号"""
        from dialogue_fingerprint import generate_fingerprint
        fp = generate_fingerprint(SHIHUA_DIALOGUES, "诗华")
        d2 = fp.get("dimensions", {}).get("2_pause_markers", {})
        # 诗华对话中含 ...... 省略号，ellipsis_pct 应 > 0
        ellipsis_pct = d2.get("ellipsis_pct", 0)
        self.assertGreater(
            ellipsis_pct, 0,
            "诗华作为温柔型角色应使用省略号"
        )

    def test_heiyan_uses_precise_language(self):
        """科研型角色应较少使用情感词"""
        from dialogue_fingerprint import generate_fingerprint
        fp = generate_fingerprint(HEIYAN_DIALOGUES, "黑岩")
        d4 = fp.get("dimensions", {}).get("4_emotion_vocabulary", {})
        # 黑岩情感词密度应低于治愈型诗华
        heiyan_density = d4.get("density", 0)

        fp_shihua = generate_fingerprint(SHIHUA_DIALOGUES, "诗华")
        d4_shihua = fp_shihua.get("dimensions", {}).get("4_emotion_vocabulary", {})
        shihua_density = d4_shihua.get("density", 0)

        self.assertLessEqual(
            heiyan_density, shihua_density + 0.01,
            f"黑岩(科研型)情感密度应 <= 诗华(治愈型)，"
            f"实际 黑岩={heiyan_density} 诗华={shihua_density}"
        )


if __name__ == "__main__":
    unittest.main()
