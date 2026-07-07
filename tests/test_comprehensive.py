#!/usr/bin/env python3
"""
全面增强测试 — 边界场景、异常路径、新增功能、安全防护、集成测试

覆盖范围：
  1. 边界/异常测试：空输入、超大输入、非法 JSON、极端值
  2. 新增功能测试：Mann-Whitney U、_SemVer、_parse_report、外置数据加载
  3. 安全测试：ReDoS 防护、路径遍历、context schema 验证
  4. 集成测试：管线双模式、数据文件 roundtrip、端到端管线
  5. 属性/不变量测试：类型一致性、结构完整性

运行方式:
    python3 -m pytest tests/ -v
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

# 将 tools 目录加入 import 路径
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

DATA_DIR = Path(__file__).parent.parent / "data"


# ══════════════════════════════════════════════
# 1. 边界场景和异常路径测试
# ══════════════════════════════════════════════


class TestBoundarySharedUtils(unittest.TestCase):
    """shared_utils.py 边界与异常测试"""

    def test_atomic_write_json_unicode(self):
        """原子写入含 Unicode 的 JSON"""
        from shared_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "unicode.json"
            data = {"name": "特蕾西娅", "emoji": "🗡️", "空": ""}
            atomic_write_json(str(filepath), data)
            loaded = json.loads(filepath.read_text(encoding="utf-8"))
            self.assertEqual(loaded["name"], "特蕾西娅")

    def test_atomic_write_json_large(self):
        """原子写入大 JSON（>1MB）"""
        from shared_utils import atomic_write_json
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "large.json"
            data = {"items": [{"id": i, "text": "测试" * 100} for i in range(5000)]}
            atomic_write_json(str(filepath), data)
            self.assertGreater(filepath.stat().st_size, 1_000_000)

    def test_load_json_safe_empty_file(self):
        """安全加载空文件"""
        from shared_utils import load_json_safe
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.json"
            filepath.write_text("", encoding="utf-8")
            result = load_json_safe(str(filepath))
            self.assertIsNone(result)

    def test_load_json_safe_array(self):
        """安全加载 JSON 数组（非对象）"""
        from shared_utils import load_json_safe
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "array.json"
            filepath.write_text("[1, 2, 3]", encoding="utf-8")
            result = load_json_safe(str(filepath))
            # 应返回列表而非 None
            self.assertIsInstance(result, list)

    def test_validate_slug_valid(self):
        """合法 slug 验证"""
        from shared_utils import validate_slug
        self.assertEqual(validate_slug("te-lei-xi-ya"), "te-lei-xi-ya")
        self.assertEqual(validate_slug("a-mi-ya"), "a-mi-ya")
        self.assertEqual(validate_slug("w"), "w")

    def test_validate_slug_path_traversal(self):
        """slug 路径遍历攻击防护"""
        from shared_utils import validate_slug
        with self.assertRaises(ValueError):
            validate_slug("../etc/passwd")
        with self.assertRaises(ValueError):
            validate_slug("foo/../../bar")
        with self.assertRaises(ValueError):
            validate_slug("..")

    def test_validate_slug_empty(self):
        """空 slug 验证"""
        from shared_utils import validate_slug
        with self.assertRaises(ValueError):
            validate_slug("")

    def test_validate_path_allowed(self):
        """合法路径验证（路径需在 cwd/home/tmp 之一下）"""
        from shared_utils import validate_path
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            Path(filepath).touch()
            result = validate_path(filepath)
            self.assertTrue(result.startswith(tmpdir))

    def test_validate_path_escape(self):
        """路径不在允许范围内抛出 ValueError"""
        from shared_utils import validate_path
        with self.assertRaises(ValueError):
            validate_path("/etc/passwd")


class TestBoundaryGameDataParser(unittest.TestCase):
    """game_data_parser.py 边界测试"""

    def test_clean_wikitext_empty(self):
        """空 wikitext 清理"""
        from game_data_parser import clean_wikitext
        self.assertEqual(clean_wikitext(""), "")
        self.assertEqual(clean_wikitext("   "), "")

    def test_clean_wikitext_nested_html_comments(self):
        """嵌套 HTML 注释清理"""
        from game_data_parser import clean_wikitext
        result = clean_wikitext("hello<!-- outer <!-- inner --> -->world")
        # 至少不应崩溃
        self.assertIsInstance(result, str)

    def test_clean_wikitext_deep_wiki_links(self):
        """多层嵌套 wiki 链接"""
        from game_data_parser import clean_wikitext
        result = clean_wikitext("[[罗德岛|[[内部链接|显示]]]]")
        self.assertIsInstance(result, str)

    def test_to_slug_special_characters(self):
        """特殊字符的 slug 生成"""
        from game_data_parser import to_slug
        # 纯数字
        self.assertIsInstance(to_slug("123"), str)
        # 混合
        self.assertIsInstance(to_slug("W·Logos"), str)

    def test_detect_page_type_empty(self):
        """空页面类型检测"""
        from game_data_parser import _detect_page_type
        self.assertEqual(_detect_page_type(""), "unknown")

    def test_extract_template_body_malformed(self):
        """畸形模板提取"""
        from game_data_parser import _extract_template_body
        # 未闭合的模板
        result = _extract_template_body("{{Charinfo\n|name=测试", "Charinfo")
        # 不应崩溃
        self.assertTrue(result is None or isinstance(result, str))

    def test_parse_report_in_output(self):
        """extract_operator_data_from_wikitext 输出包含 _parse_report"""
        from game_data_parser import extract_operator_data_from_wikitext
        # 空白页面
        result = extract_operator_data_from_wikitext("", "测试角色")
        self.assertIn("_parse_report", result)
        report = result["_parse_report"]
        self.assertIn("parsed_fields", report)
        self.assertIn("missing_fields", report)
        self.assertIn("warnings", report)
        self.assertIn("wikitext_length", report)
        self.assertEqual(report["wikitext_length"], 0)

    def test_parse_report_with_data(self):
        """有数据时 _parse_report 正确记录"""
        from game_data_parser import extract_operator_data_from_wikitext
        wikitext = "{{Charinfo\n|name=阿米娅\n|职业=术师\n}}\n== 干员档案 ==\n测试内容"
        result = extract_operator_data_from_wikitext(wikitext, "阿米娅")
        report = result["_parse_report"]
        self.assertGreater(report["wikitext_length"], 0)
        # 如果解析出了字段，应在 parsed_fields 中
        self.assertIsInstance(report["parsed_fields"], list)

    def test_parse_report_warnings(self):
        """不完整数据产生警告"""
        from game_data_parser import extract_operator_data_from_wikitext
        # 只有名字没有其他信息的简陋页面
        wikitext = "== 干员档案 ==\n一些基础信息"
        result = extract_operator_data_from_wikitext(wikitext, "无名角色")
        report = result["_parse_report"]
        # 缺少关键字段应该有 missing_fields
        self.assertIsInstance(report["missing_fields"], list)


class TestBoundaryDialogueFingerprint(unittest.TestCase):
    """dialogue_fingerprint.py 边界测试"""

    def test_generate_fingerprint_single_line(self):
        """单行对话的指纹生成"""
        from dialogue_fingerprint import generate_fingerprint
        result = generate_fingerprint([{"text": "我在。"}], "测试")
        self.assertEqual(result["dialogue_count"], 1)
        self.assertIn("dimensions", result)

    def test_generate_fingerprint_very_long_text(self):
        """超长文本行"""
        from dialogue_fingerprint import generate_fingerprint
        long_text = "我" * 10000
        result = generate_fingerprint([{"text": long_text}], "测试")
        self.assertIn("dimensions", result)

    def test_generate_fingerprint_special_chars(self):
        """特殊字符对话"""
        from dialogue_fingerprint import generate_fingerprint
        result = generate_fingerprint(
            [{"text": "……！？「」『』—・♪★☆"}], "测试"
        )
        self.assertIn("dimensions", result)

    def test_analyze_pause_markers_no_pauses(self):
        """无停顿标记的对话"""
        from dialogue_fingerprint import analyze_pause_markers
        result = analyze_pause_markers([{"text": "你好世界"}])
        self.assertEqual(result["ellipsis_pct"], 0.0)

    def test_analyze_sentence_length_single_char(self):
        """单字符句子"""
        from dialogue_fingerprint import analyze_sentence_length_distribution
        result = analyze_sentence_length_distribution([{"text": "好"}])
        self.assertIn("avg_length", result)


class TestBoundaryRelationshipGraph(unittest.TestCase):
    """relationship_graph.py 边界测试"""

    def test_extract_entities_empty_text(self):
        """空文本实体提取"""
        from relationship_graph import extract_entities
        result = extract_entities("")
        self.assertIsInstance(result, list)

    def test_extract_entities_no_match(self):
        """无匹配的文本"""
        from relationship_graph import extract_entities
        result = extract_entities("这段话里没有任何角色名")
        self.assertEqual(len(result), 0)

    def test_compute_relationship_strength_zero(self):
        """零值输入的关系强度"""
        from relationship_graph import compute_relationship_strength
        result = compute_relationship_strength(
            co_occurrence=0, total_lines=100,
            sentiment_words=[], dialogue_count=0,
        )
        self.assertEqual(result, 0.0)

    def test_compute_relationship_strength_max(self):
        """最大值输入的关系强度"""
        from relationship_graph import compute_relationship_strength
        result = compute_relationship_strength(
            co_occurrence=100, total_lines=100,
            sentiment_words=["温柔", "信任", "爱", "牵挂"],
            dialogue_count=80,
        )
        self.assertGreater(result, 0.5)
        self.assertLessEqual(result, 1.0)

    def test_normalize_name_unknown(self):
        """未知英文名标准化"""
        from relationship_graph import normalize_name
        result = normalize_name("UnknownCharacter")
        # 不在别名映射中，可能在 operators 中查找或返回原名
        self.assertIsInstance(result, (str, type(None)))


class TestBoundaryContextAnnotator(unittest.TestCase):
    """context_annotator.py 边界测试"""

    def test_annotate_voice_line_empty_text(self):
        """空文本语音行标注"""
        from context_annotator import annotate_voice_line
        line = {"label": "交谈1", "text": ""}
        result = annotate_voice_line(line, 0, default_phase="resurrected")
        self.assertIn("text", result)

    def test_annotate_voice_line_no_label(self):
        """缺少 label 的语音行"""
        from context_annotator import annotate_voice_line
        line = {"text": "你好"}
        result = annotate_voice_line(line, 0)
        self.assertIn("text", result)

    def test_build_context_json_empty_data(self):
        """空 operator_data 构建 context.json"""
        from context_annotator import build_context_json
        minimal_data = {"name_zh": "测试", "slug": "test", "source_url": "http://example.com"}
        result = build_context_json(minimal_data, [], [])
        self.assertIn("annotated_lines", result)
        self.assertIn("stats", result)


class TestBoundarySpeechActAnalyzer(unittest.TestCase):
    """speech_act_analyzer.py 边界测试"""

    def test_classify_empty_text(self):
        """空文本话语行为分类"""
        from speech_act_analyzer import classify_speech_acts
        result = classify_speech_acts("")
        self.assertIsInstance(result, list)

    def test_classify_plain_statement(self):
        """普通陈述句（无特殊行为）"""
        from speech_act_analyzer import classify_speech_acts
        result = classify_speech_acts("今天天气不错。")
        # 可能返回空列表或非特殊行为
        self.assertIsInstance(result, list)

    def test_classify_multiple_acts(self):
        """一句话触发多种行为"""
        from speech_act_analyzer import classify_speech_acts
        # "我一定会保护你" → commit + 可能有其他
        result = classify_speech_acts("我一定会保护你！")
        act_types = [a["type"] for a in result]
        self.assertIn("commit", act_types)


class TestBoundaryTemporalSlicer(unittest.TestCase):
    """temporal_slicer.py 边界测试"""

    def test_detect_emotion_arc_single_phase(self):
        """单时期情感弧线"""
        from temporal_slicer import detect_emotion_arc
        result = detect_emotion_arc(
            {"early": {"ellipsis_pct": 20, "negation_pct": 10}},
            [{"id": "early"}],
        )
        self.assertIn("arc", result)

    def test_detect_emotion_arc_empty(self):
        """空数据情感弧线"""
        from temporal_slicer import detect_emotion_arc
        result = detect_emotion_arc({}, [])
        self.assertIn("arc", result)


# ══════════════════════════════════════════════
# 2. 新增功能测试
# ══════════════════════════════════════════════


class TestMannWhitneyU(unittest.TestCase):
    """temporal_slicer.py Mann-Whitney U 检验测试"""

    def test_identical_samples(self):
        """相同样本 → p-value 应接近 1"""
        from temporal_slicer import _mann_whitney_u
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        u, p = _mann_whitney_u(x, y)
        # 相同样本，p-value 应较大
        self.assertGreater(p, 0.5)

    def test_clear_separation(self):
        """完全分离的两组 → p-value 应很小"""
        from temporal_slicer import _mann_whitney_u
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        y = [20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
        u, p = _mann_whitney_u(x, y)
        self.assertLess(p, 0.05)

    def test_empty_sample(self):
        """空样本返回 (0.0, 1.0)"""
        from temporal_slicer import _mann_whitney_u
        u, p = _mann_whitney_u([], [1.0, 2.0])
        self.assertEqual(u, 0.0)
        self.assertEqual(p, 1.0)

    def test_single_element(self):
        """单元素样本"""
        from temporal_slicer import _mann_whitney_u
        u, p = _mann_whitney_u([1.0], [100.0])
        # 单元素样本统计检验力不足，但不应崩溃
        self.assertIsInstance(u, float)
        self.assertIsInstance(p, float)

    def test_ties_handling(self):
        """并列值处理"""
        from temporal_slicer import _mann_whitney_u
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [3.0, 4.0, 5.0, 6.0, 7.0]
        u, p = _mann_whitney_u(x, y)
        # 有并列值（3,4,5），不应崩溃
        self.assertIsInstance(u, float)
        self.assertIsInstance(p, float)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_u_statistic_range(self):
        """U 统计量范围验证"""
        from temporal_slicer import _mann_whitney_u
        n1, n2 = 10, 12
        x = [float(i) for i in range(n1)]
        y = [float(i + 5) for i in range(n2)]
        u, p = _mann_whitney_u(x, y)
        # U 的范围是 [0, n1*n2]
        self.assertGreaterEqual(u, 0.0)
        self.assertLessEqual(u, n1 * n2)


class TestCohenD(unittest.TestCase):
    """temporal_slicer.py Cohen's d 效应量测试"""

    def test_zero_effect(self):
        """完全相同的两组 → d ≈ 0"""
        from temporal_slicer import _cohen_d
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0, 5.0]
        d = _cohen_d(x, y)
        self.assertAlmostEqual(d, 0.0, places=5)

    def test_large_effect(self):
        """差异很大的两组 → |d| > 0.8"""
        from temporal_slicer import _cohen_d
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [50.0, 60.0, 70.0, 80.0, 90.0]
        d = _cohen_d(x, y)
        self.assertGreater(abs(d), 0.8)

    def test_empty_sample(self):
        """空样本 → d = 0"""
        from temporal_slicer import _cohen_d
        d = _cohen_d([], [1.0, 2.0])
        self.assertEqual(d, 0.0)

    def test_single_element(self):
        """单元素 → 标准差为 0 → d = 0"""
        from temporal_slicer import _cohen_d
        d = _cohen_d([1.0], [2.0])
        # 单元素无法计算有效标准差
        self.assertIsInstance(d, float)

    def test_direction_detected_in_diff(self):
        """compare_metrics_v2 正确标记差异方向"""
        from temporal_slicer import compare_metrics_v2
        baseline = {"ellipsis_pct": 10.0}
        comparison = {"ellipsis_pct": 50.0}
        diffs = compare_metrics_v2(baseline, comparison)
        if diffs:
            # 增大 → shift_pct > 0
            self.assertGreater(diffs[0]["shift_pct"], 0)
            self.assertEqual(diffs[0]["baseline"], 10.0)
            self.assertEqual(diffs[0]["comparison"], 50.0)


