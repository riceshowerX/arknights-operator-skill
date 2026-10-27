#!/usr/bin/env python3
"""
Skill 文件管理器 - 用于列出和管理已创建的角色 Skill

meta.json 写入策略（P0-3 修复）：
    旧行为是无条件全量覆盖，重跑 `--action create` 会把用户积累的
    `corrections_count`（实测 7 → 0）与 `impression` 静默清零。
    新行为是字段级 merge：
      - 用户域（受保护）：corrections_count / impression / created_at /
        tags / knowledge_sources —— 已有则保留；
      - 工具域（受管）：slug / name / name_en / version / updated_at —— 以本次为准；
      - profile 深层 merge：用户填的 faction 不被 "unknown" 覆盖。
    逃生口：设置环境变量 ARKNIGHTS_META_RESET=1 可强制全量覆盖（重置）。

失败返回非 0，见 CHANGELOG 3.6.0。
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保 tools 目录在 import 路径中，支持从任意位置运行
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import assets
import cli
from shared_utils import atomic_write_json, atomic_write_text, load_json_safe, validate_slug

# ──────────────────────────────────────────────
# meta.json 字段分区（见模块 docstring）
# ──────────────────────────────────────────────

# 用户域：已有值一律保留（工具不得覆盖）
_PROTECTED_FIELDS: tuple[str, ...] = (
    "corrections_count",
    "impression",
    "created_at",
    "tags",
    "knowledge_sources",
)

# 工具域：一律以本次生成的值为准
_MANAGED_FIELDS: tuple[str, ...] = (
    "slug",
    "name",
    "name_en",
    "version",
    "updated_at",
)

# 视为「无信息」的占位值（不覆盖有意义的值）
_PLACEHOLDER_STRINGS = frozenset({"", "unknown", "Unknown"})


def _is_placeholder(value) -> bool:
    """判断一个值是否为「无信息」占位值（None / 空串 / unknown / 空容器）"""
    if value is None:
        return True
    if isinstance(value, str):
        return value in _PLACEHOLDER_STRINGS
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _merge_profile(default_profile: dict, existing_profile: dict) -> dict:
    """profile 深层 merge：用户填写的有效值不被默认占位值覆盖"""
    profile = dict(default_profile)
    for key, value in (existing_profile or {}).items():
        if _is_placeholder(value) and not _is_placeholder(profile.get(key)):
            # 已有侧是占位值，保留默认侧的有效值
            continue
        profile[key] = value
    return profile


def merge_meta(defaults: dict, existing: dict) -> dict:
    """按字段分区合并 meta.json（用户域保留、工具域覆盖、profile 深层 merge）

    Args:
        defaults: 本次生成的默认 meta
        existing: 磁盘上已有的 meta（可为空 dict）

    Returns:
        合并后的 meta（新 dict，不修改入参）
    """
    merged: dict = dict(defaults)

    # 1) 用户域：已有则保留
    for field in _PROTECTED_FIELDS:
        if field in existing:
            merged[field] = existing[field]

    # 2) 工具域：以本次为准
    for field in _MANAGED_FIELDS:
        if field in defaults:
            merged[field] = defaults[field]

    # 2b) 唯一一处对「工具域一律覆盖」的收窄：version 是用户版本链的状态，
    #     重跑 create 若把 v1.1 重置成 v1.0，会与 versions/ 目录里的存档脱节。
    #     因此已有非空 version 时保留（想重置用 ARKNIGHTS_META_RESET=1）。
    existing_version = existing.get("version")
    if isinstance(existing_version, str) and existing_version and "version" in defaults:
        merged["version"] = existing_version

    # 3) profile 深层 merge
    merged["profile"] = _merge_profile(defaults.get("profile", {}), existing.get("profile", {}) or {})

    # 4) 保留 defaults 未声明的既有键（避免丢失 backup_at / rolled_back_* 等历史字段）
    for key, value in existing.items():
        if key not in merged:
            merged[key] = value

    return merged


def _meta_reset_forced() -> bool:
    """是否强制覆盖 meta.json（ARKNIGHTS_META_RESET=1）"""
    return os.environ.get("ARKNIGHTS_META_RESET", "") == "1"


def _resolve_base_dir(base_dir: str | None) -> Path:
    """解析 operators 基础目录。

    ``base_dir`` 显式传入时优先；为 ``None`` 时走
    :func:`assets.default_base_dir`（env → 项目根/operators → ./operators），
    这样在任意 CWD 下都能查到同一批 Skill。
    """
    return Path(base_dir) if base_dir else assets.default_base_dir()


def list_skills(base_dir: str | None = None) -> dict:
    """
    列出所有已创建的 Skill

    ``base_dir=None`` 时使用 ``assets.default_base_dir()``；目录不存在仍返回
    ``{"success": True, "skills": []}``（保持 3.x 的下游语义）。
    """
    base_path = _resolve_base_dir(base_dir)

    if not base_path.exists():
        return {"success": True, "skills": []}

    skills = []

    for skill_dir in sorted(base_path.iterdir()):
        if not skill_dir.is_dir():
            continue
        # 跳过非 Skill 目录（如 versions、隐藏目录）
        if skill_dir.name.startswith(".") or skill_dir.name == "versions":
            continue
        # 确认是有效的 Skill 目录（包含 SKILL.md 或 meta.json）
        has_skill_md = (skill_dir / "SKILL.md").exists()
        has_meta = (skill_dir / "meta.json").exists()
        if not has_skill_md and not has_meta:
            continue

        meta_path = skill_dir / "meta.json"

        if meta_path.exists():
            meta = load_json_safe(meta_path)
            if not isinstance(meta, dict):
                print(f"警告：无法读取 {meta_path}", file=sys.stderr)
                meta = {}

            skills.append({
                "name": meta.get("name", skill_dir.name),
                "slug": meta.get("slug", skill_dir.name),
                "version": meta.get("version", "unknown"),
                "game": meta.get("profile", {}).get("game", "明日方舟"),
                "faction": meta.get("profile", {}).get("faction", "unknown"),
                "identity": meta.get("profile", {}).get("identity", "unknown"),
                "created_at": meta.get("created_at", "unknown"),
                "updated_at": meta.get("updated_at", "unknown"),
                "path": str(skill_dir)
            })
        else:
            skills.append({
                "name": skill_dir.name,
                "slug": skill_dir.name,
                "version": "unknown",
                "path": str(skill_dir)
            })

    return {"success": True, "skills": skills}


def _validate_skill_dir(skill_dir: Path) -> list[str]:
    """
    校验 Skill 目录结构是否完整，返回缺失项列表
    """
    required_files = ["SKILL.md", "meta.json"]
    required_dirs = ["versions"]
    missing = []
    for f in required_files:
        if not (skill_dir / f).exists():
            missing.append(f)
    for d in required_dirs:
        if not (skill_dir / d).is_dir():
            missing.append(d + "/")
    return missing


def delete_skill(slug: str, base_dir: str | None = None, force: bool = False) -> dict:
    """
    删除指定的 Skill
    """
    import shutil

    slug = validate_slug(slug)
    skill_dir = _resolve_base_dir(base_dir) / slug

    if not skill_dir.exists():
        return {"success": False, "error": f"Skill {slug} 不存在"}

    # 校验目录结构，记录完整性状态
    missing = _validate_skill_dir(skill_dir)

    if not force:
        return {
            "success": False,
            "error": "需要 --force 参数确认删除",
            "confirm_required": True
        }

    # 删除目录
    shutil.rmtree(skill_dir)

    result = {
        "success": True,
        "deleted": slug
    }
    if missing:
        result["note"] = f"删除前目录不完整，缺少: {', '.join(missing)}"

    return result


def _render_skill_md(slug: str, name: str) -> str:
    """渲染 SKILL.md 模板（YAML front matter + 数据边界标记）。

    front matter 让 Agent 能直接加载该 Skill（`name` / `description`）；
    `<!-- BEGIN SKILL BODY -->` / `<!-- END SKILL BODY -->` 标出「可被工具重写的
    说明正文」范围，便于后续增量同步而不破坏用户手写段落。

    Args:
        slug: 角色 slug（用作 front matter 的 `name`）
        name: 角色中文名

    Returns:
        完整的 SKILL.md 文本
    """
    # 双引号包裹的 YAML 值里不能再出现未转义的双引号
    safe_name = name.replace('"', "'")
    return f"""---
