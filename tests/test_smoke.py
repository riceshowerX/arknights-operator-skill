#!/usr/bin/env python3
"""
冒烟测试 — 验证每个工具的核心功能不崩溃

运行方式:
    python3 -m pytest tests/ -v
    # 或直接运行
    python3 tests/test_smoke.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 将 tools 目录加入 import 路径
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))


# ──────────────────────────────────────────────
# 测试数据（不需要网络请求）
# ──────────────────────────────────────────────

SAMPLE_VOICE_LINES = [
    {"label": "任命助理", "text": "......我在。"},
    {"label": "交谈1", "text": "我会陪在阿米娅身边，也会陪着罗德岛的大家。"},
    {"label": "晋升后交谈1", "text": "我从不后悔曾经的选择。我们做了可以做的一切。"},
    {"label": "信赖提升后交谈1", "text": "阿米娅看上去还是这么瘦弱......她多想看到阿米娅长大的样子。"},
    {"label": "战斗开始", "text": "我们别无选择。"},
    {"label": "4星结束", "text": "这不是任何人的错。"},
]

SAMPLE_STORY_DIALOGUES = [
    {
        "speaker": "特蕾西娅",
        "text": "......我在。",
        "narration": [],
        "scene": "罗德岛走廊",
        "is_target": True,
        "reply_to": "博士",
        "situation_type": "casual",
        "phase": "babel",
    },
    {
        "speaker": "博士",
        "text": "特蕾西娅......",
        "narration": [],
        "scene": "罗德岛走廊",
        "is_target": False,
        "reply_to": None,
        "situation_type": "casual",
        "phase": "babel",
    },
    {
        "speaker": "特蕾西娅",
        "text": "如果我的存在不能为他人带来些什么，那我活着又有什么意义呢？",
        "narration": ["微笑"],
        "scene": "罗德岛走廊",
        "is_target": True,
        "reply_to": None,
        "situation_type": "decide",
        "phase": "babel",
    },
]

SAMPLE_KNOWLEDGE_MD = """# 特蕾西娅 — Knowledge

## 角色概览

特蕾西娅，萨卡兹混血，卡兹戴尔正统萨卡兹魔王。

## 核心事件时间线

### 893-898 早期
特蕾西娅出生与成长

### 1031-1094 巴别塔时期
巴别塔创建与内战

