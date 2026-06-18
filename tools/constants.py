#!/usr/bin/env python3
"""
共享常量模块 —— 所有工具的领域知识常量统一来源

将原本分散在 context_annotator.py、phase_inferrer.py、story_extractor.py、
speech_act_analyzer.py、temporal_slicer.py 中的重复常量集中管理。

用法：
    from constants import PHASE_ORDER, PHASE_PATTERNS, PHASE_KEYWORDS, ...
"""

import re

# ──────────────────────────────────────────────
# 时期相关常量
# ──────────────────────────────────────────────

# 已知的时期列表（按时序排列）
PHASE_ORDER: list[str] = ["early", "babel", "resurrected"]

# 内容精确匹配（正则）— 优先级最高
PHASE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"魔王.{0,10}(?:卡兹戴尔|回归|归来)"), "babel"),
    (re.compile(r"(?:复活|苏醒|重获).{0,10}(?:身体|力量|记忆)"), "resurrected"),
]

# 内容关键词匹配 — 次优先
PHASE_KEYWORDS: dict[str, list[str]] = {
    "babel": ["巴别塔", "内战", "卡兹戴尔重建", "和平协议", "卡兹戴尔的和平"],
    "resurrected": ["黑冠", "赦罪师", "巫术"],
}

# 章节代码快速映射
CHAPTER_PHASE_MAP: dict[str, str] = {
    "第0章": "early",
    "第1章": "early",
    "第2章": "early",
    "第3章": "early",
    "第4章": "early",
    "第5章": "early",
    "第6章": "early",
    "第7章": "early",
    "第8章": "babel",
    "第9章": "babel",
    "第10章": "resurrected",
    "第11章": "resurrected",
    "第12章": "resurrected",
    "第13章": "resurrected",
    "第14章": "resurrected",
    "BB-": "babel",
    "LT-": "resurrected",
    "H10-": "resurrected",
    "H11-": "resurrected",
    "H12-": "resurrected",
    "H14-": "resurrected",
    "DM-": "early",
    "WD-": "early",
    "CC-": "unknown",
}

# 活动名称 → 时期
ACTIVITY_PHASE_MAP: dict[str, str] = {
    "巴别塔": "babel",
    "慈悲灯塔": "resurrected",
    "伦蒂尼姆": "resurrected",
    "生于黑夜": "early",
    "切尔诺伯格": "early",
    "遗尘漫步": "early",
}

# PRTS 分类标签 → 时期
FACTION_CATEGORY_PHASE: dict[str, str] = {
    "属于巴别塔的干员": "babel",
    "属于罗德岛的干员": "resurrected",
    "属于整合运动的干员": "early",
    "属于卡兹戴尔的干员": "early",
    "属于维多利亚的干员": "resurrected",
    "属于拉特兰的干员": "early",
    "属于莱塔尼亚的干员": "early",
    "属于乌萨斯的干员": "early",
    "属于炎国的干员": "early",
    "属于汐斯塔的干员": "early",
}

# 内容聚类关键词 — 用于 fallback 推断
CLUSTER_KEYWORDS: dict[str, list[str]] = {
    "early": [
        "切尔诺伯格", "整合运动", "塔露拉", "天灾", "矿石病", "感染者",
        "佣兵", "雇佣兵", "战场", "撤退", "行动",
    ],
    "babel": [
        "巴别塔", "特蕾西娅", "特雷西斯", "卡兹戴尔", "内战", "萨卡兹",
        "王旗", "正统", "摄政王", "和平协议",
    ],
    "resurrected": [
        "伦蒂尼姆", "飞空艇", "黑冠", "赦罪师", "巫术", "复活",
        "飞地", "城防", "维多利亚",
    ],
}

# 干员页面名 → 语音行默认时期（快速路径 / 离线缓存）
# 新增角色时无需手动添加 — phase_inferrer 会从 PRTS 分类标签自动推断
OPERATOR_DEFAULT_PHASE: dict[str, str] = {
    "魔王": "resurrected",
    "W": "early",
}

# ──────────────────────────────────────────────
# 语音行相关常量
# ──────────────────────────────────────────────

# 语音标题 → 对话对象
VOICE_INTERLOCUTOR_MAP: dict[str, str | None] = {
    "信赖触摸": "博士",
    "晋升后交谈1": "博士",
    "晋升后交谈2": "博士",
    "精二晋升后交谈": "博士",
    "任命助理": "博士",
    "4星结束": None,
    "3星结束": None,
}

