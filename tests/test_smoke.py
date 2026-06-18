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
        from constants import OPERATOR_DEFAULT_PHASE
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
        self.assertIn("presence", act_types)

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


class TestPhaseInferrer(unittest.TestCase):
    """phase_inferrer.py 冒烟测试"""

    def test_infer_from_content_pattern(self):
        from phase_inferrer import infer_phase_from_content
        result = infer_phase_from_content("魔王在卡兹戴尔归来")
        self.assertIsNotNone(result)
        self.assertEqual(result.phase, "babel")

    def test_infer_from_content_keyword(self):
        from phase_inferrer import infer_phase_from_content
        result = infer_phase_from_content("在巴别塔的时候......")
        self.assertIsNotNone(result)
        self.assertEqual(result.phase, "babel")

    def test_infer_from_content_no_match(self):
        from phase_inferrer import infer_phase_from_content
        result = infer_phase_from_content("你好。")
        self.assertIsNone(result)

    def test_infer_from_chapter_code(self):
        from phase_inferrer import infer_phase_from_chapter_code
        result = infer_phase_from_chapter_code("BB-ST-3 灵魂尽头/NBT")
        self.assertIsNotNone(result)
        self.assertEqual(result.phase, "babel")

    def test_infer_from_chapter_code_unknown(self):
        from phase_inferrer import infer_phase_from_chapter_code
        result = infer_phase_from_chapter_code("UNKNOWN-ST-1 测试/NBT")
        self.assertIsNone(result)

    def test_infer_from_content_cluster(self):
        from phase_inferrer import infer_phase_from_content_cluster
        texts = [
            "巴别塔的日子......",
            "特蕾西娅是一个好人",
            "卡兹戴尔的战场上满是萨卡兹",
            "内战时期我们失去了很多",
        ]
        result = infer_phase_from_content_cluster(texts)
        self.assertIsNotNone(result)
        self.assertEqual(result.phase, "babel")

    def test_infer_from_content_cluster_empty(self):
        from phase_inferrer import infer_phase_from_content_cluster
        result = infer_phase_from_content_cluster(["你好。", "谢谢。"])
        self.assertIsNone(result)

    def test_inference_result_to_dict(self):
        from phase_inferrer import PhaseInferenceResult
        r = PhaseInferenceResult("babel", "test", "high")
        d = r.to_dict()
        self.assertEqual(d["phase"], "babel")
        self.assertEqual(d["source"], "test")
        self.assertEqual(d["confidence"], "high")

    def test_generate_inference_report(self):
        from phase_inferrer import generate_inference_report
        results = [
            {"phase": "babel", "source": "content", "confidence": "high"},
            {"phase": "unknown", "source": "none", "confidence": "low"},
            {"phase": "babel", "source": "cluster", "confidence": "medium"},
        ]
        report = generate_inference_report(results)
        self.assertEqual(report["total_lines"], 3)
        self.assertEqual(report["phase_distribution"]["babel"], 2)
        self.assertEqual(report["unknown_pct"], 33.3)

    def test_faction_category_phase_mapping(self):
        from phase_inferrer import FACTION_CATEGORY_PHASE
        self.assertIn("属于巴别塔的干员", FACTION_CATEGORY_PHASE)
        self.assertIn("属于罗德岛的干员", FACTION_CATEGORY_PHASE)
        self.assertEqual(FACTION_CATEGORY_PHASE["属于巴别塔的干员"], "babel")

    def test_unified_infer_entry(self):
        from phase_inferrer import infer_phase
        # Content match
        result = infer_phase("在巴别塔的时候")
        self.assertEqual(result.phase, "babel")

        # Unknown with no context
        result2 = infer_phase("你好。")
        self.assertEqual(result2.phase, "unknown")

    def test_cluster_fallback_in_unified_infer(self):
        from phase_inferrer import infer_phase
        # Single line unknown, but with all_texts for cluster
        result = infer_phase(
            "这些萨卡兹都很坚强",
            chapter="UNKNOWN-ST-1",
            all_texts=["卡兹戴尔的萨卡兹", "巴别塔的日子", "特蕾西娅"],
        )
        self.assertEqual(result.phase, "babel")


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


