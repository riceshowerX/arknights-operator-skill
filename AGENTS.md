# AGENTS.md — arknights-operator-skill

## 项目概览

明日方舟角色蒸馏工具，将游戏角色转化为结构化 AI Skill。采用 Knowledge + Persona 双轨分离架构，五层优先级 Persona 结构，支持资料导入、语境化分析、对话纠正和版本管理。

**技术栈**: Python 3 (标准库), Markdown, JSON
**已验证角色**: 特蕾西娅 (operators/te-lei-xi-ya/), W (operators/w/)
**冒烟测试**: `python3 -m pytest tests/test_smoke.py -v` (51 项全部通过)

## 核心架构

- **Knowledge (knowledge.md)**: 角色"知道什么" — 背景故事、阵营关系、事件时间线
- **Persona (persona.md)**: 角色"如何存在" — 五层优先级性格结构 (Layer 0-4 + Layer 5 边界) + Correction 层
- **context.json**: 语境化数据中间层，统一标注场景/时期/对象
- **phase_inferrer.py**: 多层级时期自动推断引擎（消除手动映射依赖）

## 数据流

```
PRTS Wiki ──→ game_data_parser.py ──→ operator_data.json
                                          │
剧情页面 ──→ story_extractor.py ──→ story.json
                │                         │
                └── phase_inferrer.py ←───┘ (自动推断时期)
                                          │
                     context_annotator.py ←─┘──→ context.json (枢纽)
                          │      │
           phase_inferrer.py      │
           (自动推断默认时期)      │
                                  │
        ┌─────────────────┬───────┼────────────────┐
        ↓                 ↓       ↓                ↓
speech_act_analyzer  dialogue_fingerprint  relationship_graph  temporal_slicer
        │                 │       │                │
        └─────────────────┴───────┴────────────────┘
                                  │
                         persona_validator.py (多切片验证)
                                  │
                         knowledge.md + persona.md + SKILL.md
```

## 工具链

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `game_data_parser.py` | PRTS Wiki 数据获取 | `--source prts --name {角色名}` |
| `story_extractor.py` | 剧情页面提取 | `--chapter {页面名} --character {角色名}` (支持多次 --chapter) |
| `phase_inferrer.py` | 多层级时期自动推断 | `--operator {干员名}` / `--chapter {章节名}` / `--context-json` |
| `context_annotator.py` | 语境化标注枢纽 | `--operator-json --story-json --knowledge-md --output [--interactive]` |
| `speech_act_analyzer.py` | 话语行为分类 | `--context-json` (语境化模式) |
| `dialogue_fingerprint.py` | 7维语言指纹 | `--context-json` (语境化模式) |
| `relationship_graph.py` | 关系图谱 + 时序轨迹 | `--context-json` (语境化模式) |
| `temporal_slicer.py` | 时序切片分析 | `--context-json` (语境化模式) |
| `persona_validator.py` | 多切片一致性验证 | `--persona --context-json` (语境化模式) |
| `canon_checker.py` | 设定交叉验证 | `--sources` |
| `skill_writer.py` | 文件管理 | `--action {list/create/delete} --slug` |
| `version_manager.py` | 版本管理 | `backup / rollback / list` |

## 关键字段映射

- `game_data_parser.py` 输出语音行使用 `label` 字段（不是 `title`）
- `context_annotator.py` 已兼容 `label` 和 `title`，优先读取 `label`
- `context.json` 的 `annotated_lines` 每条包含: `id, text, source, source_detail, context{phase, scene, interlocutor, situation_type}, speech_acts, emotion`
- `story_extractor.py` 输出格式为 dict: `{character, chapters[], dialogues[], phase_distribution, total_target_lines}`

## 时期自动推断机制（phase_inferrer.py）

### 设计动机
旧版时期推断依赖三个手动映射表（`OPERATOR_DEFAULT_PHASE`、`CHAPTER_PHASE_MAP`、`ACTIVITY_PHASE_MAP`），每新增角色/章节需手动添加条目。`phase_inferrer.py` 通过多层级自动推断消除这一依赖。

### 推断优先级（从高到低）

| 优先级 | 方法 | 来源 | 离线可用 | 说明 |
|--------|------|------|----------|------|
| 1 | 内容正则匹配 | `PHASE_PATTERNS` | ✅ | 如"魔王...卡兹戴尔"→babel |
| 2 | 内容关键词匹配 | `PHASE_KEYWORDS` | ✅ | 如"巴别塔"→babel |
| 3 | 章节代码映射 | `CHAPTER_PHASE_MAP` | ✅ | 如"BB-"→babel |
| 4 | PRTS活动元数据 | `{{活动信息}}` 模板 | ❌ | 自动从活动页面提取 |
| 5 | PRTS分类标签 | 干员页"属于XX的干员" | ❌ | 如"属于巴别塔的干员"→babel |
| 6 | 内容聚类 | `CLUSTER_KEYWORDS` | ✅ | 关键词频率统计，需≥5条对话 |
| 7 | 交互式CLI | 用户手动输入 | ✅ | `--interactive` 启用 |

### 自动推断结果示例

| 角色 | PRTS分类标签 | 自动推断结果 | 置信度 |
|------|-------------|-------------|--------|
| 魔王 | 属于罗德岛的干员 | resurrected | medium |
| W | 属于巴别塔的干员 | babel | medium |
| 阿米娅 | 属于罗德岛的干员 | resurrected | medium |
| 赫德雷 | 属于巴别塔的干员 | babel | medium |
| Scout | (NPC，无分类) | 内容聚类: babel | low |

### 新增角色时的步骤（简化）