name: {slug}
description: "{safe_name} — 明日方舟角色 Skill（Knowledge + 5 层 Persona）"
---

# {name} — Skill

> 本文件由 arknights-operator-skill 自动生成

<!-- BEGIN SKILL BODY -->

## 使用说明

- `knowledge.md`：角色知识库（背景、关系、事件、理念）
- `persona.md`：角色人格定义（5 层性格结构 + Correction）
- `meta.json`：角色元数据

<!-- END SKILL BODY -->

## 进化方式

- 追加资料 → 更新 knowledge.md
- 对话纠正 → 追加 persona.md 的 Correction 层
- 版本管理 → 使用 version_manager.py
"""


def create_default_skill(slug: str, name: str, name_en: str = "",
                         base_dir: str | None = None,
                         force_skill_md: bool = False) -> dict:
    """
    创建默认的 Skill 目录结构

    已存在的 meta.json 会按字段分区 merge（见模块 docstring），
    用户积累的 corrections_count / impression 不会被清零。

    SKILL.md 已存在时**不覆盖**；只有 `force_skill_md=True`（CLI:
    `--force-skill-md`）才按当前模板重写。

    Args:
        slug: 角色 slug
        name: 角色中文名
        name_en: 角色英文名
        base_dir: 基础目录；None 时用 assets.default_base_dir()
        force_skill_md: 是否强制重写已存在的 SKILL.md

    Returns:
        结果字典（含 skill_md 字段说明是否写入/重写）
    """
    slug = validate_slug(slug)
    skill_dir = _resolve_base_dir(base_dir) / slug
    versions_dir = skill_dir / "versions"

    # 创建目录（parents=True：支持 /tmp/a/b/c 这类深层路径）
    skill_dir.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()

    # 创建默认 meta.json
    meta = {
        "name": name,
        "name_en": name_en,
        "slug": slug,
        "created_at": now,
        "updated_at": now,
        "version": "v1.0",
        "profile": {
            "game": "明日方舟",
            "faction": "unknown",
            "identity": "unknown",
            "mbti": "unknown",
            "key_relationships": []
        },
        "tags": {
            "personality": [],
            "leadership": [],
            "philosophy": []
        },
        "impression": "",
        "knowledge_sources": [],
        "corrections_count": 0
    }

    meta_path = skill_dir / "meta.json"
    existing_meta = load_json_safe(meta_path)
    if isinstance(existing_meta, dict) and existing_meta and not _meta_reset_forced():
        meta = merge_meta(meta, existing_meta)

    atomic_write_json(meta_path, meta)

    # 创建默认 SKILL.md
    # 已存在则不覆盖（原语义保留）；--force-skill-md 时显式重写
    skill_md_path = skill_dir / "SKILL.md"
    skill_md_state = "kept"
    if force_skill_md or not skill_md_path.exists():
        skill_md_state = "rewritten" if skill_md_path.exists() else "created"
        atomic_write_text(skill_md_path, _render_skill_md(slug, name))

    # 创建后校验目录结构
    missing = _validate_skill_dir(skill_dir)
    result = {
        "success": True,
        "slug": slug,
        "path": str(skill_dir),
        "skill_md": skill_md_state,
    }
    if missing:
        result["warnings"] = [f"缺少必要文件/目录: {m}" for m in missing]

    return result


def main():
    """CLI 入口

    失败返回非 0，见 CHANGELOG 3.6.0。
    """
    import argparse

    parser = argparse.ArgumentParser(description="角色 Skill 文件管理器")
    parser.add_argument("--action", choices=["list", "delete", "create"], required=True)
    parser.add_argument("--slug", help="Skill slug")
    parser.add_argument("--name", help="角色名称")
    parser.add_argument("--name-en", default="", help="角色英文名称")
    parser.add_argument("--base-dir", default=None, help="基础目录（默认 <项目根>/operators）")
    parser.add_argument("--force", action="store_true", help="强制删除")
    parser.add_argument("--force-skill-md", action="store_true",
                        help="create 时强制重写已存在的 SKILL.md（默认不覆盖）")

    args = parser.parse_args()

    result: dict = {"success": False, "error": "未知操作"}

    if args.action == "list":
        result = list_skills(args.base_dir)
    elif args.action == "delete":
        if not args.slug:
            print("错误：需要指定 --slug")
            sys.exit(1)
        result = delete_skill(args.slug, args.base_dir, args.force)
    elif args.action == "create":
        if not args.slug or not args.name:
            print("错误：需要指定 --slug 和 --name")
            sys.exit(1)
        result = create_default_skill(args.slug, args.name, args.name_en, args.base_dir,
                                      force_skill_md=args.force_skill_md)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    cli.finish(result)


if __name__ == "__main__":
    main()