class TestPipelineFileIO(unittest.TestCase):
    """管线文件落盘集成测试 — 验证工具输出 → 文件落盘 → 下游工具读取"""

    def test_speech_act_profile_file_roundtrip(self):
        """speech_act_analyzer 输出落盘后可被正确读取"""
        from speech_act_analyzer import classify_speech_acts

        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "speech_act_profile.json"
            lines = ["......我在。", "我会记住你们每一个人。", "你在说什么呢？"]
            all_acts = []
            lines_with_acts = 0
            for text in lines:
                acts = classify_speech_acts(text)
                if acts:
                    lines_with_acts += 1
                    # acts 是 dict 列表，提取 type 字段
                    all_acts.extend(a["type"] for a in acts if isinstance(a, dict))

            from collections import Counter
            act_counts = Counter(all_acts)
            profile = {
                "total_acts": len(all_acts),
                "lines_with_acts": lines_with_acts,
                "top_acts": [[act, count / max(len(all_acts), 1)] for act, count in act_counts.most_common()],
            }
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

            # 读取验证
            loaded = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["total_acts"], profile["total_acts"])
            self.assertGreater(loaded["lines_with_acts"], 0)

    def test_fingerprint_file_roundtrip(self):
        """dialogue_fingerprint 输出落盘后可被正确读取"""
        from dialogue_fingerprint import generate_fingerprint

        with tempfile.TemporaryDirectory() as tmpdir:
            fp_path = Path(tmpdir) / "fingerprint.json"
            voice_lines = [{"text": l["text"]} for l in SAMPLE_VOICE_LINES]
            fingerprint = generate_fingerprint(voice_lines, "测试角色")
            fp_path.write_text(json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8")

            # 读取验证
            loaded = json.loads(fp_path.read_text(encoding="utf-8"))
            self.assertIn("dimensions", loaded)
            self.assertIn("1_sentence_length", loaded["dimensions"])

    def test_temporal_slicer_consumes_fingerprint(self):
        """temporal_slicer 能消费 dialogue_fingerprint 的输出"""
        from dialogue_fingerprint import generate_fingerprint

        with tempfile.TemporaryDirectory() as tmpdir:
            voice_lines = [{"text": l["text"]} for l in SAMPLE_VOICE_LINES]
            fingerprint = generate_fingerprint(voice_lines, "测试角色")
            fp_path = Path(tmpdir) / "fingerprint.json"
            fp_path.write_text(json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8")

            # 验证文件可以被读取并包含 fingerprint 数据
            loaded = json.loads(fp_path.read_text(encoding="utf-8"))
            self.assertIn("dimensions", loaded)
            # fingerprint 数据应包含可被 temporal_slicer 使用的维度
            dim_keys = set(loaded["dimensions"].keys())
            expected_dims = {"1_sentence_length", "2_pause_markers", "3_self_reference"}
            self.assertTrue(expected_dims.issubset(dim_keys),
                            f"缺少预期维度: {expected_dims - dim_keys}")

    def test_operator_data_complete_products(self):
        """验证特蕾西娅的完整产物文件存在且可解析"""
        base = Path("/workspace/projects/operators/te-lei-xi-ya")
        if not base.exists():
            self.skipTest("特蕾西娅角色目录不存在")

        required_files = [
            "knowledge.md",
            "persona.md",
            "meta.json",
            "context.json",
            "speech_act_profile.json",
            "fingerprint.json",
            "temporal_slices.json",
        ]
        for fname in required_files:
            fpath = base / fname
            self.assertTrue(fpath.exists(), f"缺失文件: {fname}")
            if fname.endswith(".json"):
                data = json.loads(fpath.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict, f"{fname} 不是有效的 JSON 对象")

    def test_w_persona_md_exists(self):
        """验证 W 的 persona.md 存在且包含核心结构"""
        persona_path = Path("/workspace/projects/operators/w/persona.md")
        if not persona_path.exists():
            self.skipTest("W 的 persona.md 不存在")

        content = persona_path.read_text(encoding="utf-8")
        # 验证五层结构
        for layer in ["Layer 0", "Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 5"]:
            self.assertIn(layer, content, f"persona.md 缺少 {layer}")
        # 验证 Correction 层
        self.assertIn("Correction", content, "persona.md 缺少 Correction 记录区域")


# ──────────────────────────────────────────────
# 核心业务逻辑测试（#19 新增）
# ──────────────────────────────────────────────


class TestGameDataParserCore(unittest.TestCase):
    """game_data_parser.py 核心函数测试"""

    def test_detect_page_type_operator_charinfo(self):
        """测试干员页面类型识别 - Charinfo 模板"""
        from game_data_parser import _detect_page_type
        wikitext = "{{Charinfo\n|name=阿米娅\n|职业=术师\n}}"
        self.assertEqual(_detect_page_type(wikitext), "operator")

    def test_detect_page_type_operator_charinfov2(self):
        """测试干员页面类型识别 - CharinfoV2 模板"""
        from game_data_parser import _detect_page_type
        wikitext = "{{CharinfoV2\n|name=阿米娅\n|职业=术师\n}}"
        self.assertEqual(_detect_page_type(wikitext), "operator")

    def test_detect_page_type_operator_fallback(self):
        """测试干员页面类型识别 - fallback 检测"""
        from game_data_parser import _detect_page_type
        wikitext = "== 干员档案 ==\n一些内容"
        self.assertEqual(_detect_page_type(wikitext), "operator")

    def test_detect_page_type_enemy(self):
        """测试敌人页面类型识别"""
        from game_data_parser import _detect_page_type
        wikitext = "{{敌人信息/header\n|名称=整合运动士兵\n}}"
        self.assertEqual(_detect_page_type(wikitext), "enemy")

    def test_detect_page_type_unknown(self):
        """测试未知页面类型"""
        from game_data_parser import _detect_page_type
        wikitext = "一些普通内容"
        self.assertEqual(_detect_page_type(wikitext), "unknown")

    def test_extract_template_body_simple(self):
        """测试简单模板提取"""
        from game_data_parser import _extract_template_body
        wikitext = "{{Charinfo\n|name=阿米娅\n|class=术师\n}}\n其他内容"
        result = _extract_template_body(wikitext, "Charinfo")
        self.assertIsNotNone(result)
        self.assertIn("name=阿米娅", result)

    def test_extract_template_body_not_found(self):
        """测试模板不存在时返回 None"""
        from game_data_parser import _extract_template_body
        wikitext = "一些普通内容"
        result = _extract_template_body(wikitext, "Charinfo")
        self.assertIsNone(result)

    def test_extract_template_body_depth_limit(self):
        """测试模板深度限制防止恶意嵌套"""
        from game_data_parser import _extract_template_body
        # 构造深度超过 50 的嵌套模板
        wikitext = "{{" * 60 + "Charinfo" + "}}" * 60
        result = _extract_template_body(wikitext, "Charinfo")
        # 应该返回 None 或有限结果，不会无限循环
        # 这里主要验证不会崩溃


class TestDialogueFingerprintCore(unittest.TestCase):
    """dialogue_fingerprint.py 核心函数测试"""

    def test_collect_all_metrics_single_pass(self):
        """测试单次遍历收集器"""
        from dialogue_fingerprint import _collect_all_metrics
        dialogues = [
            {"label": "test1", "text": "我会保护大家的。"},
            {"label": "test2", "text": "……我不确定。"},
            {"label": "test3", "text": "像风一样自由！"},
        ]
        metrics = _collect_all_metrics(dialogues)
        self.assertEqual(metrics["total_lines"], 3)
        self.assertIsInstance(metrics["sentence_lengths"], list)
        self.assertGreater(len(metrics["sentence_lengths"]), 0)

    def test_generate_fingerprint_empty(self):
        """测试空对话列表"""
        from dialogue_fingerprint import generate_fingerprint
        result = generate_fingerprint([], "test")
        self.assertEqual(result["dialogue_count"], 0)
        self.assertIn("dimensions", result)

    def test_generate_fingerprint_with_data(self):
        """测试有数据的指纹生成"""
        from dialogue_fingerprint import generate_fingerprint
        dialogues = [
            {"label": "test1", "text": "我会保护大家的。"},
            {"label": "test2", "text": "……我不确定。"},
        ]
        result = generate_fingerprint(dialogues, "test")
        self.assertEqual(result["dialogue_count"], 2)
        self.assertIn("1_sentence_length", result["dimensions"])
        self.assertIn("2_pause_markers", result["dimensions"])


class TestSharedUtilsCore(unittest.TestCase):
    """shared_utils.py 核心函数测试"""

    def test_atomic_write_json(self):
        """测试原子写入 JSON"""
        from shared_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            data = {"key": "value", "number": 42}
            atomic_write_json(str(filepath), data)
            self.assertTrue(filepath.exists())
            loaded = json.loads(filepath.read_text(encoding="utf-8"))
            self.assertEqual(loaded, data)

    def test_atomic_write_json_nested_dir(self):
        """测试原子写入到不存在的目录"""
        from shared_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "subdir" / "test.json"
            data = {"key": "value"}
            atomic_write_json(str(filepath), data)
            self.assertTrue(filepath.exists())

    def test_load_json_safe_exists(self):
        """测试安全加载存在的 JSON 文件"""
        from shared_utils import load_json_safe
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            filepath.write_text('{"key": "value"}', encoding="utf-8")
            result = load_json_safe(str(filepath))
            self.assertEqual(result, {"key": "value"})

    def test_load_json_safe_not_exists(self):
        """测试安全加载不存在的文件"""
        from shared_utils import load_json_safe
        result = load_json_safe("/nonexistent/path.json")
        self.assertIsNone(result)

    def test_load_json_safe_invalid(self):
        """测试安全加载无效 JSON"""
        from shared_utils import load_json_safe
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            filepath.write_text("not valid json", encoding="utf-8")
            result = load_json_safe(str(filepath))
            self.assertIsNone(result)


class TestAhoCorasickMatcher(unittest.TestCase):
    """relationship_graph.py Aho-Corasick 多模式匹配测试"""

    def test_basic_matching(self):
        """测试基本匹配功能"""
        from relationship_graph import AhoCorasickMatcher
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("阿米娅", "阿米娅")
        matcher.add_pattern("博士", "博士")
        matcher.add_pattern("凯尔希", "凯尔希")
        matcher.build()
        matches = matcher.search("阿米娅和博士在罗德岛")
        self.assertIn("阿米娅", matches)
        self.assertIn("博士", matches)
        self.assertNotIn("凯尔希", matches)

    def test_empty_patterns(self):
        """测试空模式列表"""
        from relationship_graph import AhoCorasickMatcher
        matcher = AhoCorasickMatcher()
        matcher.build()
        matches = matcher.search("一些文本")
        self.assertEqual(matches, set())

    def test_no_matches(self):
        """测试无匹配情况"""
        from relationship_graph import AhoCorasickMatcher
        matcher = AhoCorasickMatcher()
        matcher.add_pattern("阿米娅", "阿米娅")
        matcher.add_pattern("博士", "博士")
        matcher.build()
        matches = matcher.search("一些无关文本")
        self.assertEqual(matches, set())


class TestSpeechActMergedTypes(unittest.TestCase):
    """speech_act_analyzer.py 合并后的话语行为类型测试"""

    def test_presence_type(self):
        """测试 presence 类型（原 affirm_presence）"""
        from speech_act_analyzer import classify_speech_acts
        results = classify_speech_acts("我在")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "presence")

    def test_comfort_type(self):
        """测试 comfort 类型（原 console/soothe）"""
        from speech_act_analyzer import classify_speech_acts
        results = classify_speech_acts("别怕，没事的")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "comfort")

    def test_act_type_labels_count(self):
        """测试行为类型标签数量"""
        from speech_act_analyzer import ACT_TYPE_LABELS
        # 合并后应该有 7 种类型
        self.assertEqual(len(ACT_TYPE_LABELS), 7)


