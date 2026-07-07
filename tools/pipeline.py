#!/usr/bin/env python3
"""
蒸馏流水线编排器 —— 一键执行全流程角色蒸馏

将原本需要手动依次执行的 11 个工具串联为自动化流水线。

支持两种执行模式：
  - subprocess 模式（默认）：每个工具在独立进程中运行，隔离性好
  - function 模式：直接调用 Python 函数，共享进程，便于单元测试和调试

用法：
    # 一键蒸馏（从 PRTS 数据到最终 Skill 文件）
    python3 pipeline.py --name 特蕾西娅 --full

    # 分步执行
    python3 pipeline.py --name 特蕾西娅 --step fetch    # 仅获取 PRTS 数据
    python3 pipeline.py --name 特蕾西娅 --step analyze  # 仅分析
    python3 pipeline.py --name 特蕾西娅 --step write    # 仅写入 Skill

    # 使用函数调用模式（同进程，便于调试和测试）
    python3 pipeline.py --name 特蕾西娅 --full --mode function

    # 指定输出目录
    python3 pipeline.py --name 特蕾西娅 --full --output-dir ./my_operators

    # 跳过 PRTS 请求（使用已有数据）
    python3 pipeline.py --name 特蕾西娅 --full --skip-fetch

步骤说明：
    1. fetch:    game_data_parser → story_extractor → 获取原始数据
    2. annotate: context_annotator → 语境化标注
    3. analyze:  phase_inferrer → speech_act_analyzer → dialogue_fingerprint
                → relationship_graph → temporal_slicer → canon_checker
                → persona_validator
    4. write:    skill_writer → 生成最终 Skill 文件

编程接口：
    from pipeline import PipelineRunner, PipelineConfig

    config = PipelineConfig(name="特蕾西娅", mode="function")
    runner = PipelineRunner(config)
    runner.run_full()
"""

import argparse
import importlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from shared_utils import setup_logging, validate_slug

logger = setup_logging("pipeline")

# 工具目录
TOOLS_DIR = Path(__file__).parent

# 执行模式常量
MODE_SUBPROCESS = "subprocess"
MODE_FUNCTION = "function"


# ──────────────────────────────────────────────
# 执行模式：subprocess（原有逻辑）
# ──────────────────────────────────────────────


def run_tool_subprocess(tool_name: str, args: list[str], description: str = "") -> bool:
    """以子进程方式运行一个工具脚本

    Args:
        tool_name: 工具脚本名（不含 .py）
        args: 命令行参数列表
        description: 步骤描述

    Returns:
        是否成功
    """
    if description:
        logger.info("=" * 60)
        logger.info("步骤: %s", description)
        logger.info("=" * 60)

    cmd = [sys.executable, str(TOOLS_DIR / f"{tool_name}.py")] + args
    logger.info("执行: %s", " ".join(cmd))

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)

    elapsed = time.time() - start

    if result.returncode != 0:
        logger.error("失败 (%.1fs): %s", elapsed, tool_name)
        if result.stderr:
            logger.error("stderr:\n%s", result.stderr[:500])
        return False

    logger.info("完成 (%.1fs): %s", elapsed, tool_name)
    if result.stdout:
        # 只打印前 200 字符
        preview = result.stdout[:200].replace("\n", " ")
        logger.info("输出: %s...", preview)
    return True


# ──────────────────────────────────────────────
# 执行模式：function（新增）
# ──────────────────────────────────────────────


