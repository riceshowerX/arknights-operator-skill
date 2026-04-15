#!/usr/bin/env python3
"""
版本管理器 - 用于角色 Skill 的版本存档与回滚
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def _get_next_version(versions_dir: Path) -> str:
    """
    确定下一个版本号

    规则：使用 v{大版本}.{小版本} 格式
    - 首次备份 → v1.0
    - 后续备份 → 小版本 +1
    - 如果目录名不规范（如旧格式 v1, v2），兼容处理
    """
    existing = list(versions_dir.glob("v*"))
    max_major = 1
    max_minor = -1  # -1 表示还没有任何版本

    for v in existing:
        # 支持 v1.0, v1.1 格式
        m = re.match(r"v(\d+)\.(\d+)", v.name)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2))
            if major == max_major and minor > max_minor:
                max_minor = minor
            elif major > max_major:
                max_major = major
                max_minor = minor
            continue

        # 兼容旧格式 v1, v2 等 → 视为 v1.1, v1.2
        m2 = re.match(r"v(\d+)$", v.name)
        if m2:
            num = int(m2.group(1))
            if num > max_minor:
                max_minor = num

    if max_minor < 0:
        return "v1.0"
    return f"v{max_major}.{max_minor + 1}"


def backup_version(slug: str, base_dir: str = "./operators") -> dict:
    """
    备份当前版本到 versions 目录
    """
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
        with open(meta_path, "r", encoding="utf-8") as f:
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


def rollback_version(slug: str, version: str, base_dir: str = "./operators") -> dict:
    """
    回滚到指定版本
    """
    skill_dir = Path(base_dir) / slug
    versions_dir = skill_dir / "versions"
    version_dir = versions_dir / version
    
    if not version_dir.exists():
        return {"success": False, "error": f"版本 {version} 不存在"}
    
    # 备份当前版本
    current_backup = backup_version(slug, base_dir)
    if not current_backup["success"]:
        return current_backup
    
    # 复制版本文件
    for file in ["knowledge.md", "persona.md", "meta.json", "SKILL.md"]:
        src = version_dir / file
        if src.exists():
            shutil.copy2(src, skill_dir / file)
    
    # 更新 meta.json
    meta_path = skill_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["rolled_back_from"] = meta.get("version", "unknown")
        meta["rolled_back_to"] = version
        meta["updated_at"] = datetime.now().isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "rolled_to": version,
        "note": f"已从 {current_backup['version']} 回滚到 {version}"
    }


def list_versions(slug: str, base_dir: str = "./operators") -> dict:
    """
    列出所有版本
    """
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
                with open(meta_path, "r", encoding="utf-8") as f:
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
        result = rollback_version(args.slug, args.version, args.base_dir)
    elif args.action == "list":
        if not args.slug:
            print("错误：需要指定 --slug")
            sys.exit(1)
        result = list_versions(args.slug, args.base_dir)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