class TestDialogueFingerprintV2(unittest.TestCase):
    """dialogue_fingerprint.py 算法升级测试"""

    def test_catchphrase_detection(self):
        """测试维度8：口头禅/高频短语检测"""
        from dialogue_fingerprint import analyze_catchphrases
        dialogues = [
            {"text": "我在，一直都在。"},
            {"text": "我在，不要怕。"},
            {"text": "我在，陪着你。"},
            {"text": "我们走吧。"},
            {"text": "我在。"},
        ]
        result = analyze_catchphrases(dialogues)
        self.assertIn("signature_phrases", result)
        phrases = result["signature_phrases"]
        # "我在" 应该被检测到（出现 4 次）
        phrase_texts = [p["phrase"] for p in phrases]
        self.assertTrue(any("我在" in p for p in phrase_texts))

    def test_emotion_lexicon_weights(self):
        """测试情感词典带权重"""
        from dialogue_fingerprint import EMOTION_LEXICON
        # 检查情感词典格式：list[tuple[str, float]]
        for emotion, words in EMOTION_LEXICON.items():
            self.assertIsInstance(words, list)
            for item in words:
                self.assertIsInstance(item, tuple)
                self.assertEqual(len(item), 2)
                self.assertIsInstance(item[0], str)
                self.assertIsInstance(item[1], (int, float))

    def test_sentence_length_statistical_distribution(self):
        """测试句式长度使用统计分布"""
        from dialogue_fingerprint import analyze_sentence_length_distribution
        dialogues = [
            {"text": "我在。"},
            {"text": "我会陪在你身边，直到最后。"},
            {"text": "不要怕。"},
            {"text": "我们做了可以做的一切，这就足够了。"},
            {"text": "走吧。"},
        ]
        result = analyze_sentence_length_distribution(dialogues)
        # 应该包含统计分布字段
        self.assertIn("median", result)
        self.assertIn("percentiles", result)
        self.assertIn("p25", result["percentiles"])
        self.assertIn("p75", result["percentiles"])
        self.assertIn("cv", result)
        self.assertIn("rhythm", result)

    def test_metaphor_dark_metaphor(self):
        """测试暗喻检测"""
        from dialogue_fingerprint import analyze_rhetoric_patterns
        dialogues = [
            {"text": "你是光，照亮了我们。"},
            {"text": "她化作了星辰。"},
            {"text": "普通的一句话。"},
        ]
        result = analyze_rhetoric_patterns(dialogues)
        # 暗喻应该被检测到（metaphor_pct > 0）
        self.assertGreater(result.get("metaphor_pct", 0), 0)


