#!/usr/bin/env python3
"""v3.6.0 回归用例 —— 针对本轮修复的 P0/P1 缺陷逐条建立「能独立暴露它」的断言。

设计原则：
    1. 每条用例都对**具体值**断言（文件名、计数、退出码、产物字节数），
       不允许「只要不抛异常就算过」这种结构性恒真断言；
    2. 关键缺陷（产物契约、story 双读、meta merge、slug 确定性）各覆盖
       ≥ 2 个用例，其中 slug 与实体顺序必须**跨进程**验证——只有跨进程
       才能抓到 `hash()` 受 PYTHONHASHSEED 随机化影响这一类缺陷；
    3. 用例与实现解耦到「契约层」：断言 artifacts.ARTIFACT 里的文件名常量，
       而不是各自模块内部写死的字面量。

覆盖清单（对应审查报告编号）：
    T1 产物契约          P0-1
    T2 story 双读        P0-2
    T3 meta 字段级 merge P0-3
    T4 slug 确定性       P1-1
    T5 data_injector 双读 P1-3 / P1-4
    T6 CLI 退出码        隐患
    T7 编码健壮性        隐患
    T8 确定性（排序）    本轮修复
    T9 端到端冒烟（旧名 story.json）
    T10 --resume 语义    P1-2
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# tools 目录加入 import 路径（与其余测试保持一致）
TOOLS_DIR = Path(__file__).parent.parent / "tools"
PROJECT_ROOT = TOOLS_DIR.parent
PYTHON = sys.executable
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import artifacts  # noqa: E402
import data_injector  # noqa: E402
import game_data_parser  # noqa: E402
import pipeline  # noqa: E402
import relationship_graph  # noqa: E402
import skill_writer  # noqa: E402
import temporal_slicer  # noqa: E402
from artifacts import ANALYZE_TOOLS, ARTIFACT, STEP_ARTIFACTS  # noqa: E402
from shared_utils import load_json_safe, read_text_utf8  # noqa: E402


def _run_tool(script_name: str, args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """以子进程方式跑 tools/ 下的一个脚本，返回 CompletedProcess（文本模式）"""
    cmd = [PYTHON, str(TOOLS_DIR / f"{script_name}.py")] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=env,
    )


def _run_py(code: str, hashseed: str) -> str:
    """在指定 PYTHONHASHSEED 的子进程里执行一段代码，返回 stdout（strip 后）"""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [PYTHON, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"子进程失败: {result.stderr}"
    return result.stdout.strip()


# ──────────────────────────────────────────────
# T1 产物契约（P0-1）
# ──────────────────────────────────────────────


class TestArtifactContract:
    """analyze 步骤必须落盘 4 个产物，且每个工具都必须带输出参数键。"""

    def test_analyze_step_declares_exactly_four_artifacts(self):
        """analyze 的 resume 判据必须是它自己的 4 个产物（而不是 context.json）"""
        declared = STEP_ARTIFACTS["analyze"]
        assert declared == [
            "fingerprint.json",
            "speech_act_profile.json",
            "temporal_slices.json",
            "relationship_graph.json",
        ]
        assert len(declared) == 4
        # 关键回归点：context.json 是 annotate 的产物，不得出现在 analyze 判据里
        assert ARTIFACT.CONTEXT not in declared

    def test_every_analyze_tool_declares_an_output_flag(self):
        """删掉输出参数 → 工具只 print 不落盘 → 本用例必须失败"""
        tools = {name: (out_args, artifact) for name, out_args, artifact in ANALYZE_TOOLS}
        assert set(tools) == {
            "speech_act_analyzer",
            "dialogue_fingerprint",
            "relationship_graph",
            "temporal_slicer",
        }

        flags: dict[str, str] = {}
        for name, (out_args, artifact) in tools.items():
            output_flags = [a for a in out_args if a in ("--output", "--output-profile")]
            assert output_flags, f"{name} 未声明输出参数，产物 {artifact} 将无法落盘"
            flags[name] = output_flags[0]
            # 产物名必须是真实文件名常量，而不是任意字符串
            assert artifact in vars(ARTIFACT).values()

        # speech_act_analyzer 的参数名与其他三个不同（历史契约），必须精确
        assert flags["speech_act_analyzer"] == "--output-profile"
        assert flags["dialogue_fingerprint"] == "--output"
        assert flags["relationship_graph"] == "--output"
        assert flags["temporal_slicer"] == "--output"

    def test_analyze_artifact_names_are_distinct(self):
        """4 个产物文件名互不重复（重复会互相覆盖，下游读到半份数据）"""
        names = [artifact for _, _, artifact in ANALYZE_TOOLS]
        assert len(set(names)) == 4


# ──────────────────────────────────────────────
# T2 story 双读（P0-2）
# ──────────────────────────────────────────────


class TestStoryDoubleRead:
    """context_annotator 的 --story-json 必须新旧文件名双读，旧名必须告警。"""

    @staticmethod
    def _prepare_dir(tmp_path: Path, story_names: list[str]) -> Path:
        work = tmp_path / "op"
        work.mkdir(parents=True, exist_ok=True)
        (work / ARTIFACT.OPERATOR_DATA).write_text('{"name_zh": "测试"}', encoding="utf-8")
        (work / "knowledge.md").write_text("# 测试\n\n### 早期\n占位\n", encoding="utf-8")
        for name in story_names:
            (work / name).write_text('{"dialogues": []}', encoding="utf-8")
        return work

    @staticmethod
    def _capture(monkeypatch, work: Path) -> list[list[str]]:
        calls: list[list[str]] = []

        def fake_run_tool(tool_name, args, description=""):
            calls.append([tool_name, *args])
            return True

        monkeypatch.setattr(pipeline, "run_tool", fake_run_tool)
        cfg = pipeline.PipelineConfig(name="测试", slug="test-op", output_dir=str(work),
                                      mode=pipeline.MODE_FUNCTION)
        assert pipeline.PipelineRunner(cfg).step_annotate() is True
        return calls

    def test_legacy_story_json_is_passed_and_warned(self, tmp_path, monkeypatch, caplog):
        """只有 story.json（旧名）时：必须照样传给下游，且必须告警"""
        work = self._prepare_dir(tmp_path, [ARTIFACT.STORY_LEGACY])
        with caplog.at_level(logging.WARNING, logger="pipeline"):
            calls = self._capture(monkeypatch, work)

        assert len(calls) == 1
        tool_name, *args = calls[0]
        assert tool_name == "context_annotator"
        assert "--story-json" in args
        story_arg = args[args.index("--story-json") + 1]
        assert Path(story_arg) == work / "story.json", "--story-json 必须指向旧名文件本体"
        assert Path(story_arg).exists()

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "使用旧文件名时必须产生 warning（否则契约漂移再次静默发生）"
        assert "story.json" in caplog.text
        assert "story_data.json" in caplog.text

    def test_new_story_json_takes_priority_without_warning(self, tmp_path, monkeypatch, caplog):
        """新旧两个文件都在时：必须优先新名，且不得误告警"""
        work = self._prepare_dir(tmp_path, [ARTIFACT.STORY, ARTIFACT.STORY_LEGACY])
        with caplog.at_level(logging.WARNING, logger="pipeline"):
            calls = self._capture(monkeypatch, work)

        tool_name, *args = calls[0]
        story_arg = Path(args[args.index("--story-json") + 1])
        assert story_arg == work / "story_data.json"
        assert story_arg.name != "story.json"
        assert "使用旧文件名" not in caplog.text

    def test_no_story_file_no_flag(self, tmp_path, monkeypatch):
        """两个文件都不存在时不传 --story-json（保持旧行为，不伪造空剧情）"""
        work = self._prepare_dir(tmp_path, [])
        calls = self._capture(monkeypatch, work)
        assert "--story-json" not in calls[0]


# ──────────────────────────────────────────────
# T3 meta 字段级 merge（P0-3）
# ──────────────────────────────────────────────


class TestMetaFieldLevelMerge:
    """重跑 create 不得把用户域字段（corrections_count / impression）清零。"""

    @staticmethod
    def _seed_user_state(base_dir: Path) -> None:
        meta_path = base_dir / "recall-op" / ARTIFACT.META
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["corrections_count"] = 7
        meta["impression"] = "X"
        meta["version"] = "v1.1"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_user_fields_survive_recreate(self, tmp_path):
        base = str(tmp_path)
        skill_writer.create_default_skill("recall-op", "回滚阿", base_dir=base)
        self._seed_user_state(tmp_path)

        skill_writer.create_default_skill("recall-op", "回滚阿", base_dir=base)
        meta = load_json_safe(tmp_path / "recall-op" / ARTIFACT.META)

        assert meta["corrections_count"] == 7, "重跑 create 把 corrections_count 清零了（P0-3 回归）"
        assert meta["impression"] == "X", "重跑 create 把 impression 清空了（P0-3 回归）"
        # version 属于工具域，但已有非空版本必须保留（否则与 versions/ 存档脱节）
        assert meta["version"] == "v1.1"

    def test_tool_fields_are_still_refreshed(self, tmp_path):
        """工具域字段仍以本次为准：name 改名后必须更新"""
        base = str(tmp_path)
        skill_writer.create_default_skill("recall-op", "旧名字", base_dir=base)
        skill_writer.create_default_skill("recall-op", "新名字", base_dir=base)
        meta = load_json_safe(tmp_path / "recall-op" / ARTIFACT.META)
        assert meta["name"] == "新名字"
        assert meta["slug"] == "recall-op"

    def test_reset_env_forces_full_overwrite(self, tmp_path, monkeypatch):
        """逃生口：ARKNIGHTS_META_RESET=1 时用户域字段允许被重置"""
        base = str(tmp_path)
        skill_writer.create_default_skill("recall-op", "回滚阿", base_dir=base)
        self._seed_user_state(tmp_path)

        monkeypatch.setenv("ARKNIGHTS_META_RESET", "1")
        skill_writer.create_default_skill("recall-op", "回滚阿", base_dir=base)
        meta = load_json_safe(tmp_path / "recall-op" / ARTIFACT.META)

        assert meta["corrections_count"] == 0
        assert meta["impression"] == ""
        assert meta["version"] == "v1.0"


# ──────────────────────────────────────────────
# T4 slug 确定性（P1-1）
# ──────────────────────────────────────────────


class TestSlugDeterminism:
    """无法拼音化的角色名必须落到「跨进程稳定」的 fallback slug。"""

    NAME = "阿尔图罗"
    # 期望值 = "op-" + sha1("阿尔图罗".encode("utf-8")).hexdigest()[:8]
    EXPECTED = "op-27dfe9cd"

    def test_fallback_slug_matches_hardcoded_sha1(self):
        """硬编码期望值：实现若回退到内置 hash() 或换算法，本用例立即失败"""
        assert game_data_parser.to_slug(self.NAME) == self.EXPECTED

    def test_fallback_slug_is_stable_in_process(self):
        """同进程多次调用结果一致"""
        results = {game_data_parser.to_slug(self.NAME) for _ in range(5)}
        assert results == {self.EXPECTED}

    def test_fallback_slug_is_stable_across_processes(self):
        """跨进程（不同 PYTHONHASHSEED）必须一致 —— 只有这个用例能抓到 hash 随机化"""
        code = (
            f"import sys; sys.path.insert(0, {str(TOOLS_DIR)!r}); "
            "import game_data_parser; "
            f"sys.stdout.write(game_data_parser.to_slug({self.NAME!r}))"
        )
        seen = {_run_py(code, seed) for seed in ("0", "1")}
        assert seen == {self.EXPECTED}, f"跨进程 slug 不一致: {seen}"

    def test_source_does_not_use_builtin_hash(self):
        """静态守卫：源码里不得出现 hash(name)（受 PYTHONHASHSEED 影响）"""
        source = read_text_utf8(TOOLS_DIR / "game_data_parser.py")
        assert "hash(name)" not in source
        assert "hashlib.sha1(name.encode" in source


# ──────────────────────────────────────────────
# T5 data_injector 双读（P1-3 / P1-4）
# ──────────────────────────────────────────────


class TestDataInjectorDoubleRead:
    """关系段必须真实输出人名与强度；场景分布必须能从 stats 下读到。"""

    @staticmethod
    def _write_context(tmp_path: Path, payload: dict, slug: str = "double-read") -> Path:
        operator_dir = tmp_path / slug
        operator_dir.mkdir(parents=True, exist_ok=True)
        (operator_dir / ARTIFACT.CONTEXT).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return tmp_path

    def test_new_relation_schema_outputs_real_names(self, tmp_path):
        """新格式 annotated_relations[{from,to,type,confidence,sources}]"""
        base = self._write_context(tmp_path, {
            "annotated_relations": [
                {
                    "from": "W",
                    "to": "凯尔希",
                    "type": "trust",
                    "confidence": "high",
                    "sources": ["S001", "S002"],
                }
            ]
        })
        out = data_injector.generate_data_context("double-read", base_dir=str(base),
                                                  sections=["relationships"])
        assert "**凯尔希**" in out, "新格式关系对象名未被读到（P1-3 回归）"
        assert "强度 0.90" in out, f"confidence=high 应映射为 0.90，实际输出:\n{out}"
        assert "2 条证据" in out
        assert "未知" not in out, "关系段退化为「未知」即 P1-3 缺陷复发"

    def test_legacy_relation_schema_still_works(self, tmp_path):
        """旧格式 relations[{target,strength,evidence_count}] 输出必须保持等价"""
        base = self._write_context(tmp_path, {
            "relations": [
                {
                    "target": "阿米娅",
                    "relation_type": "bond",
                    "strength": 0.75,
                    "evidence_count": 3,
                }
            ]
        })
        out = data_injector.generate_data_context("double-read", base_dir=str(base),
                                                  sections=["relationships"])
        assert "**阿米娅**" in out
        assert "强度 0.75" in out
        assert "3 条证据" in out
        assert "未知" not in out

    def test_situation_distribution_under_stats(self, tmp_path):
        """分布数据在 stats 下时必须输出「场景分布」（P1-4）"""
        base = self._write_context(tmp_path, {
            "stats": {
                "situation_distribution": {"casual": 12, "battle": 3},
                "interlocutor_distribution": {"博士": 9},
            }
        })
        out = data_injector.generate_data_context("double-read", base_dir=str(base),
                                                  sections=["context"])
        assert "场景分布" in out, f"stats 下的 situation_distribution 未被读到:\n{out}"
        assert "- casual: 12 条" in out
        assert "- 博士: 9 条" in out

    def test_confidence_string_maps_to_nonzero_strength(self):
        """confidence 字符串必须映射为非零数值（0.00 是旧缺陷的表征）"""
        assert data_injector._resolve_strength({"confidence": "high"}) == pytest.approx(0.9)
        assert data_injector._resolve_strength({"confidence": "medium"}) == pytest.approx(0.6)
        assert data_injector._resolve_strength({"confidence": "low"}) == pytest.approx(0.3)


# ──────────────────────────────────────────────
# T6 CLI 退出码（隐患）
# ──────────────────────────────────────────────


class TestCliExitCodes:
    """退出码三值语义：0 成功 / 1 运行期失败 / 2 用法或前置错误。"""

    def test_delete_missing_skill_returns_1(self, tmp_path):
        result = _run_tool("skill_writer", [
            "--action", "delete", "--slug", "no-such-slug", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 1, result.stdout + result.stderr
        assert "不存在" in result.stdout

    def test_delete_without_force_returns_2(self, tmp_path):
        skill_dir = tmp_path / "guarded-op"
        (skill_dir / "versions").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# x\n", encoding="utf-8")
        (skill_dir / ARTIFACT.META).write_text('{"slug": "guarded-op"}', encoding="utf-8")

        result = _run_tool("skill_writer", [
            "--action", "delete", "--slug", "guarded-op", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 2, result.stdout + result.stderr
        assert skill_dir.exists(), "未确认删除时不得真的删除目录"

    def test_rollback_missing_version_returns_1(self, tmp_path):
        (tmp_path / "guarded-op" / "versions").mkdir(parents=True)
        result = _run_tool("version_manager", [
            "--action", "rollback", "--slug", "guarded-op", "--version", "v9.9",
            "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 1, result.stdout + result.stderr
        assert "v9.9" in result.stdout

    def test_data_injector_missing_operator_returns_1(self, tmp_path):
        result = _run_tool("data_injector", [
            "--slug", "no-such-slug", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 1, result.stdout + result.stderr


# ──────────────────────────────────────────────
# T7 编码健壮性（隐患）
# ──────────────────────────────────────────────


class TestEncodingRobustness:
    """read_text_utf8 必须兼容 UTF-8 / UTF-8-BOM / GB18030 三态。"""

    TEXT = "特蕾西娅在罗德岛说过：我们别无选择。"
    ENCODINGS = ["utf-8", "utf-8-sig", "gb18030"]

    @pytest.mark.parametrize("encoding", ENCODINGS)
    def test_read_text_utf8_handles_encoding(self, tmp_path, encoding):
        path = tmp_path / f"sample-{encoding}.txt"
        path.write_bytes(self.TEXT.encode(encoding))
        assert read_text_utf8(path) == self.TEXT

    def test_bom_json_does_not_raise(self, tmp_path):
        """BOM 文件走 JSON 读取路径不得抛 UnicodeDecodeError / BOM 解析错误"""
        path = tmp_path / "bom.json"
        payload = "\ufeff" + json.dumps({"角色": "W", "n": 1}, ensure_ascii=False)
        path.write_bytes(payload.encode("utf-8"))

        loaded = load_json_safe(path)
        assert loaded == {"角色": "W", "n": 1}
        # 直接 json.loads(read_text_utf8(...)) 也必须可用（BOM 已剥离）
        assert json.loads(read_text_utf8(path))["n"] == 1

    def test_gb18030_json_is_readable(self, tmp_path):
        """GB18030 编码的 JSON 也必须能读出来（老版本 Windows 保存的文件）"""
        path = tmp_path / "gbk.json"
        path.write_bytes(json.dumps({"角色": "W"}, ensure_ascii=False).encode("gb18030"))
        assert load_json_safe(path) == {"角色": "W"}


# ──────────────────────────────────────────────
# T8 确定性（本轮修复）
# ──────────────────────────────────────────────


class TestDeterminism:
    """列表顺序不得随 PYTHONHASHSEED 变化。"""

    @staticmethod
    def _slice(line_count, avg_len, ellipsis_pct, negation_pct, acts):
        return {
            "line_count": line_count,
            "avg_sentence_length": avg_len,
            "ellipsis_pct": ellipsis_pct,
            "negation_pct": negation_pct,
            "speech_act_distribution": acts,
        }

    EXPECTED_METRICS = [
        "avg_sentence_length",
        "ellipsis_pct",
        "negation_pct",
        "speech_act:assert",
        "speech_act:command",
    ]

    def test_compare_metrics_metric_order_is_ascending(self):
        """compare_metrics 的 metric 序列必须严格升序（含话语行为项）"""
        baseline = self._slice(20, 20.0, 10.0, 10.0, {"assert": 10, "command": 0})
        comparison = self._slice(20, 12.0, 20.0, 20.0, {"assert": 2, "command": 8})

        diffs = temporal_slicer.compare_metrics(baseline, comparison)
        metrics = [d["metric"] for d in diffs]

        assert metrics == self.EXPECTED_METRICS, f"实际顺序: {metrics}"
        assert metrics == sorted(metrics)

    def test_compare_metrics_order_independent_of_input_key_order(self):
        """交换 speech_act_distribution 的插入顺序，输出顺序不得变化"""
        acts_a = {"assert": 10, "command": 0, "question": 5}
        acts_b = {"question": 5, "command": 0, "assert": 10}
        baseline = self._slice(20, 20.0, 10.0, 10.0, acts_a)
        comparison = self._slice(20, 12.0, 20.0, 20.0, {"assert": 2, "command": 8, "question": 5})

        first = [d["metric"] for d in temporal_slicer.compare_metrics(baseline, comparison)]
        second = [d["metric"] for d in temporal_slicer.compare_metrics(
            self._slice(20, 20.0, 10.0, 10.0, acts_b), comparison)]
        assert first == second

    def test_compare_metrics_order_is_stable_across_processes(self):
        """跨 PYTHONHASHSEED 的话语行为项顺序必须一致（set 迭代顺序的正面检出点）

        只断言「等于 sorted」在单进程里不够：两个键的 set 迭代顺序可能恰好
        是字典序。四类行为 + 跨进程对比才能稳定暴露「取消 sorted」的回归。
        """
        baseline = {"line_count": 60, "avg_sentence_length": 20.0, "ellipsis_pct": 10.0,
                    "negation_pct": 10.0,
                    "speech_act_distribution": {"assert": 40, "command": 10,
                                                "question": 10, "threat": 0}}
        comparison = {"line_count": 60, "avg_sentence_length": 12.0, "ellipsis_pct": 20.0,
                      "negation_pct": 20.0,
                      "speech_act_distribution": {"assert": 0, "command": 20,
                                                  "question": 20, "threat": 20}}
        expected = [
            "avg_sentence_length",
            "ellipsis_pct",
            "negation_pct",
            "speech_act:assert",
            "speech_act:command",
            "speech_act:question",
            "speech_act:threat",
        ]
        assert [d["metric"] for d in temporal_slicer.compare_metrics(baseline, comparison)] == expected

        code = f"""
