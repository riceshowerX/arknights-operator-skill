<div align="center">

# ◈ arknights-operator-skill

**罗德岛干员档案蒸馏协议**

*「……我在。」*

Knowledge + Persona 双轨分离 · 五层优先级结构 · 语境化分析 · 持续进化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![AgentSkills](https://img.shields.io/badge/compatible-AgentSkills-green.svg)](https://github.com/perkfly/ex-skill)

</div>

---

> *博士，这份文档记录了我们从源石与记忆中提取干员精神轮廓的方法——不是复刻，是蒸馏。*

---

## 目录

- [概述](#-概述)
- [快速开始](#-快速开始)
- [核心设计](#-核心设计)
- [工具链](#-工具链)
- [项目结构](#-项目结构)
- [蒸馏实录](#-蒸馏实录)
- [还原度评估](#-还原度评估)
- [参考与致谢](#-参考与致谢)
- [免责声明](#-免责声明)

---

## ◈ 概述

arknights-operator-skill 是一套**角色蒸馏协议**，将明日方舟的角色——干员、领袖、宿敌——转化为结构化的 AI Skill。它提供完整的 **提取 → 分析 → 生成 → 进化** 管线。

**任意角色均可蒸馏**：特蕾西娅、阿米娅、特雷西斯、塔露拉、银灰……即使只出现过一次的线索人物。

**架构溯源**：参照 [ex-skill](https://github.com/perkfly/ex-skill) 与 [colleague-skill](https://github.com/titanwings/colleague-skill) 的蒸馏框架。核心改进——将「知道什么」与「如何存在」彻底分离，通过带优先级的五层 Persona 结构实现可预测、可验证、可持续进化的角色还原。

---

## ◈ 快速开始

### 安装

```bash
# Claude Code（项目级）
mkdir -p .claude/skills
git clone https://github.com/riceshowerX/arknights-operator-skill .claude/skills/create-operator

# OpenClaw（全局）
git clone https://github.com/riceshowerX/arknights-operator-skill ~/.openclaw/skills/arknights-operator-skill
```

### 依赖

核心工具链仅依赖 Python 3.10+ 标准库，无需安装额外依赖。

```bash
# 运行测试
python -m pytest tests/ -v
```

### 创建角色

```
/create-operator
```

或自然语言触发："帮我创建一个明日方舟角色 skill"、"我想蒸馏一个角色"。

### 调用角色

```
/te-lei-xi-ya           # 完整版（Knowledge + Persona）
/te-lei-xi-ya-knowledge # 仅知识库
/te-lei-xi-ya-persona   # 仅人格
```

### 进化与纠错

| 触发方式 | 效果 |
|---------|------|
| "我有新资料" / `/update-operator {slug}` | 追加资料，联动更新 Persona |
| "她不会这样" / "她应该是……" | 写入 Correction，立即生效 |
| `/operator-rollback {slug} {version}` | 回滚到历史版本 |

---

## ◈ 核心设计

### 双轨分离：Knowledge + Persona

```
┌─────────────────────────────────────────────┐
│                通讯信号输入                    │
│                   ↓                          │
│  ┌──────────────────────────────────────┐   │
│  │  Persona（人格层）                    │   │
│  │  判断态度 → 决定风格 → 处理关系       │   │
│  └────────────┬─────────────────────────┘   │
│               ↓ 需要背景时调取               │
│  ┌──────────────────────────────────────┐   │
│  │  Knowledge（知识层）                  │   │
│  │  阵营、关系、时间线、哲学理念         │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

| 模块 | 文件 | 职责 |
|------|------|------|
| **Knowledge** | `knowledge.md` | 角色「知道什么」——背景、阵营关系、事件时间线、哲学理念 |
| **Persona** | `persona.md` | 角色「如何存在」——五层优先级性格 + Correction 纠正层 |

**分离收益**：独立进化（补资料只改 Knowledge，纠行为只改 Persona）、灵活复用、冲突可追溯。

### Persona 五层优先级

```
Layer 0 · 核心性格     ← 最高优先级，具体场景+行为的硬约束
Correction · 纠正层    ← "她不会这样" → 立即写入，优先于 Layer 1-4
Layer 1 · 身份         ← 自我认知（种族、阵营）
Layer 2 · 表达风格     ← 说话方式、口头禅、情绪模式
Layer 3 · 决策与判断   ← 价值观优先级、权衡逻辑
Layer 4 · 关系行为     ← 对不同人物的差异化表现
Layer 5 · 边界与雷区   ← 底线、无法容忍的行为
```

**Layer 0 的关键性**：不写形容词，写**具体可执行的行为规则**。

| ❌ 错误写法 | ✅ 正确写法 |
|-----------|-----------|
| 她很温柔 | 从不用命令口吻，用邀请——"你愿意和我一起吗？" |
| 她会悲伤 | 面对牺牲时不会哭，而是更安静，语速更慢，省略号更多 |

### 进化机制

| 路径 | 说明 |
|------|------|
| 追加资料 | 新资料 → knowledge.md → 联动检查 persona.md → 同步更新 |
| 对话纠正 | "她不会这样" → 场景+反例+正例三元组 → 写入 Correction → 立即生效 |
| 版本管理 | 每次变更前自动备份到 `versions/v{n}/`，支持回滚 |

### 冲突解决优先级

```
Layer 0 新规则 > Layer 0 旧规则
Correction 序号越大越新，越新越优先
跨层冲突：Layer 0 > Correction > Layer 1-5
知识冲突：剧情文本 > 官方 Wiki > 社区考据
```

---

## ◈ 工具链

### 数据获取

| 工具 | 功能 |
|------|------|
| `game_data_parser.py` | PRTS Wiki API / 本地文件解析，自动生成拼音 slug |
| `story_extractor.py` | PRTS 剧情页面 → 结构化对话提取（支持 `--discover` 自动发现子页面） |

### 语境化分析

| 工具 | 功能 |
|------|------|
| `context_annotator.py` | 多信号场景分类 + 对话对象内容推断 → `context.json` |
| `speech_act_analyzer.py` | 上下文感知话语行为分类（7 种核心类型）+ 行为链检测 |
| `dialogue_fingerprint.py` | 8 维度量化语言指纹（含口头禅检测 + 加权情感词典） |
| `relationship_graph.py` | 12 种关系类型 + Aho-Corasick + 关系强度量化 + 演变追踪 |
| `temporal_slicer.py` | 统计显著性检验 + 情感弧线检测 → Persona Layer 2 规则 |

### 验证与生成

| 工具 | 功能 |
|------|------|
| `persona_validator.py` | 四维度多切片验证 + 风格一致性验证 + A-D 评分 |
| `canon_checker.py` | 多来源交叉验证 + 外置误解库 + 通用模式检测 + ReDoS 防护 |
| `data_injector.py` | 将工具量化数据注入到 Prompt 模板占位符 |
| `skill_writer.py` | Skill 文件管理（list / create / delete） |
| `version_manager.py` | 版本快照与回滚 |

### 共享模块

| 模块 | 职责 |
|------|------|
| `constants.py` | 领域知识常量（时期映射、关系类型、角色别名等） |
| `prts_client.py` | 统一 PRTS API 调用 + 速率限制 + 指数退避重试 |
| `shared_utils.py` | 通用工具（路径验证、slug 验证、原子写入、分句等） |
| `pipeline.py` | 一键编排：`python pipeline.py --full --slug {slug} --name {name}`（支持 `--resume` 断点续传 + `--discover` 自动发现剧情页面） |

---

## ◈ 项目结构

```
arknights-operator-skill/
├── SKILL.md                       # AI Agent 入口（触发条件、主流程、工具调用规则）
├── README.md                      # 本文件
├── pyproject.toml                 # 项目配置（ruff / mypy / pytest）
├── AGENTS.md                      # 开发者规范（含数据流图）
├── prompts/                       # Prompt 模板（蒸馏管线核心逻辑）
│   ├── intake.md                  #   Step 1：3 问信息录入
│   ├── knowledge_analyzer.md      #   Step 3A：知识库分析维度
│   ├── knowledge_builder.md       #   Step 4A：知识库生成模板
│   ├── persona_analyzer.md        #   Step 3B：人格分析维度
│   ├── persona_builder.md         #   Step 4B：人格生成模板
│   ├── merger.md                  #   进化：合并逻辑与冲突解决
│   └── correction_handler.md      #   进化：对话纠正处理
├── tools/                         # Python 工具链
│   ├── constants.py               #   领域知识常量
│   ├── prts_client.py             #   PRTS API 客户端（重试 + 线程安全）
│   ├── shared_utils.py            #   通用工具函数（含原子写入）
│   ├── pipeline.py                #   一键编排器（支持断点续传）
│   ├── context_annotator.py       #   语境标注器（多信号分类）
│   ├── speech_act_analyzer.py     #   话语行为分析（上下文感知 + 行为链）
│   ├── temporal_slicer.py         #   时序切片分析（统计显著性 + 弧线检测）
│   ├── dialogue_fingerprint.py    #   对话指纹分析（8 维度 + 口头禅）
│   ├── relationship_graph.py      #   关系图谱构建（强度量化 + 演变追踪）
│   ├── persona_validator.py       #   Persona 验证器（风格一致性）
│   ├── canon_checker.py           #   设定交叉验证（外置误解库）
│   ├── data_injector.py           #   数据注入器（Prompt 模板填充）
│   ├── game_data_parser.py        #   游戏资料解析
│   ├── story_extractor.py         #   剧情提取器（情感标注）
│   ├── skill_writer.py            #   Skill 文件管理
│   └── version_manager.py         #   版本存档与回滚
├── data/                          # 配置文件
│   ├── pinyin_map.json            #   拼音映射（可用户扩展）
│   └── misconceptions.json        #   外置误解库（按角色分组）
├── operators/                     # 生成的角色 Skill
│   └── te-lei-xi-ya/              #   特蕾西娅示例
│       ├── knowledge.md           #     Part A — 知识库
│       ├── persona.md             #     Part B — 人格（5 层 + Correction）
│       ├── meta.json              #     元数据 + 常见误解
│       ├── SKILL.md               #     Skill 入口 + 核心规则
│       ├── context.json           #     语境化数据中间层（原子写入）
│       ├── speech_act_profile.json
│       ├── fingerprint.json
│       ├── temporal_slices.json
│       └── versions/              #     版本快照
├── tests/
│   └── test_smoke.py              # 冒烟测试（98 个用例）
├── requirements.txt               # 核心依赖（仅标准库）
├── requirements-optional.txt      # 可选依赖（pypinyin）
├── .gitignore
└── LICENSE
```

---

## ◈ 蒸馏实录

> *以下为特蕾西娅角色 Skill 的对话测试记录。*

**场景一：面对追随者的牺牲**

```
用户 > 报告，前线部队全灭...

角色 > ...我知道了。
      将他们的名字记下。每一个人。
      总有一天，我们会建立一个新的家园，
      让他们不必再为我们而战。
      ...他们选择了相信我。这份信任，我会用一生去守护。
```

**场景二：面对质疑**

```
用户 > 这样做值得吗？牺牲这么多人...

角色 > 你问我值不值得。
      我明白你的疑惑。让我问你一个问题：
      如果不这样，你会怎么做？
      ...
      我不是在质问。我是真的想知道。
      因为有时候，我想找到比牺牲更温柔的路。
```

**场景三：与阿米娅的对话**

```
用户 > 阿米娅，我有些话想对你说...

角色 > （目光变得更加柔和）
      怎么了，阿米娅？
      你不必像在众人面前那样坚强，
      在我面前，你可以做你自己。
      ...不管发生什么，我都在。
```

**场景四：对话纠正**

```
用户 > 她不会说"牺牲"，她会说"选择"

角色 > 收到。已写入 Correction #1：
      [场景：被问及个人牺牲] 不应该使用"牺牲"，
      应该使用"选择"——"这不是牺牲，是我选择的路。"
      此规则立即生效。
```

---

## ◈ 还原度评估

> *诚实地说，博士——我们能做到的，和角色本身之间，还有很长的路。*

### 总体判断：约 70–80%

| 维度 | 还原度 | 说明 |
|------|--------|------|
| 事实性还原 | ~90% | 种族、阵营、身份、核心事件——PRTS API + canon_checker 交叉验证 |
| 表面语言模仿 | ~75–85% | 8 维度对话指纹 + 口头禅检测 + 加权情感词典 + Prompt 数据注入 |
| 关系还原 | ~65–75% | 12 种关系类型 + 强度量化(0.0-1.0) + 跨期演变追踪 |
| 情感深度 | ~50–60% | 上下文感知分类 + 行为链检测 + 情感弧线识别 |
| 决策还原 | ~40–50% | 对象差异化分析 + 多信号场景分类 + 风格一致性验证 |

### 算法升级亮点（v3.1）

1. **8 维度对话指纹** — 新增口头禅/高频短语提取（n-gram 分析），句式长度改用统计分布（百分位数 + CV）
2. **加权情感词典** — 12 类情感（+嘲讽/绝望/好奇/戏谑），每词带权重（0.5-1.5）
3. **关系强度量化** — 综合共现频率、情感词密度、直接对话次数，输出 0.0-1.0 强度值
4. **上下文感知分类** — 考虑前后文调整话语行为分类置信度，检测行为链（如 question→evade→comfort）
5. **Prompt 数据注入** — 工具量化数据直接填充到 Prompt 模板占位符，消除工具-LLM 断层
6. **统计显著性检验** — 小样本警告 + 情感弧线检测（U型/下降/平稳/波动）
7. **多证据融合推断** — 时期推断从串行改为加权投票，多证据一致时置信度更高

### 局限性

1. **量化 ≠ 理解**——可以统计省略号频率，但无法理解沉默
2. **关键词匹配的天花板**——含蓄表达会失效（暗喻检测已部分缓解）
3. **情感复杂性的缺失**——无法捕捉矛盾情感和情感转折
4. **决策逻辑的黑盒**——"她为什么这样做"只能交给 LLM 推断
5. **数据覆盖偏差**——语音数据量远大于剧情数据，且场景单一

### 提升方向

1. **深层语义分析**——从关键词匹配升级到语义嵌入
2. **对话模拟验证**——生成模拟对话，让角色 Skill 自我测试
3. **多人角色交互**——多角色 Skill 对话模拟，检测关系行为一致性

---

## ◈ 参考与致谢

本项目参照以下开源项目的蒸馏架构：

- **[ex-skill](https://github.com/perkfly/ex-skill)** — 前任蒸馏技能
- **[colleague-skill](https://github.com/titanwings/colleague-skill)** — 同事蒸馏技能

### 与 ex-skill / colleague-skill 的差异

| 维度 | ex/colleague-skill | arknights-operator-skill |
|------|-------------------|-------------------------|
| 蒸馏对象 | 真人（前任/同事） | 游戏角色（有官方设定可考证） |
| 架构 | 单层人格描述 | Knowledge + Persona 双轨 + 五层优先级 |
| 语言风格 | 主观描述 | 8 维度量化语言指纹 + 口头禅检测 + Prompt 数据注入 |
| 关系网络 | 手动罗列 | 自动提取（12 种关系 + 强度量化 + 演变追踪） |
| 一致性验证 | 无 | Persona 验证器（风格一致性 + A-D 评分） |
| 设定准确性 | 依赖主观记忆 | 多来源交叉验证 + 外置误解库 + 通用模式检测 |
| 纠正方式 | 重新生成 | Correction 层即时写入 |
| 版本管理 | 无 | 自动快照 + 回滚 + 冲突解决 |

---

## ◈ 免责声明

1. **非官方项目**：与《明日方舟》开发商鹰角网络（Hypergryph）及 PRTS Wiki 无任何关联。所有游戏角色、剧情、设定的著作权归原权利人所有。

2. **数据来源**：通过 PRTS Wiki 公开 API 获取页面数据，仅用于个人学习和研究。请遵守 PRTS Wiki 使用条款，避免高频请求。

3. **角色设定准确性**：工具链基于 Wiki wikitext 自动解析，可能因页面格式变动产生偏差。**不保证与官方设定完全一致**，重要内容请以游戏内文本为准。

4. **AI 角色扮演风险**：AI 生成的对话可能与角色原始设定存在偏差。请勿将其视为官方剧情或设定。

5. **使用边界**：仅供学习、研究和技术探索。禁止用于任何商业用途或可能损害原作品权益的场景。

---

## ◈ 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

*「……我会记住你们每一个人。」*

</div>
