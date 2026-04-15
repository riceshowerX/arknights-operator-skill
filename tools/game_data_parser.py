#!/usr/bin/env python3
"""
游戏资料解析器 —— 从 PRTS Wiki 等来源提取角色信息

用法:
    python game_data_parser.py --source prts --name 特蕾西娅
    python game_data_parser.py --source prts --name Theresa --lang zh
    python game_data_parser.py --source local --file ./raw_data/theresa.md

输出:
    JSON 格式的结构化角色数据，写入 stdout
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────

OPERATOR_SCHEMA = {
    "name_zh": "",
    "name_en": "",
    "slug": "",
    "race": "",
    "faction": "",
    "identity": "",
    "mbti": "",
    "personality_type": "",
    "core_traits": [],
    "leadership_style": "",
    "impression": "",
    "timeline": [],
    "relationships": [],
    "abilities": [],
    "weaknesses": [],
    "signature_lines": [],
    "visual_traits": [],
    "misconceptions": [],
    "source_url": "",
    "last_updated": "",
}


# ──────────────────────────────────────────────
# 文本清洗
# ──────────────────────────────────────────────

def clean_wikitext(raw: str) -> str:
    """移除 MediaWiki 标记，保留纯文本"""
    text = raw

    # 移除 HTML 注释
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # 移除 <ref>...</ref>
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)

    # 移除模板调用 {{...}}（保留内部文本供后续提取）
    # 简单版本：移除不含换行的模板
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)

    # 移除 Wiki 链接标记 [[...|显示文本]] → 显示文本
    text = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", text)

    # 移除加粗/斜体标记
    text = re.sub(r"'{2,5}", "", text)

    # 移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)

    # 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


# ──────────────────────────────────────────────
# PRTS Wiki 解析
# ──────────────────────────────────────────────

def parse_prts_operator_name(name: str) -> dict:
    """
    从 PRTS Wiki 角色名构造 URL 和 slug

    PRTS URL 格式: https://prts.wiki/w/{角色名}
    """
    slug = name.lower().replace(" ", "-")
    # 中文角色名直接使用
    url = f"https://prts.wiki/w/{name}"
    return {"slug": slug, "source_url": url}


def extract_operator_data_from_wikitext(wikitext: str, name: str) -> dict:
    """
    从 PRTS Wiki 的 wikitext 中提取角色信息

    注意：此函数提供基础解析能力。对于复杂的模板结构，
    建议使用 PRTS Wiki 的 API 获取结构化数据。
    """
    data = {
        "name_zh": name,
        "slug": name.lower().replace(" ", "-"),
        "source": "prts",
    }

    # 提取干员信息框模板中的字段
    # PRTS 使用 {{干员/信息}} 或类似模板

    # 提取种族
    race_match = re.search(r"\|\s*种族\s*=\s*([^\n|]+)", wikitext)
    if race_match:
        data["race"] = race_match.group(1).strip()

    # 提取阵营/阵营
    faction_match = re.search(r"\|\s*阵营\s*=\s*([^\n|]+)", wikitext)
    if faction_match:
        data["faction"] = faction_match.group(1).strip()

    # 提取职业
    profession_match = re.search(r"\|\s*职业\s*=\s*([^\n|]+)", wikitext)
    if profession_match:
        data["profession"] = profession_match.group(1).strip()

    # 提取语音文本
    voice_lines = []
    voice_section = re.search(
        r"==.*语音.*==\n(.*?)(?=\n==|$)", wikitext, re.DOTALL
    )
    if voice_section:
        lines = voice_section.group(1)
        for line in lines.split("\n"):
            line = line.strip()
            if line.startswith("|"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    label = parts[0].lstrip("|").strip()
                    content = clean_wikitext(parts[1].strip())
                    if content:
                        voice_lines.append({"label": label, "text": content})

    if voice_lines:
        data["voice_lines"] = voice_lines

    # 提取档案文本
    archive_lines = []
    archive_section = re.search(
        r"==.*档案.*==\n(.*?)(?=\n==|$)", wikitext, re.DOTALL
    )
    if archive_section:
        archive_text = clean_wikitext(archive_section.group(1))
        # 按档案条目分割
        entries = re.split(r"档案资料\s*\w", archive_text)
        for i, entry in enumerate(entries):
            entry = entry.strip()
            if entry:
                archive_lines.append({"index": i, "text": entry})

    if archive_lines:
        data["archives"] = archive_lines

    return data


# ──────────────────────────────────────────────
# 本地文件解析
# ──────────────────────────────────────────────

def parse_local_file(filepath: str) -> dict:
    """
    解析本地 Markdown 文件中的角色信息

    支持的格式：
    - 标准 Markdown 标题结构
    - YAML frontmatter
    - 自由格式文本（尝试提取关键信息）
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    content = path.read_text(encoding="utf-8")
    data = {"source": "local", "filename": path.name}

    # 尝试提取 YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                data[key.strip()] = value.strip().strip('"').strip("'")

    # 提取各标题下的内容
    sections = re.split(r"^#+\s+", content, flags=re.MULTILINE)
    for section in sections[1:]:  # 跳过第一段（标题前的内容）
        lines = section.split("\n", 1)
        if lines:
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            data[f"section_{title}"] = body

    return data