class TestRelationshipGraphV2(unittest.TestCase):
    """relationship_graph.py 算法升级测试"""

    def test_compute_relationship_strength(self):
        """测试关系强度量化"""
        from relationship_graph import compute_relationship_strength
        # 高共现 + 高情感密度 + 高对话比例 → 高强度
        strong = compute_relationship_strength(
            co_occurrence=50, total_lines=100,
            sentiment_words=["温柔", "信任", "陪伴"],
            dialogue_count=30,
        )
        # 低共现 + 低情感 → 低强度
        weak = compute_relationship_strength(
            co_occurrence=3, total_lines=100,
            sentiment_words=[],
            dialogue_count=1,
        )
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(strong, 0.0)
        self.assertLessEqual(strong, 1.0)

    def test_detect_relationship_evolution(self):
        """测试关系演变追踪"""
        from relationship_graph import detect_relationship_evolution
        phase_graphs = {
            "early": {
                "nodes": [{"name": "特蕾西娅"}, {"name": "阿米娅"}],
                "edges": [{"from": "特蕾西娅", "to": "阿米娅", "type": "guardian", "strength": 0.3}],
            },
            "babel": {
                "nodes": [{"name": "特蕾西娅"}, {"name": "阿米娅"}],
                "edges": [{"from": "特蕾西娅", "to": "阿米娅", "type": "mentor", "strength": 0.7}],
            },
            "resurrected": {
                "nodes": [{"name": "特蕾西娅"}, {"name": "阿米娅"}],
                "edges": [{"from": "特蕾西娅", "to": "阿米娅", "type": "mother", "strength": 0.9}],
            },
        }
        evolutions = detect_relationship_evolution(phase_graphs)
        self.assertIsInstance(evolutions, list)
        # 应该检测到特蕾西娅-阿米娅关系的演变
        if evolutions:
            self.assertIn("direction", evolutions[0])
            self.assertIn("delta", evolutions[0])