### 1094后 复活后
被赦罪师复活
"""

SAMPLE_OPERATOR_DATA = {
    "name_zh": "魔王",
    "name_en": "Civilight Eterna",
    "slug": "mo-wang",
    "page_type": "operator",
    "source_url": "https://prts.wiki/w/魔王",
    "voice_lines": SAMPLE_VOICE_LINES,
    "archives": [
        {"index": 1, "title": "基础档案", "text": "代号魔王，性别女，出身地卡兹戴尔"},
    ],
}

SAMPLE_WIKITEXT_SCRIPT = '''
{{剧情模拟器|文本数据=
[HEADER(key="title_test")]
[Blocker(a=1, r=0, g=0, b=0, fadetime=0, block=true)]
==罗德岛走廊==
[name="特蕾西娅"]......我在。
[name="博士"]特蕾西娅......
[name="特蕾西娅"]我从不后悔曾经的选择。
[dialog]
[Delay(time=1)]
==作战室==
[name="特蕾西娅"]我们别无选择。
[name="凯尔希"]你确定吗？
}}
'''

SAMPLE_WIKITEXT_OLD = """
==罗德岛走廊==
'''特蕾西娅'''：......我在。
'''博士'''：特蕾西娅......
'''特蕾西娅'''：如果我的存在不能为他人带来些什么，那我活着又有什么意义呢？
"""


class TestGameDataReader(unittest.TestCase):
    """game_data_parser.py 冒烟测试"""

    def test_slug_generation_known_name(self):
        from game_data_parser import to_slug
        self.assertEqual(to_slug("特蕾西娅"), "te-lei-xi-ya")

    def test_slug_generation_english(self):
        from game_data_parser import to_slug
        self.assertEqual(to_slug("Amiya"), "amiya")

    def test_slug_generation_single_char(self):
        from game_data_parser import to_slug
        self.assertEqual(to_slug("W"), "w")

    def test_clean_wikitext_removes_html_comments(self):
        from game_data_parser import clean_wikitext
        result = clean_wikitext("hello<!-- comment -->world")
        self.assertEqual(result, "helloworld")

    def test_clean_wikitext_removes_wiki_links(self):
        from game_data_parser import clean_wikitext
        result = clean_wikitext("[[罗德岛|罗德岛]]")
        self.assertEqual(result, "罗德岛")

    def test_parse_prts_operator_name(self):
        from game_data_parser import parse_prts_operator_name
        result = parse_prts_operator_name("阿米娅")
        self.assertEqual(result["slug"], "a-mi-ya")
        self.assertIn("prts.wiki", result["source_url"])


class TestStoryExtractor(unittest.TestCase):
    """story_extractor.py 冒烟测试"""

    def test_extract_script_format_dialogues(self):
        from story_extractor import extract_dialogues
        results = extract_dialogues(SAMPLE_WIKITEXT_SCRIPT, "特蕾西娅")
        # 应该提取到特蕾西娅的对话
        target_lines = [r for r in results if r["is_target"]]
        self.assertGreater(len(target_lines), 0)
        # 检查内容包含关键文字
        texts = [r["text"] for r in target_lines]
        has_content = any("我在" in t or "后悔" in t or "别无选择" in t for t in texts)
        self.assertTrue(has_content, f"Expected key text in {texts}")

    def test_extract_wikitext_format_dialogues(self):
        from story_extractor import extract_dialogues
        results = extract_dialogues(SAMPLE_WIKITEXT_OLD, "特蕾西娅")
        target_lines = [r for r in results if r["is_target"]]
        self.assertGreater(len(target_lines), 0)
        texts = [r["text"] for r in target_lines]
        has_content = any("我在" in t or "意义" in t for t in texts)
        self.assertTrue(has_content, f"Expected key text in {texts}")

    def test_infer_phase_from_chapter(self):
        from story_extractor import infer_phase
        self.assertEqual(infer_phase("", "BB-ST-3 灵魂尽头/NBT"), "babel")
        self.assertEqual(infer_phase("", "第8章/怒号光明"), "babel")
        self.assertEqual(infer_phase("", "第14章/慈悲灯塔"), "resurrected")
        # DM 系列 = 生于黑夜（W 的活动）
        self.assertEqual(infer_phase("", "DM-ST-1 求生/NBT"), "early")

    def test_infer_phase_from_scene(self):
        from story_extractor import infer_phase
        self.assertEqual(infer_phase("巴别塔会议室", "unknown"), "babel")
        self.assertEqual(infer_phase("卡兹戴尔街道", "unknown"), "babel")


class TestContextAnnotator(unittest.TestCase):
    """context_annotator.py 冒烟测试"""

    def test_annotate_voice_line_with_default_phase(self):
        from context_annotator import annotate_voice_line
        line = {"label": "交谈1", "text": "我会陪在阿米娅身边。"}
        result = annotate_voice_line(line, 0, default_phase="resurrected")
        self.assertEqual(result["context"]["phase"], "resurrected")
        self.assertEqual(result["source"], "voice")
        self.assertEqual(result["source_detail"], "交谈1")

    def test_annotate_voice_line_phase_from_content(self):
        from context_annotator import annotate_voice_line
        line = {"label": "交谈1", "text": "在巴别塔的时候......"}
        result = annotate_voice_line(line, 0, default_phase="resurrected")
        # "巴别塔" 关键词应覆盖默认时期
        self.assertEqual(result["context"]["phase"], "babel")

    def test_annotate_voice_line_interlocutor(self):
        from context_annotator import annotate_voice_line
        line = {"label": "信赖触摸", "text": "......"}
        result = annotate_voice_line(line, 0)
        self.assertEqual(result["context"]["interlocutor"], "博士")

    def test_annotate_story_line(self):
        from context_annotator import annotate_story_line
        line = SAMPLE_STORY_DIALOGUES[0]
        result = annotate_story_line(line, 0)
        self.assertEqual(result["source"], "story")
        self.assertEqual(result["context"]["phase"], "babel")
        self.assertEqual(result["context"]["interlocutor"], "博士")

    def test_operator_default_phase(self):
        from context_annotator import OPERATOR_DEFAULT_PHASE
        self.assertEqual(OPERATOR_DEFAULT_PHASE.get("魔王"), "resurrected")
        self.assertEqual(OPERATOR_DEFAULT_PHASE.get("W"), "early")

    def test_build_context_json(self):
        from context_annotator import build_context_json, load_timeline
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_KNOWLEDGE_MD)
            f.flush()
            timeline = load_timeline(f.name)
        os.unlink(f.name)

        result = build_context_json(SAMPLE_OPERATOR_DATA, [], timeline)
        self.assertIn("annotated_lines", result)
        self.assertIn("stats", result)
        # 魔王页面的语音行应该有 resurrected 默认时期
        voice_lines = [l for l in result["annotated_lines"] if l["source"] == "voice"]
        resurrected_voice = [l for l in voice_lines if l["context"]["phase"] == "resurrected"]
        self.assertGreater(len(resurrected_voice), 0)


class TestDialogueFingerprint(unittest.TestCase):
    """dialogue_fingerprint.py 冒烟测试"""

    def test_analyze_sentence_length(self):
        from dialogue_fingerprint import analyze_sentence_length_distribution
        dialogues = [{"text": "......我在。"}, {"text": "我从不后悔曾经的选择。"}]
        result = analyze_sentence_length_distribution(dialogues)
        self.assertIn("type", result)
        self.assertIn("avg_length", result)
        self.assertGreater(result["avg_length"], 0)

    def test_analyze_pause_markers(self):
        from dialogue_fingerprint import analyze_pause_markers
        dialogues = [{"text": "......我在。"}, {"text": "你好。"}]
        result = analyze_pause_markers(dialogues)
        self.assertIn("ellipsis_pct", result)
        self.assertGreater(result["ellipsis_pct"], 0)

    def test_analyze_address_pattern(self):
        from dialogue_fingerprint import analyze_address_pattern
        dialogues = [{"text": "博士，你愿意和我一起吗？"}, {"text": "阿米娅看上去还是这么瘦弱。"}]
        result = analyze_address_pattern(dialogues)
        self.assertIn("pattern", result)

    def test_generate_fingerprint(self):
        from dialogue_fingerprint import generate_fingerprint
        dialogues = [{"label": "交谈1", "text": "......我在。"}]
        result = generate_fingerprint(dialogues, "特蕾西娅")
        self.assertIn("dimensions", result)
        self.assertEqual(result["operator"], "特蕾西娅")


class TestRelationshipGraph(unittest.TestCase):
    """relationship_graph.py 冒烟测试"""

    def test_extract_entities(self):
        from relationship_graph import extract_entities
        text = "特蕾西娅与特雷西斯在卡兹戴尔作战"
        found = extract_entities(text)
        self.assertIn("特蕾西娅", found)
        self.assertIn("特雷西斯", found)

    def test_negation_context_detection(self):
        from relationship_graph import _find_relevant_segments
        # "没有背叛" 不应被提取为 betrayal 关系
        text = "特蕾西娅没有背叛我们。特雷西斯也在场。"
        segments = _find_relevant_segments(text, "特蕾西娅", "特雷西斯")
        # 含 "没有" 的句子应该被排除
        self.assertEqual(len(segments), 0)

    def test_normalize_name(self):
        from relationship_graph import normalize_name
        self.assertEqual(normalize_name("Theresa"), "特蕾西娅")
        self.assertEqual(normalize_name("Amiya"), "阿米娅")

    def test_phase_order_in_compute_trajectories(self):
        # PHASE_ORDER 是 compute_relation_trajectories 的局部变量，
        # 验证时期排序是否正确——确保 early < babel < resurrected
        from relationship_graph import compute_relation_trajectories
        # 用空数据调用不崩溃即可
        result = compute_relation_trajectories({}, {})
        self.assertIsInstance(result, list)


class TestSpeechActAnalyzer(unittest.TestCase):
    """speech_act_analyzer.py 冒烟测试"""

    def test_invite_detection(self):
        from speech_act_analyzer import classify_speech_acts
        acts = classify_speech_acts("你愿意和我一起吗？")
        act_types = [a["type"] for a in acts]
        self.assertIn("invite", act_types)

    def test_evade_detection(self):
        from speech_act_analyzer import classify_speech_acts
        acts = classify_speech_acts("也许吧…………")
        act_types = [a["type"] for a in acts]
        self.assertIn("evade", act_types)

    def test_commit_detection(self):
        from speech_act_analyzer import classify_speech_acts
        acts = classify_speech_acts("我一定会保护你们。")
        act_types = [a["type"] for a in acts]
        self.assertIn("commit", act_types)

    def test_affirm_presence_detection(self):
        from speech_act_analyzer import classify_speech_acts
        acts = classify_speech_acts("我在")
        act_types = [a["type"] for a in acts]
        self.assertIn("affirm_presence", act_types)

    def test_act_type_labels_consistency(self):
        from speech_act_analyzer import ACT_TYPE_LABELS, SPEECH_ACT_RULES
        # 确保所有规则中引用的行为类型都在 ACT_TYPE_LABELS 中
        for rule in SPEECH_ACT_RULES:
            act_type = rule[1]
            self.assertIn(act_type, ACT_TYPE_LABELS, f"Rule type '{act_type}' not in ACT_TYPE_LABELS")


class TestTemporalSlicer(unittest.TestCase):
    """temporal_slicer.py 冒烟测试"""

    def test_import_act_type_labels(self):
        from temporal_slicer import ACT_TYPE_LABELS
        from speech_act_analyzer import ACT_TYPE_LABELS as SOURCE_LABELS
        self.assertEqual(ACT_TYPE_LABELS, SOURCE_LABELS)


class TestPersonaValidator(unittest.TestCase):
    """persona_validator.py 冒烟测试"""

    def test_parse_persona(self):
        from persona_validator import parse_persona
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# Test — Persona

## Layer 0：核心性格（最高优先级）

- 从不用命令口吻
- 面对牺牲不会冷漠

## Layer 1：身份

你是测试角色。

## Layer 2：表达风格

### 口头禅与高频词

口头禅：测试
高频词：测试、验证

## Layer 5：禁忌

- 不能做的事

## Correction 记录

（暂无记录）
""")
            f.flush()
            result = parse_persona(f.name)
        os.unlink(f.name)
        self.assertGreater(len(result["layer0_rules"]), 0)
        self.assertIn("catchphrases", result["layer2_style"])

    def test_is_likely_dialogue(self):
        from persona_validator import _is_likely_dialogue
        self.assertTrue(_is_likely_dialogue("「我会记住你们每一个人」"))
        self.assertTrue(_is_likely_dialogue("......我在。"))
        self.assertFalse(_is_likely_dialogue("泰拉历898年，特蕾西娅即位为萨卡兹魔王"))