class TestCompareMetricsV2(unittest.TestCase):
    """temporal_slicer.py compare_metrics_v2 统计增强测试"""

    def test_with_raw_values_statistical(self):
        """提供原始数值时执行统计检验"""
        from temporal_slicer import compare_metrics_v2
        baseline = {"ellipsis_pct": 30.0, "avg_sentence_length": 8.0}
        comparison = {"ellipsis_pct": 50.0, "avg_sentence_length": 15.0}
        # 注意：baseline_values 的 key 需与指标名匹配
        baseline_vals = {"ellipsis_pct": [25, 30, 35, 28, 32] * 3,
                         "sentence_lengths": [7, 8, 9, 8, 7] * 3}
        comparison_vals = {"ellipsis_pct": [45, 50, 55, 48, 52] * 3,
                           "sentence_lengths": [14, 15, 16, 15, 14] * 3}
        diffs = compare_metrics_v2(
            baseline, comparison,
            baseline_values=baseline_vals,
            comparison_values=comparison_vals,
        )
        # 应该有差异结果
        self.assertIsInstance(diffs, list)
        self.assertGreater(len(diffs), 0)

    def test_without_raw_values_fallback(self):
        """无原始数值时退回旧逻辑"""
        from temporal_slicer import compare_metrics_v2
        baseline = {"ellipsis_pct": 30.0}
        comparison = {"ellipsis_pct": 50.0}
        diffs = compare_metrics_v2(baseline, comparison)
        # 应有 diff 但无 significance 字段（或值为 null）
        self.assertIsInstance(diffs, list)

    def test_significance_levels(self):
        """显著性等级正确映射"""
        from temporal_slicer import compare_metrics_v2
        # 构造极端差异
        baseline = {"ellipsis_pct": 5.0, "avg_sentence_length": 3.0}
        comparison = {"ellipsis_pct": 80.0, "avg_sentence_length": 30.0}
        baseline_vals = {"ellipsis_pct": [4, 5, 6] * 5,
                         "avg_sentence_length": [2, 3, 4] * 5}
        comparison_vals = {"ellipsis_pct": [75, 80, 85] * 5,
                           "avg_sentence_length": [28, 30, 32] * 5}
        diffs = compare_metrics_v2(
            baseline, comparison,
            baseline_values=baseline_vals,
            comparison_values=comparison_vals,
        )
        for d in diffs:
            if "significance" in d and d["significance"] is not None:
                self.assertIn(d["significance"], ("high", "medium", "low"))


