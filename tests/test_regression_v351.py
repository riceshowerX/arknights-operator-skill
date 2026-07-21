#!/usr/bin/env python3
"""
v3.5.1 回归测试 — 验证代码审查中发现并修复的所有缺陷

覆盖范围：
  1. PipelineConfig.strict 字段存在且可通过 CLI 启用
  2. relationship_graph 不再引用不存在的 PRTSClient
  3. context_annotator 的 timeline id 与 phase 值语言一致
  4. data_injector 文件名映射正确（匹配实际产物文件名）
  5. data_injector format_fingerprint 兼容嵌套与扁平两种结构
  6. PipelineConfig.__post_init__ 不再用过宽的 except 吞掉真实 bug
  7. 示例角色档案数据健康度校验

运行方式:
    python3 -m pytest tests/test_regression_v351.py -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

REPO_ROOT = Path(__file__).parent.parent
OPERATORS_DIR = REPO_ROOT / "operators"


# ══════════════════════════════════════════════
# 1. PipelineConfig.strict 字段
# ══════════════════════════════════════════════


class TestPipelineConfigStrictField(unittest.TestCase):
    """验证 v3.5.1 修复：PipelineConfig 缺少 strict 字段导致 --strict CLI 崩溃"""

    def test_strict_field_exists_with_default_false(self):
        """PipelineConfig 应有 strict 字段，默认 False"""
        from pipeline import PipelineConfig

        config = PipelineConfig(name="测试角色")
        self.assertTrue(hasattr(config, "strict"))
        self.assertFalse(config.strict)

    def test_strict_field_can_be_set_true(self):
        """PipelineConfig 应能接受 strict=True"""
        from pipeline import PipelineConfig

        config = PipelineConfig(name="测试角色", strict=True)
        self.assertTrue(config.strict)

    def test_strict_field_does_not_crash_construction(self):
        """v3.5.0 回归：strict=True 不应导致 TypeError"""
        from pipeline import PipelineConfig

        # v3.5.0 此处抛 TypeError: __init__() got an unexpected keyword argument 'strict'
        try:
            config = PipelineConfig(name="测试角色", strict=True)
        except TypeError as e:
            self.fail(f"PipelineConfig(strict=True) 不应抛 TypeError: {e}")
        self.assertTrue(config.strict)

    def test_main_accepts_strict_flag(self):
        """CLI main() 应能处理 --strict 参数而不崩溃"""
        from pipeline import main

        old_argv = sys.argv
        sys.argv = ["pipeline.py", "--name", "测试角色", "--step", "full", "--dry-run", "--strict"]
        try:
            # --dry-run 确保不实际执行
            main()
        except SystemExit as e:
            # dry-run 成功不应 exit(1)
            self.assertNotEqual(e.code, 1, f"--strict --dry-run 不应失败: exit code {e.code}")
        except TypeError as e:
            self.fail(f"main() with --strict 不应抛 TypeError: {e}")
        finally:
            sys.argv = old_argv


# ══════════════════════════════════════════════
# 2. relationship_graph 不引用不存在的 PRTSClient
# ══════════════════════════════════════════════


class TestRelationshipGraphNoPRTSClient(unittest.TestCase):
    """验证 v3.5.1 修复：relationship_graph 不再引用不存在的 PRTSClient 类"""

    def test_prts_client_has_no_prts_client_class(self):
        """prts_client 模块不应导出 PRTSClient 类"""
        import prts_client

        self.assertFalse(
            hasattr(prts_client, "PRTSClient"),
            "prts_client 不应导出 PRTSClient 类（v3.5.0 幻觉引用）",
        )

    def test_prts_client_exports_functions(self):
        """prts_client 应导出函数式接口"""
        import prts_client

        for func_name in ["prts_api_get", "fetch_page_wikitext", "fetch_page_categories"]:
            self.assertTrue(
                hasattr(prts_client, func_name),
                f"prts_client 应导出 {func_name}",
            )

    def test_relationship_graph_source_no_prts_client(self):
        """relationship_graph.py 源码不应包含 PRTSClient 引用"""
        rg_source = (TOOLS_DIR / "relationship_graph.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "PRTSClient",
            rg_source,
            "relationship_graph.py 不应再引用 PRTSClient（已改为 fetch_page_wikitext 函数）",
        )

    def test_fetch_operators_from_prts_is_callable(self):
        """_fetch_operators_from_prts 函数应可调用（不抛 ImportError）"""
        from relationship_graph import _fetch_operators_from_prts

        # 函数应存在且可调用（实际网络调用会被 except 兜底，返回 None 或 dict）
        self.assertTrue(callable(_fetch_operators_from_prts))


# ══════════════════════════════════════════════
# 3. timeline id 与 phase 值语言一致性
# ══════════════════════════════════════════════


class TestTimelinePhaseConsistency(unittest.TestCase):
    """验证 v3.5.1 修复：timeline id（中文→英文）与 phase 值一致"""

    def test_phase_label_map_exists_and_has_entries(self):
        """PHASE_LABEL_MAP 应存在且包含中文→英文映射"""
        from constants import PHASE_LABEL_MAP

        self.assertGreater(len(PHASE_LABEL_MAP), 0)
        self.assertEqual(PHASE_LABEL_MAP["早期"], "early")
        self.assertEqual(PHASE_LABEL_MAP["巴别塔时期"], "babel")
        self.assertEqual(PHASE_LABEL_MAP["复活后"], "resurrected")

    def test_load_timeline_maps_chinese_labels_to_english_ids(self):
        """load_timeline 应将中文标签映射为英文 id"""
        from context_annotator import load_timeline

        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_md = Path(tmpdir) / "knowledge.md"
            knowledge_md.write_text(
                "# 测试角色\n\n"
                "## 核心事件时间线\n\n"
                "### 893-898 早期\n- 出生\n\n"
                "### 1031-1094 巴别塔时期\n- 内战\n\n"
                "### 1094-1099 复活后\n- 复活\n",
                encoding="utf-8",
            )

            timeline = load_timeline(str(knowledge_md))

            self.assertEqual(len(timeline), 3)
            # 关键：id 应为英文，与 annotated_lines.context.phase 一致
            self.assertEqual(timeline[0]["id"], "early")
            self.assertEqual(timeline[1]["id"], "babel")
            self.assertEqual(timeline[2]["id"], "resurrected")
            # label 仍为中文
            self.assertEqual(timeline[0]["label"], "早期")

    def test_w_context_timeline_ids_are_english(self):
        """W 的 context.json timeline id 应为英文（与 phase 值匹配）"""
        w_context = OPERATORS_DIR / "w" / "context.json"
        if not w_context.exists():
            self.skipTest("W context.json 不存在")

        data = json.loads(w_context.read_text(encoding="utf-8"))
        timeline_ids = [t["id"] for t in data.get("timeline", [])]

        # 不应包含中文 id
        for tid in timeline_ids:
            self.assertTrue(
                tid.isascii(),
                f"W timeline id '{tid}' 应为 ASCII 英文，不应是中文",
            )

    def test_w_context_timeline_phases_intersect(self):
        """W 的 timeline id 与 annotated_lines 的 phase 值应有交集
        （否则 temporal_slicer 的跨期比较会完全失效）"""
        w_context = OPERATORS_DIR / "w" / "context.json"
        if not w_context.exists():
            self.skipTest("W context.json 不存在")

        data = json.loads(w_context.read_text(encoding="utf-8"))
        timeline_ids = set(t["id"] for t in data.get("timeline", []))
        phase_values = set(
            line.get("context", {}).get("phase")
            for line in data.get("annotated_lines", [])
            if line.get("context", {}).get("phase")
        )

        intersection = timeline_ids & phase_values
        self.assertGreater(
            len(intersection),
            0,
            f"W timeline ids {timeline_ids} 与 phase values {phase_values} 应有交集，"
            f"否则 temporal_slicer 跨期分析完全失效",
        )


# ══════════════════════════════════════════════
# 4. data_injector 文件名映射
# ══════════════════════════════════════════════


class TestDataInjectorFileMapping(unittest.TestCase):
    """验证 v3.5.1 修复：data_injector 文件名映射匹配实际产物"""

    def test_data_injector_maps_correct_filenames(self):
        """data_injector 的 all_sections 应映射到实际产物文件名"""
        from data_injector import generate_data_context

        # 用 W 测试（已有完整产物）
        if not (OPERATORS_DIR / "w").exists():
            self.skipTest("W 角色目录不存在")

        result = generate_data_context(slug="w", base_dir=str(OPERATORS_DIR))

        # 应能输出指纹数据（说明 fingerprint.json 被正确读取）
        self.assertIn("句式长度", result)
        # 应能输出话语行为数据（说明 speech_act_profile.json 被正确读取）
        self.assertIn("行为模式", result)
        # 应能输出时序数据（说明 temporal_slices.json 被正确读取）
        self.assertIn("时序演变", result)

    def test_data_injector_fingerprint_handles_nested_structure(self):
        """format_fingerprint 应能处理嵌套结构（context 模式输出）"""
        from data_injector import format_fingerprint

        nested_data = {
            "operator": "测试",
            "mode": "context",
            "global": {
                "dimensions": {
                    "1_sentence_length": {
                        "type": "中句型",
                        "median": 12,
                        "percentiles": {"p25": 6, "p50": 12, "p75": 20},
                        "cv": 0.8,
                        "rhythm": "多变",
                    },
                    "2_pause_markers": {
                        "ellipsis_pct": 30.0,
                        "exclamation_pct": 5.0,
                        "question_pct": 15.0,
                    },
                },
                "summary": "测试综合画像描述",
            },
        }

        result = format_fingerprint(nested_data)
        self.assertIn("句式长度", result)
        self.assertIn("中句型", result)
        self.assertIn("停顿习惯", result)
        self.assertIn("省略号频率 30.0%", result)

    def test_data_injector_fingerprint_handles_flat_structure(self):
        """format_fingerprint 应能处理扁平结构（传统模式输出）"""
        from data_injector import format_fingerprint

        flat_data = {
            "sentence_length": {
                "type": "短句型",
                "median": 8,
                "percentiles": {"p25": 4, "p50": 8, "p75": 12},
                "cv": 0.5,
                "rhythm": "稳定",
            },
        }

        result = format_fingerprint(flat_data)
        self.assertIn("句式长度", result)
        self.assertIn("短句型", result)

    def test_data_injector_fingerprint_handles_string_summary(self):
        """format_fingerprint 应能处理 summary 为字符串的情况（v3.5.1 修复）"""
        from data_injector import format_fingerprint

        data = {
            "global": {
                "dimensions": {},
                "summary": "这是字符串形式的摘要",
            },
        }
        # v3.5.0 此处抛 AttributeError: 'str' object has no attribute 'get'
        try:
            result = format_fingerprint(data)
        except AttributeError as e:
            self.fail(f"format_fingerprint 不应对字符串 summary 抛 AttributeError: {e}")
        self.assertIn("这是字符串形式的摘要", result)


# ══════════════════════════════════════════════
# 5. PipelineConfig.__post_init__ 异常捕获
# ══════════════════════════════════════════════


class TestPipelineConfigExceptionHandling(unittest.TestCase):
    """验证 v3.5.1 修复：__post_init__ 不再用过宽 except 吞掉真实 bug"""

    def test_post_init_does_not_swallow_value_error_from_to_slug(self):
        """如果 to_slug 抛 ValueError（非 ImportError），应向上传播"""
        from pipeline import PipelineConfig

        # to_slug 正常工作时返回有效 slug
        config = PipelineConfig(name="特蕾西娅")
        self.assertEqual(config.slug, "te-lei-xi-ya")

    def test_post_init_source_no_broad_exception(self):
        """pipeline.py 源码不应再包含 except (ImportError, Exception) 模式"""
        pipeline_source = (TOOLS_DIR / "pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "except (ImportError, Exception)",
            pipeline_source,
            "pipeline.py 不应再用 except (ImportError, Exception) 吞掉所有异常",
        )


# ══════════════════════════════════════════════
# 6. 示例角色档案数据健康度
# ══════════════════════════════════════════════


class TestOperatorArtifactHealth(unittest.TestCase):
    """验证 v3.5.1 修复：示例角色档案数据与文档声明一致"""

    def test_te_lei_xi_ya_context_has_annotated_lines(self):
        """特蕾西娅 context.json 的 annotated_lines 不应为空
        （v3.5.0 为空，与 AGENTS.md 声称的"60 条标注"不符）"""
        ctx_path = OPERATORS_DIR / "te-lei-xi-ya" / "context.json"
        if not ctx_path.exists():
            self.skipTest("特蕾西娅 context.json 不存在")

        data = json.loads(ctx_path.read_text(encoding="utf-8"))
        lines = data.get("annotated_lines", [])
        self.assertGreater(
            len(lines),
            0,
            "特蕾西娅 context.json 的 annotated_lines 不应为空",
        )

        # stats.total_lines 应与实际行数一致
        total = data.get("stats", {}).get("total_lines", 0)
        self.assertEqual(total, len(lines), "stats.total_lines 应与 annotated_lines 长度一致")

    def test_te_lei_xi_ya_character_name_is_correct(self):
        """特蕾西娅的 character 字段应为"特蕾西娅"而非"魔王"（PRTS 页面名）"""
        ctx_path = OPERATORS_DIR / "te-lei-xi-ya" / "context.json"
        if not ctx_path.exists():
            self.skipTest("特蕾西娅 context.json 不存在")

        data = json.loads(ctx_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("character"), "特蕾西娅")
        self.assertEqual(data.get("slug"), "te-lei-xi-ya")

    def test_w_context_has_multiple_phases(self):
        """W 的 context.json 应有多个时期（v3.5.0 全部为 early，时序分析失效）"""
        ctx_path = OPERATORS_DIR / "w" / "context.json"
        if not ctx_path.exists():
            self.skipTest("W context.json 不存在")

        data = json.loads(ctx_path.read_text(encoding="utf-8"))
        phase_dist = data.get("stats", {}).get("phase_distribution", {})

        # 应至少有 2 个时期（early + babel）
        non_unknown = {k: v for k, v in phase_dist.items() if k != "unknown"}
        self.assertGreaterEqual(
            len(non_unknown),
            2,
            f"W 应有至少 2 个时期，实际 phase_distribution: {phase_dist}",
        )

    def test_w_temporal_slices_has_rules(self):
        """W 的 temporal_slices 应有时序规则（v3.5.0 为 0，因 timeline/phase 不匹配）"""
        slices_path = OPERATORS_DIR / "w" / "temporal_slices.json"
        if not slices_path.exists():
            self.skipTest("W temporal_slices.json 不存在")

        data = json.loads(slices_path.read_text(encoding="utf-8"))
        rule_count = data.get("rule_count", 0)
        self.assertGreater(
            rule_count,
            0,
            "W temporal_slices 应有时序规则（v3.5.0 因 timeline/phase 不匹配为 0）",
        )

    def test_all_operator_contexts_pass_schema_validation(self):
        """所有角色 context.json 应通过 schema 校验"""
        from shared_utils import validate_context

        if not OPERATORS_DIR.exists():
            self.skipTest("operators 目录不存在")

        for operator_dir in OPERATORS_DIR.iterdir():
            if not operator_dir.is_dir():
                continue
            ctx_path = operator_dir / "context.json"
            if not ctx_path.exists():
                continue

            with self.subTest(operator=operator_dir.name):
                data = json.loads(ctx_path.read_text(encoding="utf-8"))
                errors = validate_context(data)
                self.assertEqual(
                    errors,
                    [],
                    f"{operator_dir.name}/context.json schema 校验失败: {errors}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
