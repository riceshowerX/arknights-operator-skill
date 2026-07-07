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
from typing import TypedDict
from urllib.parse import quote

# 确保 tools 目录在 import 路径中
_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from prts_client import fetch_page_wikitext as _prts_fetch_wikitext
from prts_client import prts_api_get
from shared_utils import setup_logging

logger = setup_logging("game_data_parser")


class _OperatorDataRequired(TypedDict):
    """角色数据 — 必填字段（核心标识，缺失则无法定位角色）"""

    name_zh: str
    slug: str
    source_url: str


class OperatorData(_OperatorDataRequired, total=False):
    """角色数据 — 可选字段（从 PRTS 解析，可能因页面格式而缺失）

    必填字段继承自 _OperatorDataRequired:
        name_zh: 角色中文名
        slug: URL 安全标识符
        source_url: PRTS 页面 URL

    以下为可选字段:
    """

    name_en: str
    race: str
    faction: str
    identity: str
    mbti: str
    personality_type: str
    core_traits: list[str]
    speech_style: str
    archives: list[dict]
    voice_lines: list[dict]
    tags: list[str]
    page_type: str


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
# PRTS API 请求（委托给 prts_client）
# ──────────────────────────────────────────────

def _get_page_wikitext(title: str) -> str | None:
    """通过 prts_client 获取页面 wikitext 内容

    Args:
        title: 页面标题（如 "阿米娅"、"魔王"）

    Returns:
        Wikitext 字符串，页面不存在或获取失败时返回 None
    """
    # 优先使用 prts_client 的 parse API（自动跟随 redirect）
    wikitext = _prts_fetch_wikitext(title, follow_redirects=True)
    if wikitext:
        return wikitext

    # fallback: 通过 revisions API 检查页面是否存在
    data = prts_api_get({
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvlimit": "1",
    })
    pages = data.get("query", {}).get("pages", {})
    for _page_id, page in pages.items():
        if "missing" in page:
            return None
        revisions = page.get("revisions", [])
        if revisions:
            return revisions[0].get("*", "")

    return None


# ──────────────────────────────────────────────
# 文本清洗
# ──────────────────────────────────────────────

def _extract_template_body(wikitext: str, template_name: str) -> str | None:
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
    # 支持两种格式: {{TemplateName\n...}} 和 {{TemplateName|...}}
    start_pattern = re.compile(r"\{\{" + escaped_name + r"(?:\s*\n|\s*\|)")
    start_match = start_pattern.search(wikitext)
    if not start_match:
        return None

    # 判断模板名后紧跟的是换行还是 |
    matched_suffix = start_match.group(0)
    starts_with_pipe = matched_suffix.endswith("|")

    # 从模板开始位置计数大括号深度
    pos = start_match.end()  # 跳过 {{TemplateName\n 或 {{TemplateName|
    depth = 1  # 已经进入了第一层 {{
    body_start = pos
    max_depth = 50  # 防止恶意嵌套导致长时间运行

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
            if depth > max_depth:
                logger.warning("模板嵌套深度超过 %d，可能为异常数据", max_depth)
                break
            pos = next_open + 2
        else:
            # 先遇到 }}
            depth -= 1
            pos = next_close + 2
            if depth == 0:
                # 模板闭合，返回内部内容
                body = wikitext[body_start:next_close]
                # 如果模板名后紧跟的是 |（如 {{TemplateName|...}}），
                # 补回开头的 |，使解析逻辑与 {{TemplateName\n|...}} 一致
                if starts_with_pipe and not body.startswith("|"):
                    body = "|" + body
                return body

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

    # 预编译清洗正则，避免循环内重复编译
    _COLOR_RE = re.compile(r"\{\{color\|[^|]*\|([^}]*)\}\}")  # noqa: N806  (模块常量风格)
    _TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")  # noqa: N806  (模块常量风格)
    _WIKILINK_RE = re.compile(r"\[\[([^|\]]*\|)?([^\]]*)\]\]")  # noqa: N806  (模块常量风格)

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
            # 清洗模板标记（使用预编译正则）
            value = _COLOR_RE.sub(r"\1", value)
            value = _TEMPLATE_RE.sub("", value)
            value = _WIKILINK_RE.sub(r"\2", value)
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
    # 先检测是否存在档案字段
    archive_keys = set(re.findall(r"\|档案(\d+)=", fields))
    if not archive_keys:
        return archives

    archive_pattern = re.compile(
        r"\|档案(\d+)=([^\n|]+)\s*\n\s*\|档案\1条件=[^\n]*\n\s*\|档案\1文本=(.*?)(?=\n\s*\|档案\d+=|$)",
        re.DOTALL,
    )
    matched_indices = set()
    for m in archive_pattern.finditer(fields):
        idx = int(m.group(1))
        matched_indices.add(str(idx))
        title = m.group(2).strip()
        text = m.group(3).strip()
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = clean_wikitext(text)
        if text:
            archives.append({"index": idx, "title": title, "text": text})

    # 格式变动检测：预期字段存在但正则未匹配
    missed = archive_keys - matched_indices
    if missed:
        logger.warning(
            "档案格式可能已变动：以下档案编号存在于模板中但正则未匹配到完整条目：%s。"
            "请检查 PRTS Wiki 模板格式是否发生变化。",
            sorted(missed, key=int),
        )

    return archives