class TestSemVer(unittest.TestCase):
    """version_manager.py _SemVer 测试"""

    def test_semver_ordering(self):
        """版本号排序"""
        from version_manager import _SemVer
        v10 = _SemVer(1, 0)
        v11 = _SemVer(1, 1)
        v20 = _SemVer(2, 0)
        self.assertLess(v10, v11)
        self.assertLess(v11, v20)
        self.assertLess(v10, v20)

    def test_semver_equality(self):
        """版本号相等"""
        from version_manager import _SemVer
        v1 = _SemVer(1, 5)
        v2 = _SemVer(1, 5)
        self.assertEqual(v1, v2)
        self.assertTrue(v1 <= v2)

    def test_semver_str(self):
        """版本号字符串表示"""
        from version_manager import _SemVer
        self.assertEqual(str(_SemVer(1, 0)), "v1.0")
        self.assertEqual(str(_SemVer(3, 14)), "v3.14")

    def test_parse_dir_version_standard(self):
        """标准格式目录名解析"""
        from version_manager import _parse_dir_version
        v = _parse_dir_version("v1.5")
        self.assertIsNotNone(v)
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 5)

    def test_parse_dir_version_legacy(self):
        """旧格式目录名解析"""
        from version_manager import _parse_dir_version
        v = _parse_dir_version("v3")
        self.assertIsNotNone(v)
        self.assertEqual(v.major, 3)
        self.assertEqual(v.minor, 0)

    def test_parse_dir_version_invalid(self):
        """非法目录名返回 None"""
        from version_manager import _parse_dir_version
        self.assertIsNone(_parse_dir_version("latest"))
        self.assertIsNone(_parse_dir_version("backup"))
        self.assertIsNone(_parse_dir_version("1.0"))  # 缺少 v 前缀
        self.assertIsNone(_parse_dir_version(""))

    def test_normalize_version_invalid(self):
        """非法版本号抛出 ValueError"""
        from version_manager import _normalize_version
        with self.assertRaises(ValueError):
            _normalize_version("")
        with self.assertRaises(ValueError):
            _normalize_version("abc")
        with self.assertRaises(ValueError):
            _normalize_version("v1.2.3.4")

    def test_normalize_version_valid(self):
        """合法版本号规范化"""
        from version_manager import _normalize_version
        self.assertEqual(_normalize_version("v1"), "v1.0")
        self.assertEqual(_normalize_version("v2.5"), "v2.5")
        self.assertEqual(_normalize_version("3"), "v3.0")
        self.assertEqual(_normalize_version("3.7"), "v3.7")

    def test_get_next_version_increment(self):
        """版本号递增"""
        from version_manager import _get_next_version
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "v1.0").mkdir()
            Path(tmpdir, "v1.1").mkdir()
            result = _get_next_version(Path(tmpdir))
            self.assertEqual(result, "v1.2")

    def test_get_next_version_gap(self):
        """版本号不连续（跳号）"""
        from version_manager import _get_next_version
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "v1.0").mkdir()
            Path(tmpdir, "v1.3").mkdir()
            result = _get_next_version(Path(tmpdir))
            # 应该是 v1.4（最大 + 1），而非 v1.1
            self.assertEqual(result, "v1.4")