def run_tool_function(tool_name: str, args: list[str], description: str = "") -> bool:
    """以函数调用方式运行一个工具（同进程内执行）

    通过临时替换 sys.argv 来复用各工具的 main() 入口函数，
    避免为每个工具单独封装函数接口。

    Args:
        tool_name: 工具脚本名（不含 .py）
        args: 命令行参数列表
        description: 步骤描述

    Returns:
        是否成功
    """
    if description:
        logger.info("=" * 60)
        logger.info("步骤: %s", description)
        logger.info("=" * 60)

    logger.info("调用: %s.main(%s)", tool_name, " ".join(args))

    start = time.time()
    try:
        module = importlib.import_module(tool_name)
        if not hasattr(module, "main"):
            logger.error("模块 %s 没有 main() 函数", tool_name)
            return False

        # 临时替换 sys.argv 以复用 CLI 入口
        old_argv = sys.argv
        sys.argv = [tool_name] + args
        try:
            module.main()
        finally:
            sys.argv = old_argv

        elapsed = time.time() - start
        logger.info("完成 (%.1fs): %s (function mode)", elapsed, tool_name)
        return True

    except SystemExit as e:
        elapsed = time.time() - start
        # argparse 在 --help 或参数错误时调用 sys.exit()
        # exit code 0 表示正常结束（如 --help），非 0 表示错误
        if e.code == 0:
            logger.info("完成 (%.1fs): %s (function mode, exit 0)", elapsed, tool_name)
            return True
        logger.error("失败 (%.1fs): %s (exit code %s)", elapsed, tool_name, e.code)
        return False

    except Exception as e:
        elapsed = time.time() - start
        logger.error("失败 (%.1fs): %s — %s: %s", elapsed, tool_name, type(e).__name__, e)
        return False


# ──────────────────────────────────────────────
# 统一调度接口
# ──────────────────────────────────────────────


# 当前执行模式（全局状态，供 step_* 函数使用）
_current_mode: str = MODE_SUBPROCESS


def run_tool(tool_name: str, args: list[str], description: str = "") -> bool:
    """运行一个工具脚本（根据当前模式选择执行方式）

    Args:
        tool_name: 工具脚本名（不含 .py）
        args: 命令行参数列表
        description: 步骤描述

    Returns:
        是否成功
    """
    if _current_mode == MODE_FUNCTION:
        return run_tool_function(tool_name, args, description)
    return run_tool_subprocess(tool_name, args, description)


# ──────────────────────────────────────────────
# 管线配置
# ──────────────────────────────────────────────


@dataclass
class PipelineConfig:
    """管线运行配置"""

    name: str                          # 角色中文名
    slug: str = ""                     # 角色 slug（留空则自动生成）
    output_dir: str = ""               # 输出目录（留空则默认 operators/<slug>）
    mode: str = MODE_SUBPROCESS        # 执行模式: subprocess / function
    skip_fetch: bool = False           # 跳过 PRTS 数据获取
    chapters: list[str] = field(default_factory=list)  # 手动指定的章节
    discover: str | None = None     # 自动发现的页面前缀
    resume: bool = False               # 断点续传
    dry_run: bool = False              # 仅打印计划

    def __post_init__(self) -> None:
        if not self.slug:
            try:
                from game_data_parser import to_slug
                self.slug = to_slug(self.name)
            except (ImportError, Exception):
                self.slug = self.name.lower().replace(" ", "-")

        validate_slug(self.slug)

        if not self.output_dir:
            self.output_dir = str(Path("operators") / self.slug)


# ──────────────────────────────────────────────
# 管线运行器
# ──────────────────────────────────────────────


# 每个步骤的中间产物文件（用于 --resume 检测）
_STEP_ARTIFACTS: dict[str, list[str]] = {
    "fetch": ["operator_data.json"],
    "annotate": ["context.json"],
    "analyze": ["context.json"],  # analyze 会回写 context.json（添加 speech_acts 等字段）
    "validate": [],  # validate 输出到 stdout，无特定文件产物
    "write": ["meta.json"],  # skill_writer --action create 生成 meta.json
}


def _step_completed(output_dir: str, step_name: str) -> bool:
    """检查步骤的中间产物是否已存在（用于 --resume）"""
    artifacts = _STEP_ARTIFACTS.get(step_name, [])
    if not artifacts:
        return False
    return all(
        (Path(output_dir) / f).exists() and (Path(output_dir) / f).stat().st_size > 0
        for f in artifacts
    )


