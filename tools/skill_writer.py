#!/usr/bin/env python3
"""
Skill 文件管理器 - 用于列出和管理已创建的角色 Skill
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def list_skills(base_dir: str = "./operators") -> dict:
    """
    列出所有已创建的 Skill
    """
    base_path = Path(base_dir)
    
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
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"警告：无法读取 {meta_path}: {e}", file=sys.stderr)
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


def delete_skill(slug: str, base_dir: str = "./operators", force: bool = False) -> dict:
    """
    删除指定的 Skill
    """
    import shutil
    
    skill_dir = Path(base_dir) / slug
    
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


def create_default_skill(slug: str, name: str, name_en: str = "", base_dir: str = "./operators") -> dict:
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
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    # 创建默认 SKILL.md
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        skill_md_content = f"""# {name} — Skill

> 本文件由 arknights-operator-skill 自动生成

## 使用说明

- `knowledge.md`：角色知识库（背景、关系、事件、理念）
- `persona.md`：角色人格定义（5 层性格结构 + Correction）
- `meta.json`：角色元数据

## 进化方式

- 追加资料 → 更新 knowledge.md
- 对话纠正 → 追加 persona.md 的 Correction 层
- 版本管理 → 使用 version_manager.py
"""
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

    # 创建后校验目录结构
    missing = _validate_skill_dir(skill_dir)
    result = {
        "success": True,
        "slug": slug,
        "path": str(skill_dir)
    }
    if missing:
        result["warnings"] = [f"缺少必要文件/目录: {m}" for m in missing]
    
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="角色 Skill 文件管理器")
    parser.add_argument("--action", choices=["list", "delete", "create"], required=True)
    parser.add_argument("--slug", help="Skill slug")
    parser.add_argument("--name", help="角色名称")
    parser.add_argument("--name-en", default="", help="角色英文名称")
    parser.add_argument("--base-dir", default="./operators", help="基础目录")
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
        result = create_default_skill(args.slug, args.name, args.name_en, args.base_dir)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