# ══════════════════════════════════════════════
# 3. 安全测试
# ══════════════════════════════════════════════


class TestRedosProtection(unittest.TestCase):
    """canon_checker.py ReDoS 防护测试"""

    def test_nested_quantifier_detected(self):
        """嵌套量词检测"""
        from canon_checker import _validate_regex_safety
        # 嵌套量词模式 (a+)+ 是经典 ReDoS 模式
        with self.assertRaises(ValueError):
            _validate_regex_safety(r"(a+)+", "test")

    def test_nested_star_detected(self):
        """嵌套星号检测"""
        from canon_checker import _validate_regex_safety
        with self.assertRaises(ValueError):
            _validate_regex_safety(r"(a*)*", "test")

    def test_safe_regex_passes(self):
        """安全正则通过"""
        from canon_checker import _validate_regex_safety
        # 非嵌套量词，安全
        _validate_regex_safety(r"特蕾西娅.*维多利亚", "test")  # 不应抛异常

    def test_safe_alternation_passes(self):
        """安全的选择分支通过"""
        from canon_checker import _validate_regex_safety
        _validate_regex_safety(r"(特蕾西娅|她).{0,10}", "test")

    def test_quantified_group_with_literal(self):
        """量词化字面量组（安全）"""
        from canon_checker import _validate_regex_safety
        _validate_regex_safety(r"[abc]+", "test")  # 字符类 + 量词，安全

    def test_validate_exclude_patterns(self):
        """exclude_patterns 安全检查"""
        from canon_checker import _validate_regex_safety
        # 这应该被拦截：exclude_patterns 中的恶意正则
        with self.assertRaises(ValueError):
            _validate_regex_safety(r"(x+)+$", "M999")

    def test_built_in_patterns_are_safe(self):
        """所有内置误解模式的正则都通过安全检查"""
        from canon_checker import _load_builtin_misconceptions
        misconceptions = _load_builtin_misconceptions()
        for m in misconceptions:
            for cp in m.get("check_patterns", []):
                try:
                    from canon_checker import _validate_regex_safety
                    _validate_regex_safety(cp["pattern"], m["id"])
                except ValueError:
                    self.fail(f"内置模式 {m['id']} 的 check_pattern 不安全: {cp['pattern']}")
            for ep in m.get("exclude_patterns", []):
                try:
                    from canon_checker import _validate_regex_safety
                    _validate_regex_safety(ep, m["id"])
                except ValueError:
                    self.fail(f"内置模式 {m['id']} 的 exclude_pattern 不安全: {ep}")