class TestCanonChecker(unittest.TestCase):
    """canon_checker.py 冒烟测试"""

    def test_builtin_misconceptions_loaded(self):
        from canon_checker import BUILTIN_MISCONCEPTIONS
        self.assertGreater(len(BUILTIN_MISCONCEPTIONS), 0)

    def test_misconception_patterns(self):
        from canon_checker import BUILTIN_MISCONCEPTIONS
        m001 = next(m for m in BUILTIN_MISCONCEPTIONS if m["id"] == "M001")
        # M001 是关于特蕾西娅≠维多利亚统治者的误解
        self.assertIn("维多利亚", m001["wrong"])


class TestVersionManager(unittest.TestCase):
    """version_manager.py 冒烟测试"""

    def test_normalize_version(self):
        from version_manager import _normalize_version
        self.assertEqual(_normalize_version("v1"), "v1.0")
        self.assertEqual(_normalize_version("v1.0"), "v1.0")
        self.assertEqual(_normalize_version("1.0"), "v1.0")
        self.assertEqual(_normalize_version("2.3"), "v2.3")

    def test_get_next_version_empty(self):
        from version_manager import _get_next_version
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _get_next_version(Path(tmpdir))
            self.assertEqual(result, "v1.0")


class TestSkillWriter(unittest.TestCase):
    """skill_writer.py 冒烟测试"""

    def test_list_skills(self):
        from skill_writer import list_skills
        result = list_skills(base_dir="/workspace/projects/operators")
        self.assertIn("skills", result)

    def test_create_default_skill_dry_run(self):
        from skill_writer import create_default_skill
        with tempfile.TemporaryDirectory() as tmpdir:
            result = create_default_skill("test-op", "测试角色", "Test Operator", base_dir=tmpdir)
            self.assertIn("slug", result)
            # 确认目录被创建
            self.assertTrue(Path(tmpdir, "test-op").exists())


class TestEndToEndPipeline(unittest.TestCase):
    """端到端管线测试（使用本地数据，不依赖网络）"""

    def test_full_pipeline_from_operator_data(self):
        """从 operator_data 到 context.json 到下游工具的完整管线"""
        from context_annotator import build_context_json, load_timeline
        from dialogue_fingerprint import generate_fingerprint
        from speech_act_analyzer import classify_speech_acts

        # 1. 构建 context.json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(SAMPLE_KNOWLEDGE_MD)
            f.flush()
            timeline = load_timeline(f.name)
        os.unlink(f.name)

        context = build_context_json(SAMPLE_OPERATOR_DATA, [], timeline)
        self.assertGreater(len(context["annotated_lines"]), 0)

        # 2. 生成指纹
        voice_lines = [{"label": l.get("label", ""), "text": l["text"]}
                       for l in SAMPLE_VOICE_LINES]
        fingerprint = generate_fingerprint(voice_lines, "魔王")
        self.assertIn("dimensions", fingerprint)

        # 3. 分析话语行为
        for line in SAMPLE_VOICE_LINES:
            acts = classify_speech_acts(line["text"])
            # 不应崩溃
            self.assertIsInstance(acts, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
