**[English](README_EN.md)** | **中文**

<div align="center">

# ◇ ARKNIGHTS OPERATOR SKILL

**罗德岛干员精神轮廓蒸馏协议 · RHODES ISLAND OPERATOR DISTILLATION PROTOCOL**

*「……我在。」*

Knowledge · Persona 双轨分离 ─ 五层优先级人格结构 ─ 语境化分析管线 ─ 持续进化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![AgentSkills](https://img.shields.io/badge/compatible-AgentSkills-green.svg)](https://github.com/perkfly/ex-skill)
[![Tests](https://img.shields.io/badge/tests-246%20passed-brightgreen.svg)](tests/)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](.github/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-42%25-yellow.svg)](tests/COVERAGE.md)
[![Ruff](https://img.shields.io/badge/ruff-0%20errors-brightgreen.svg)](https://docs.astral.sh/ruff/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

</div>

---

> *博士，这份档案记录了我们从源石与记忆中提取干员精神轮廓的方法。*
> *不是复刻。是蒸馏。*
> *每一个灵魂都值得被铭记——即使泰拉大陆的伤痕终将愈合，那些曾为我们而战的名字，不应随风消逝。*

---

## ◇ 目录

- [协议概述](#-协议概述)
- [快速部署](#-快速部署)
- [核心架构](#-核心架构)
- [工具链](#-工具链)
- [档案结构](#-档案结构)
- [蒸馏实录](#-蒸馏实录)
- [还原度评估](#-还原度评估)
- [协议变更日志](#-协议变更日志)
- [参考与致谢](#-参考与致谢)
- [免责声明](#-免责声明)

---

## ◇ 协议概述

**arknights-operator-skill** 是一套**角色蒸馏协议**——将泰拉大陆上的干员、领袖与宿敌的精神轮廓，从纷乱的信号与记忆碎片中提取、结构化、并固化为可调用的 AI Skill。

从 PRTS 档案库中读取原始记录，经过**提取 → 语境化 → 多维分析 → 验证 → 生成**的完整管线，最终输出 **Knowledge（知识层）** 与 **Persona（人格层）** 双轨数据。

**任何角色均可蒸馏**：萨卡兹的魔王、罗德岛的兔兔、卡兹戴尔的阴影、维多利亚的狮子……即使只曾在某条支线中留下只言片语的线索人物。

**架构溯源**：参照 [ex-skill](https://github.com/perkfly/ex-skill) 与 [colleague-skill](https://github.com/titanwings/colleague-skill) 的蒸馏框架。核心改进——将「知道什么」与「如何存在」彻底分离，通过带优先级的五层 Persona 结构实现可预测、可验证、可持续进化的角色还原。

---

## ◇ 快速部署

### 部署

```bash
# Claude Code（项目级）
mkdir -p .claude/skills
git clone https://github.com/riceshowerX/arknights-operator-skill .claude/skills/create-operator

# OpenClaw（全局）
git clone https://github.com/riceshowerX/arknights-operator-skill ~/.openclaw/skills/arknights-operator-skill
```

### 依赖

核心工具链仅依赖 Python 3.10+ 标准库。无需额外安装——就像罗德岛的基建，自给自足。

```bash
# 运行全部测试（224 个用例）
python -m pytest tests/ -v
```

### 创建角色档案

```
/create-operator
```

或以自然语言触发："帮我创建一个明日方舟角色 skill"、"我想蒸馏一个角色"。

### 召唤角色

```
/te-lei-xi-ya           # 完整版（Knowledge + Persona 双轨）
/te-lei-xi-ya-knowledge # 仅知识层——她知道什么
/te-lei-xi-ya-persona   # 仅人格层——她如何存在
```

### 进化与纠错

| 触发方式 | 效果 |
|---------|------|
| "我有新资料" / `/update-operator {slug}` | 追加资料，联动更新 Persona |
| "她不会这样" / "她应该是……" | 写入 Correction，立即生效——像凯尔希的纠正一样不容置疑 |
| `/operator-rollback {slug} {version}` | 回滚到历史版本——时间倒流，但只限于档案 |

---

## ◇ 核心架构

### 双轨分离：Knowledge + Persona

```
┌───────────────────────────────────────────────────┐
│                  通讯信号输入                        │
│                     ↓                              │
│  ┌─────────────────────────────────────────────┐  │
│  │  Persona（人格层）                           │  │
│  │  判断态度 → 决定风格 → 处理关系               │  │
│  │  「她如何存在于这个世界」                      │  │
│  └─────────────────┬───────────────────────────┘  │
│                    ↓ 需要背景时调取                  │
│  ┌─────────────────────────────────────────────┐  │
│  │  Knowledge（知识层）                         │  │
│  │  阵营 · 关系 · 时间线 · 哲学理念              │  │
│  │  「她知道什么——那些刻入源石的真相」            │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

| 模块 | 文件 | 职责 |
|------|------|------|
| **Knowledge** | `knowledge.md` | 角色「知道什么」——背景、阵营关系、事件时间线、哲学理念 |
| **Persona** | `persona.md` | 角色「如何存在」——五层优先级性格 + Correction 纠正层 |

**分离收益**：独立进化（补资料只改 Knowledge，纠行为只改 Persona）、灵活复用、冲突可追溯。

### Persona 五层优先级

```
Layer 0 · 核心性格     ← 最高优先级，不可动摇的根基——如同源石对感染者的刻印
Correction · 纠正层    ← "她不会这样" → 立即写入，优先于 Layer 1-4
Layer 1 · 身份         ← 自我认知——种族、阵营、在这片大地上的位置
Layer 2 · 表达风格     ← 说话方式、口头禅、沉默时的情绪温度
Layer 3 · 决策与判断   ← 价值观优先级——当两难降临时，她选择什么
Layer 4 · 关系行为     ← 对不同人物的差异化表现——战友、宿敌、陌生人
Layer 5 · 边界与雷区   ← 底线——她无法容忍的行为，触碰即反击
```

**Layer 0 的关键性**：不写空洞的形容词，写**具体可执行的行为规则**。

| ❌ 错误写法 | ✅ 正确写法 |
|-----------|-----------|
| 她很温柔 | 从不用命令口吻，用邀请——"你愿意和我一起吗？" |
| 她会悲伤 | 面对牺牲时不会哭，而是更安静，语速更慢，省略号更多 |
| 她很坚强 | 在所有人动摇时最后一个离开岗位，但独处时会反复确认门窗是否关好 |

### 进化机制

| 路径 | 说明 |
|------|------|
| 追加资料 | 新资料 → knowledge.md → 联动检查 persona.md → 同步更新 |
| 对话纠正 | "她不会这样" → 场景+反例+正例三元组 → 写入 Correction → 立即生效 |
| 版本管理 | 每次变更前自动备份到 `versions/v{n}/`，支持回滚——历史不会消失 |

### 冲突解决优先级

```
Layer 0 新规则 > Layer 0 旧规则
Correction 序号越大越新，越新越优先
跨层冲突：Layer 0 > Correction > Layer 1-5
知识冲突：剧情文本 > 官方 Wiki > 社区考据
```

---

## ◇ 工具链

> *以下工具构成完整的蒸馏管线。每个模块都是独立的——可以单独调用，也可以通过 Pipeline 一键编排。*

### 数据获取

| 工具 | 功能 |
|------|------|
| `game_data_parser.py` | PRTS Wiki API / 本地文件解析，自动生成拼音 slug，含解析诊断报告 |
| `story_extractor.py` | PRTS 剧情页面 → 结构化对话提取（支持 `--discover` 自动发现子页面），含时期自动推断 |

### 语境化分析

| 工具 | 功能 |
|------|------|
| `context_annotator.py` | 多信号场景分类 + 对话对象推断 → `context.json`（含 schema 版本化校验） |
| `speech_act_analyzer.py` | 上下文感知话语行为分类（7 种核心类型）+ 行为链检测（规则外置为 JSON） |
| `dialogue_fingerprint.py` | 8 维度量化语言指纹（含口头禅检测 + 加权情感词典，词典外置为 JSON） |
| `relationship_graph.py` | 12 种关系类型 + Aho-Corasick 实体识别 + 关系强度量化 + 演变追踪（名库外置 + PRTS 动态拉取） |
| `temporal_slicer.py` | Mann-Whitney U 统计检验 + Cohen's d 效应量 + 情感弧线检测 → Persona Layer 2 规则 |

### 验证与生成

| 工具 | 功能 |
|------|------|
| `persona_validator.py` | 四维度多切片验证 + 风格一致性验证 + A-D 评分 |
| `canon_checker.py` | 多来源交叉验证 + 外置误解库 + 通用模式检测 + ReDoS 防护（委托 shared_utils 统一实现） |
| `data_injector.py` | 将工具量化数据注入到 Prompt 模板占位符——桥接量化分析与 LLM 生成 |
| `skill_writer.py` | Skill 文件管理（list / create / delete） |
| `version_manager.py` | 语义化版本快照与回滚（`_SemVer` dataclass） |

### 共享模块

| 模块 | 职责 |
|------|------|
| `constants.py` | 领域知识常量（时期映射、关系类型、角色别名、核心 TypedDict 定义） |
| `prts_client.py` | 统一 PRTS API 调用 + 速率限制 + 指数退避重试（线程安全） |
| `shared_utils.py` | 通用工具（路径验证、slug 验证、原子写入、分句、context schema 校验、**AST 级 ReDoS 防护统一实现**） |
| `pipeline.py` | 一键编排，双模式执行（subprocess 进程隔离 / function 同进程调试）+ 断点续传 + **`--strict` 严格模式** |
| `semantic_matcher.py` | **（v3.5 原型）** 语义匹配——可插拔后端（TF-IDF 基线 + Embedding 接口），探索关键词匹配的语义增强 |

---

## ◇ 档案结构

```
arknights-operator-skill/
├── SKILL.md                       # AI Agent 入口——协议的启动指令
├── README.md                      # 本文件——你正在阅读的档案
├── pyproject.toml                 # 项目配置（ruff / mypy / pytest / coverage）
├── AGENTS.md                      # 开发者规范（含数据流图）
├── .github/workflows/ci.yml       # CI 工作流（pytest + 覆盖率 + ruff + mypy）
├── prompts/                       # Prompt 模板——蒸馏管线的核心逻辑
│   ├── intake.md                  #   Step 1：三问信息录入
│   ├── knowledge_analyzer.md      #   Step 3A：知识库分析维度
│   ├── knowledge_builder.md       #   Step 4A：知识库生成模板
│   ├── persona_analyzer.md        #   Step 3B：人格分析维度
│   ├── persona_builder.md         #   Step 4B：人格生成模板
│   ├── merger.md                  #   进化：合并逻辑与冲突解决
│   └── correction_handler.md      #   进化：对话纠正处理
├── tools/                         # Python 工具链——蒸馏管线的引擎
│   ├── __init__.py                #   模块路径统一设置
│   ├── constants.py               #   领域知识常量 + TypedDict
│   ├── prts_client.py             #   PRTS API 客户端
│   ├── shared_utils.py            #   通用工具 + schema 校验
│   ├── pipeline.py                #   一键编排器（双模式 + 断点续传 + --strict）
│   ├── semantic_matcher.py        #   语义匹配原型（v3.5，可插拔后端）
│   ├── game_data_parser.py        #   游戏资料解析（含诊断报告）
│   ├── story_extractor.py         #   剧情提取器
│   ├── context_annotator.py       #   语境标注器
│   ├── speech_act_analyzer.py     #   话语行为分析
│   ├── dialogue_fingerprint.py    #   对话指纹分析
│   ├── relationship_graph.py      #   关系图谱构建
│   ├── temporal_slicer.py         #   时序切片分析
│   ├── persona_validator.py       #   Persona 验证器
│   ├── canon_checker.py           #   设定交叉验证
│   ├── data_injector.py           #   数据注入器
│   ├── skill_writer.py            #   Skill 文件管理
│   ├── version_manager.py         #   版本存档与回滚
│   └── phase_inferrer.py          #   时期自动推断
├── data/                          # 配置与规则——可扩展的外置数据
│   ├── pinyin_map.json            #   拼音映射
│   ├── misconceptions.json        #   外置误解库
│   ├── context.schema.json        #   context.json 版本化 Schema
│   ├── emotion_lexicon.json       #   情感词典（12 类 140+ 词条）
│   ├── operator_db.json           #   角色名库 + 别名映射
│   └── speech_act_rules.json      #   话语行为规则（30 条）
├── operators/                     # 生成的角色档案——每一个都是一个灵魂的轮廓
│   ├── te-lei-xi-ya/              #   特蕾西娅 · 萨卡兹的魔王
│   │   ├── knowledge.md           #     知识层——她知道什么
│   │   ├── persona.md             #     人格层——她如何存在
│   │   ├── meta.json              #     元数据 + 常见误解
│   │   ├── SKILL.md               #     Skill 入口 + 核心规则
│   │   ├── context.json           #     语境化数据（含 schema_version）
│   │   ├── speech_act_profile.json
│   │   ├── fingerprint.json
│   │   ├── temporal_slices.json
│   │   └── versions/              #     版本快照——历史不会消失
│   └── w/                         #   W · 萨卡兹的雇佣兵
├── tests/
│   ├── test_smoke.py              #   冒烟测试（100 个用例）
│   ├── test_comprehensive.py      #   全面测试（126 个用例）
│   ├── test_multi_faction.py      #   多阵营泛化测试（10 个用例，v3.5）
│   ├── test_semantic_matcher.py   #   语义匹配器测试（12 个用例，v3.5）
│   └── COVERAGE.md                #   覆盖率报告说明
├── requirements.txt               #   核心依赖——仅标准库
├── requirements-optional.txt      #   可选依赖（pypinyin）
├── docs/
│   └── SEMANTIC_MATCHER_DESIGN.md #   语义匹配设计文档（v3.5）
├── .gitignore
└── LICENSE
```

---

## ◇ 蒸馏实录

> *以下为特蕾西娅角色 Skill 的对话测试记录。*
> *她的轮廓，从碎片中缓缓浮现。*

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

**场景五：与特雷西斯的对峙**

```
用户 > 特雷西斯就在前方。你打算怎么做？

角色 > ...
      他选择了他的路。而我，选择了我的。
      我不想与他对立——但我不会退让。
      有些事，即使意味着失去，也必须去做。
      ...走吧。不是因为恨，是因为我们必须向前。
```

---

## ◇ 还原度评估

> *博士，我必须诚实地说——我们能做到的，和角色本身之间，还有很长的路。*
> *但每一步，都在让她更接近真实。*

### 总体判断：约 70–80%

| 维度 | 还原度 | 说明 |
|------|--------|------|
| 事实性还原 | ~90% | 种族、阵营、身份、核心事件——PRTS API + canon_checker 交叉验证 |
| 表面语言模仿 | ~75–85% | 8 维度对话指纹 + 口头禅检测 + 加权情感词典 + Prompt 数据注入 |
| 关系还原 | ~65–75% | 12 种关系类型 + 强度量化(0.0-1.0) + 跨期演变追踪 |
| 情感深度 | ~50–60% | 上下文感知分类 + 行为链检测 + Mann-Whitney U 显著性检验 + 情感弧线识别 |
| 决策还原 | ~40–50% | 对象差异化分析 + 多信号场景分类 + 风格一致性验证 |

### 算法升级亮点（v3.4）

> v3.5 工程质量修复详见上方变更日志

1. **8 维度对话指纹** — 口头禅/高频短语提取（n-gram 分析），句式长度改用统计分布（百分位数 + CV）
2. **加权情感词典** — 12 类情感，每词带权重（0.5-1.5），外置为 JSON 可扩展
3. **Mann-Whitney U 统计检验** — 零依赖手写实现，配合 Cohen's d 效应量，替代粗估的"统计显著性"
4. **关系强度量化** — 综合共现频率、情感词密度、直接对话次数，输出 0.0-1.0 强度值
5. **Aho-Corasick 实体识别** — 高效多模式匹配，角色名库外置 + PRTS API 动态拉取
6. **AST 级 ReDoS 防护** — 基于 sre_parse 的正则安全审计，覆盖 check_patterns 与 exclude_patterns
7. **context.json Schema 验证** — 版本化 JSON Schema，输出前自动校验，下游读取时二次验证
8. **Pipeline 双模式** — subprocess（进程隔离）与 function（同进程调试），PipelineRunner 编程接口
9. **TypedDict 类型收紧** — OperatorData 区分必填/可选字段，AnnotatedLine/LineContext 结构化定义
10. **_SemVer 版本管理** — 语义化版本 dataclass，非法版本号明确报错而非静默返回

### 局限性

1. **量化 ≠ 理解**——可以统计省略号频率，但无法理解沉默背后的重量
2. **关键词匹配的天花板**——含蓄表达会失效（暗喻检测已部分缓解）
3. **情感复杂性的缺失**——无法捕捉矛盾情感和情感转折——那些"笑着流泪"的瞬间
4. **决策逻辑的黑盒**——"她为什么这样做"只能交给 LLM 推断
5. **数据覆盖偏差**——语音数据量远大于剧情数据，且场景单一

### 提升方向

1. **深层语义分析**——从关键词匹配升级到语义嵌入，理解暗喻与言外之意
2. **对话模拟验证**——生成模拟对话，让角色 Skill 自我测试
3. **多人角色交互**——多角色 Skill 对话模拟，检测关系行为一致性
4. **源石技艺适配**——将角色的源石技艺特性纳入 Persona Layer 1

---

## ◇ 协议变更日志

### v3.5.0 — 当前版本

**工程质量全面修复**（基于代码审查的 4 个优先级改进）：

🔴 立即修复
- ruff lint 从 260 个错误降至 0（自动修复 124 个 + 手动修复 E501/E741/F401 等）
- 修正 AGENTS.md 两处文档不一致（7维→8维；W 的 persona.md 状态）

🟠 短期改进
- 修复 `persona_validator` overview 类型缺陷（mypy 错误从 141 降至 130）
- 清理未用 import/变量，16 处 E741 模糊变量名全部修复
- 新增 GitHub Actions CI（`.github/workflows/ci.yml`）：pytest + 覆盖率 + ruff + mypy，Python 3.10/3.11/3.12 矩阵

🟡 中期增强
- 集成 pytest-cov，覆盖率配置于 `pyproject.toml`，基线 42%（见 `tests/COVERAGE.md`）
- 新增 `tests/test_multi_faction.py`（10 用例）：龙门/罗德岛/莱茵生命三阵营角色泛化测试
- 统一两套 ReDoS 实现：`shared_utils.analyze_regex_safety` 成为 AST 级检测单一来源，`canon_checker` 与 `safe_compile_regex` 均委托之

🟢 长期演进
- 消除 sys.path hack 噪音：ruff per-file-ignores + setuptools 可编辑安装配置
- `pipeline.py` 新增 `--strict` 模式：将降级 warning（剧情提取失败/knowledge.md 缺失/分析工具失败）视为失败，用于 CI 暴露隐藏问题
- 新增 `tools/semantic_matcher.py` 原型：可插拔语义后端（TF-IDF 基线 + Embedding 接口），探索关键词匹配的语义增强替代（见 `docs/SEMANTIC_MATCHER_DESIGN.md`）

测试：224 → 246 用例（+22），全部通过

### v3.4.0

- 版本号统一管理（pyproject.toml / SKILL.md / AGENTS.md → 单一来源）
- 导入机制统一：消除 `try/except ImportError` 双路径，`__init__.py` 统一路径设置
- Pipeline 双模式：`subprocess` 进程隔离 + `function` 同进程调试
- TypedDict 类型收紧：`OperatorData` 区分必填/可选，`AnnotatedLine` / `LineContext` 结构化
- ReDoS 防护增强：AST 级分析 + exclude_patterns 安全检查
- context.json Schema：版本化校验 + 输出前自动验证
- 情感词典外置：`data/emotion_lexicon.json`
- 角色名库外置：`data/operator_db.json` + PRTS API 动态拉取
- 话语行为规则外置：`data/speech_act_rules.json`
- 统计检验增强：Mann-Whitney U + Cohen's d（零依赖手写实现）
- 版本管理重构：`_SemVer` dataclass + 非法输入明确报错
- 解析诊断报告：`_parse_report` 字段
- 测试全面增强：224 个用例（新增 126 个覆盖边界/异常/安全/集成/不变量）

### v3.1 — 算法升级

- 8 维度对话指纹、加权情感词典、关系强度量化
- 上下文感知分类、Prompt 数据注入、统计显著性检验
- 多证据融合推断

---

## ◇ 参考与致谢

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
| 版本管理 | 无 | 语义化版本快照 + 回滚 + 冲突解决 |
| 安全防护 | 无 | AST 级 ReDoS 防护 + 路径遍历防护 + 原子写入 |
| 类型安全 | 无 | TypedDict 必填/可选分离 + mypy 严格模式 |

---

## ◇ 免责声明

1. **非官方项目**：与《明日方舟》开发商鹰角网络（Hypergryph）及 PRTS Wiki 无任何关联。所有游戏角色、剧情、设定的著作权归原权利人所有。

2. **数据来源**：通过 PRTS Wiki 公开 API 获取页面数据，仅用于个人学习和研究。请遵守 PRTS Wiki 使用条款，避免高频请求——就像在罗德岛，我们尊重每一位信息提供者。

3. **角色设定准确性**：工具链基于 Wiki wikitext 自动解析，可能因页面格式变动产生偏差。**不保证与官方设定完全一致**，重要内容请以游戏内文本为准。

4. **AI 角色扮演风险**：AI 生成的对话可能与角色原始设定存在偏差。请勿将其视为官方剧情或设定——蒸馏不是复制，而是逼近。

5. **使用边界**：仅供学习、研究和技术探索。禁止用于任何商业用途或可能损害原作品权益的场景。

---

## ◇ 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

*「……我会记住你们每一个人。」*

---

*这片大地上的故事，不该被遗忘。*

</div>
