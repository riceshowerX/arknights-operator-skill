#!/usr/bin/env python3
"""
设定交叉验证器 —— 从多个来源交叉验证角色设定，标注矛盾和可信度

这是 arknights-operator-skill 的核心差异化工具之一：
游戏角色的设定常有社区误解或翻译差异，本工具通过多来源交叉验证，
标注哪些设定有可靠依据、哪些存在矛盾。

用法:
    # 从多个知识库文件交叉验证
    python canon_checker.py --sources ./knowledge1.md ./knowledge2.md

    # 从知识库 + Wiki 数据验证
    python canon_checker.py --sources ./knowledge.md --wiki-data ./prts_data.json

    # 使用自定义误解库
    python canon_checker.py --sources ./knowledge.md --misconceptions ./misconceptions.json

输出:
    JSON 格式的验证报告，包含每个设定项的来源、一致性和可信度
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# 已知常见误解库（明日方舟特化）
# ──────────────────────────────────────────────

BUILTIN_MISCONCEPTIONS = [
    {
        "id": "M001",
        "wrong": "特蕾西娅是维多利亚的实际统治者",
        "correct": "特蕾西娅是卡兹戴尔正统萨卡兹魔王，维多利亚摄政王是特雷西斯",
        "check_patterns": [
            {
                "pattern": r"特蕾西娅.*维多利亚.*(统治|摄政|女王|掌权)",
                "warning": "可能混淆了特蕾西娅与特雷西斯的身份",
            },
        ],
        "exclude_patterns": [
            r"特雷西斯.*维多利亚.*(摄政|统治)",
            r"维多利亚.*摄政.*特雷西斯",
            r"特蕾西娅[^，。]*不是.*维多利亚",
        ],
    },
    {
        "id": "M002",
        "wrong": "特蕾西娅属于整合运动",
        "correct": "特蕾西娅创立的是巴别塔（罗德岛前身），整合运动是塔露拉领导的独立组织",
        "check_patterns": [
            {
                "pattern": r"特蕾西娅.*整合运动",
                "warning": "特蕾西娅不属于整合运动",
            },
        ],
        "exclude_patterns": [
            r"特蕾西娅[^，。]*不属于?整合运动",
            r"特蕾西娅[^，。]*不是.*整合运动",
        ],
    },
    {
        "id": "M003",
        "wrong": "「让所有人为我而死，这便是慈悲」是特蕾西娅的理念",
        "correct": "这不是她的理念或原话，她主张和平重建、尽量减少牺牲",
        "check_patterns": [
            {
                "pattern": r"为我而死.*慈悲|慈悲.*为我而死",
                "warning": "这不是特蕾西娅的理念",
            },
            {
                "pattern": r"让所有人.*死.*慈悲",
                "warning": "错误归因——这不是特蕾西娅的原话",
            },
        ],
        "exclude_patterns": [
            r"不是.*理念",
            r"错误.*归因",
        ],
    },
    {
        "id": "M004",
        "wrong": "特雷西斯是纯粹的恶人",
        "correct": "特雷西斯理念与特蕾西娅对立但并非单纯恶人，曾主动放弃魔王之位为胞妹加冕",
        "check_patterns": [
            {
                "pattern": r"特雷西斯.*(纯粹|完全|绝对是).*恶|邪恶",
                "warning": "过度简化了特雷西斯的角色",
            },
        ],
        "exclude_patterns": [
            r"特雷西斯[^，。]*(不是|并非).*(纯粹|完全|绝对).*恶",
            r"并非单纯.*恶人",
        ],
    },
]


def load_misconceptions(filepath: Optional[str] = None) -> list[dict]:
    """
    加载误解库

    支持从外部 JSON 文件加载自定义误解库，
    格式与 BUILTIN_MISCONCEPTIONS 相同，但 check_patterns
    可以是字符串数组（旧格式）或对象数组（新格式）

    外部文件格式:
    [
        {
            "id": "M005",
            "wrong": "描述",
            "correct": "正确版本",
            "check_patterns": ["正则1", "正则2"]
            // 或 "check_patterns": [{"pattern": "正则", "warning": "警告文字"}]
        }
    ]
    """
    if not filepath:
        return BUILTIN_MISCONCEPTIONS

    path = Path(filepath)
    if not path.exists():
        print(f"警告：误解库文件不存在 {filepath}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    try:
        custom = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"警告：误解库文件格式错误 {filepath}：{e}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    if not isinstance(custom, list):
        print(f"警告：误解库文件应为 JSON 数组 {filepath}，使用内置误解库", file=sys.stderr)
        return BUILTIN_MISCONCEPTIONS

    # 归一化格式：字符串 → 对象
    normalized = []
    for item in custom:
        if not isinstance(item, dict) or "id" not in item:
            continue

        patterns = item.get("check_patterns", [])
        norm_patterns = []
        for p in patterns:
            if isinstance(p, str):
                norm_patterns.append({"pattern": p, "warning": f"匹配到误解模式: {p}"})
            elif isinstance(p, dict) and "pattern" in p:
                norm_patterns.append(p)

        normalized.append({
            "id": item["id"],
            "wrong": item.get("wrong", ""),
            "correct": item.get("correct", ""),
            "check_patterns": norm_patterns,
            "exclude_patterns": item.get("exclude_patterns", []),
        })

    # 合并：内置 + 自定义
    builtin_ids = {m["id"] for m in BUILTIN_MISCONCEPTIONS}
    extra = [m for m in normalized if m["id"] not in builtin_ids]
    overridden = {m["id"]: m for m in normalized if m["id"] in builtin_ids}

    result = []
    for m in BUILTIN_MISCONCEPTIONS:
        if m["id"] in overridden:
            result.append(overridden[m["id"]])
        else:
            result.append(m)
    result.extend(extra)

    return result


# ──────────────────────────────────────────────
# 设定提取
# ──────────────────────────────────────────────

# 关注的设定字段及其提取模式
CANON_FIELDS = {
    "race": {
        "label": "种族",
        "patterns": [
            r"种族[：:]\s*(萨卡兹|卡特斯|佩洛|鲁珀|菲林|瓦伊凡|鬼|德拉克|里拉|黎博利|龙|沃尔珀|阿达克利斯|安努拉|埃德菲尔|菲尼克斯|未知)(?:\s|混血|[，,\n。]|$)",
            r"(?:是|身为)(萨卡兹|卡特斯|佩洛|鲁珀|菲林|瓦伊凡|鬼|德拉克|里拉|黎博利|龙|沃尔珀|未知)",
        ],
    },
    "faction": {
        "label": "阵营",
        "patterns": [
            r"阵营[：:]\s*(巴别塔|罗德岛|整合运动|龙门近卫局|龙门|卡兹戴尔|莱茵生命|喀兰贸易|维多利亚|深池|谢拉格|乌萨斯|炎国|东国|叙拉古|伊比利亚|萨米)(?:\s|[，,\n。]|$)",
            r"(巴别塔|罗德岛|整合运动|龙门|卡兹戴尔|莱茵生命|喀兰贸易|维多利亚|深池)(?:的|创始人|成员|领袖|核心)",
        ],
    },
    "identity": {
        "label": "身份",
        "patterns": [
            r"身份[：:]\s*([^\n,，。]{2,30})",
            r"是([^\n,，。]*?(?:魔王|领袖|摄政王|干员|创始人|指挥官|战士|学者|公爵|骑士|医生|猎人))(?:[，,\n。]|$)",
        ],
    },
    "mbti": {
        "label": "MBTI",
        "patterns": [
            r"MBTI[：:]\s*([A-Z]{4})",
            r"(INFJ|INTJ|INFP|ENFP|ENTJ|ISTJ|ISFJ|ESFJ|ESTJ|ESTP|ESFP|ISTP|ISFP|ENTP|INTP)",
        ],
    },
}


def extract_canon_claims(text: str, source_label: str) -> list[dict]:
    """
    从文本中提取设定声明

    返回: [{"field": "race", "value": "萨卡兹", "source": "xxx", "context": "xxx"}, ...]
    """
    claims = []

    for field, config in CANON_FIELDS.items():
        for pattern in config["patterns"]:
            for match in re.finditer(pattern, text):
                value = match.group(1).strip() if match.lastindex else match.group(0).strip()
                if value and len(value) < 50:
                    # 提取上下文
                    start = max(0, match.start() - 30)
                    end = min(len(text), match.end() + 30)
                    context = text[start:end].strip()

                    claims.append({
                        "field": field,
                        "field_label": config["label"],
                        "value": value,
                        "source": source_label,
                        "context": context,
                    })

    # 去重：同一字段同一值同一来源只保留一条
    seen = set()
    deduped = []
    for c in claims:
        key = (c["field"], c["value"], c["source"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped


def check_misconceptions(
    text: str,
    source_label: str,
    misconceptions: Optional[list[dict]] = None,
) -> list[dict]:
    """
    检查文本中是否包含已知误解

    改进：
    - 支持 exclude_patterns：如果匹配到排除模式，说明文本正在纠正误解，不应报警
    - 上下文验证：检查匹配位置前后是否有否定词，避免将"纠正误解"判定为"含有误解"

    返回: [{"misconception_id": "M001", "matched_pattern": "...", "warning": "...", "source": "xxx"}, ...]
    """
    if misconceptions is None:
        misconceptions = BUILTIN_MISCONCEPTIONS

    warnings = []

    for m in misconceptions:
        # 先检查排除模式
        excluded = False
        for exc_pat in m.get("exclude_patterns", []):
            if re.search(exc_pat, text):
                excluded = True
                break

        if excluded:
            continue

        for cp in m["check_patterns"]:
            pattern = cp["pattern"] if isinstance(cp, dict) else cp
            warning_text = cp.get("warning", "") if isinstance(cp, dict) else f"匹配到误解模式: {pattern}"

            match = re.search(pattern, text)
            if match:
                # 二次验证：检查匹配位置前后是否有否定词
                start = max(0, match.start() - 40)
                end = min(len(text), match.end() + 40)
                surrounding = text[start:end]

                negation_cues = ["不是", "并非", "并不", "没有", "错误", "误解", "不等于", "不同于"]
                is_negation_context = any(cue in surrounding for cue in negation_cues)

                if is_negation_context:
                    # 文本正在纠正误解，不报警
                    continue

                warnings.append({
                    "misconception_id": m["id"],
                    "wrong": m["wrong"],
                    "correct": m["correct"],
                    "matched_pattern": pattern,
                    "matched_text": match.group(0),
                    "warning": warning_text,
                    "source": source_label,
                })

    return warnings


# ──────────────────────────────────────────────
# 交叉验证
# ──────────────────────────────────────────────

def cross_validate(all_claims: list[dict]) -> list[dict]:
    """
    对同一字段的多来源声明进行交叉验证

    规则：
    - 所有来源一致 → confirmed
    - 存在不一致 → conflicted，标注各版本
    - 仅有一个来源 → unverified
    """
    # 按 field 分组
    field_claims = defaultdict(list)
    for claim in all_claims:
        field_claims[claim["field"]].append(claim)

    results = []

    for field, claims in sorted(field_claims.items()):
        # 归一化值（去空格、统一标点）
        normalized_values = {}
        for c in claims:
            nv = c["value"].replace(" ", "").replace("（", "(").replace("）", ")")
            normalized_values.setdefault(nv, []).append(c)

        field_label = claims[0]["field_label"]

        if len(normalized_values) == 1:
            # 所有来源一致
            value = list(normalized_values.keys())[0]
            sources = [c["source"] for c in normalized_values[value]]
            results.append({
                "field": field,
                "label": field_label,
                "status": "confirmed",
                "value": value,
                "source_count": len(sources),
                "sources": sources,
                "confidence": "high" if len(sources) >= 2 else "medium",
            })
        else:
            # 存在不一致
            versions = []
            for nv, cs in normalized_values.items():
                versions.append({
                    "value": cs[0]["value"],
                    "sources": [c["source"] for c in cs],
                    "source_count": len(cs),
                })

            results.append({
                "field": field,
                "label": field_label,
                "status": "conflicted",
                "versions": versions,
                "confidence": "low",
                "recommendation": "需要人工确认正确版本",
            })

    # 标记仅有单一来源的字段
    for r in results:
        if r["status"] == "confirmed" and r.get("source_count", 0) == 1:
            r["status"] = "unverified"

    return results


# ──────────────────────────────────────────────
# 来源可信度评级
# ──────────────────────────────────────────────

SOURCE_RELIABILITY = {
    "prts_wiki": "high",
    "prts": "high",
    "game_text": "high",
    "official": "high",
    "community_research": "medium",
    "fan_work": "low",
    "unknown": "medium",
}


def rate_source_reliability(source_label: str) -> str:
    """根据来源标签评估可信度"""
    label_lower = source_label.lower()
    for key, reliability in SOURCE_RELIABILITY.items():
        if key in label_lower:
            return reliability
    return "medium"


# ──────────────────────────────────────────────
# 文件读取
# ──────────────────────────────────────────────

def load_sources(filepaths: list[str]) -> list[tuple[str, str]]:
    """加载多个来源文件"""
    sources = []
    for fp in filepaths:
        path = Path(fp)
        if not path.exists():
            print(f"警告：文件不存在 {fp}，已跳过", file=sys.stderr)
            continue
        content = path.read_text(encoding="utf-8")
        sources.append((content, path.name))
    return sources


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="设定交叉验证器 — 多来源交叉验证角色设定，标注矛盾和可信度",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python canon_checker.py --sources ./knowledge.md ./other_source.md
  python canon_checker.py --sources ./knowledge.md --output validation.json
  python canon_checker.py --sources ./knowledge.md --misconceptions ./custom_misconceptions.json
        """,
    )

    parser.add_argument("--sources", nargs="+", required=True, help="来源文件路径（支持多个）")
    parser.add_argument("--output", help="输出文件路径（默认 stdout）")
    parser.add_argument("--misconceptions", help="自定义误解库 JSON 文件路径")

    args = parser.parse_args()

    # 加载误解库
    misconceptions = load_misconceptions(args.misconceptions)

    sources = load_sources(args.sources)

    if not sources:
        print("错误：未找到任何有效来源文件", file=sys.stderr)
        sys.exit(1)

    # 提取所有声明
    all_claims = []
    all_warnings = []

    for content, source_label in sources:
        claims = extract_canon_claims(content, source_label)
        all_claims.extend(claims)

        warnings = check_misconceptions(content, source_label, misconceptions)
        all_warnings.extend(warnings)

    # 交叉验证
    validated = cross_validate(all_claims)

    # 统计
    confirmed = sum(1 for v in validated if v["status"] == "confirmed")
    conflicted = sum(1 for v in validated if v["status"] == "conflicted")
    unverified = sum(1 for v in validated if v["status"] == "unverified")

    report = {
        "summary": {
            "source_count": len(sources),
            "total_claims": len(all_claims),
            "confirmed": confirmed,
            "conflicted": conflicted,
            "unverified": unverified,
            "misconception_warnings": len(all_warnings),
        },
        "validated_fields": validated,
        "misconception_warnings": all_warnings,
        "source_reliability": {
            label: rate_source_reliability(label) for _, label in sources
        },
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"验证报告已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