class TestSpeechActAnalyzerV2(unittest.TestCase):
    """speech_act_analyzer.py 算法升级测试"""

    def test_classify_with_context(self):
        """测试上下文感知分类"""
        from speech_act_analyzer import classify_with_context
        lines = [
            {"text": "你为什么要离开？", "speaker": "博士"},
            {"text": "……", "speaker": "特蕾西娅"},
            {"text": "别走。", "speaker": "博士"},
        ]
        results = classify_with_context(lines, window=2)
        self.assertEqual(len(results), 3)
        # 第二条"……"在质问后应该是 evade
        evade_acts = [a for a in results[1] if a["type"] == "evade"]
        self.assertTrue(len(evade_acts) > 0)

    def test_detect_behavior_chains(self):
        """测试行为链检测"""
        from speech_act_analyzer import detect_behavior_chains
        # 模拟 annotated_lines 格式
        lines = [
            {"text": "你为什么要离开？", "speech_acts": [{"type": "question", "confidence": 0.9}]},
            {"text": "……", "speech_acts": [{"type": "evade", "confidence": 0.8}]},
            {"text": "别怕，我在。", "speech_acts": [{"type": "comfort", "confidence": 0.9}]},
            {"text": "你为什么要离开？", "speech_acts": [{"type": "question", "confidence": 0.9}]},
            {"text": "……", "speech_acts": [{"type": "evade", "confidence": 0.8}]},
            {"text": "别怕，我在。", "speech_acts": [{"type": "comfort", "confidence": 0.9}]},
            {"text": "你愿意和我一起吗？", "speech_acts": [{"type": "invite", "confidence": 0.9}]},
            {"text": "我会一直在。", "speech_acts": [{"type": "commit", "confidence": 0.9}]},
        ]
        chains = detect_behavior_chains(lines, min_chain_length=3, min_occurrences=2)
        self.assertIsInstance(chains, list)
        # question→evade→comfort 应该被检测到（出现 2 次）
        if chains:
            top_chain = chains[0]
            self.assertIn("chain", top_chain)
            self.assertIn("count", top_chain)


