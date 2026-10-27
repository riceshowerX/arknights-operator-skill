#!/usr/bin/env python3
"""
产物契约模块 —— 所有中间产物的文件名与「步骤 → 产物」映射的唯一来源

背景（为什么需要这个模块）：
    此前同一个文件名在多个模块中各写一遍字面量，导致契约漂移：
      - story_extractor 写 `story_data.json`，pipeline 读 `story.json` → 剧情 100% 丢失
      - analyze 步骤的 4 个工具只 print 不落盘，data_injector 却按文件名去读 → 分析结果全丢
    把文件名收敛到本模块后，`grep ARTIFACT` 即可穷举全部读写点。

设计约束：
    - 本模块**只放常量与纯函数**，不 import 任何 tools 模块（避免循环依赖）；
    - 不新增任何运行期依赖（仅标准库 types）。

用法：
    from artifacts import ARTIFACT, STEP_ARTIFACTS, ANALYZE_TOOLS

    path = Path(output_dir) / ARTIFACT.STORY
"""

from types import SimpleNamespace
from typing import Final

# ──────────────────────────────────────────────
# 产物文件名（唯一来源）
# ──────────────────────────────────────────────

ARTIFACT: Final = SimpleNamespace(
    # 采集阶段
    OPERATOR_DATA="operator_data.json",
    STORY="story_data.json",
    # 语境标注阶段
    CONTEXT="context.json",
    # 分析阶段
    FINGERPRINT="fingerprint.json",
    SPEECH_PROFILE="speech_act_profile.json",
    TEMPORAL="temporal_slices.json",
    RELATIONS="relationship_graph.json",
    # 校验阶段
    VALIDATION="validation.json",
    PERSONA_VALIDATION="persona_validation.json",
    # 写入阶段
    META="meta.json",
    SKILL_MD="SKILL.md",
    # 旧版文件名（仅用于读取端兼容探测，写入端一律使用新名）
    STORY_LEGACY="story.json",
)

# 分析阶段必须落盘的 4 个产物
ANALYZE_ARTIFACTS: Final[list[str]] = [
    ARTIFACT.FINGERPRINT,
    ARTIFACT.SPEECH_PROFILE,
    ARTIFACT.TEMPORAL,
    ARTIFACT.RELATIONS,
]

# 旧版文件名 → 新文件名的别名表（key = 新名，value = 旧名）
# 仅用于「读取端双读」；写入端永远写新名。
LEGACY_ALIASES: Final[dict[str, str]] = {
    ARTIFACT.STORY: ARTIFACT.STORY_LEGACY,
}

# ──────────────────────────────────────────────
# 步骤 → 产物映射（--resume 判据）
# ──────────────────────────────────────────────

# 说明：
#   - analyze 判据由「context.json」改为 4 个自身产物：context.json 是 annotate 的产物，
#     旧判据会导致 --resume 永远跳过 analyze（P1-2）。
#   - validate 保持空列表（永不跳过）：strict 模式下校验可能被合法跳过，
#     用产物判定会误跳；详见 docs/ARTIFACTS.md。
STEP_ARTIFACTS: Final[dict[str, list[str]]] = {
    "fetch": [ARTIFACT.OPERATOR_DATA],
    "annotate": [ARTIFACT.CONTEXT],
    "analyze": list(ANALYZE_ARTIFACTS),
    "validate": [],
    "write": [ARTIFACT.META, ARTIFACT.SKILL_MD],
}

# ──────────────────────────────────────────────
# 分析阶段工具清单
# ──────────────────────────────────────────────

# 每项：(工具模块名, 输出参数前缀（不含路径）, 该工具负责产出的文件名)
# pipeline 实际拼接为：["--context-json", ctx] + output_args + [产物绝对路径]
# 注意：speech_act_analyzer 的画像参数名是 --output-profile，其余三个是 --output。
ANALYZE_TOOLS: Final[list[tuple[str, list[str], str]]] = [
    ("speech_act_analyzer", ["--output-profile"], ARTIFACT.SPEECH_PROFILE),
    ("dialogue_fingerprint", ["--output"], ARTIFACT.FINGERPRINT),
    ("relationship_graph", ["--output"], ARTIFACT.RELATIONS),
    ("temporal_slicer", ["--output"], ARTIFACT.TEMPORAL),
]

# 工具 → 中文描述（用于日志）
TOOL_LABELS: Final[dict[str, str]] = {
    "speech_act_analyzer": "话语行为分析",
    "dialogue_fingerprint": "语言指纹分析",
    "relationship_graph": "关系图谱构建",
    "temporal_slicer": "时序切片分析",
}


def artifact_path(output_dir: str, filename: str) -> str:
    """拼出产物路径（避免各调用点自行拼接字符串）

    Args:
        output_dir: 输出目录
        filename: 产物文件名（应取自 ARTIFACT）

    Returns:
        产物完整路径字符串
    """
    from pathlib import Path

    return str(Path(output_dir) / filename)


if __name__ == "__main__":
    # 自检：打印全部产物契约，便于排查「到底读写哪些文件」
    import json

    print(json.dumps(
        {
            "artifacts": vars(ARTIFACT),
            "step_artifacts": STEP_ARTIFACTS,
            "analyze_tools": ANALYZE_TOOLS,
        },
        ensure_ascii=False,
        indent=2,
    ))