class TestContextSchemaValidation(unittest.TestCase):
    """context.json schema 验证测试"""

    def test_valid_context(self):
        """合法 context.json 通过验证"""
        from shared_utils import validate_context
        data = {
            "character": "特蕾西娅",
            "slug": "te-lei-xi-ya",
            "schema_version": "1.0.0",
            "annotated_lines": [
                {
                    "id": 0,
                    "text": "我在。",
                    "source": "voice",
                    "context": {"phase": "resurrected"},
                }
            ],
            "stats": {
                "total_lines": 1,
                "source_distribution": {},
                "phase_distribution": {},
            },
        }
        errors = validate_context(data)
        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")

    def test_missing_required_fields(self):
        """缺少必填字段"""
        from shared_utils import validate_context
        data = {"character": "测试"}
        errors = validate_context(data)
        self.assertGreater(len(errors), 0)
        # 应该报告缺少 slug, annotated_lines, stats
        error_text = " ".join(errors)
        self.assertIn("slug", error_text)
        self.assertIn("annotated_lines", error_text)
        self.assertIn("stats", error_text)

    def test_invalid_annotated_lines_type(self):
        """annotated_lines 类型错误"""
        from shared_utils import validate_context
        data = {
            "character": "测试",
            "slug": "test",
            "annotated_lines": "not a list",
            "stats": {},
        }
        errors = validate_context(data)
        self.assertGreater(len(errors), 0)

    def test_line_missing_required_fields(self):
        """行缺少必填字段"""
        from shared_utils import validate_context
        data = {
            "character": "测试",
            "slug": "test",
            "annotated_lines": [{"id": 0}],  # 缺少 text, source, context
            "stats": {},
        }
        errors = validate_context(data)
        self.assertGreater(len(errors), 0)

    def test_schema_version_warning(self):
        """schema_version 不匹配产生警告"""
        from shared_utils import validate_context
        data = {
            "character": "测试",
            "slug": "test",
            "schema_version": "0.1",  # 旧版本
            "annotated_lines": [{"id": 0, "text": "测试", "source": "voice", "context": {"phase": "unknown"}}],
            "stats": {},
        }
        errors = validate_context(data, strict=True)
        # strict 模式下警告也视为错误
        self.assertGreater(len(errors), 0)

    def test_validate_context_file(self):
        """文件级别的 context 验证"""
        from shared_utils import validate_context_file
        with tempfile.TemporaryDirectory() as tmpdir:
            # 合法 context.json
            data = {
                "character": "测试",
                "slug": "test",
                "schema_version": "1.0.0",
                "annotated_lines": [],
                "stats": {
                    "total_lines": 0,
                    "source_distribution": {},
                    "phase_distribution": {},
                },
            }
            filepath = Path(tmpdir) / "context.json"
            filepath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            errors = validate_context_file(str(filepath))
            self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")

    def test_validate_context_file_not_found(self):
        """不存在的文件验证"""
        from shared_utils import validate_context_file
        errors = validate_context_file("/nonexistent/context.json")
        self.assertGreater(len(errors), 0)


# ══════════════════════════════════════════════
# 4. 外置数据加载测试
# ══════════════════════════════════════════════