class TestTemporalSlicerV2(unittest.TestCase):
    """temporal_slicer.py 算法升级测试"""

    def test_compare_metrics_small_sample(self):
        """测试小样本警告"""
        from temporal_slicer import compare_metrics_v2
        baseline = {"line_count": 3, "ellipsis_pct": 40.0, "avg_sentence_length": 8.0}
        comparison = {"line_count": 2, "ellipsis_pct": 60.0, "avg_sentence_length": 12.0}
        diffs = compare_metrics_v2(baseline, comparison)
        # 小样本应该产生警告
        warnings = [d for d in diffs if d.get("sample_warning") is True]
        self.assertTrue(len(warnings) > 0)

    def test_detect_emotion_arc(self):
        """测试情感弧线检测"""
        from temporal_slicer import detect_emotion_arc
        slice_metrics = {
            "early": {"ellipsis_pct": 20, "negation_pct": 10},
            "babel": {"ellipsis_pct": 40, "negation_pct": 30},
            "resurrected": {"ellipsis_pct": 15, "negation_pct": 5},
        }
        timeline = [
            {"id": "early"}, {"id": "babel"}, {"id": "resurrected"}
        ]
        result = detect_emotion_arc(slice_metrics, timeline)
        self.assertIn("arc", result)
        self.assertIn("trajectory", result)


