#!/usr/bin/env python3
"""
版本管理器 - 用于角色 Skill 的版本存档与回滚
"""

import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# 确保 tools 目录在 import 路径中，支持从任意位置运行
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from shared_utils import validate_slug


def _normalize_version(version: str) -> str:
    """规范化版本号为 v{major}.{minor} 格式。

    支持的输入格式：
    - "v1"     → "v1.0"
    - "v1.0"   → "v1.0"
    - "1.0"    → "v1.0"
    - "1"      → "v1.0"

    无法解析时，抛出 ValueError 而非静默返回。
    """
    version = version.strip()
    if not version:
        raise ValueError("版本号不能为空")

    # 去掉前缀 v
    raw = version[1:] if version.startswith("v") else version

    # 已经是 major.minor 格式
    m = re.match(r"^(\d+)\.(\d+)$", raw)
    if m:
        return f"v{m.group(1)}.{m.group(2)}"

    # 只有 major
    m2 = re.match(r"^(\d+)$", raw)
    if m2:
        return f"v{m2.group(1)}.0"

    raise ValueError(
        f"无法解析版本号 '{version}'，合法格式: v1, v1.0, 1, 1.0"
    )


# 版本号内部表示（方便比较）
@dataclass
class _SemVer:
    """简化语义版本（仅 major.minor）"""
    major: int
    minor: int

    def __lt__(self, other: "_SemVer") -> bool:
        if self.major != other.major:
            return self.major < other.major
        return self.minor < other.minor

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _SemVer):
            return NotImplemented
        return self.major == other.major and self.minor == other.minor

    def __le__(self, other: "_SemVer") -> bool:
        return self == other or self < other

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}"


def _parse_dir_version(dir_name: str) -> _SemVer | None:
    """从目录名解析版本号。

    支持新旧两种格式：
    - v1.0, v2.3 → 标准格式
    - v1, v2     → 旧格式，视为 v1.0, v2.0

    不合法的名称返回 None（而非抛异常，因为 versions 目录下
    可能有非版本目录）。
    """
    # 标准格式 v{major}.{minor}
    m = re.match(r"^v(\d+)\.(\d+)$", dir_name)
    if m:
        return _SemVer(int(m.group(1)), int(m.group(2)))

    # 旧格式 v{N} → 视为 v{N}.0（仅 major，minor=0）
    m2 = re.match(r"^v(\d+)$", dir_name)
    if m2:
        return _SemVer(int(m2.group(1)), 0)

    return None


def _get_next_version(versions_dir: Path, major: int | None = None) -> str:
    """确定下一个版本号。

    规则：
    - 首次备份 → v1.0
    - 后续备份 → 同一 major 下 minor +1
    - --major 指定大版本 → 在该大版本下递增 minor
    - 旧格式目录（v1, v2）→ 已由 _parse_dir_version 统一处理

    不再在 _get_next_version 中内联正则，统一走 _parse_dir_version。
    """
    existing = list(versions_dir.glob("v*"))

    # 收集所有已存在版本
    parsed_versions: list[_SemVer] = []
    for v in existing:
        sv = _parse_dir_version(v.name)
        if sv is not None:
            parsed_versions.append(sv)

    # 确定 major
    target_major = major if major is not None else 1

    # 筛选目标 major 下的版本
    same_major = [sv for sv in parsed_versions if sv.major == target_major]

    if not same_major:
        # 目标 major 下无任何版本
        # 如果未指定 major，检查是否需要跟随更大的 major
        if major is None and parsed_versions:
            max_existing = max(parsed_versions)
            if max_existing.major > target_major:
                target_major = max_existing.major
                same_major = [sv for sv in parsed_versions if sv.major == target_major]
        if not same_major:
            return f"v{target_major}.0"

    max_ver = max(same_major)
    return str(_SemVer(target_major, max_ver.minor + 1))