class PipelineRunner:
    """管线运行器 —— 管理蒸馏管线的执行流程

    用法:
        config = PipelineConfig(name="特蕾西娅", mode="function")
        runner = PipelineRunner(config)
        success = runner.run_step("fetch")
        success = runner.run_full()
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._set_mode(config.mode)

    def _set_mode(self, mode: str) -> None:
        """设置全局执行模式"""
        global _current_mode
        if mode not in (MODE_SUBPROCESS, MODE_FUNCTION):
            raise ValueError(f"不支持的执行模式: {mode}，可选: {MODE_SUBPROCESS}, {MODE_FUNCTION}")
        _current_mode = mode

    def run_step(self, step_name: str) -> bool:
        """执行指定步骤

        Args:
            step_name: 步骤名 (fetch / annotate / analyze / validate / write)

        Returns:
            是否成功
        """
        step_map = {
            "fetch": self.step_fetch,
            "annotate": self.step_annotate,
            "analyze": self.step_analyze,
            "validate": self.step_validate,
            "write": self.step_write,
        }
        fn = step_map.get(step_name)
        if fn is None:
            logger.error("未知步骤: %s", step_name)
            return False
        return fn()

    def run_full(self) -> bool:
        """执行完整管线

        Returns:
            是否全部成功
        """
        cfg = self.config

        logger.info("蒸馏流水线启动")
        logger.info("  角色: %s", cfg.name)
        logger.info("  slug: %s", cfg.slug)
        logger.info("  输出: %s", cfg.output_dir)
        logger.info("  模式: %s", cfg.mode)
        if cfg.strict:
            logger.info("  严格模式: 已启用（降级情况将视为失败）")

        if cfg.dry_run:
            logger.info("（dry-run 模式，不执行实际操作）")
            return True

        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)

        step_order = ["fetch", "annotate", "analyze", "validate", "write"]
        for step_name in step_order:
            if cfg.resume and _step_completed(cfg.output_dir, step_name):
                logger.info("跳过已完成的步骤: %s（--resume）", step_name)
                continue
            if not self.run_step(step_name):
                logger.error("流水线在 '%s' 步骤失败", step_name)
                return False

        logger.info("流水线完成！输出目录: %s", cfg.output_dir)
        return True

    # ──────────────────────────────────────────────
    # 各步骤实现
    # ──────────────────────────────────────────────

    def step_fetch(self) -> bool:
        """步骤 1: 获取原始数据"""
        cfg = self.config
        if cfg.skip_fetch:
            logger.info("跳过 fetch 步骤（--skip-fetch）")
            return True

        operator_json = str(Path(cfg.output_dir) / "operator_data.json")

        # 1a. 从 PRTS 获取角色数据
        if not run_tool(
            "game_data_parser",
            ["--source", "prts", "--name", cfg.name, "--output", operator_json],
            f"获取 {cfg.name} 的 PRTS 数据",
        ):
            return False

        # 1b. 提取剧情对话
        story_json = str(Path(cfg.output_dir) / "story_data.json")
        story_args = ["--character", cfg.name, "--output", story_json]

        if cfg.discover:
            story_args.extend(["--discover", cfg.discover])
            logger.info("使用自动发现模式，前缀: %s", cfg.discover)
        elif cfg.chapters:
            for ch in cfg.chapters:
                story_args.extend(["--chapter", ch])
        else:
            logger.info("未指定章节或发现前缀，跳过剧情提取")
            logger.info("提示: python3 story_extractor.py --discover DM --character %s", cfg.name)
            return True

        if not run_tool("story_extractor", story_args, f"提取 {cfg.name} 的剧情对话"):
            if cfg.strict:
                logger.error("剧情提取失败（--strict 模式：视为失败）")
                return False
            logger.warning("剧情提取失败，但不阻断流程")

        return True

    def step_annotate(self) -> bool:
        """步骤 2: 语境化标注

        注意: context_annotator 需要 --knowledge-md（由 AI Agent 根据 knowledge_analyzer prompt 生成），
        在全自动 pipeline 中此文件可能不存在。如果不存在，跳过此步骤并提示用户手动生成。
        """
        cfg = self.config
        operator_json = str(Path(cfg.output_dir) / "operator_data.json")
        knowledge_md = str(Path(cfg.output_dir) / "knowledge.md")
        context_json = str(Path(cfg.output_dir) / "context.json")

        if not Path(operator_json).exists():
            logger.warning("operator_data.json 不存在，跳过语境标注")
            return True

        if not Path(knowledge_md).exists():
            msg = (
                "knowledge.md 不存在，跳过语境标注。"
                "请先使用 AI Agent 根据 prompts/knowledge_builder.md 生成 knowledge.md"
            )
            if cfg.strict:
                logger.error(msg + "（--strict 模式：视为失败）")
                return False
            logger.warning(msg)
            return True

        args = [
            "--operator-json", operator_json,
            "--knowledge-md", knowledge_md,
            "--output", context_json,
        ]

        # 添加 story JSON（如果存在）
        story_json = Path(cfg.output_dir) / "story.json"
        if story_json.exists():
            args.extend(["--story-json", str(story_json)])

        return run_tool("context_annotator", args, f"语境化标注: {cfg.name}")

    def step_analyze(self) -> bool:
        """步骤 3: 分析"""
        cfg = self.config
        context_json = str(Path(cfg.output_dir) / "context.json")

        if not Path(context_json).exists():
            msg = "context.json 不存在，跳过分析步骤"
            if cfg.strict:
                logger.error(msg + "（--strict 模式：视为失败）")
                return False
            logger.warning(msg)
            return True

        tools = [
            ("speech_act_analyzer", ["--context-json", context_json], "话语行为分析"),
            ("dialogue_fingerprint", ["--context-json", context_json], "语言指纹分析"),
            ("relationship_graph", ["--context-json", context_json], "关系图谱构建"),
            ("temporal_slicer", ["--context-json", context_json], "时序切片分析"),
        ]

        failed_tools = []
        for tool_name, args, desc in tools:
            if not run_tool(tool_name, args, desc):
                logger.warning("%s 失败，继续执行后续步骤", desc)
                failed_tools.append(tool_name)

        if failed_tools and cfg.strict:
            logger.error("以下分析工具失败（--strict 模式：视为失败）: %s", failed_tools)
            return False

        return True

    def step_validate(self) -> bool:
        """步骤 3b: 验证"""
        cfg = self.config
        persona_md = str(Path(cfg.output_dir) / "persona.md")
        knowledge_md = str(Path(cfg.output_dir) / "knowledge.md")
        context_json = str(Path(cfg.output_dir) / "context.json")

        # canon_checker: 使用 --sources 交叉验证 knowledge.md 和 persona.md
        sources = [p for p in [knowledge_md, persona_md] if Path(p).exists()]
        if sources:
            run_tool(
                "canon_checker",
                ["--sources"] + sources,
                "设定一致性校验",
            )

        # persona_validator: 使用 --persona + --context-json
        if Path(persona_md).exists() and Path(context_json).exists():
            run_tool(
                "persona_validator",
                ["--persona", persona_md, "--context-json", context_json],
                "Persona 一致性验证",
            )

        return True

    def step_write(self) -> bool:
        """步骤 4: 写入 Skill 文件

        注意: skill_writer 的 --action create 会创建默认模板文件。
        实际的 knowledge.md 和 persona.md 内容由 AI Agent 根据 Prompt 生成，
        此步骤仅确保目录结构和 meta.json 存在。
        """
        cfg = self.config
        return run_tool(
            "skill_writer",
            [
                "--action", "create",
                "--slug", cfg.slug,
                "--name", cfg.name,
                "--base-dir", str(Path(cfg.output_dir).parent),
            ],
            f"写入 Skill 文件: {cfg.slug}",
        )


# ──────────────────────────────────────────────
# 兼容旧版 step_* 函数接口（供外部代码直接调用）
# ──────────────────────────────────────────────


def step_fetch(
    name: str,
    output_dir: str,
    skip_fetch: bool = False,
    chapters: list[str] | None = None,
    discover: str | None = None,
    discover_prefix: str | None = None,
) -> bool:
    """步骤 1: 获取原始数据（兼容旧版接口）

    Args:
        name: 角色名
        output_dir: 输出目录
        skip_fetch: 跳过 fetch
        chapters: 手动指定的章节列表
        discover: 自动发现的页面前缀
        discover_prefix: discover 的别名（向后兼容）
    """
    cfg = PipelineConfig(
        name=name,
        output_dir=output_dir,
        skip_fetch=skip_fetch,
        chapters=chapters or [],
        discover=discover or discover_prefix,
    )
    # 跳过 slug 验证（兼容旧版调用，output_dir 已指定）
    runner = PipelineRunner(cfg)
    return runner.step_fetch()


def step_annotate(name: str, output_dir: str, slug: str) -> bool:
    """步骤 2: 语境化标注（兼容旧版接口）"""
    cfg = PipelineConfig(name=name, slug=slug, output_dir=output_dir)
    runner = PipelineRunner(cfg)
    return runner.step_annotate()


def step_analyze(name: str, output_dir: str) -> bool:
    """步骤 3: 分析（兼容旧版接口）"""
    cfg = PipelineConfig(name="", output_dir=output_dir)
    runner = PipelineRunner(cfg)
    return runner.step_analyze()


def step_validate(name: str, output_dir: str) -> bool:
    """步骤 3b: 验证（兼容旧版接口）"""
    cfg = PipelineConfig(name="", output_dir=output_dir)
    runner = PipelineRunner(cfg)
    return runner.step_validate()


def step_write(name: str, output_dir: str, slug: str) -> bool:
    """步骤 4: 写入 Skill 文件（兼容旧版接口）"""
    cfg = PipelineConfig(name=name, slug=slug, output_dir=output_dir)
    runner = PipelineRunner(cfg)
    return runner.step_write()


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="明日方舟角色蒸馏流水线 —— 一键从 PRTS 数据生成 AI Skill",
    )
    parser.add_argument("--name", required=True, help="角色中文名（如 特蕾西娅）")
    parser.add_argument("--slug", help="角色 slug（自动从名称生成）")
    parser.add_argument(
        "--step",
        choices=["fetch", "annotate", "analyze", "validate", "write", "full"],
        default="full",
        help="执行步骤（默认 full）",
    )
    parser.add_argument("--output-dir", help="输出目录（默认 operators/<slug>）")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过 PRTS 数据获取")
    parser.add_argument(
        "--mode",
        choices=[MODE_SUBPROCESS, MODE_FUNCTION],
        default=MODE_SUBPROCESS,
        help="执行模式：subprocess（独立进程，默认）或 function（同进程，便于调试）",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="断点续传：检测已有中间产物，跳过已完成的步骤",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")
    parser.add_argument(
        "--strict", action="store_true",
        help="严格模式：将原本只 warning 的降级情况（如剧情提取失败、knowledge.md 缺失、"
             "分析工具失败）视为失败，用于 CI 和自动化场景暴露隐藏问题",
    )
    parser.add_argument(
        "--discover",
        help="自动发现剧情页面的前缀（如 DM、BB、SV），自动搜索所有匹配页面",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        dest="chapters",
        help="手动指定剧情章节名（可多次使用，如 --chapter 'DM-1 埋藏' --chapter 'DM-2 遗愿'）",
    )

    args = parser.parse_args()

    try:
        cfg = PipelineConfig(
            name=args.name,
            slug=args.slug or "",
            output_dir=args.output_dir or "",
            mode=args.mode,
            skip_fetch=args.skip_fetch,
            chapters=args.chapters or [],
            discover=args.discover,
            resume=args.resume,
            dry_run=args.dry_run,
            strict=args.strict,
        )
    except ValueError as e:
        logger.error("配置验证失败: %s", e)
        sys.exit(1)

    runner = PipelineRunner(cfg)

    success = runner.run_full() if args.step == "full" else runner.run_step(args.step)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