def _extract_voice_lines(wikitext: str) -> list[dict]:
    """
    从语音记录模板中提取语音台词

    格式: |标题1=xxx |台词1={{VoiceData/word|中文|内容}} ...
    """
    lines = []

    for m in re.finditer(r"\|标题(\d+)\s*=\s*([^\n|]+)\s*\n\s*\|台词\1\s*=\s*(.*?)(?=\n\s*\|标题\d+=|\n\s*\|语音\d+=|$)", wikitext, re.DOTALL):  # noqa: E501  (中文消息折行破坏可读性)
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

def fetch_and_parse_prts(name: str, lang: str = "zh") -> OperatorData:
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
    logger.info("正在从 PRTS Wiki 获取「%s」...", name)
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
    """检测 PRTS 页面类型

    使用精确枚举匹配模板名，避免脆弱的可选字符正则。
    """
    # 精确匹配 CharinfoV2 或 Charinfo 模板（模板名后必须紧跟换行或 |）
    if re.search(r"\{\{(?:CharinfoV2|Charinfo)(?:\s*\n|\s*\|)", wikitext):
        return "operator"
    if re.search(r"\{\{敌人信息/", wikitext):
        return "enemy"
    # fallback: 检查是否有干员档案区域
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
    """从 PRTS Wiki 的 wikitext 中提取角色信息

    此函数保留用于向后兼容，推荐使用 fetch_and_parse_prts() 获取更完整的数据。

    Returns:
        角色数据字典，含 ``_parse_report`` 子字典记录解析诊断信息。
        ``_parse_report`` 结构：
        - ``parsed_fields``: 成功提取的字段名列表
        - ``missing_fields``: 期望但未能提取的字段名列表
        - ``warnings``: 解析过程中的警告列表
        - ``wikitext_length``: 原始 wikitext 字符数
        - ``wikitext_snippet``: 前 200 字符预览（用于调试格式问题）
    """
    # 解析报告
    report = {
        "parsed_fields": [],
        "missing_fields": [],
        "warnings": [],
        "wikitext_length": len(wikitext),
        "wikitext_snippet": wikitext[:200] if wikitext else "",
    }

    # 期望提取的字段
    expected_fields = ["race", "faction", "profession", "archives", "voice_lines"]

    data = {
        "name_zh": name,
        "slug": to_slug(name),
        "source": "prts",
    }

    # 检测 wikitext 是否为空或过短
    if not wikitext or len(wikitext.strip()) < 20:
        report["warnings"].append(
            f"wikitext 过短或为空（{len(wikitext)} 字符），可能无法提取有效数据"
        )
        data["_parse_report"] = report
        report["missing_fields"] = expected_fields
        return data

    # 检测是否包含标准信息框
    has_infobox = bool(re.search(r"\{\{[^{}]*干员[^{}]*\}\}", wikitext))
    if not has_infobox:
        report["warnings"].append(
            "未检测到标准干员信息框（{{干员|...}}），页面格式可能非标准"
        )

    # 提取种族
    race_match = re.search(r"\|\s*种族\s*=\s*([^\n|]+)", wikitext)
    if race_match:
        data["race"] = race_match.group(1).strip()
        report["parsed_fields"].append("race")
    else:
        report["missing_fields"].append("race")
        # 尝试替代模式
        alt_race = re.search(r"\|\s*race\s*=\s*([^\n|]+)", wikitext)
        if alt_race:
            data["race"] = alt_race.group(1).strip()
            report["parsed_fields"].append("race")
            report["warnings"].append("种族字段通过替代模式 (race=) 提取")

    # 提取阵营/阵营
    faction_match = re.search(r"\|\s*阵营\s*=\s*([^\n|]+)", wikitext)
    if faction_match:
        data["faction"] = faction_match.group(1).strip()
        report["parsed_fields"].append("faction")
    else:
        report["missing_fields"].append("faction")
        alt_faction = re.search(r"\|\s*(?:group|faction)\s*=\s*([^\n|]+)", wikitext)
        if alt_faction:
            data["faction"] = alt_faction.group(1).strip()
            report["parsed_fields"].append("faction")
            report["warnings"].append("阵营字段通过替代模式提取")

    # 提取职业
    profession_match = re.search(r"\|\s*职业\s*=\s*([^\n|]+)", wikitext)
    if profession_match:
        data["profession"] = profession_match.group(1).strip()
        report["parsed_fields"].append("profession")
    else:
        report["missing_fields"].append("profession")

    # 提取档案
    archives = _extract_archives(wikitext)
    if archives:
        data["archives"] = archives
        report["parsed_fields"].append("archives")
        if len(archives) < 2:
            report["warnings"].append(
                f"仅提取到 {len(archives)} 条档案，可能不完整（通常 4+ 条）"
            )
    else:
        report["missing_fields"].append("archives")
        report["warnings"].append("未能提取任何档案内容，Wikitext 格式可能不匹配")

    # 提取语音
    voice_lines = _extract_voice_lines(wikitext)
    if voice_lines:
        data["voice_lines"] = voice_lines
        report["parsed_fields"].append("voice_lines")
        if len(voice_lines) < 5:
            report["warnings"].append(
                f"仅提取到 {len(voice_lines)} 条语音，可能不完整"
            )
    else:
        report["missing_fields"].append("voice_lines")
        report["warnings"].append("未能提取任何语音内容，Wikitext 格式可能不匹配")

    # 附加解析报告
    data["_parse_report"] = report
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

# 角色名拼音映射表（从外部配置文件加载）
_PINYIN_MAP_PATH = Path(__file__).parent.parent / "data" / "pinyin_map.json"
PINYIN_MAP: dict[str, str] = {}
if _PINYIN_MAP_PATH.exists():
    with open(_PINYIN_MAP_PATH, encoding="utf-8") as _f:
        PINYIN_MAP = json.load(_f)


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
                safe_slug += "?"
        safe_slug = re.sub(r"\?+", "", safe_slug)  # 移除未知字符标记
        safe_slug = re.sub(r"\s+", "-", safe_slug).strip("-")
        if not safe_slug:
            safe_slug = f"op-{hash(name) % 10000:04d}"
        logger.warning(
            "角色名 '%s' 无法自动转为 URL-safe slug，"
            "已使用 fallback '%s'，"
            "建议手动指定英文 slug 或 pip install pypinyin",
            name, safe_slug,
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


def _output(data: dict, filepath: str | None = None):
    """输出 JSON 数据"""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if filepath:
        Path(filepath).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
