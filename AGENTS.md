# AGENTS.md — arknights-operator-skill

## 项目概览

明日方舟角色蒸馏工具，将游戏角色转化为结构化 AI Skill。采用 Knowledge + Persona 双轨分离架构，五层优先级 Persona 结构，支持资料导入、语境化分析、对话纠正和版本管理。

**技术栈**: Python 3 (标准库), Markdown, JSON
**默认角色**: 特蕾西娅 (operators/te-lei-xi-ya/)

## 核心架构

- **Knowledge (knowledge.md)**: 角色"知道什么" — 背景故事、阵营关系、事件时间线
- **Persona (persona.md)**: 角色"如何存在" — 五层优先级性格结构 (Layer 0-4 + Layer 5 边界) + Correction 层
- **context.json**: 语境化数据中间层，统一标注场景/时期/对象

## 数据流

```
PRTS Wiki ──→ game_data_parser.py ──→ operator_data.json
                                          │
剧情页面 ──→ story_extractor.py ──→ story.json
                                          │
                     context_annotator.py ←─┘──→ context.json (枢纽)
                                          │
        ┌─────────────────┬────────────────┼────────────────┐
        ↓                 ↓                ↓                ↓
speech_act_analyzer  dialogue_fingerprint  relationship_graph  temporal_slicer
        │                 │                │                │
        └─────────────────┴────────────────┴────────────────┘
                                   │
                          persona_validator.py (多切片验证)
                                   │
                          knowledge.md + persona.md + SKILL.md
```

## 工具链

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `game_data_parser.py` | PRTS Wiki 数据获取 | `--source prts --name {角色名}` |
| `story_extractor.py` | 剧情页面提取 | `--url {wiki_url} --name {角色名}` |
| `context_annotator.py` | 语境化标注枢纽 | `--operator-json --story-json --knowledge-md --output` |
| `speech_act_analyzer.py` | 话语行为分类 | `--context-json` (语境化模式) |
| `dialogue_fingerprint.py` | 7维语言指纹 | `--context-json` (语境化模式) |
| `relationship_graph.py` | 关系图谱 + 时序轨迹 | `--context-json` (语境化模式) |
| `temporal_slicer.py` | 时序切片分析 | `--context-json` (语境化模式) |
| `persona_validator.py` | 多切片一致性验证 | `--persona --context-json` (语境化模式) |
| `canon_checker.py` | 设定交叉验证 | `--sources` |
| `skill_writer.py` | 文件管理 | `list / create / delete` |
| `version_manager.py` | 版本管理 | `backup / rollback / list` |

## 关键字段映射

- `game_data_parser.py` 输出语音行使用 `label` 字段（不是 `title`）
- `context_annotator.py` 已兼容 `label` 和 `title`，优先读取 `label`
- `context.json` 的 `annotated_lines` 每条包含: `id, text, source, source_detail, context{phase, scene, interlocutor, situation_type}, speech_acts, emotion`

## 常见问题

### 语音行 source_detail 为空
- 原因: `game_data_parser.py` 输出 `label` 字段，旧版 `context_annotator.py` 读取 `title` 字段
- 修复: v3.1 已兼容两种字段名

### persona_validator 切片样本不足
- 当某切片对话数 < 2 时跳过该切片
- 置信度: high(>=20) / medium(>=10) / low(>=3) / very_low(<3)

## 环境变量

| 变量 | 说明 |
|------|------|
| `OPERATOR_SKILL_DIR` | 工具链根目录，SKILL.md 中通过 `${OPERATOR_SKILL_DIR}` 引用 |

## 编码规范

- Python 3 标准库，无第三方依赖（可选: pypinyin）
- 文件编码: UTF-8
- JSON 输出: `ensure_ascii=False, indent=2`