旧版需要 3 步手动配置，现在**无需任何手动操作**即可获得基本可用的结果：

1. ~~在 `OPERATOR_DEFAULT_PHASE` 添加映射~~ → phase_inferrer 自动从 PRTS 分类推断
2. ~~在 `CHAPTER_PHASE_MAP` 添加映射~~ → phase_inferrer 自动从活动元数据推断
3. 在 `relationship_graph.py` 的 `NAME_ALIASES` 添加角色别名（如有）— 仍需手动

**仅在自动推断结果不满意时**，可选地在 `OPERATOR_DEFAULT_PHASE` 中覆盖默认值。

### 推断报告

`context_annotator.py` 运行后会输出 `inference_report`，包含：
- `unknown_pct`: 未知时期占比
- `confidence_distribution`: 各置信度级别数量
- `suggestions`: 改进建议（如 unknown 占比 >50% 时提示使用 `--interactive`）

## 常见问题

### 语音行 source_detail 为空
- 原因: `game_data_parser.py` 输出 `label` 字段，旧版 `context_annotator.py` 读取 `title` 字段
- 修复: v3.1 已兼容两种字段名

### persona_validator 切片样本不足
- 当某切片对话数 < 2 时跳过该切片
- 置信度: high(>=20) / medium(>=10) / low(>=3) / very_low(<3)

### 时期推断误标注
- 原因: `context_annotator.py` 的 PHASE_KEYWORDS 包含过于宽泛的关键词（如"和平"、"魔王"），导致语音行被错误归入 babel 时期
- 修复: v3.2 将"和平"替换为更精确的"和平协议"/"卡兹戴尔的和平"；"魔王"需要结合卡兹戴尔语境（通过 PHASE_PATTERNS 正则匹配）；新增 PHASE_PATTERNS 优先级高于 PHASE_KEYWORDS

### 关系轨迹时期排序错误
- 原因: `relationship_graph.py` 的 `compute_relation_trajectories` 使用字母序排列时期（"babel" < "early" < "resurrected"），导致"从 early 到 babel"的描述被错误写成"从 babel 到 resurrected"
- 修复: v3.2 使用预定义时序 PHASE_ORDER = ["early", "babel", "resurrected"]

### 话语行为标签重复定义
- 原因: act_labels 字典在 `speech_act_analyzer.py` 和 `temporal_slicer.py` 中各自定义，容易不同步
- 修复: v3.2 提取为 `speech_act_analyzer.ACT_TYPE_LABELS`，`temporal_slicer.py` 通过 import 引用

### 新角色时期全部为 unknown
- 旧版原因: 新角色的干员页面名不在 `OPERATOR_DEFAULT_PHASE` 中，且相关活动不在映射表中
- v3.4 修复: `phase_inferrer.py` 自动从 PRTS 分类标签和活动元数据推断，无需手动配置
- 兜底: 运行 `python3 tools/context_annotator.py --interactive ...` 可手动指定

### 否定上下文误提取关系
- 原因: `relationship_graph.py` 的否定词列表不全，如"没有背叛"被误提取为 betrayal 关系
- 修复: v3.3 补全 `negation_markers`，新增 "没有"、"不曾"、"未尝"、"并不"

### Correction 规则覆盖 Layer 0
- 原因: 未明确 Correction 的作用范围，导致运行时纠正可能修改核心性格
- 修复: v3.3 在 persona.md 中明确标注 Correction 只能修改 Layer 1-4，不得覆盖 Layer 0

### 自动推断时期与预期不符
- 原因: PRTS 分类标签反映的是角色的"当前阵营归属"，而非"该语音行的时期"。例如 W 标注为"属于巴别塔的干员"，但其语音行可能属于早期（切尔诺伯格时期）
- 处理: 自动推断给出的是**合理的默认值**，如需精确控制可在 `OPERATOR_DEFAULT_PHASE` 中覆盖
- 建议: 使用 `context_annotator.py --interactive` 逐条确认低置信度推断

## 管线验证记录

### 特蕾西娅 (operators/te-lei-xi-ya/)
- game_data_parser: ✅ 从 PRTS 获取"魔王"数据，38 条语音行
- story_extractor: ✅ BB-ST-3 提取 85 条对话（特蕾西娅 0 条，W 不在此章）
- context_annotator: ✅ 60 条标注数据，unknown 从 37 降至 0（OPERATOR_DEFAULT_PHASE 修复后）
- phase_inferrer: ✅ 自动推断"魔王"→ resurrected（PRTS分类: 属于罗德岛的干员）
- 下游工具: ✅ fingerprint / speech_act / temporal_slicer / persona_validator 全部通过

### W (operators/w/)
- game_data_parser: ✅ 从 PRTS 获取 W 数据，38 条语音行 + 8 份档案
- story_extractor: ✅ DM-ST-1 求生/NBT 提取 239 条对话（W 114 条）
- context_annotator: ✅ 160 条标注数据，unknown 从 152 降至 0（添加 DM 映射后）
- phase_inferrer: ✅ 自动推断"W"→ babel（PRTS分类: 属于巴别塔的干员）
- 下游工具: ✅ fingerprint / speech_act / temporal_slicer 全部通过
- 注意: W 的 persona.md 尚未创建，persona_validator 报 FileNotFound 是预期行为

## 环境变量

| 变量 | 说明 |
|------|------|
| `OPERATOR_SKILL_DIR` | 工具链根目录，SKILL.md 中通过 `${OPERATOR_SKILL_DIR}` 引用 |

## 编码规范

- Python 3 标准库，无第三方依赖（可选: pypinyin）
- 文件编码: UTF-8
- JSON 输出: `ensure_ascii=False, indent=2`
