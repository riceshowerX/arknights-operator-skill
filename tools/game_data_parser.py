#!/usr/bin/env python3
"""
游戏资料解析器 —— 从 PRTS Wiki 等来源提取角色信息

用法:
    # 从 PRTS Wiki 直接获取并解析角色信息
    python game_data_parser.py --source prts --name 阿米娅
    python game_data_parser.py --source prts --name 魔王

    # 解析本地 Markdown/Wikitext 文件
    python game_data_parser.py --source local --file ./raw_data/theresa.md

    # 仅生成 slug
    python game_data_parser.py --slug-only --name 特蕾西娅

输出:
    JSON 格式的结构化角色数据，写入 stdout 或 --output 指定文件
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

PRTS_API_URL = "https://prts.wiki/api.php"
PRTS_USER_AGENT = "arknights-operator-skill/2.0"
REQUEST_TIMEOUT = 15  # 秒

# 速率限制
_last_request_time = 0.0
_REQUEST_INTERVAL = 0.5  # 最小请求间隔（秒）


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
# PRTS API 请求
# ──────────────────────────────────────────────

def _prts_api_request(params: dict) -> dict:
    """向 PRTS Wiki MediaWiki API 发送 GET 请求（含速率限制）

    Args:
        params: API 查询参数

    Returns:
        解析后的 JSON 响应

    Raises:
        RuntimeError: 请求失败或 API 返回错误
    """
    global _last_request_time

    # 速率限制：确保两次请求间隔 >= _REQUEST_INTERVAL
    elapsed = time.time() - _last_request_time
    if elapsed < _REQUEST_INTERVAL:
        time.sleep(_REQUEST_INTERVAL - elapsed)

    params["format"] = "json"
    # 使用 urlencode 正确编码中文参数
    query_string = urlencode(params)
    url = f"{PRTS_API_URL}?{query_string}"

    req = Request(url, headers={"User-Agent": PRTS_USER_AGENT})

    try:
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            _last_request_time = time.time()
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        _last_request_time = time.time()
        raise RuntimeError(f"PRTS API HTTP 错误: {e.code} {e.reason}") from e
    except URLError as e:
        _last_request_time = time.time()
        raise RuntimeError(f"无法连接 PRTS Wiki: {e.reason}") from e
    except json.JSONDecodeError as e:
        _last_request_time = time.time()
        raise RuntimeError(f"PRTS API 返回了无效的 JSON: {e}") from e


def _get_page_wikitext(title: str) -> Optional[str]:
    """
    通过 PRTS API 获取页面 wikitext 内容

    Args:
        title: 页面标题（如 "阿米娅"、"魔王"）

    Returns:
        Wikitext 字符串，页面不存在时返回 None
    """
    data = _prts_api_request({
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvlimit": "1",
    })

    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if "missing" in page:
            return None
        revisions = page.get("revisions", [])
        if revisions:
            return revisions[0].get("*", "")

    return None


# ──────────────────────────────────────────────
# 文本清洗
# ──────────────────────────────────────────────

def _extract_template_body(wikitext: str, template_name: str) -> Optional[str]:
    """从 wikitext 中提取指定模板的主体内容，正确处理嵌套 {{}}

    与简单的正则不同，此函数通过计数大括号深度来匹配模板边界，
    因此模板内部包含 {{color|...}} 等嵌套模板时不会提前截断。

    Args:
        wikitext: 完整的 wikitext 文本
        template_name: 模板名（如 "CharinfoV2"、"人员档案" 等）

    Returns:
        模板主体文本（含 | 字段行），未找到时返回 None
    """
    # 构建模板开始标记的转义正则
    escaped_name = re.escape(template_name)
    start_pattern = re.compile(r"\{\{" + escaped_name + r"\s*\n")
    start_match = start_pattern.search(wikitext)
    if not start_match:
        return None

    # 从模板开始位置计数大括号深度
    pos = start_match.end()  # 跳过 {{TemplateName\n
    depth = 1  # 已经进入了第一层 {{
    body_start = pos

    while pos < len(wikitext) and depth > 0:
        # 查找下一个 {{ 或 }}
        next_open = wikitext.find("{{", pos)
        next_close = wikitext.find("}}", pos)

        if next_close == -1:
            # 没有找到闭合，返回已匹配的内容
            break

        if next_open != -1 and next_open < next_close:
            # 先遇到 {{
            depth += 1
            pos = next_open + 2
        else:
            # 先遇到 }}
            depth -= 1
            pos = next_close + 2
            if depth == 0:
                # 模板闭合，返回内部内容
                return wikitext[body_start:next_close]

    # 未找到完整闭合，返回可能不完整的匹配
    return wikitext[body_start:pos] if depth <= 0 else None

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


def _clean_voice_line(raw: str) -> str:
    """从语音台词中提取中文文本，移除 VoiceData 模板标记"""
    # 提取中文部分：{{VoiceData/word|中文|内容}}
    zh_match = re.search(r"\{\{VoiceData/word\|中文\|(.+?)\}\}", raw)
    if zh_match:
        return zh_match.group(1)
    # fallback：直接清洗
    return clean_wikitext(raw)


# ──────────────────────────────────────────────
# PRTS Wiki 解析 — 元数据
# ──────────────────────────────────────────────

def parse_prts_operator_name(name: str) -> dict:
    """
    从 PRTS Wiki 角色名构造 URL 和 slug

    PRTS URL 格式: https://prts.wiki/w/{角色名}
    """
    slug = to_slug(name)
    url = f"https://prts.wiki/w/{quote(name)}"
    return {"slug": slug, "source_url": url}


# ──────────────────────────────────────────────
# PRTS Wiki 解析 — 干员信息
# ──────────────────────────────────────────────

def _extract_charinfo(wikitext: str) -> dict:
    """
    从干员页面的 CharinfoV2 或 Charinfo 模板中提取基本信息
    """
    info = {}

    # 使用深度计数匹配，正确处理嵌套 {{}}
    # 拆分为精确匹配，避免 Charinfo 误匹配 CharinfoV2 的内容
    fields = _extract_template_body(wikitext, "CharinfoV2")
    if not fields:
        fields = _extract_template_body(wikitext, "Charinfo")
    if not fields:
        return info

    # 字段映射：wikitext key → output key
    field_map = {
        "干员名": "name_zh",
        "干员外文名": "name_en",
        "稀有度": "rarity",
        "职业": "profession",
        "分支": "branch",
        "所属国家": "country",
        "所属组织": "faction",
        "位置": "position",
        "标签": "tags",
        "画师": "artist",
        "中文配音": "cv_zh",
    }

    for line in fields.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        # 去掉前导 |
        line = line[1:]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if key in field_map and value:
            output_key = field_map[key]
            # 清洗模板标记
            value = re.sub(r"\{\{color\|[^|]*\|([^}]*)\}\}", r"\1", value)
            value = re.sub(r"\{\{[^{}]*\}\}", "", value)
            value = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", value)
            value = value.strip()
            if value:
                info[output_key] = value

    return info


def _extract_enemy_info(wikitext: str) -> dict:
    """
    从敌人/NPC 页面的 敌人信息 模板中提取基本信息
    （适用于特蕾西娅等非干员角色）
    """
    info = {}

    # 匹配 {{敌人信息/xxx ... }}，使用深度计数处理嵌套
    # 先找出所有敌人信息模板的名称
    template_name_match = re.search(r"\{\{敌人信息/([a-z0-9]+)\s*\n", wikitext)
    if not template_name_match:
        return info

    full_template_name = f"敌人信息/{template_name_match.group(1)}"
    fields = _extract_template_body(wikitext, full_template_name)
    if not fields:
        return info

    field_map = {
        "名称": "name_zh",
        "地位级别": "threat_level",
        "描述": "description",
        "伤害类型": "damage_type",
        "攻击方式": "attack_type",
        "种类": "race",
    }

    for line in fields.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        line = line[1:]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in field_map and value:
            value = re.sub(r"\{\{color\|[^|]*\|([^}]*)\}\}", r"\1", value)
            value = re.sub(r"\{\{[^{}]*\}\}", "", value)
            value = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", value)
            info[field_map[key]] = value.strip()

    # 从能力字段提取行为描述
    ability_match = re.search(r"\|能力\s*=\s*(.*?)(?=\n\||\n?\}\})", fields, re.DOTALL)
    if ability_match:
        ability_text = ability_match.group(1).strip()
        ability_text = re.sub(r"\{\{color\|[^|]*\|([^}]*)\}\}", r"\1", ability_text)
        ability_text = re.sub(r"\{\{[^{}]*\}\}", "", ability_text)
        ability_text = re.sub(r"<br\s*/?>", "\n", ability_text)
        info["abilities_raw"] = ability_text.strip()

    return info


def _extract_archives(wikitext: str) -> list[dict]:
    """
    从干员档案模板中提取档案文本

    格式: {{人员档案 |档案1=标题 |档案1文本=内容 ...}}
    """
    archives = []

    # 匹配 {{人员档案 ... }}，使用深度计数处理嵌套
    fields = _extract_template_body(wikitext, "人员档案")
    if not fields:
        # fallback：尝试旧格式 ==干员档案== 区域
        archive_section = re.search(
            r"==\s*干员档案\s*==\n(.*?)(?=\n==[^=])",
            wikitext,
            re.DOTALL,
        )
        if archive_section:
            archives.append({
                "index": 0,
                "title": "干员档案",
                "text": clean_wikitext(archive_section.group(1))[:500],
            })
        return archives

    # 提取所有档案条目
    # 终止条件：下一个 |档案N= 或字符串末尾（_extract_template_body 已移除尾部 }}）
    for m in re.finditer(r"\|档案(\d+)=([^\n|]+)\s*\n\s*\|档案\1条件=[^\n]*\n\s*\|档案\1文本=(.*?)(?=\n\s*\|档案\d+=|$)", fields, re.DOTALL):
        idx = int(m.group(1))
        title = m.group(2).strip()
        text = m.group(3).strip()
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = clean_wikitext(text)
        if text:
            archives.append({"index": idx, "title": title, "text": text})

    return archives


def _extract_voice_lines(wikitext: str) -> list[dict]:
    """
    从语音记录模板中提取语音台词

    格式: |标题1=xxx |台词1={{VoiceData/word|中文|内容}} ...
    """
    lines = []

    for m in re.finditer(r"\|标题(\d+)\s*=\s*([^\n|]+)\s*\n\s*\|台词\1\s*=\s*(.*?)(?=\n\s*\|标题\d+=|\n\s*\|语音\d+=|$)", wikitext, re.DOTALL):
        label = m.group(2).strip()
        raw_text = m.group(3).strip()
        text = _clean_voice_line(raw_text)
        if text:
            lines.append({"label": label, "text": text})

    return lines


def _extract_profile_fields(wikitext: str) -> dict:
    """
    从 {{人员档案set}} 模板中提取基础档案字段（种族、出身地等）
    """
    info = {}

    fields = _extract_template_body(wikitext, "人员档案set")
    if not fields:
        return info

    field_map = {
        "性别": "gender",
        "战斗经验": "combat_experience",
        "出身地": "birthplace",
        "生日": "birthday",
        "种族": "race",
        "身高": "height",
        "矿石病感染情况": "infection_status",
        "是否感染者": "is_infected",
    }

    for line in fields.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        line = line[1:]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in field_map and value and value != "未公开":
            info[field_map[key]] = value

    return info


def _extract_attribute_fields(wikitext: str) -> dict:
    """
    从 {{属性}} 模板提取属性信息（所属势力等）
    """
    info = {}

    fields = _extract_template_body(wikitext, "属性")
    if not fields:
        return info

    field_map = {
        "所属势力": "faction",
        "隐藏势力": "hidden_faction",
    }

    for line in fields.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        line = line[1:]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key in field_map and value:
            info[field_map[key]] = value

    return info


# ──────────────────────────────────────────────
# PRTS Wiki 解析 — 主入口
# ──────────────────────────────────────────────

def fetch_and_parse_prts(name: str, lang: str = "zh") -> dict:
    """
    从 PRTS Wiki 获取并解析角色数据

    工作流：
    1. 请求角色主页 wikitext
    2. 自动识别页面类型（干员/敌人/NPC）
    3. 提取基本信息、档案、语音等
    4. 如果是干员且有语音子页面，额外获取语音记录

    Args:
        name: 角色名称（中文）
        lang: 语言偏好

    Returns:
        结构化角色数据 dict
    """
    result = {
        **parse_prts_operator_name(name),
        "source": "prts",
        "lang": lang,
    }

    # Step 1: 获取主页面 wikitext
    print(f"正在从 PRTS Wiki 获取「{name}」...", file=sys.stderr)
    wikitext = _get_page_wikitext(name)

    if wikitext is None:
        result["error"] = f"PRTS Wiki 上未找到「{name}」页面"
        result["suggestion"] = (
            "可能原因：1) 角色名拼写有误；"
            "2) 该角色在 PRTS 上使用不同名称（如特蕾西娅的干员版为「魔王」）；"
            "3) 该角色尚未有独立页面。"
        )
        return result

    # Step 2: 识别页面类型并提取基本信息
    page_type = _detect_page_type(wikitext)
    result["page_type"] = page_type

    if page_type == "operator":
        # 干员页面
        charinfo = _extract_charinfo(wikitext)
        result.update(charinfo)

        # 提取属性（势力等）
        attrs = _extract_attribute_fields(wikitext)
        if attrs.get("faction") and not result.get("faction"):
            result["faction"] = attrs["faction"]

        # 提取基础档案（种族、出身地等）
        profile = _extract_profile_fields(wikitext)
        for key, value in profile.items():
            if key == "race" and value and not result.get("race"):
                result["race"] = value
            elif not result.get(key):
                result[key] = value

        # 提取档案文本
        archives = _extract_archives(wikitext)
        if archives:
            result["archives"] = archives

        # 提取语音（可能在子页面）
        voice_lines = _extract_voice_lines(wikitext)
        if not voice_lines:
            # 尝试从子页面获取
            voice_lines = _fetch_voice_subpage(name)
        if voice_lines:
            result["voice_lines"] = voice_lines

    elif page_type == "enemy":
        # 敌人/NPC 页面
        enemy_info = _extract_enemy_info(wikitext)
        result.update(enemy_info)

        # 尝试获取基础档案（部分敌人页面也有）
        profile = _extract_profile_fields(wikitext)
        for key, value in profile.items():
            if key == "race" and value and not result.get("race"):
                result["race"] = value
            elif not result.get(key):
                result[key] = value

    else:
        # 未知页面类型，尝试通用提取
        result["raw_length"] = len(wikitext)
        result["note"] = f"页面类型未识别（{page_type}），已提取基本元数据"

        # 尝试提取任何看起来像角色信息的字段
        for pattern, key in [
            (r"\|\s*种族\s*=\s*([^\n|]+)", "race"),
            (r"\|\s*阵营\s*=\s*([^\n|]+)", "faction"),
            (r"\|\s*职业\s*=\s*([^\n|]+)", "profession"),
            (r"\|\s*描述\s*=\s*([^\n|]+)", "description"),
        ]:
            m = re.search(pattern, wikitext)
            if m and not result.get(key):
                result[key] = m.group(1).strip()

    result["fetch_time"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return result


def _detect_page_type(wikitext: str) -> str:
    """检测 PRTS 页面类型"""
    if re.search(r"\{\{CharinfoV?2?\b", wikitext):
        return "operator"
    if re.search(r"\{\{敌人信息/", wikitext):
        return "enemy"
    if re.search(r"==\s*干员档案\s*==", wikitext):
        return "operator"
    return "unknown"


def _fetch_voice_subpage(name: str) -> list[dict]:
    """
    尝试从「角色名/语音记录」子页面获取语音数据
    """
    voice_title = f"{name}/语音记录"
    voice_wikitext = _get_page_wikitext(voice_title)
    if voice_wikitext is None:
        return []
    return _extract_voice_lines(voice_wikitext)


# ──────────────────────────────────────────────
# 旧接口兼容：从 wikitext 提取（供 --source local 使用）
# ──────────────────────────────────────────────

def extract_operator_data_from_wikitext(wikitext: str, name: str) -> dict:
    """
    从 PRTS Wiki 的 wikitext 中提取角色信息

    此函数保留用于向后兼容，推荐使用 fetch_and_parse_prts() 获取更完整的数据。
    """
    data = {
        "name_zh": name,
        "slug": to_slug(name),
        "source": "prts",
    }

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

    # 提取档案
    archives = _extract_archives(wikitext)
    if archives:
        data["archives"] = archives

    # 提取语音
    voice_lines = _extract_voice_lines(wikitext)
    if voice_lines:
        data["voice_lines"] = voice_lines

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
    "魔王": "mo-wang",
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

    # 无法转换，提示用户手动指定
    slug = re.sub(r"\s+", "-", name.lower())
    if not re.match(r"^[a-z0-9-]+$", slug):
        # 使用拼音映射表中逐字符查找，剩余字符用简短标记替代
        safe_slug = ""
        for ch in name:
            if re.match(r"[a-zA-Z0-9\s-]", ch):
                safe_slug += ch.lower()
            elif ch in PINYIN_MAP:
                safe_slug += PINYIN_MAP[ch]
            else:
                # 不再使用冗长的 Unicode 编码，改用简短标记
                safe_slug += f"?"
        safe_slug = re.sub(r"\?+", "", safe_slug)  # 移除未知字符标记
        safe_slug = re.sub(r"\s+", "-", safe_slug).strip("-")
        if not safe_slug:
            safe_slug = f"op-{hash(name) % 10000:04d}"
        print(
            f"警告：角色名 '{name}' 无法自动转为 URL-safe slug，"
            f"已使用 fallback '{safe_slug}'，"
            "建议手动指定英文 slug 或 pip install pypinyin",
            file=sys.stderr,
        )
        return safe_slug
    return slug


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="明日方舟角色资料解析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 PRTS Wiki 直接获取并解析角色信息
  python game_data_parser.py --source prts --name 阿米娅
  python game_data_parser.py --source prts --name 魔王

  # 解析本地 Markdown 文件
  python game_data_parser.py --source local --file ./raw_data/theresa.md

  # 仅生成 slug
  python game_data_parser.py --slug-only --name 特蕾西娅
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
        "--metadata-only",
        action="store_true",
        help="仅输出元数据（slug + URL），不做 HTTP 请求",
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

        if args.metadata_only:
            # 仅生成元数据模式（兼容旧行为）
            result = {
                **parse_prts_operator_name(args.name),
                "lang": args.lang,
                "note": "元数据模式，未获取页面内容。去掉 --metadata-only 可自动获取并解析。",
            }
        else:
            # 完整解析模式
            try:
                result = fetch_and_parse_prts(args.name, args.lang)
            except RuntimeError as e:
                # 网络不可用时降级为元数据模式
                result = {
                    **parse_prts_operator_name(args.name),
                    "lang": args.lang,
                    "error": f"无法获取 PRTS 数据: {e}",
                    "fallback": "元数据模式（网络不可用）",
                    "suggestion": "请检查网络连接，或使用 --source local 手动解析本地文件。",
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