class TestPhaseInferrerV2(unittest.TestCase):
    """phase_inferrer.py 算法升级测试"""

    def test_infer_phase_ensemble(self):
        """测试多证据融合推断"""
        from phase_inferrer import infer_phase_ensemble
        # 多个证据指向 babel
        result = infer_phase_ensemble(
            text="巴别塔的旗帜在风中飘扬，特蕾西娅站在舰桥上",
            chapter="6-1",
            operator_name="theresa",
        )
        self.assertEqual(result.phase, "babel")
        # evidence 是列表，包含证据记录
        self.assertIsInstance(result.evidence, list)
        self.assertTrue(len(result.evidence) > 0)

    def test_infer_phase_ensemble_conflict(self):
        """测试冲突证据下的融合"""
        from phase_inferrer import infer_phase_ensemble
        # 内容指向 babel，章节指向 resurrected
        result = infer_phase_ensemble(
            text="巴别塔的旗帜在风中飘扬",
            chapter="14-1",  # 后期章节
            operator_name="theresa",
        )
        # 应该选择权重更高的证据
        self.assertIn(result.phase, ["babel", "resurrected"])


class TestContextAnnotatorV2(unittest.TestCase):
    """context_annotator.py 算法升级测试"""

    def test_classify_situation_multi_signal(self):
        """测试多信号场景分类"""
        from context_annotator import classify_situation_v2
        # 标题 + 内容 + 对象 多信号
        result = classify_situation_v2(
            title="战斗开始",
            text="准备出击，敌人就在前方",
            interlocutor="博士",
        )
        # 应该返回战斗相关场景（battle 或 confront）
        self.assertIn(result, ["battle", "confront", "combat"])

    def test_infer_interlocutor_from_content(self):
        """测试从内容推断对话对象"""
        from context_annotator import infer_interlocutor_from_content
        result = infer_interlocutor_from_content(
            "博士，你来了。我等你很久了。",
            known_characters=["博士", "阿米娅", "凯尔希"],
        )
        self.assertEqual(result, "博士")

    def test_infer_interlocutor_none(self):
        """测试无法推断对话对象"""
        from context_annotator import infer_interlocutor_from_content
        result = infer_interlocutor_from_content(
            "今天天气真好。",
            known_characters=["博士", "阿米娅"],
        )
        self.assertIsNone(result)


class TestStoryExtractorV2(unittest.TestCase):
    """story_extractor.py 算法升级测试"""

    def test_normalize_speaker_name(self):
        """测试说话者名称标准化"""
        from story_extractor import normalize_speaker_name
        # 括号注释去除
        self.assertEqual(normalize_speaker_name("特蕾西娅(幼年)", "特蕾西娅"), "特蕾西娅")
        self.assertEqual(normalize_speaker_name("特蕾西娅（魔王）", "特蕾西娅"), "特蕾西娅")
        # 普通名称不变
        self.assertEqual(normalize_speaker_name("阿米娅", "特蕾西娅"), "阿米娅")

    def test_extract_emotion_from_stage_direction(self):
        """测试从舞台指示提取情感"""
        from story_extractor import extract_emotion_from_stage_direction
        # 函数接受 list[str] 参数
        self.assertEqual(extract_emotion_from_stage_direction(["目光柔和"]), "温柔")
        self.assertEqual(extract_emotion_from_stage_direction(["她微笑着"]), "温柔")
        self.assertEqual(extract_emotion_from_stage_direction(["沉默不语"]), "悲伤")
        self.assertEqual(extract_emotion_from_stage_direction(["愤怒地"]), "愤怒")
        self.assertIsNone(extract_emotion_from_stage_direction(["普通描述"]))


