#!/usr/bin/env python3
"""
CLI 退出码与安全输出 —— 统一进程退出语义

背景（为什么需要这个模块）：
    重构前三个模块（data_injector / version_manager / skill_writer）无论成败都 exit 0，
    而 argparse 参数错误天然 exit 2 —— 三套语义并存，CI/脚本无法判断失败。

退出码规范（0 / 1 / 2 三值）：
    0  成功（含 list 查无结果、--dry-run）
    1  运行期失败（数据/网络/校验失败，但参数合法）—— result["success"] is False
    2  用法/前置错误（缺参数、confirm_required、资产自检失败、validate_slug 拒绝）

约束：
    - 本模块**不改变 stdout 输出内容**，只改进程退出码；
    - 各模块禁止自行 sys.exit(1/2)，一律走 finish()（--help 由 argparse 处理）。

用法：
    from cli import finish, safe_print

    print(json.dumps(result, ensure_ascii=False, indent=2))
    finish(result)
"""

import sys
from typing import Any, TextIO

# ──────────────────────────────────────────────
# 退出码常量
# ──────────────────────────────────────────────

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def exit_code_for(result: dict[str, Any] | None) -> int:
    """依据结果字典推导退出码（不抛异常，便于单测）

    Args:
        result: 工具返回的结果字典；None 视为成功

    Returns:
        0 / 1 / 2
    """
    if not isinstance(result, dict):
        return EXIT_OK
    # 用法/前置错误优先：需要用户确认也是「参数不足」的一种
    if result.get("confirm_required"):
        return EXIT_USAGE
    if result.get("success") is False:
        return EXIT_FAILURE
    return EXIT_OK


def finish(result: dict[str, Any] | None) -> None:
    """按结果字典结束进程

    失败返回非 0，见 CHANGELOG 3.6.0。

    Args:
        result: 工具返回的结果字典

    Raises:
        SystemExit: 总是抛出，携带推导出的退出码
    """
    raise SystemExit(exit_code_for(result))


# ──────────────────────────────────────────────
# 前置自检：领域资产完整性
# ──────────────────────────────────────────────


def require_assets() -> None:
    """校验领域资产（data 目录）完整；缺失时以退出码 2 结束进程。

    CLI 入口应在 ``main()`` 起始调用，避免安装态「资产缺失 → 能力静默降级为空」。

    Raises:
        SystemExit: 资产缺失时抛出，退出码 :data:`EXIT_USAGE`
    """
    # 延迟导入：assets 依赖 shared_utils，避免模块导入顺序耦合
    import assets

    try:
        assets.assert_data_assets()
    except assets.DataAssetsMissingError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from exc


# ──────────────────────────────────────────────
# 安全输出（GBK 控制台不再 UnicodeEncodeError）
# ──────────────────────────────────────────────


def _ensure_replace_errors(stream: TextIO) -> None:
    """尽力把流的编码错误策略改为 replace（失败则静默忽略）"""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace")
    except (ValueError, OSError):
        # 已被包装（如 pytest capture）或已关闭：退化为写入时的兜底
        return


def safe_print(text: str = "", file: TextIO | None = None, end: str = "\n", flush: bool = False) -> None:
    """打印文本，遇到无法编码的字符时用 '?' 替代而不是抛异常

    Args:
        text: 待输出文本
        file: 目标流（默认 stdout）
        end: 行尾
        flush: 是否立即刷新
    """
    stream = sys.stdout if file is None else file
    _ensure_replace_errors(stream)
    try:
        stream.write(text + end)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace") + end)
    if flush:
        stream.flush()