def backup_version(slug: str, base_dir: str = "./operators") -> dict:
    """
    备份当前版本到 versions 目录
    """
    slug = validate_slug(slug)
    skill_dir = Path(base_dir) / slug
    versions_dir = skill_dir / "versions"

    if not skill_dir.exists():
        return {"success": False, "error": f"Skill {slug} 不存在"}

    # 创建版本目录
    versions_dir.mkdir(exist_ok=True)

    # 生成版本号
    version_name = _get_next_version(versions_dir)
    version_dir = versions_dir / version_name

    # 复制文件
    version_dir.mkdir(exist_ok=True)

    for file in ["knowledge.md", "persona.md", "meta.json", "SKILL.md"]:
        src = skill_dir / file
        if src.exists():
            shutil.copy2(src, version_dir / file)

    # 更新 meta.json 中的 version
    meta_path = skill_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["version"] = version_name
        meta["backup_at"] = datetime.now().isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "version": version_name,
        "path": str(version_dir)
    }


def rollback_version(slug: str, version: str, base_dir: str = "./operators", backup_before: bool = False) -> dict:
    """
    回滚到指定版本

    Args:
        backup_before: 回滚前是否备份当前版本（默认 False，避免版本号跳跃）。
            如需保留回滚前状态，请显式设为 True。
    """
    slug = validate_slug(slug)
    skill_dir = Path(base_dir) / slug
    versions_dir = skill_dir / "versions"
    # 规范化版本号格式
    try:
        version = _normalize_version(version)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    version_dir = versions_dir / version

    if not version_dir.exists():
        return {"success": False, "error": f"版本 {version} 不存在"}

    # 记录回滚前的版本号
    current_version = "unknown"
    meta_path = skill_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            current_meta = json.load(f)
        current_version = current_meta.get("version", "unknown")

    # 可选：回滚前备份当前版本
    backup_info = None
    if backup_before:
        backup_info = backup_version(slug, base_dir)
        if not backup_info["success"]:
            return backup_info

    # 复制版本文件
    for file in ["knowledge.md", "persona.md", "meta.json", "SKILL.md"]:
        src = version_dir / file
        if src.exists():
            shutil.copy2(src, skill_dir / file)

    # 更新 meta.json
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["rolled_back_from"] = current_version
        meta["rolled_back_to"] = version
        meta["updated_at"] = datetime.now().isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    note = f"已从 {current_version} 回滚到 {version}"
    if backup_info:
        note += f"（已备份当前版本为 {backup_info['version']}）"

    return {
        "success": True,
        "rolled_to": version,
        "backup_created": backup_before,
        "note": note,
    }


def list_versions(slug: str, base_dir: str = "./operators") -> dict:
    """
    列出所有版本
    """
    slug = validate_slug(slug)
    skill_dir = Path(base_dir) / slug
    versions_dir = skill_dir / "versions"

    if not versions_dir.exists():
        return {"success": True, "versions": []}

    versions = []
    for v_dir in sorted(versions_dir.iterdir()):
        if v_dir.is_dir() and v_dir.name.startswith("v"):
            # 读取版本信息
            meta_path = v_dir / "meta.json"
            version_info = {
                "name": v_dir.name,
                "path": str(v_dir)
            }
            if meta_path.exists():
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                version_info["created"] = meta.get("created_at", "unknown")
                version_info["backup_at"] = meta.get("backup_at", "unknown")
            versions.append(version_info)

    return {"success": True, "versions": versions}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="角色 Skill 版本管理器")
    parser.add_argument("--action", choices=["backup", "rollback", "list"], required=True)
    parser.add_argument("--slug", help="Skill slug")
    parser.add_argument("--version", help="版本号 (如 v1.0, v1.1)")
    parser.add_argument("--base-dir", default="./operators", help="基础目录")
    parser.add_argument("--backup", action="store_true", help="回滚前备份当前版本（默认不备份）")

    args = parser.parse_args()

    if args.action == "backup":
        if not args.slug:
            print("错误：需要指定 --slug")
            sys.exit(1)
        result = backup_version(args.slug, args.base_dir)
    elif args.action == "rollback":
        if not args.slug or not args.version:
            print("错误：需要指定 --slug 和 --version")
            sys.exit(1)
        result = rollback_version(args.slug, args.version, args.base_dir, backup_before=args.backup)
    elif args.action == "list":
        if not args.slug:
            print("错误：需要指定 --slug")
            sys.exit(1)
        result = list_versions(args.slug, args.base_dir)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