# 语音标题 → 场景类型（按特异性从高到低排列）
VOICE_SITUATION_MAP: list[tuple[str, str]] = [
    ("信赖触摸", "comfort"),
    ("信赖", "comfort"),
    ("战斗开始", "confront"),
    ("战斗失败", "confront"),
    ("精二晋升后交谈", "casual"),
    ("晋升后交谈", "casual"),
    ("晋升", "casual"),
    ("助理", "casual"),
    ("交谈", "casual"),
    ("进驻", "casual"),
    ("编入", "casual"),
    ("精英化", "casual"),
]

# ──────────────────────────────────────────────
# 话语行为类型标签
# ──────────────────────────────────────────────

ACT_TYPE_LABELS: dict[str, str] = {
    "invite": "邀请/请求",
    "evade": "回避/转移",
    "question": "提问/反问",
    "commit": "承诺/表态",
    "console": "安慰/共情",
    "restrain": "克制/隐忍",
    "affirm_presence": "存在确认",
    "promise_remember": "记忆承诺",
    "farewell": "告别/嘱托",
    "soothe": "安抚/劝解",
}

# ──────────────────────────────────────────────
# 场景类型关键词
# ──────────────────────────────────────────────

SITUATION_KEYWORDS: dict[str, list[str]] = {
    "confront": ["战斗", "敌", "进攻", "撤退", "交战", "对峙", "冲突", "攻击", "防线"],
    "comfort": ["安慰", "不必", "没关系", "不是你的错", "不要紧", "已经足够"],
    "decide": ["决定", "必须", "只能如此", "没有选择", "别无选择", "这是我的选择"],
    "reminisce": ["回忆", "过去", "曾经", "记得", "那时候", "还记得", "从前"],
    "command": ["命令", "执行", "立刻", "全员", "出发", "集合"],
}

# ──────────────────────────────────────────────
# PRTS API 常量
# ──────────────────────────────────────────────

PRTS_API_URL: str = "https://prts.wiki/api.php"
PRTS_USER_AGENT: str = "arknights-operator-skill/2.0"
PRTS_REQUEST_TIMEOUT: int = 15
PRTS_REQUEST_INTERVAL: float = 0.5  # 最小请求间隔（秒）

# ──────────────────────────────────────────────
# 安全相关
# ──────────────────────────────────────────────

# slug 格式验证正则：仅允许小写字母、数字和连字符
SLUG_RE: re.Pattern = re.compile(r'^[a-z0-9][-a-z0-9]*$')

# 正则复杂度限制（防止 ReDoS）
MAX_REGEX_LENGTH: int = 500
MAX_REGEX_REPETITION_NESTING: int = 3

# ──────────────────────────────────────────────
# 剧情提取相关正则
# ──────────────────────────────────────────────

# 场景标题正则（wikitext 中 === 标题 === 或 == 标题 ==）
SCENE_HEADER_RE: re.Pattern = re.compile(r'^={2,4}\s*(.+?)\s*={2,4}', re.MULTILINE)

# Wikitext 对话行正则（'''角色名'''：台词）
WIKITEXT_DIALOGUE_RE: re.Pattern = re.compile(
    r"""[''\u2018\u2019]{2,3}(.+?)[''\u2018\u2019]{2,3}[：:]\s*(.+?)(?:\n|$)"""
)

# 剧情模拟器脚本格式正则：[name="角色名"]对话内容
SCRIPT_DIALOGUE_RE: re.Pattern = re.compile(
    r'\[name="([^"]+)"\](.*?)(?=\[name="|\[决策|\[选项|$)',
    re.DOTALL,
)

# 脚本控制指令正则（需要过滤掉）
SCRIPT_CONTROL_RE: re.Pattern = re.compile(
    r'\[PlayMusic[^\]]*\]|\[StopMusic[^\]]*\]'
    r'|\[soundchannel[^\]]*\]|\[SoundChannel[^\]]*\]'
    r'|\[delay[^\]]*\]|\[Delay[^\]]*\]'
)

# 时间线正则（从 knowledge.md 提取）
TIMELINE_RE: re.Pattern = re.compile(r'###\s*(\d{3,4})\s*[-–—]\s*(\d{3,4})\s*(.+)')
