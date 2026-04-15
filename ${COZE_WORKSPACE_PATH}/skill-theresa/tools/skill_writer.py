#!/usr/bin/env python3
"""
Skill 文件管理器 - 用于列出和管理已创建的角色 Skill
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime


def list_skills(base_dir: str = "./theresas") -> dict:
    """
    列出所有已创建的 Skill
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        return {"success": True, "skills": []}
    
    skills = []
    
    for skill_dir in sorted(base_path.iterdir()):
        if skill_dir.is_dir() and skill_dir.name != "versions":
            meta_path = skill_dir / "meta.json"
            
            if meta_path.exists():
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
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


def delete_skill(slug: str, base_dir: str = "./theresas", force: bool = False) -> dict:
    """
    删除指定的 Skill
    """
    import shutil
    
    skill_dir = Path(base_dir) / slug
    
    if not skill_dir.exists():
        return {"success": False, "error": f"Skill {slug} 不存在"}
    
    if not force:
        return {
            "success": False,
            "error": "需要 --force 参数确认删除",
            "confirm_required": True
        }
    
    # 删除目录
    shutil.rmtree(skill_dir)
    
    return {
        "success": True,
        "deleted": slug
    }


def create_default_skill(slug: str, name: str, base_dir: str = "./theresas") -> dict:
    """
    创建默认的 Skill 目录结构
    """
    skill_dir = Path(base_dir) / slug
    versions_dir = skill_dir / "versions"
    
    # 创建目录
    skill_dir.mkdir(exist_ok=True)
    versions_dir.mkdir(exist_ok=True)
    
    now = datetime.now().isoformat()
    
    # 创建默认 meta.json
    meta = {
        "name": name,
        "slug": slug,
        "created_at": now,
        "updated_at": now,
        "version": "v1",
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
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    return {
        "success": True,
        "slug": slug,
        "path": str(skill_dir)
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="角色 Skill 文件管理器")
    parser.add_argument("--action", choices=["list", "delete", "create"], required=True)
    parser.add_argument("--slug", help="Skill slug")
    parser.add_argument("--name", help="角色名称")
    parser.add_argument("--base-dir", default="./theresas", help="基础目录")
    parser.add_argument("--force", action="store_true", help="强制删除")
    
    args = parser.parse_args()
    
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
        result = create_default_skill(args.slug, args.name, args.base_dir)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