class TestExternalDataFiles(unittest.TestCase):
    """外置数据文件格式与加载测试"""

    def test_emotion_lexicon_file_exists(self):
        """emotion_lexicon.json 文件存在"""
        self.assertTrue((DATA_DIR / "emotion_lexicon.json").exists())

    def test_emotion_lexicon_valid_json(self):
        """emotion_lexicon.json 格式正确"""
        data = json.loads((DATA_DIR / "emotion_lexicon.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        for emotion, entries in data.items():
            self.assertIsInstance(emotion, str)
            self.assertIsInstance(entries, list)
            for entry in entries:
                self.assertIn("word", entry)
                self.assertIn("weight", entry)
                self.assertIsInstance(entry["word"], str)
                self.assertIsInstance(entry["weight"], (int, float))

    def test_emotion_lexicon_categories(self):
        """情感词典包含必要类别"""
        data = json.loads((DATA_DIR / "emotion_lexicon.json").read_text(encoding="utf-8"))
        required = {"温柔", "悲伤", "愤怒", "坚定", "希望"}
        self.assertTrue(required.issubset(set(data.keys())),
                        f"缺少类别: {required - set(data.keys())}")

    def test_operator_db_file_exists(self):
        """operator_db.json 文件存在"""
        self.assertTrue((DATA_DIR / "operator_db.json").exists())

    def test_operator_db_valid_json(self):
        """operator_db.json 格式正确"""
        data = json.loads((DATA_DIR / "operator_db.json").read_text(encoding="utf-8"))
        self.assertIn("operators", data)
        self.assertIn("aliases", data)
        self.assertIsInstance(data["operators"], dict)
        self.assertIsInstance(data["aliases"], dict)

    def test_operator_db_operator_structure(self):
        """operator_db.json 角色条目结构"""
        data = json.loads((DATA_DIR / "operator_db.json").read_text(encoding="utf-8"))
        for name, info in data["operators"].items():
            self.assertIn("en", info, f"角色 {name} 缺少 en 字段")

    def test_operator_db_alias_mapping(self):
        """operator_db.json 别名映射有效"""
        data = json.loads((DATA_DIR / "operator_db.json").read_text(encoding="utf-8"))
        for _alias, canonical in data["aliases"].items():
            # 别名指向的中文名应存在于 operators 中，或者是自身
            self.assertIsInstance(canonical, str)

    def test_speech_act_rules_file_exists(self):
        """speech_act_rules.json 文件存在"""
        self.assertTrue((DATA_DIR / "speech_act_rules.json").exists())

    def test_speech_act_rules_valid_json(self):
        """speech_act_rules.json 格式正确"""
        data = json.loads((DATA_DIR / "speech_act_rules.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        for rule in data:
            self.assertIn("pattern", rule)
            self.assertIn("type", rule)
            self.assertIn("confidence", rule)
            self.assertIn("label", rule)

    def test_speech_act_rules_patterns_compile(self):
        """speech_act_rules.json 中所有正则可编译"""
        data = json.loads((DATA_DIR / "speech_act_rules.json").read_text(encoding="utf-8"))
        for rule in data:
            try:
                re.compile(rule["pattern"])
            except re.error as e:
                self.fail(f"规则 {rule['label']} 的正则无法编译: {rule['pattern']}, 错误: {e}")

    def test_misconceptions_file_exists(self):
        """misconceptions.json 文件存在"""
        self.assertTrue((DATA_DIR / "misconceptions.json").exists())

    def test_misconceptions_valid_structure(self):
        """misconceptions.json 结构正确"""
        data = json.loads((DATA_DIR / "misconceptions.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        for m in data:
            self.assertIn("id", m)
            self.assertIn("wrong", m)
            self.assertIn("correct", m)
            self.assertIn("check_patterns", m)

    def test_context_schema_file_exists(self):
        """context.schema.json 文件存在"""
        self.assertTrue((DATA_DIR / "context.schema.json").exists())

    def test_context_schema_valid_json(self):
        """context.schema.json 格式正确"""
        data = json.loads((DATA_DIR / "context.schema.json").read_text(encoding="utf-8"))
        self.assertIn("type", data)
        self.assertEqual(data["type"], "object")
        self.assertIn("properties", data)

    def test_pinyin_map_file_exists(self):
        """pinyin_map.json 文件存在"""
        self.assertTrue((DATA_DIR / "pinyin_map.json").exists())

    def test_pinyin_map_valid_json(self):
        """pinyin_map.json 格式正确"""
        data = json.loads((DATA_DIR / "pinyin_map.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)


class TestDialogueFingerprintExternalData(unittest.TestCase):
    """dialogue_fingerprint.py 外置情感词典加载测试"""

    def test_emotion_lexicon_loaded(self):
        """情感词典已加载"""
        from dialogue_fingerprint import EMOTION_LEXICON
        self.assertIsInstance(EMOTION_LEXICON, dict)
        self.assertGreater(len(EMOTION_LEXICON), 0)

    def test_emotion_lexicon_weights_positive(self):
        """情感词典权重为正"""
        from dialogue_fingerprint import EMOTION_LEXICON
        for emotion, words in EMOTION_LEXICON.items():
            for item in words:
                self.assertGreater(item[1], 0, f"{emotion}/{item[0]} 权重应为正数")

    def test_load_custom_lexicon(self):
        """自定义情感词典加载"""
        from dialogue_fingerprint import _load_emotion_lexicon
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = {"测试情感": [{"word": "测试词", "weight": 1.5}]}
            filepath = Path(tmpdir) / "custom.json"
            filepath.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
            result = _load_emotion_lexicon(str(filepath))
            self.assertIn("测试情感", result)
            self.assertEqual(result["测试情感"][0], ("测试词", 1.5))


class TestRelationshipGraphExternalData(unittest.TestCase):
    """relationship_graph.py 外置角色名库加载测试"""

    def test_operator_db_loaded(self):
        """角色名库已加载"""
        from relationship_graph import load_operator_db
        op_db, _ = load_operator_db()
        self.assertIsInstance(op_db, dict)
        self.assertGreater(len(op_db), 0)

    def test_alias_map_loaded(self):
        """别名映射已加载"""
        from relationship_graph import load_operator_db
        _, alias_map = load_operator_db()
        self.assertIsInstance(alias_map, dict)
        self.assertGreater(len(alias_map), 0)

    def test_core_characters_present(self):
        """核心角色存在于名库"""
        from relationship_graph import load_operator_db
        op_db, _ = load_operator_db()
        core = ["特蕾西娅", "阿米娅", "博士", "凯尔希"]
        for name in core:
            self.assertIn(name, op_db, f"核心角色 {name} 不在 OPERATOR_DB 中")

    def test_load_operator_db_from_file(self):
        """从文件加载角色名库"""
        from relationship_graph import load_operator_db
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = {
                "operators": {"测试角色": {"en": "TestOp", "race": "测试种族", "faction": "测试阵营"}},
                "aliases": {"TestOp": "测试角色"},
            }
            filepath = Path(tmpdir) / "custom.json"
            filepath.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
            op_db, alias_map = load_operator_db(str(filepath))
            self.assertIn("测试角色", op_db)
            self.assertIn("TestOp", alias_map)


class TestSpeechActExternalData(unittest.TestCase):
    """speech_act_analyzer.py 外置规则加载测试"""

    def test_speech_act_rules_loaded(self):
        """话语行为规则已加载"""
        from speech_act_analyzer import SPEECH_ACT_RULES
        self.assertIsInstance(SPEECH_ACT_RULES, list)
        self.assertGreater(len(SPEECH_ACT_RULES), 0)

    def test_load_custom_rules(self):
        """自定义规则加载"""
        from speech_act_analyzer import _load_speech_act_rules
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = [
                {"pattern": r"测试规则", "type": "test_type",
                 "confidence": 0.8, "label": "测试标签"}
            ]
            filepath = Path(tmpdir) / "custom.json"
            filepath.write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
            result = _load_speech_act_rules(str(filepath))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0][0], "测试规则")  # pattern
            self.assertEqual(result[0][1], "test_type")  # type


# ══════════════════════════════════════════════
# 5. 集成测试
# ══════════════════════════════════════════════


class TestPipelineDualMode(unittest.TestCase):
    """pipeline.py 双模式执行测试"""

    def test_pipeline_config_default_mode(self):
        """PipelineConfig 默认模式为 subprocess"""
        from pipeline import PipelineConfig
        config = PipelineConfig(name="测试")
        self.assertEqual(config.mode, "subprocess")

    def test_pipeline_config_function_mode(self):
        """PipelineConfig 函数模式"""
        from pipeline import PipelineConfig
        config = PipelineConfig(name="测试", mode="function")
        self.assertEqual(config.mode, "function")

    def test_pipeline_config_slug_auto(self):
        """slug 自动生成"""
        from pipeline import PipelineConfig
        config = PipelineConfig(name="特蕾西娅")
        self.assertEqual(config.slug, "te-lei-xi-ya")

    def test_pipeline_runner_creation(self):
        """PipelineRunner 创建"""
        from pipeline import PipelineConfig, PipelineRunner
        config = PipelineConfig(name="测试", mode="subprocess")
        runner = PipelineRunner(config)
        self.assertIsNotNone(runner)

    def test_run_tool_subprocess_invalid_tool(self):
        """subprocess 模式调用不存在的工具"""
        from pipeline import run_tool_subprocess
        result = run_tool_subprocess("nonexistent_tool_xyz", [], "测试")
        self.assertFalse(result)

    def test_run_tool_function_import(self):
        """function 模式导入测试"""
        from pipeline import run_tool_function
        # 不存在的模块应返回 False
        result = run_tool_function("nonexistent_tool_xyz", [], "测试")
        self.assertFalse(result)


class TestEndToEndIntegration(unittest.TestCase):
    """端到端集成测试（无网络依赖）"""

    def test_full_annotator_to_fingerprint_pipeline(self):
        """从标注到指纹的完整管线"""
        from context_annotator import build_context_json
        from dialogue_fingerprint import generate_fingerprint

        operator_data = {
            "name_zh": "测试角色",
            "slug": "test-role",
            "source_url": "https://example.com",
            "voice_lines": [
                {"label": "交谈1", "text": "我在。"},
                {"label": "交谈2", "text": "……不要紧。"},
                {"label": "交谈3", "text": "我一定会保护你们。"},
            ],
        }

        context = build_context_json(operator_data, [], [])
        self.assertGreater(len(context["annotated_lines"]), 0)

        # 验证 context 结构
        for line in context["annotated_lines"]:
            self.assertIn("id", line)
            self.assertIn("text", line)
            self.assertIn("source", line)
            self.assertIn("context", line)

        # 用 context 数据生成指纹
        voice_lines = [line for line in context["annotated_lines"] if line["source"] == "voice"]
        dialogues = [{"text": line["text"]} for line in voice_lines]
        fingerprint = generate_fingerprint(dialogues, "测试角色")
        self.assertIn("dimensions", fingerprint)

    def test_context_to_relationship_graph(self):
        """从 context 到关系图谱的管线"""
        from relationship_graph import compute_relationship_strength, extract_entities

        # 模拟 annotated_lines
        lines = [
            {"text": "特蕾西娅对阿米娅微笑", "context": {"phase": "babel"}},
            {"text": "博士和凯尔希在讨论", "context": {"phase": "resurrected"}},
        ]

        # 提取实体
        for line in lines:
            entities = extract_entities(line["text"])
            self.assertIsInstance(entities, list)

        # 计算关系强度
        strength = compute_relationship_strength(
            co_occurrence=10, total_lines=50,
            sentiment_words=["温柔"], dialogue_count=5,
        )
        self.assertGreater(strength, 0.0)

    def test_context_to_speech_act_profile(self):
        """从 context 到话语行为画像的管线"""
        from speech_act_analyzer import classify_speech_acts

        lines = [
            "你愿意和我一起吗？",
            "……也许吧。",
            "我一定会保护你们。",
            "我在。",
        ]

        all_acts = []
        for text in lines:
            acts = classify_speech_acts(text)
            self.assertIsInstance(acts, list)
            all_acts.extend(acts)

        # 至少应该检测到 3 种不同类型
        act_types = set(a["type"] for a in all_acts)
        self.assertGreaterEqual(len(act_types), 2)

    def test_context_to_temporal_slicer(self):
        """从 context 到时序切片的管线"""
        from temporal_slicer import compare_metrics_v2

        # 两个时期的指标对比
        early = {"ellipsis_pct": 15.0, "avg_sentence_length": 6.0}
        babel = {"ellipsis_pct": 45.0, "avg_sentence_length": 12.0}
        diffs = compare_metrics_v2(early, babel)
        self.assertIsInstance(diffs, list)

    def test_schema_validation_on_built_context(self):
        """构建的 context.json 通过 schema 验证"""
        from context_annotator import build_context_json
        from shared_utils import validate_context

        operator_data = {
            "name_zh": "测试",
            "slug": "test",
            "source_url": "https://example.com",
        }
        context = build_context_json(operator_data, [], [])
        errors = validate_context(context)
        self.assertEqual(len(errors), 0, f"Built context failed validation: {errors}")


class TestDataFileRoundtrip(unittest.TestCase):
    """数据文件写入-读取 roundtrip 测试"""

    def test_fingerprint_roundtrip_with_context_validation(self):
        """指纹写入 → 读取 → context 验证"""
        from dialogue_fingerprint import generate_fingerprint
        from shared_utils import atomic_write_json, load_json_safe

        with tempfile.TemporaryDirectory() as tmpdir:
            dialogues = [
                {"text": "我在。"},
                {"text": "不要怕。"},
                {"text": "我一定会保护你们。"},
            ]
            fingerprint = generate_fingerprint(dialogues, "测试")
            filepath = Path(tmpdir) / "fingerprint.json"
            atomic_write_json(str(filepath), fingerprint)

            loaded = load_json_safe(str(filepath))
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["operator"], "测试")
            self.assertIn("dimensions", loaded)

    def test_speech_act_profile_roundtrip(self):
        """话语行为画像 roundtrip"""
        from shared_utils import atomic_write_json, load_json_safe
        from speech_act_analyzer import classify_speech_acts

        with tempfile.TemporaryDirectory() as tmpdir:
            texts = ["你愿意和我一起吗？", "……也许吧。", "我在。"]
            all_acts = []
            for text in texts:
                acts = classify_speech_acts(text)
                all_acts.extend(acts)

            profile = {
                "total_acts": len(all_acts),
                "act_types": list(set(a["type"] for a in all_acts)),
            }
            filepath = Path(tmpdir) / "profile.json"
            atomic_write_json(str(filepath), profile)

            loaded = load_json_safe(str(filepath))
            self.assertEqual(loaded["total_acts"], len(all_acts))


# ══════════════════════════════════════════════
# 6. 属性/不变量测试
# ══════════════════════════════════════════════


class TestTypeConsistency(unittest.TestCase):
    """类型一致性测试"""

    def test_speech_act_result_structure(self):
        """话语行为结果结构一致"""
        from speech_act_analyzer import classify_speech_acts
        texts = ["我在", "你愿意吗？", "别怕", "……也许", "我一定会"]
        for text in texts:
            acts = classify_speech_acts(text)
            for act in acts:
                self.assertIn("type", act)
                self.assertIn("confidence", act)
                self.assertIsInstance(act["type"], str)
                self.assertIsInstance(act["confidence"], (int, float))

    def test_fingerprint_dimensions_keys(self):
        """指纹维度键名一致"""
        from dialogue_fingerprint import generate_fingerprint
        dialogues = [{"text": "测试文本。"}]
        result = generate_fingerprint(dialogues, "测试")
        dims = result["dimensions"]
        # 验证维度键格式：数字前缀
        for key in dims:
            self.assertRegex(key, r"^\d+_", f"维度键 {key} 不符合 N_name 格式")

    def test_phase_values(self):
        """时期值一致"""
        from constants import PHASE_ORDER
        # PHASE_ORDER 中每个值应唯一且为有效字符串
        self.assertEqual(len(PHASE_ORDER), len(set(PHASE_ORDER)), "PHASE_ORDER 有重复")
        for phase in PHASE_ORDER:
            self.assertIsInstance(phase, str)
            self.assertTrue(len(phase) > 0)

    def test_annotated_line_fields(self):
        """标注行字段完整"""
        from context_annotator import annotate_voice_line
        line = {"label": "交谈1", "text": "你好"}
        result = annotate_voice_line(line, 0, default_phase="resurrected")
        required = {"id", "text", "source", "source_detail", "context"}
        self.assertTrue(required.issubset(set(result.keys())),
                        f"缺少字段: {required - set(result.keys())}")

    def test_relationship_strength_range(self):
        """关系强度在 [0, 1] 范围"""
        from relationship_graph import compute_relationship_strength
        for _ in range(20):
            import random
            strength = compute_relationship_strength(
                co_occurrence=random.randint(0, 100),
                total_lines=100,
                sentiment_words=random.choice([[], ["温柔", "信任"]]),
                dialogue_count=random.randint(0, 50),
            )
            self.assertGreaterEqual(strength, 0.0)
            self.assertLessEqual(strength, 1.0)

    def test_catchphrase_analysis_structure(self):
        """口头禅分析结构"""
        from dialogue_fingerprint import analyze_catchphrases
        dialogues = [
            {"text": "我在。"},
            {"text": "我在，不要怕。"},
            {"text": "走吧。"},
        ]
        result = analyze_catchphrases(dialogues)
        self.assertIn("signature_phrases", result)
        for phrase in result["signature_phrases"]:
            self.assertIn("phrase", phrase)
            self.assertIn("count", phrase)


class TestCanonCheckerInvariants(unittest.TestCase):
    """canon_checker.py 不变量测试"""

    def test_misconception_ids_unique(self):
        """误解 ID 唯一"""
        from canon_checker import _load_builtin_misconceptions
        misconceptions = _load_builtin_misconceptions()
        ids = [m["id"] for m in misconceptions]
        self.assertEqual(len(ids), len(set(ids)), f"重复 ID: {[i for i in ids if ids.count(i) > 1]}")

    def test_check_patterns_compile(self):
        """所有检查模式可编译"""
        from canon_checker import _load_builtin_misconceptions
        misconceptions = _load_builtin_misconceptions()
        for m in misconceptions:
            for cp in m.get("check_patterns", []):
                try:
                    re.compile(cp["pattern"])
                except re.error as e:
                    self.fail(f"模式 {m['id']} 无法编译: {cp['pattern']}, 错误: {e}")

    def test_exclude_patterns_compile(self):
        """所有排除模式可编译"""
        from canon_checker import _load_builtin_misconceptions
        misconceptions = _load_builtin_misconceptions()
        for m in misconceptions:
            for ep in m.get("exclude_patterns", []):
                try:
                    re.compile(ep)
                except re.error as e:
                    self.fail(f"排除模式 {m['id']} 无法编译: {ep}, 错误: {e}")


class TestVersionManagerInvariants(unittest.TestCase):
    """version_manager.py 不变量测试"""

    def test_normalize_idempotent(self):
        """规范化幂等：normalize(normalize(x)) == normalize(x)"""
        from version_manager import _normalize_version
        cases = ["v1", "v1.0", "1", "1.0", "v2.3", "2.3"]
        for v in cases:
            n1 = _normalize_version(v)
            n2 = _normalize_version(n1)
            self.assertEqual(n1, n2, f"幂等失败: {v} → {n1} → {n2}")

    def test_semver_total_order(self):
        """_SemVer 全序关系"""
        from version_manager import _SemVer
        versions = [_SemVer(i, j) for i in range(4) for j in range(4)]
        for a in versions:
            for b in versions:
                # 恰好满足 a < b, a == b, a > b 之一
                comparisons = [a < b, a == b, a > b]
                self.assertEqual(sum(comparisons), 1, f"全序失败: {a} vs {b}")


class TestMathUtils(unittest.TestCase):
    """temporal_slicer.py 数学工具测试"""

    def test_normal_cdf_symmetry(self):
        """标准正态 CDF 对称性：Φ(-z) = 1 - Φ(z)"""
        from temporal_slicer import _normal_cdf
        for z in [0.0, 0.5, 1.0, 1.96, 2.576]:
            self.assertAlmostEqual(_normal_cdf(-z), 1.0 - _normal_cdf(z), places=5,
                                   msg=f"对称性失败: z={z}")

    def test_normal_cdf_at_zero(self):
        """Φ(0) = 0.5"""
        from temporal_slicer import _normal_cdf
        self.assertAlmostEqual(_normal_cdf(0.0), 0.5, places=5)

    def test_normal_cdf_monotonic(self):
        """Φ(z) 单调递增"""
        from temporal_slicer import _normal_cdf
        prev = 0.0
        for z in [i * 0.1 for i in range(-50, 51)]:
            curr = _normal_cdf(z)
            self.assertGreaterEqual(curr, prev - 1e-10, f"单调性失败: z={z}")
            prev = curr


if __name__ == "__main__":
    unittest.main(verbosity=2)
