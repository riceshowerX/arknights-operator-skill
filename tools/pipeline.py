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


def step_fetch(name: str, output_dir: str, skip_fetch: bool = False,
               chapters: list[str] | None = None, discover: str | None = None) -> bool:
    """步骤 1: 获取原始数据

    Args:
        name: 角色名
        output_dir: 输出目录
        skip_fetch: 跳过 fetch
        chapters: 手动指定的章节列表
        discover: 自动发现的页面前缀（如 "DM"、"BB"）
    """
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

    # 1b. 提取剧情对话
    story_json = str(Path(output_dir) / "story_data.json")
    story_args = ["--character", name, "--output", story_json]

    if discover:
        # 自动发现模式：根据前缀搜索所有剧情页面
        story_args.extend(["--discover", discover])
        logger.info("使用自动发现模式，前缀: %s", discover)
    elif chapters:
        # 手动指定章节
        for ch in chapters:
            story_args.extend(["--chapter", ch])
    else:
        logger.info("未指定章节或发现前缀，跳过剧情提取")
        logger.info("提示: python3 story_extractor.py --discover DM --character %s", name)
        return True

    if not run_tool("story_extractor", story_args, f"提取 {name} 的剧情对话"):
        logger.warning("剧情提取失败，但不阻断流程")

    return True


def step_annotate(name: str, output_dir: str, slug: str) -> bool:
    """步骤 2: 语境化标注

    注意: context_annotator 需要 --knowledge-md（由 AI Agent 根据 knowledge_analyzer prompt 生成），
    在全自动 pipeline 中此文件可能不存在。如果不存在，跳过此步骤并提示用户手动生成。
    """
    operator_json = str(Path(output_dir) / "operator_data.json")
    knowledge_md = str(Path(output_dir) / "knowledge.md")
    context_json = str(Path(output_dir) / "context.json")

    if not Path(operator_json).exists():
        logger.warning("operator_data.json 不存在，跳过语境标注")
        return True

    if not Path(knowledge_md).exists():
        logger.warning(
            "knowledge.md 不存在，跳过语境标注。"
            "请先使用 AI Agent 根据 prompts/knowledge_builder.md 生成 knowledge.md"
        )
        return True

    args = [
        "--operator-json", operator_json,
        "--knowledge-md", knowledge_md,
        "--output", context_json,
    ]

    # 添加 story JSON（如果存在）
    story_json = Path(output_dir) / "story.json"
    if story_json.exists():
        args.extend(["--story-json", str(story_json)])

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
    knowledge_md = str(Path(output_dir) / "knowledge.md")
    context_json = str(Path(output_dir) / "context.json")

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


def step_write(name: str, output_dir: str, slug: str) -> bool:
    """步骤 4: 写入 Skill 文件

    注意: skill_writer 的 --action create 会创建默认模板文件。
    实际的 knowledge.md 和 persona.md 内容由 AI Agent 根据 Prompt 生成，
    此步骤仅确保目录结构和 meta.json 存在。
    """
    return run_tool(
        "skill_writer",
        [
            "--action", "create",
            "--slug", slug,
            "--name", name,
            "--base-dir", str(Path(output_dir).parent),
        ],
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
    parser.add_argument(
        "--resume", action="store_true",
        help="断点续传：检测已有中间产物，跳过已完成的步骤",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不执行")
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
        "fetch": lambda: step_fetch(
            args.name, output_dir, args.skip_fetch,
            discover_prefix=args.discover,
            chapters=args.chapters,
        ),
        "annotate": lambda: step_annotate(args.name, output_dir, slug),
        "analyze": lambda: step_analyze(args.name, output_dir),
        "validate": lambda: step_validate(args.name, output_dir),
        "write": lambda: step_write(args.name, output_dir, slug),
    }

    step_order = ["fetch", "annotate", "analyze", "validate", "write"]

    if args.step == "full":
        for step_name in step_order:
            if args.resume and _step_completed(output_dir, step_name):
                logger.info("跳过已完成的步骤: %s（--resume）", step_name)
                continue
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
