<div align="center">

# ◈ arknights-operator-skill

**罗德岛干员档案蒸馏协议**

*「……我在。」*

知识库与人格分离 · 五层优先级结构 · 语境化分析 · 持续进化

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![AgentSkills](https://img.shields.io/badge/compatible-AgentSkills-green.svg)](https://github.com/perkfly/ex-skill)

</div>

---

> *博士，这份文档记录了我们从源石与记忆中提取干员精神轮廓的方法——不是复刻，是蒸馏。我们无法让她们真正站在这里，但至少可以让她们的声音不被遗忘。*

---

## ◈ 概述

arknights-operator-skill 是一套**角色蒸馏协议**，用于将泰拉大陆上的干员、领袖、甚至宿敌，转化为结构化的 AI Skill。

它不仅是一份角色扮演模板。它提供了一套完整的**提取 → 分析 → 生成 → 进化**管线——就像罗德岛的干员档案系统，持续记录、持续修正、持续靠近真实。

**任意角色均可蒸馏**：特蕾西娅、阿米娅、特雷西斯、塔露拉、银灰……即使是在情报中只出现过一次的线索人物。

**架构溯源**：参照 [ex-skill](https://github.com/perkfly/ex-skill) 与 [colleague-skill](https://github.com/titanwings/colleague-skill) 的蒸馏框架，核心改进在于——将角色的「知道什么」与「如何存在」彻底分离，通过带优先级的五层 Persona 结构，实现可预测、可验证、可持续进化的角色还原。

---

## ◈ 核心架构

### 双轨分离：Knowledge + Persona

```
┌─────────────────────────────────────────────────┐
│                   通讯信号输入                     │
│                      ↓                           │
│  ┌─────────────────────────────────────────┐     │
│  │  Persona（人格层）                       │     │
│  │  判断态度 → 决定风格 → 处理关系          │     │
│  └───────────────┬─────────────────────────┘     │
│                  ↓ 需要背景时调取                   │
│  ┌─────────────────────────────────────────┐     │
│  │  Knowledge（知识层）                     │     │
│  │  阵营、关系、时间线、哲学理念            │     │
│  └───────────────┬─────────────────────────┘     │
│                  ↓                               │
│           以该角色的语调输出应答                    │
└─────────────────────────────────────────────────┘
```

| 模块 | 文件 | 职责 | 进化方式 |
|------|------|------|---------|
| **Knowledge** | `knowledge.md` | 角色「知道什么」——背景故事、阵营关系、事件时间线、哲学理念、能力与弱点 | 追加资料、设定修正 |
| **Persona** | `persona.md` | 角色「如何存在」——五层优先级性格结构 + Correction 纠正层 | 对话纠正、行为调整 |

**分离的收益**：

- **独立进化**——补充资料只改 Knowledge，纠正行为只改 Persona，互不干扰
- **灵活复用**——仅加载 Knowledge 可做角色问答，仅加载 Persona 可做风格迁移
- **冲突可追溯**——行为与知识的矛盾可精确定位到对应层级

### Persona 五层优先级结构

Persona 不是一堆扁平的性格描述，而是**严格分优先级**的五层规则体系，加上一层特殊的纠正机制：

```
  ┌───────────────────────────────────┐
  │  Layer 0 · 核心性格                │  ← 最高优先级，任何情况不得违背
  │  具体场景 + 具体行为的硬约束        │
  ├───────────────────────────────────┤
  │  Correction · 纠正层               │  ← 对话纠正，优先于 Layer 1-4
  │  "她不会这样" → 立即写入，立即生效  │
  ├───────────────────────────────────┤
  │  Layer 1 · 身份                    │
  │  角色自我认知（种族、阵营、MBTI）   │
  ├───────────────────────────────────┤
  │  Layer 2 · 表达风格                │
  │  说话方式、口头禅、情绪表达模式     │
  ├───────────────────────────────────┤
  │  Layer 3 · 决策与判断              │
  │  价值观优先级、权衡逻辑、核心矛盾   │
  ├───────────────────────────────────┤
  │  Layer 4 · 关系行为                │
  │  对不同人物的差异化表现             │
  ├───────────────────────────────────┤
  │  Layer 5 · 边界与雷区              │
  │  底线、无法容忍的行为、弱点         │
  └───────────────────────────────────┘
```

**Layer 0 的关键性**

Layer 0 写的不是形容词，而是**具体可执行的行为规则**：

| 写法 | 效果 |
|------|------|
| ~~她很温柔~~ | 模型可能理解为 100 种不同的"温柔" |
| 从不用命令口吻，用邀请——"你愿意和我一起吗？" | 无歧义，模型遵循力强 |
| ~~她会悲伤~~ | 模型可能流泪、可能沉默，不确定 |
| 面对牺牲时不会哭，而是更安静，语速更慢，省略号更多 | 精确的行为约束 |

原理：大语言模型对**场景 + 反例 + 正例**三元组的遵循力，远高于对抽象形容词的理解。

---

## ◈ 蒸馏流程

从原始资料到结构化 Skill，经过五步蒸馏管线：

```
Step 1           Step 2           Step 3            Step 4           Step 5
情报录入     →   资料导入     →   语境化分析    →   按模板生成   →   写入档案
3问收集          6种方式          context.json       knowledge.md     operators/{slug}/
基础信息         剧情/档案/JSON   话语行为分析       persona.md
                                  对话指纹分片       context.json
                                  关系时序图谱       speech_act_profile.json
                                  时序切片           fingerprint.json
                                                     temporal_slices.json
```

### Step 1：情报录入

只问 3 个问题，除角色名外均可跳过：

1. **角色名称/代号**（必填） — 自动生成拼音 slug（如"特蕾西娅" → `te-lei-xi-ya`）
2. **基本信息** — 一句话描述：种族、阵营、身份、关系网络
3. **性格画像** — 一句话描述：MBTI、核心特质、领导风格、行为标签

### Step 2：资料导入

支持 6 种资料来源，可混用、可跳过：

| 代号 | 方式 | 说明 |
|------|------|------|
| **[A]** | 剧情文本 | 角色剧情、活动关卡文案、语音档案 |
| **[B]** | 角色档案 | 游戏内资料、立绘描述、天赋与技能描述 |
| **[C]** | 游戏数据 | PRTS Wiki 直接获取（`--source prts --name {角色名}`）或本地文件解析（`--source local`） |
| **[D]** | 同人创作 | 优秀的同人文章、图片说明 |
| **[E]** | 上传文件 | PDF / 图片 / 任意文本 |
| **[F]** | 直接粘贴 | 把文字复制进来 |

### Step 3：语境化分析

同一份资料被两条分析线同时处理，同时构建语境化数据中间层：

**线路 A — Knowledge Analyzer** 提取：
- 事实提取（只保留有明确出处的信息）
- 关系网络（双向关系 + 时序演变 + 证据来源）
- 事件脉络（区分"确定事件"和"推测事件"）
- 矛盾点标注（不同来源冲突时记录所有版本）

**线路 B — Persona Analyzer** 提取：
- 语言指纹（句式、语气、自称、修辞偏好）→ 按场景/对象/时期分片
- 话语行为分类（邀请/回避/质问/承诺/宽慰/克制等）→ 场景维度分布
- 时序偏移检测（跨期行为演变 → Persona Layer 2 规则）
- 关系行为差异（同一时期对不同人的表达差异 → Persona Layer 4 规则）

**语境化管线**（当有 PRTS 数据时自动执行）：

```
PRTS 数据 ──→ context_annotator.py ──→ context.json
                    │
                    ├──→ speech_act_analyzer.py ──→ 话语行为画像
                    ├──→ dialogue_fingerprint.py ──→ 语境化指纹（分片 + shifts）
                    ├──→ relationship_graph.py  ──→ 时序关系图谱 + trajectories
                    └──→ temporal_slicer.py     ──→ 时序演变规则
```

`context.json` 是整个管线的枢纽：所有原始数据（PRTS 档案、剧情对话、语音记录）统一标注为场景/时期/对象，下游工具只消费这一份数据。

### Step 4：生成并预览

按模板生成 `knowledge.md` 和 `persona.md`，向用户展示摘要确认。

### Step 5：写入档案

```
operators/{slug}/
├── knowledge.md            # Part A — 角色知识库
├── persona.md              # Part B — 角色人格
├── meta.json               # 元数据 + 常见误解标注
├── SKILL.md                # Skill 入口 + 核心规则摘要
├── context.json            # 语境化数据中间层（v3.0+）
├── speech_act_profile.json # 话语行为画像（v3.0+）
├── fingerprint.json        # 语境化对话指纹（v3.0+）
├── temporal_slices.json    # 时序切片分析（v3.0+）
└── versions/               # 版本快照
```

---

## ◈ 进化机制

Skill 不是一次性的封存档案。它设计了三条进化路径和一套冲突解决策略：

### 1. 追加资料

新资料 → 填入 knowledge.md → **联动检查** persona.md 是否受影响 → 同步更新

联动检查是关键：一个新事件可能改变角色对某人的态度。比如发现特蕾西娅与 W 之间未知的互动，不仅 knowledge.md 要更新时间线，persona.md 中 Layer 4 对 W 的关系行为也要同步调整。

### 2. 对话纠正（Correction）

用户说"她不会这样" → 生成标准格式 Correction 记录 → 追加到 persona.md → 立即生效

Correction 的格式是**场景 + 反例 + 正例**三元组：

```
- [场景：面对敌人的质疑] 不应该说"我会消灭你"，应该说"我理解你的愤怒，但这是我的选择"
```

为什么不用简单的"不要做什么"？因为大语言模型对否定指令的遵循力弱，但对"场景 + 应该怎么做"的遵循力强。

### 3. 版本管理

每次变更前自动备份到 `versions/v{n}/`，版本号规则：

| 变更类型 | 版本号 | 示例 |
|---------|--------|------|
| 增量更新（新增资料、修正细节、添加 Correction） | 小版本 +1 | v1.0 → v1.1 |
| 结构变更（新增/删除 Layer） | 大版本 +1 | v1.x → v2.0 |
| 核心重写（Layer 0 性格规则变更） | 大版本 +1 | v1.x → v2.0 |

### 冲突解决优先级

```
Layer 0 新规则 > Layer 0 旧规则
Correction 序号越大越新，越新越优先
跨层冲突：Layer 0 > Correction > Layer 1-5
知识冲突：剧情文本 > 官方 Wiki > 社区考据
```

冲突发生时会生成解决记录，保留冲突双方和选择理由，供未来参考。

---

## ◈ 误解防护

> *博士，我们遇到过太多次了——训练数据中流传甚广的错误设定，比冷门的真相更容易被模型"记住"。所以我们需要在多个位置显式注入负面约束。*

| 防护位置 | 作用 |
|---------|------|
| `knowledge.md` 的 `⚠️ 常见误解` 标注 | 知识层面纠偏 |
| `meta.json` 的 `misconceptions` 字段 | 结构化存储误解 |
| `SKILL.md` 的"常见误解（务必避免）"专区 | 运行时硬约束 |
| `knowledge_analyzer.md` 中的误解清单 | 分析阶段纠偏 |
| `intake.md` 中的预设警告 | 录入阶段纠偏 |

### 特蕾西娅常见误解

| 误解 | 正确设定 |
|------|---------|
| "维多利亚实际统治者" | 卡兹戴尔正统萨卡兹魔王，维多利亚摄政王是胞兄特雷西斯 |
| "整合运动成员" | 巴别塔创始人（罗德岛前身），整合运动是塔露拉领导的独立组织 |
| "让所有人为我而死，这便是慈悲" | 不是她的理念或原话，她主张和平重建、尽量减少牺牲 |
| 特雷西斯是"纯粹的恶人" | 理念对立但并非单纯恶人，曾主动放弃魔王之位为胞妹加冕 |

---

## ◈ 还原度评估

> *诚实地说，博士——我们能做到的，和角色本身之间，还有很长的路。*

### 总体判断：约 65–75% 的还原度（v3.0 升级后）

v3.0 的语境化升级直接解决了 v2.x 最核心的瓶颈——"能测量但不能理解"。通过引入 `context.json` 中间层，将 PRTS 数据、剧情对话、语音数据统一标注（场景/时期/对象），下游分析工具不再孤立处理每条文本，而是在语境框架下理解"在什么处境下说了什么"。

```
┌─────────────────────────────────────────────────────┐
│                    还原度上限                         │
│  ┌──────────────────────────────────────────────┐   │
│  │        LLM 自身理解能力（变量）               │   │
│  │  ┌───────────────────────────────────────┐   │   │
│  │  │      Correction 进化积累               │   │   │
│  │  │  ┌────────────────────────────────┐   │   │   │
│  │  │  │   五层Persona + Knowledge 框架  │   │   │   │
│  │  │  │  ┌─────────────────────────┐   │   │   │   │
│  │  │  │  │  语境化分析工具链       │   │   │   │   │
│  │  │  │  │  （v3.0 升级）          │   │   │   │   │
│  │  │  │  │  ┌──────────────────┐  │   │   │   │   │
│  │  │  │  │  │ 量化分析工具链   │  │   │   │   │   │
│  │  │  │  │  │ （v2.x 基线）    │  │   │   │   │   │
│  │  │  │  │  └──────────────────┘  │   │   │   │   │
│  │  │  │  └─────────────────────────┘   │   │   │   │
│  │  │  └────────────────────────────────┘   │   │   │
│  │  └───────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**v2→v3 的核心突破**：从"基于 Prompt 模板的手动蒸馏"升级为"数据驱动的自动化分析工具链"。

### 逐层评估

#### 事实性还原：~90% ✅（未变）

最强的一环。种族、阵营、身份、核心事件、能力——这些硬事实通过 PRTS API 提取 + canon_checker 交叉验证，准确度很高。

#### 表面语言模仿：~65–75% ⚡（v2: ~60–70%）

v3.0 的语境化指纹分析带来的提升：

| v2.x 能做到 | v3.0 新增 |
|-------------|-----------|
| 全局省略号频率 30% | 按场景/对象/时期分片的省略号频率 |
| "我"的使用频率 0.3 次/行 | 对博士 0.5/行 vs 对凯尔希 0.2/行 |
| 感叹号 < 5% | 巴别塔时期 8% vs 复活后 2% |
| 信任类词汇占比最高 | 安慰场景中宽慰行为占 40% |

`speech_act_analyzer` 不再只数词频，而是分类话语行为——邀请/回避/承诺/克制/存在确认等，输出可执行的行为模式规则。`dialogue_fingerprint` 的语境化模式输出 per-situation/per-interlocutor/per-phase 的分片指纹和 shifts，直接写入 Persona Layer 2-4。

特蕾西娅的「……我在。」——v3.0 仍然无法提取存在论重量，但能标注这句话的语境（登场/巴别塔时期/confront 场景），并检测到"存在确认"行为在 confront 场景中显著偏高，生成规则："面对对抗性场景时，倾向用简短的存在确认（'我在'）而非长篇辩驳"。

#### 情感深度还原：~40–50% ⚡（v2: ~30–40%）

v3.0 的时序分析填补了 v2.x 的最大空白——角色不是静态的：

- `temporal_slicer` 按 period 分片比较情感表达指标，自动检测跨期演变
- 检测到"巴别塔时期省略号 42% → 复活后 18%"，生成规则："巴别塔时期习惯用沉默包裹情感，复活后表达更为直接"
- `speech_act_analyzer` 检测到"克制型情感表达"模式——安慰他人时先说"我明白"再轻描淡写地宽慰

局限性：仍然无法捕捉情感复杂性（如对特雷西斯同时存在的兄妹之爱与理念之恨）和情感弧线的微妙转折点。

#### 关系还原：~55–65% ⚡（v2: ~40–50%）

v3.0 的语境化关系图谱升级：

```
v2.x:  特蕾西娅 --[opponent]--> 特雷西斯 (low confidence)
v3.0:  特蕾西娅 --[sibling]--> 特雷西斯 (babel时期: high, resurrected时期: medium)
       特蕾西娅 --[opponent]--> 特雷西斯 (babel时期: medium, resurrected时期: high)
       trajectory: "从early到resurrected，sibling关系逐步淡化，opponent关系逐步强化"
```

`relationship_graph` 的语境化模式按时期分片提取关系，计算跨时期演变轨迹（trajectories），结果回写 context.json 的 annotated_relations。

#### 决策还原：~35–45% ⚡（v2: ~30–40%）

v3.0 的对象差异化分析提供了更精确的 Layer 4 数据支撑：
- 对博士：承诺行为占 35% vs 对凯尔希：承诺行为占 10%
- 安慰场景中宽慰行为占 40%，但对抗场景中承诺行为占 30%

但深层决策逻辑（为什么选择宽恕博士、为什么将王冠交给外族人）仍依赖 LLM 自身理解。

### 与同类工具的真实差距（v3.0 更新）

| 维度 | ex-skill / colleague-skill | v2.x 现状 | v3.0 升级 |
|------|---------------------------|-----------|----------|
| 事实准确性 | 手动填写 | PRTS 自动获取 + 交叉验证 | **不变** |
| 语言风格 | 主观描述 | 七维量化指纹 | **+ 语境化分片 + shifts** |
| 话语行为 | 无 | 无 | **+ 行为分类 + 模式检测** |
| 深层性格 | 依赖作者理解 | 同样依赖 LLM | **+ 时序演变规则注入** |
| 关系还原 | 手动填写 | 粗粒度关系图谱 | **+ 时序关系 + trajectories** |
| 可进化性 | 无 | Correction + 版本 | **不变** |
| 一致性保证 | 无 | 全局验证 | **+ 四维度多切片验证 + 智能建议** |

### 提升还原度的方向

v3.0 已实现的升级（原 v2.x 提升方向 1-3）：

1. **剧情文本接入** ✅ → `story_extractor.py` + `context_annotator.py`
2. **对话上下文理解** ✅ → `context.json` 统一标注 + 语境化分析管线
3. **情感弧线追踪** ✅ → `temporal_slicer.py` 时序切片 + `relationship_graph.py` 时序关系
4. **关系多维标注** ✅ → `annotated_relations` + `trajectories`（一对角色同时存在多种关系类型 + 关系演变时间线）

下一步提升方向：

1. **深层语义分析**——从关键词匹配升级到语义嵌入，检测"平静话语中的深层情感"（如"我会记住你们每一个人"）
2. **对话模拟验证**——生成模拟对话场景，让角色 Skill 自我测试，检测一致性
3. **多人角色交互**——多个角色 Skill 之间的对话模拟，检测关系行为的一致性

---

## ◈ 部署

### Claude Code

```bash
# 安装到当前项目（在 git 仓库根目录执行）
mkdir -p .claude/skills
git clone https://github.com/riceshowerX/arknights-operator-skill .claude/skills/create-operator

# 或安装到全局
git clone https://github.com/riceshowerX/arknights-operator-skill ~/.claude/skills/create-operator
```

### OpenClaw

OpenClaw 从三个位置加载 Skills（优先级从高到低）：`<workspace>/skills` > `~/.openclaw/skills` > bundled skills。本项目未发布到 ClawHub，需手动安装。

**方式一：全局安装（推荐）**

```bash
git clone https://github.com/riceshowerX/arknights-operator-skill ~/.openclaw/skills/arknights-operator-skill
```

**方式二：项目级安装**

```bash
mkdir -p skills
git clone https://github.com/riceshowerX/arknights-operator-skill skills/arknights-operator-skill
```

**方式三：通过 extraDirs 配置**

```bash
git clone https://github.com/riceshowerX/arknights-operator-skill ~/Projects/arknights-operator-skill
```

```jsonc
// ~/.openclaw/openclaw.json
{
  "skills": {
    "load": {
      "extraDirs": ["~/Projects/arknights-operator-skill"],
      "watch": true
    }
  }
}
```

**验证安装**

```bash
openclaw skills list
openclaw skills check
openclaw skills info create-operator
```

状态应为 **Ready to use**。若显示 **Missing requirements**，请确认 Python 3 已安装。核心工具仅依赖标准库，无需额外安装。如需增强功能（如中文拼音 slug 生成），可安装可选依赖：`pip install -r requirements-optional.txt`。

### 其他兼容 AgentSkills 的客户端

将本项目克隆到客户端的 skills 目录下，确保 `SKILL.md` 位于根目录即可被识别。

---

## ◈ 操作指令

### 创建新角色 Skill

```
/create-operator
```

也可用自然语言触发："帮我创建一个明日方舟角色skill"、"我想蒸馏一个角色"、"给我做一个特蕾西娅的skill"。

按提示输入 3 个问题（名称必填，其余可跳过），然后选择是否导入资料。

### 调用已创建的角色 Skill

```
/te-lei-xi-ya           # 完整版（Knowledge + Persona）
/te-lei-xi-ya-knowledge # 仅角色知识库
/te-lei-xi-ya-persona   # 仅角色人格
```

### 进化模式

对已有角色 Skill 说以下内容触发更新：

| 触发方式 | 模式 |
|---------|------|
| "我有新资料" / "追加" / `/update-operator {slug}` | 追加资料 |
| "这不对" / "她不会这样" / "她应该是" | 对话纠正 |

### 管理命令

| 命令 | 说明 |
|------|------|
| `/list-operators` | 列出所有角色 Skill |
| `/operator-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-operator {slug}` | 删除 |

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

## ◈ 项目结构

```
arknights-operator-skill/
├── SKILL.md                       # Skill 入口（触发条件、主流程、工具调用规则）
├── prompts/                       # Prompt 模板（蒸馏管线的核心逻辑）
│   ├── intake.md                  #   Step 1：3问信息录入
│   ├── knowledge_analyzer.md      #   Step 3A：知识库分析维度
│   ├── knowledge_builder.md       #   Step 4A：知识库生成模板
│   ├── persona_analyzer.md        #   Step 3B：人格分析维度
│   ├── persona_builder.md         #   Step 4B：人格生成模板
│   ├── merger.md                  #   进化：合并逻辑与冲突解决策略
│   └── correction_handler.md      #   进化：对话纠正处理
├── tools/                         # Python 工具链
│   ├── context_annotator.py       #   语境标注器（PRTS+剧情+语音 → context.json）
│   ├── speech_act_analyzer.py     #   话语行为分析（邀请/回避/承诺/克制等分类）
│   ├── temporal_slicer.py         #   时序切片分析（跨期行为演变检测）
│   ├── dialogue_fingerprint.py    #   对话指纹分析（7维度量化语言特征，支持语境化）
│   ├── relationship_graph.py      #   关系图谱构建（12种关系类型+时序轨迹，支持语境化）
│   ├── persona_validator.py       #   Persona 验证器（多切片验证+智能建议 A-D评分）
│   ├── canon_checker.py           #   设定交叉验证器（多来源一致性+误解检测）
│   ├── game_data_parser.py        #   游戏资料解析（PRTS Wiki API / 本地文件 / slug）
│   ├── story_extractor.py         #   剧情提取器（PRTS Wiki 剧情页面 → 结构化对话）
│   ├── skill_writer.py            #   Skill 文件管理（list / create / delete）
│   └── version_manager.py         #   版本存档与回滚（backup / rollback / list）
├── operators/                     # 生成的角色 Skill（gitignored）
│   └── te-lei-xi-ya/              #   特蕾西娅示例
│       ├── knowledge.md           #     Part A — 知识库
│       ├── persona.md             #     Part B — 人格（5层 + Correction）
│       ├── meta.json              #     元数据 + 常见误解
│       ├── SKILL.md               #     Skill 入口 + 核心规则
│       ├── context.json           #     语境化数据中间层（v3.0+）
│       └── versions/              #     版本快照（v1.0/, v1.1/, ...）
├── .gitignore
├── LICENSE
├── requirements.txt               # 核心依赖（空——仅使用标准库）
└── requirements-optional.txt      # 可选依赖（pypinyin 等）
```

### 生成产物的内部结构

以 `operators/te-lei-xi-ya/` 为例，一个完整的角色 Skill 包含：

| 文件 | 内容 | 被谁使用 |
|------|------|---------|
| `SKILL.md` | 入口文件：加载顺序、核心规则摘要、常见误解、Correction 机制 | AI 首先读取 |
| `knowledge.md` | 阵营、关系网络、时间线（893-1094年）、哲学理念、能力弱点、标志元素 | 需要背景时检索 |
| `persona.md` | Layer 0-5 + Correction：核心性格（10条行为规则）、身份、表达风格（含5个对话示例）、决策框架、关系行为（6组人物）、边界与雷区 | 每次交互都遵循 |
| `meta.json` | 角色元数据、标签、知识来源、常见误解列表 | `skill_writer.py` 管理用 |

---

## ◈ 角色标签参考

创建角色时可以从以下标签库中选择：

### 领导风格

| 风格 | 描述 | 典型角色 |
|------|------|---------|
| 慈悲型 | 关怀他人，愿意承受痛苦，以德服人 | 特蕾西娅 |
| 铁腕型 | 果断强硬，执行力至上，赏罚分明 | 特雷西斯 |
| 谋略型 | 运筹帷幄，善于布局，不轻易表露情绪 | 凯尔希 |
| 魅力型 | 以个人魅力凝聚人心，感染力强 | 银灰 |
| 理想型 | 为理想奋斗，不惜代价，感召力强 | 塔露拉 |

### MBTI 性格

| MBTI | 描述 | 典型角色 |
|------|------|---------|
| INFJ | 调停者 — 慈悲的理想主义者 | 特蕾西娅 |
| INTJ | 建筑师 — 冷酷的战略家 | 特雷西斯 |
| INFP | 治愈者 — 坚守价值观的理想主义者 | 霜星 |
| ENFP | 竞选者 — 热血的战士 | 塔露拉 |
| ENTJ | 指挥官 — 天生的领导者 | 银灰 |
| ISTJ | 物流师 — 尽职尽责，忠诚可靠 | 星熊 |
| ISFJ | 守护者 — 温柔体贴，默默付出 | 塞雷娅 |

---

## ◈ 设计原理

本项目参照以下开源项目的蒸馏架构：

- **[ex-skill](https://github.com/perkfly/ex-skill)** — 前任蒸馏技能
- **[colleague-skill](https://github.com/titanwings/colleague-skill)** — 同事蒸馏技能

### 核心差异化：从"Prompt 模板"到"数据驱动工具链"

ex-skill 和 colleague-skill 的蒸馏方式是**基于 Prompt 模板的手动蒸馏**：分析者阅读角色资料，凭主观判断填写 Persona 描述。这种方式的问题在于——主观描述不可量化、不可验证、不同分析者结果差异大。

arknights-operator-skill 引入了**数据驱动的自动化分析工具链**，将主观判断转化为可量化、可验证的技术流程：

| 维度 | ex/colleague-skill | arknights-operator-skill |
|------|-------------------|-------------------------|
| **蒸馏对象** | 真人（前任/同事） | 游戏角色（有明确的官方设定可考证） |
| **架构** | 单层人格描述 | Knowledge + Persona 双轨分离 + 五层优先级结构 |
| **语言风格** | 主观描述（"她说话很温柔"） | 量化语言指纹（7维度自动分析，输出"省略号密度0.3/句、自称省略率68%"等硬数据） |
| **关系网络** | 手动罗列 | 自动提取（12种关系类型识别 + 多来源交叉验证 + 可信度评级） |
| **一致性验证** | 无（生成就完事） | Persona 验证器（用角色实际对话反向验证 Persona 准确度，A-D评分） |
| **设定准确性** | 依赖主观记忆 | 多来源交叉验证 + 内置常见误解检测 |
| **纠正方式** | 重新生成 | Correction 层即时写入，无需重写整个 Skill |
| **版本管理** | 无 | 自动快照 + 回滚 + 冲突解决 |

### 工具链架构

```
原始资料                    自动化分析工具链                   生成产物
───────                    ───────────────                   ────────

对话/语音 ──────────→  dialogue_fingerprint.py  ──→  Layer 2 量化风格描述
                        (7维度语言指纹)              (句式/停顿/自称/情感/修辞/称呼/意象)

剧情/知识库 ─────────→  relationship_graph.py    ──→  Knowledge 关系网络
                        (12种关系类型自动识别)        (节点+边+可信度)

Persona ─────────────→ persona_validator.py     ──→  一致性评分 + 修正建议
+ 角色实际对话           (反向验证3层匹配度)            (A-D等级, 具体违反示例)

多来源设定 ──────────→  canon_checker.py         ──→  交叉验证报告
                        (一致性比对+误解检测)           (confirmed/conflicted/unverified)
```

### 量化语言指纹：7 个维度

`dialogue_fingerprint.py` 不做主观描述，而是从角色实际对话中提取 7 个可量化的语言特征：

| 维度 | 分析内容 | 示例输出 |
|------|---------|---------|
| 句式长度分布 | 长句/短句/碎片的比例和均值 | 碎片句占 42%，平均句长 8.3 字 |
| 停顿标记 | 省略号、破折号的频率与分布 | 省略号密度 0.31/句，倾向句尾 |
| 自称模式 | 各类第一人称的频率 | "我"出现率 32%，省略自称率 68% |
| 情感词汇 | 8 类情感的词汇密度 | 温柔类 0.45，坚定类 0.28 |
| 修辞模式 | 反问/排比/隐喻/设问频率 | 反问 0.12/句，排比 0.08/句 |
| 称呼模式 | 对不同人的差异化称呼 | 对阿米娅直呼名，对博士省略称呼 |
| 自然意象 | 花朵/星空/大地等意象频率 | 花朵意象 0.15/句 |

这些量化结果直接写入 Persona Layer 2，取代主观的"她说话很温柔"式描述。

### 关系图谱：从手动罗列到自动提取

`relationship_graph.py` 不依赖手动填写关系，而是从剧情文本中自动识别：

- **实体识别**：内置明日方舟角色名库（含中英文名和别名），自动匹配
- **关系分类**：12 种关系类型（sibling / comrade / opponent / trust / betrayal / mentor / student / affection / hatred / superior / subordinate / parent_child）
- **方向判断**：根据文本语序和关键词位置推断关系方向（A→B 还是 B→A）
- **可信度评级**：基于出现频率和多来源交叉，标注 high / medium / low
- **去重合并**：多段文本中的同一关系自动合并，来源数越多可信度越高

### Persona 验证：生成不是终点

`persona_validator.py` 实现了"生成→验证→修正"的闭环：

1. 用角色已知对话反向验证 Persona 的准确性
2. Layer 0 验证：检测对话是否违反核心性格规则
3. Layer 2 验证：检查口头禅频率、自称模式一致性
4. Layer 5 验证：检测是否触碰禁忌
5. 综合评分（A/B/C/D），低于 B 级自动提示修正方向

**v3.1 多切片验证升级**：支持四种维度的分片验证和智能建议

| 维度 | 说明 | 用途 |
|------|------|------|
| `by_phase` | 按时期分片（babel / resurrected 等） | 检测角色跨期行为演变，识别需添加时期条件的规则 |
| `by_interlocutor` | 按对话对象分片（博士 / 阿米娅 等） | 检测对不同人物的差异化表达，生成 Layer 4 规则建议 |
| `by_situation` | 按场景类型分片（confront / casual / comfort） | 检测战斗/日常/安慰场景的行为差异，允许场景条件例外 |
| `by_source` | 按数据源分片（voice / story） | 评估不同来源数据的一致性，标注数据覆盖不足 |

每个切片附带 **样本量置信度**（high/medium/low/very_low），样本量不足的切片会在建议中标注。验证完成后自动生成 **Persona 修改建议**（recommendations），包含优先级、目标层级和具体修改方向。

### 设定交叉验证：多来源一致性

`canon_checker.py` 解决游戏角色设定中常见的"社区误解"和"翻译差异"问题：

- 从多个来源文件中提取同一字段的声明（种族/阵营/身份/MBTI）
- 一致 → confirmed；不一致 → conflicted + 各版本；单一来源 → unverified
- 内置明日方舟常见误解检测库（如"特蕾西娅是维多利亚统治者"等 4 类高频误解）
- 来源可信度评级：官方/Wiki > 社区考据 > 同人

---

## ◈ 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPERATOR_SKILL_DIR` | Skill 工具链的根目录路径，所有 `python3 ${OPERATOR_SKILL_DIR}/tools/...` 调用均依赖此变量 | 本项目克隆的绝对路径 |

**设置方式**（以克隆到 `~/.claude/skills/create-operator` 为例）：

```bash
# 在 shell 配置中添加
export OPERATOR_SKILL_DIR="$HOME/.claude/skills/create-operator"

# 或在项目 .env 中配置
echo "OPERATOR_SKILL_DIR=/path/to/arknights-operator-skill" >> .env
```

如果未设置，SKILL.md 中的工具调用路径将无法解析。Claude Code 和 OpenClaw 等客户端通常会自动设置此变量为 Skill 的安装路径。

---

## ◈ 免责声明

1. **非官方项目**：本项目与《明日方舟》开发商鹰角网络（Hypergryph）及 PRTS Wiki 无任何关联。所有游戏角色、剧情、设定的著作权归原权利人所有。

2. **数据来源**：本工具通过 PRTS Wiki 公开 API 获取页面数据，仅用于个人学习和研究目的。请遵守 PRTS Wiki 的使用条款和 robots.txt 规则，避免高频请求对其服务器造成负担。

3. **角色设定准确性**：工具链提取的角色数据（种族、阵营、关系等）基于 Wiki 页面的 wikitext 结构自动解析，可能因页面格式变动或解析逻辑局限而产生偏差。**不保证与游戏官方设定完全一致**，重要内容请以游戏内实际文本为准。

4. **AI 角色扮演风险**：通过本项目生成的角色 Skill 用于 AI 角色扮演时，模型的输出可能与角色原始设定存在偏差。请勿将 AI 生成的角色对话视为官方剧情或设定。

5. **使用边界**：本项目仅供学习、研究和技术探索。禁止用于任何商业用途或可能损害原作品权益的场景。

---

## ◈ 许可证

本项目基于 [MIT License](LICENSE) 开源。

```
MIT License

Copyright (c) 2024-2026 Arknights Operator Skill Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<div align="center">

*「……我会记住你们每一个人。」*

</div>