import json, sys
sys.path.insert(0, {str(TOOLS_DIR)!r})
import temporal_slicer
diffs = temporal_slicer.compare_metrics({baseline!r}, {comparison!r})
sys.stdout.write(json.dumps([d["metric"] for d in diffs], ensure_ascii=False))
"""
        orders = {_run_py(code, seed) for seed in ("0", "1")}
        assert len(orders) == 1, f"metric 顺序随 PYTHONHASHSEED 变化: {orders}"
        assert json.loads(orders.pop()) == expected

    def test_extract_entities_is_stable_in_process(self):
        text = "Dagda、伊内丝、迷迭香、Indra、阿米娅、伊芙利特"
        first = relationship_graph.extract_entities(text)
        assert len(first) == 6
        for _ in range(5):
            assert relationship_graph.extract_entities(text) == first

    def test_extract_entities_is_stable_across_processes(self):
        """跨 PYTHONHASHSEED 的实体顺序必须一致（set 迭代顺序缺陷的正面检出点）"""
        text = "Dagda、伊内丝、迷迭香、Indra、阿米娅、伊芙利特"
        code = (
            f"import sys, json; sys.path.insert(0, {str(TOOLS_DIR)!r}); "
            "import relationship_graph; "
            f"sys.stdout.write(json.dumps(relationship_graph.extract_entities({text!r}), "
            "ensure_ascii=False))"
        )
        orders = {_run_py(code, seed) for seed in ("0", "1")}
        assert len(orders) == 1, f"实体顺序随 PYTHONHASHSEED 变化: {orders}"

        # 与主进程结果一致
        in_process = json.dumps(relationship_graph.extract_entities(text), ensure_ascii=False)
        assert orders == {in_process}

    def test_extract_entities_pure_chinese_names_are_sorted(self):
        """纯中文名（无别名命中）时必须按字典序输出"""
        text = "凯尔希、阿米娅、特蕾西娅、博士"
        found = relationship_graph.extract_entities(text)
        assert found == ["凯尔希", "博士", "特蕾西娅", "阿米娅"]
        assert found == sorted(found)


# ──────────────────────────────────────────────
# T9 / T10 端到端（旧名 story.json + --resume 语义）
# ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def w_pipeline_dir(tmp_path_factory):
    """把 operators/w 复制到临时目录（只保留旧名 story.json），跑 annotate + analyze。"""
    source_dir = PROJECT_ROOT / "operators" / "w"
    needed = ["operator_data.json", "knowledge.md", "persona.md", "story.json"]
    missing = [name for name in needed if not (source_dir / name).exists()]
    if missing:
        pytest.skip(f"缺少端到端源数据: {missing}")

    work = tmp_path_factory.mktemp("e2e-w") / "w"
    work.mkdir(parents=True, exist_ok=True)
    for name in needed:
        shutil.copy2(source_dir / name, work / name)

    # 契约：临时目录里只有旧名，没有新名
    assert (work / "story.json").exists()
    assert not (work / "story_data.json").exists()

    common = ["--name", "W", "--slug", "w", "--output-dir", str(work)]
    annotate = _run_tool("pipeline", common + ["--step", "annotate"])
    analyze = _run_tool("pipeline", common + ["--step", "analyze"])
    return {
        "dir": work,
        "annotate": annotate,
        "analyze": analyze,
        "common": common,
    }


class TestEndToEndSmoke:
    """真实工具链冒烟：旧名 story.json → context.json → 4 个分析产物。"""

    def test_annotate_succeeds_with_legacy_story_warning(self, w_pipeline_dir):
        result = w_pipeline_dir["annotate"]
        assert result.returncode == 0, result.stdout + result.stderr
        assert "使用旧文件名 story.json" in result.stderr

    def test_context_includes_story_lines(self, w_pipeline_dir):
        context = load_json_safe(w_pipeline_dir["dir"] / ARTIFACT.CONTEXT)
        assert context is not None
        distribution = context["stats"]["source_distribution"]

        # 断言「剧情行确实进了 context」，而不是钉死样例里的具体条数：
        # 样例语料是可裁剪的（仓库内仅保留摘录），但 story 计数必须与
        # story.json 自己声明的目标行数严格一致，否则就是 P0-2 回归。
        story = load_json_safe(w_pipeline_dir["dir"] / "story.json")
        expected_story = story["total_target_lines"]
        assert distribution["story"] == expected_story, (
            f"剧情行未进入 context.json: 期望 {expected_story}, 实得 {distribution}"
        )
        assert distribution["voice"] == 38
        assert distribution["archive"] == 8

    def test_analyze_produces_four_non_empty_artifacts(self, w_pipeline_dir):
        result = w_pipeline_dir["analyze"]
        assert result.returncode == 0, result.stdout + result.stderr

        output_dir = w_pipeline_dir["dir"]
        sizes = {}
        for artifact_name in STEP_ARTIFACTS["analyze"]:
            path = output_dir / artifact_name
            assert path.exists(), f"缺失分析产物: {artifact_name}"
            sizes[artifact_name] = path.stat().st_size
            assert sizes[artifact_name] > 0, f"分析产物为空: {artifact_name}"
            # 必须是可以被下游解析的 JSON
            assert isinstance(load_json_safe(path), dict), f"{artifact_name} 不是 JSON 对象"
        assert set(sizes) == {
            "fingerprint.json",
            "speech_act_profile.json",
            "temporal_slices.json",
            "relationship_graph.json",
        }

    def test_resume_does_not_misjudge_analyze(self, w_pipeline_dir, monkeypatch, tmp_path):
        """缺 1 个分析产物时 --resume 必须重跑 analyze、跳过 annotate（P1-2）

        这里替换各步骤实现为「记录调用」，让 run_full 的真实 resume 判定
        （_step_completed + STEP_ARTIFACTS）跑在真实产物目录上，避免再起 4 个
        子进程（全链路 subprocess 版本见 04-qa-report.md 的独立验证记录）。
        """
        work = tmp_path / "resume-w"
        shutil.copytree(w_pipeline_dir["dir"], work)
        removed = work / ARTIFACT.RELATIONS
        removed.unlink()

        executed: list[str] = []

        def _record(name):
            def _step(self):
                executed.append(name)
                return True
            return _step

        for step_name in ("fetch", "annotate", "analyze", "validate", "write"):
            monkeypatch.setattr(pipeline.PipelineRunner, f"step_{step_name}", _record(step_name))

        cfg = pipeline.PipelineConfig(
            name="W", slug="w", output_dir=str(work),
            mode=pipeline.MODE_FUNCTION, skip_fetch=True, resume=True,
        )
        assert pipeline.PipelineRunner(cfg).run_full() is True

        assert "annotate" not in executed, "annotate 产物齐备，--resume 却重跑了"
        assert "analyze" in executed, "analyze 缺产物却被判为已完成（P1-2 回归）"
        assert executed == ["analyze", "validate", "write"]


class TestResumeUnit:
    """_step_completed 的判据必须精确到 4 个产物。"""

    def test_analyze_not_completed_with_only_context(self, tmp_path):
        (tmp_path / ARTIFACT.CONTEXT).write_text('{"annotated_lines": []}', encoding="utf-8")
        assert pipeline._step_completed(str(tmp_path), "analyze") is False

    def test_analyze_completed_when_all_four_exist(self, tmp_path):
        for name in STEP_ARTIFACTS["analyze"]:
            (tmp_path / name).write_text('{"ok": true}', encoding="utf-8")
        assert pipeline._step_completed(str(tmp_path), "analyze") is True

    def test_analyze_incomplete_when_one_artifact_empty(self, tmp_path):
        for name in STEP_ARTIFACTS["analyze"]:
            (tmp_path / name).write_text('{"ok": true}', encoding="utf-8")
        (tmp_path / ARTIFACT.TEMPORAL).write_text("", encoding="utf-8")
        assert pipeline._step_completed(str(tmp_path), "analyze") is False

    def test_validate_step_never_skipped(self, tmp_path):
        assert pipeline._step_completed(str(tmp_path), "validate") is False
        assert artifacts.STEP_ARTIFACTS["validate"] == []