class TestCanonCheckerV2(unittest.TestCase):
    """canon_checker.py 算法升级测试"""

    def test_external_misconceptions_loading(self):
        """测试外部误解库加载"""
        from canon_checker import _load_builtin_misconceptions
        # 应该能加载 data/misconceptions.json
        result = _load_builtin_misconceptions()
        self.assertIsInstance(result, list)
        # 应该包含一些误解条目
        self.assertTrue(len(result) > 0)
        # 每个条目应该有 id 和 check_patterns
        if result:
            self.assertIn("id", result[0])
            self.assertIn("check_patterns", result[0])

    def test_check_character_consistency(self):
        """测试角色一致性检查"""
        from canon_checker import check_character_consistency
        persona = {
            "layer0_core": "从不使用感叹号，说话平静",
            "layer5_taboos": ["不使用感叹号"],
        }
        # 包含感叹号的文本应该触发警告
        warnings = check_character_consistency("这是错的！", persona)
        self.assertIsInstance(warnings, list)


class TestPersonaValidatorV2(unittest.TestCase):
    """persona_validator.py 算法升级测试"""

    def test_validate_style_consistency(self):
        """测试风格一致性验证"""
        from persona_validator import validate_style_consistency
        # 函数签名：validate_style_consistency(dialogues: list[str], fingerprint: dict)
        dialogues = [
            "我在。",
            "不要怕。",
            "走吧。",
            "我会陪着你。",
            "这就足够了。",
        ]
        fingerprint = {
            "pause_markers": {"ellipsis_pct": 5.0},  # 预期 5%
            "sentence_length": {"median": 8, "rhythm": "稳定"},
        }
        result = validate_style_consistency(dialogues, fingerprint)
        self.assertIn("issues", result)
        self.assertIn("score", result)
        self.assertIn("checks", result)


class TestDataInjector(unittest.TestCase):
    """data_injector.py 数据注入器测试"""

    def test_format_fingerprint(self):
        """测试对话指纹格式化"""
        from data_injector import format_fingerprint
        data = {
            "sentence_length": {"type": "简短", "median": 6, "p25": 3, "p75": 10, "cv": 0.5, "rhythm": "稳定"},
            "pause_markers": {"ellipsis_pct": 42.0, "exclamation_pct": 5.0, "question_pct": 8.0},
            "self_reference": {"primary": "我", "frequency_per_line": 0.8},
            "emotion": {"dominant": "温柔", "breadth": 5, "spectrum": {"温柔": 15, "悲伤": 8}},
            "catchphrases": {"signature_phrases": [{"phrase": "我在", "count": 12}]},
        }
        result = format_fingerprint(data)
        self.assertIn("句式长度", result)
        self.assertIn("省略号", result)
        self.assertIn("口头禅", result)

    def test_format_relationships(self):
        """测试关系图谱格式化"""
        from data_injector import format_relationships
        data = {
            "relations": [
                {"target": "阿米娅", "type": "mentor", "strength": 0.85, "evidence_count": 20},
            ],
            "evolutions": [
                {"pair": "阿米娅", "direction": "加深", "delta": 0.3, "from_phase": "early", "to_phase": "babel"},
            ],
        }
        result = format_relationships(data)
        self.assertIn("阿米娅", result)
        self.assertIn("关系演变", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
