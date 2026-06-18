#!/usr/bin/env python3
"""
蒸馏流水线编排器 —— 一键执行全流程角色蒸馏

将原本需要手动依次执行的 11 个工具串联为自动化流水线。

用法：
    # 一键蒸馏（从 PRTS 数据到最终 Skill 文件）
    python3 pipeline.py --name 特蕾西娅 --full

    # 分步执行
    python3 pipeline.py --name 特蕾西娅 --step fetch    # 仅获取 PRTS 数据
    python3 pipeline.py --name 特蕾西娅 --step analyze  # 仅分析
    python3 pipeline.py --name 特蕾西娅 --step write    # 仅写入 Skill

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
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from constants import SLUG_RE
from shared_utils import setup_logging, validate_slug

logger = setup_logging("pipeline")

# 工具目录
TOOLS_DIR = Path(__file__).parent


def run_tool(tool_name: str, args: list[str], description: str = "") -> bool:
    """运行一个工具脚本

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


def step_fetch(name: str, output_dir: str, skip_fetch: bool = False) -> bool:
    """步骤 1: 获取原始数据"""
    if skip_fetch:
        logger.info("跳过 fetch 步骤（--skip-fetch）")
        return True

    operator_json = str(Path(output_dir) / "operator_data.json")

    # 1a. 从 PRTS 获取角色数据
    if not run_tool(
        "game_data_parser",
        ["--source", "prts", "--name", name, "--output", operator_json],
        f"获取 {name} 的 PRTS 数据",
    ):
        return False

    # 1b. 提取剧情对话（尝试常见章节）
    # 这里需要根据角色手动指定章节，暂时跳过自动提取
    logger.info("剧情提取需要手动指定章节，跳过自动提取")
    logger.info("提示: python3 story_extractor.py --chapter 'BB-ST-3/NBT' --character %s", name)

    return True


def step_annotate(name: str, output_dir: str, slug: str) -> bool:
    """步骤 2: 语境化标注"""
    operator_json = str(Path(output_dir) / "operator_data.json")
    knowledge_md = str(Path(output_dir) / "knowledge.md")
    context_json = str(Path(output_dir) / "context.json")

    if not Path(operator_json).exists():
        logger.warning("operator_data.json 不存在，跳过语境标注")
        return True

    args = [
        "--operator-json", operator_json,
        "--output", context_json,
    ]

    if Path(knowledge_md).exists():
        args.extend(["--knowledge-md", knowledge_md])

    return run_tool("context_annotator", args, f"语境化标注: {name}")


def step_analyze(name: str, output_dir: str) -> bool:
    """步骤 3: 分析"""
    context_json = str(Path(output_dir) / "context.json")

    if not Path(context_json).exists():
        logger.warning("context.json 不存在，跳过分析步骤")
        return True

    tools = [
        ("speech_act_analyzer.py", ["--context-json", context_json], "话语行为分析"),
        ("dialogue_fingerprint.py", ["--context-json", context_json], "语言指纹分析"),
        ("relationship_graph.py", ["--context-json", context_json], "关系图谱构建"),
        ("temporal_slicer.py", ["--context-json", context_json], "时序切片分析"),
    ]

    for tool_file, args, desc in tools:
        tool_name = tool_file.replace(".py", "")
        if not run_tool(tool_name, args, desc):
            logger.warning("%s 失败，继续执行后续步骤", desc)

    return True


def step_validate(name: str, output_dir: str) -> bool:
    """步骤 3b: 验证"""
    persona_md = str(Path(output_dir) / "persona.md")
    context_json = str(Path(output_dir) / "context.json")

    # canon_checker
    if Path(persona_md).exists():
        run_tool("canon_checker", ["--persona", persona_md], "设定一致性校验")

    # persona_validator
    if Path(persona_md).exists() and Path(context_json).exists():
        run_tool(
            "persona_validator",
            ["--persona", persona_md, "--context-json", context_json],
            "Persona 一致性验证",
        )

    return True


def step_write(name: str, output_dir: str, slug: str) -> bool:
    """步骤 4: 写入 Skill 文件"""
    return run_tool(
        "skill_writer",
        ["--slug", slug, "--name", name, "--base-dir", str(Path(output_dir).parent)],
        f"写入 Skill 文件: {slug}",
    )


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
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")

    args = parser.parse_args()

    # 生成 slug
    slug = args.slug
    if not slug:
        try:
            from game_data_parser import to_slug
            slug = to_slug(args.name)
        except ImportError:
            slug = args.name.lower().replace(" ", "-")

    try:
        validate_slug(slug)
    except ValueError as e:
        logger.error("slug 验证失败: %s", e)
        sys.exit(1)

    # 确定输出目录
    output_dir = args.output_dir or str(Path("operators") / slug)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    logger.info("蒸馏流水线启动")
    logger.info("  角色: %s", args.name)
    logger.info("  slug: %s", slug)
    logger.info("  输出: %s", output_dir)
    logger.info("  步骤: %s", args.step)

    if args.dry_run:
        logger.info("（dry-run 模式，不执行实际操作）")
        return

    steps = {
        "fetch": lambda: step_fetch(args.name, output_dir, args.skip_fetch),
        "annotate": lambda: step_annotate(args.name, output_dir, slug),
        "analyze": lambda: step_analyze(args.name, output_dir),
        "validate": lambda: step_validate(args.name, output_dir),
        "write": lambda: step_write(args.name, output_dir, slug),
    }

    step_order = ["fetch", "annotate", "analyze", "validate", "write"]

    if args.step == "full":
        for step_name in step_order:
            if not steps[step_name]():
                logger.error("流水线在 '%s' 步骤失败", step_name)
                sys.exit(1)
    else:
        if not steps[args.step]():
            logger.error("步骤 '%s' 失败", args.step)
            sys.exit(1)

    logger.info("流水线完成！输出目录: %s", output_dir)


if __name__ == "__main__":
    main()