# ──────────────────────────────────────────────
# 中文转拼音 slug
# ──────────────────────────────────────────────

# 常见角色名拼音映射表
# 完整映射建议使用 pypinyin 库，此处仅覆盖明日方舟常见角色
PINYIN_MAP = {
    "特蕾西娅": "te-lei-xi-ya",
    "特雷西斯": "te-lei-xi-si",
    "阿米娅": "a-mi-ya",
    "凯尔希": "kai-er-xi",
    "博士": "bo-shi",
    "塔露拉": "ta-lu-la",
    "银灰": "yin-hui",
    "陈": "chen",
    "星熊": "xing-xiong",
    "W": "w",
    "可露希尔": "ke-lu-xi-er",
    "华法琳": "hua-fa-lin",
    "伊芙利特": "yi-fu-li-te",
    "塞雷娅": "sai-lei-ya",
    "推进之王": "tui-jin-zhi-wang",
    "煌": "huang",
    "史尔特尔": "shi-er-te-er",
    "浊心斯卡蒂": "zhuo-xin-si-ka-di",
    "玛恩纳": "ma-en-na",
    "令": "ling",
    "耀骑士临光": "yao-qi-shi-lin-guang",
    "异客": "yi-ke",
    "爱布拉娜": "ai-bu-la-na",
    "维什戴尔": "wei-shi-dai-er",
}


def to_slug(name: str) -> str:
    """
    将角色名转为 URL-safe slug

    规则：
    - 中文：查拼音映射表，未知字符用 pypinyin（如已安装）或保留原文
    - 英文：小写 + 用 - 连接
    - 混合：各部分分别转换后用 - 连接
    """
    # 先查映射表
    if name in PINYIN_MAP:
        return PINYIN_MAP[name]

    # 尝试使用 pypinyin（如已安装）
    try:
        from pypinyin import lazy_pinyin
        parts = lazy_pinyin(name)
        slug = "-".join(p.lower() for p in parts if p)
        return re.sub(r"[^a-z0-9-]", "", slug)
    except ImportError:
        pass

    # 纯英文
    if re.match(r"^[a-zA-Z\s]+$", name):
        return re.sub(r"\s+", "-", name.lower())

    # 无法转换，保留原文
    return re.sub(r"\s+", "-", name.lower())


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="明日方舟角色资料解析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 PRTS Wiki 获取角色信息
  python game_data_parser.py --source prts --name 特蕾西娅

  # 解析本地 Markdown 文件
  python game_data_parser.py --source local --file ./raw_data/theresa.md

  # 生成 slug
  python game_data_parser.py --slug 特蕾西娅
        """,
    )

    parser.add_argument(
        "--source",
        choices=["prts", "local"],
        default="prts",
        help="资料来源",
    )
    parser.add_argument("--name", help="角色名称（中/英文）")
    parser.add_argument("--file", help="本地文件路径（--source local 时必填）")
    parser.add_argument(
        "--lang",
        choices=["zh", "en"],
        default="zh",
        help="语言偏好",
    )
    parser.add_argument(
        "--slug-only",
        action="store_true",
        help="仅输出 slug（角色名的 URL 安全标识符）",
    )
    parser.add_argument(
        "--output",
        help="输出文件路径（默认输出到 stdout）",
    )

    args = parser.parse_args()

    # 仅生成 slug
    if args.slug_only:
        if not args.name:
            parser.error("--slug-only 需要 --name 参数")
        result = {"name": args.name, "slug": to_slug(args.name)}
        _output(result, args.output)
        return

    # 按来源解析
    if args.source == "local":
        if not args.file:
            parser.error("--source local 需要 --file 参数")
        result = parse_local_file(args.file)
    elif args.source == "prts":
        if not args.name:
            parser.error("--source prts 需要 --name 参数")
        # 构造元数据（实际爬取需调用方自行实现 HTTP 请求）
        result = {
            **parse_prts_operator_name(args.name),
            "lang": args.lang,
            "note": "PRTS Wiki 爬取需外部 HTTP 请求支持，此处仅输出元数据。"
            "请使用 fetch-url 工具或浏览器获取页面内容后，"
            "使用 --source local 解析。",
        }
    else:
        parser.error(f"不支持的来源: {args.source}")

    _output(result, args.output)


def _output(data: dict, filepath: Optional[str] = None):
    """输出 JSON 数据"""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if filepath:
        Path(filepath).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
