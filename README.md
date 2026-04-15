# arknights-operator-skill

> 将明日方舟角色蒸馏成 AI Skill，创建真实而立体的角色人格

*「……我在。」*

---

## 简介

arknights-operator-skill 是一个基于角色蒸馏原理的 AI Skill 创建工具，专门用于《明日方舟》中的角色。它可以用于创建**任何明日方舟角色**的 Skill，包括但不限于：

- **巴别塔/罗德岛**：特蕾西娅、阿米娅、凯尔希、博士、W（维什戴尔）、可露希尔
- **卡兹戴尔**：特雷西斯、赦罪师、萨卡兹诸王庭
- **整合运动**：塔露拉、爱国者、霜星、梅菲斯特、浮士德
- **龙门**：陈、星熊、诗怀雅
- **其他阵营**：银灰、煌、塞雷娅、伊芙利特 等

**设计原理**：参照 [ex-skill](https://github.com/perkfly/ex-skill) 和 [colleague-skill](https://github.com/titanwings/colleague-skill) 的蒸馏架构，将角色的**知识库**与**人格**分离，通过 5 层 Persona 结构实现真实感的角色扮演。

**特蕾西娅作为默认预设**：项目内置了特蕾西娅（Theresa）的完整预设信息，方便快速上手。

---

## 核心架构

每个角色 Skill 由两部分组成：

| 部分 | 内容 |
|------|------|
| **Part A — Knowledge** | 背景故事、阵营关系、核心事件、哲学理念、能力与弱点 |
| **Part B — Persona** | 5 层性格结构：核心性格 → 身份 → 表达风格 → 决策判断 → 关系行为 |

**运行逻辑**：`接收消息 → Persona 判断态度 → Knowledge 提供背景 → 用角色的语气输出`

### 5 层 Persona 结构

| Layer | 名称 | 作用 | 优先级 |
|-------|------|------|--------|
| Layer 0 | 核心性格 | 最高优先级行为规则，任何情况不得违背 | 最高 |
| Layer 1 | 身份 | 角色的基本设定和自我认知 | |
| Layer 2 | 表达风格 | 说话方式、口头禅、语气特征 | |
| Layer 3 | 决策与判断 | 价值观优先级、决策逻辑 | |
| Layer 4 | 关系行为 | 对不同人物和场景的差异化表现 | |
| Correction | 纠正层 | 对话纠正记录，优先级高于 Layer 1-4 | 仅次于 Layer 0 |

---

## 支持的功能

### 创建角色 Skill

提供角色信息 + 资料（可选），生成完整的角色 Skill。

### 进化机制

- **追加资料** → 自动分析增量 → merge 进对应部分
- **对话纠正** → 说「她不会这样」→ 写入 Correction 层，立即生效
- **版本管理** → 每次更新自动存档，支持回滚

---

## 安装

### Claude Code

```bash
# 安装到当前项目（在 git 仓库根目录执行）
mkdir -p .claude/skills
git clone https://github.com/your-repo/arknights-operator-skill .claude/skills/create-operator

# 或安装到全局
git clone https://github.com/your-repo/arknights-operator-skill ~/.claude/skills/create-operator
```

### OpenClaw

```bash
git clone https://github.com/your-repo/arknights-operator-skill ~/.openclaw/workspace/skills/create-operator
```

---

## 使用

### 创建新角色 Skill

在 Claude Code 中输入：

```
/create-operator
```

按提示输入：
1. **角色名称**（必填）
2. **基本信息**（阵营、身份、关系）
3. **性格画像**（MBTI、特质、领导风格）

所有字段均可跳过，仅凭描述也能生成。

### 调用已创建的 Skill

```
/{slug}           # 完整版（Knowledge + Persona）
/{slug}-knowledge # 仅角色知识库
/{slug}-persona   # 仅角色人格
```

### 管理命令

| 命令 | 说明 |
|------|------|
| `/list-operators` | 列出所有角色 Skill |
| `/operator-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-operator {slug}` | 删除 |

---

## 效果示例

### 特蕾西娅角色扮演

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

---

## 项目结构

```
arknights-operator-skill/
├── SKILL.md                    # Skill 入口
├── README.md                   # 说明文档
├── prompts/                    # Prompt 模板
│   ├── intake.md               # 信息录入脚本
│   ├── knowledge_analyzer.md   # 知识库分析器
│   ├── knowledge_builder.md    # 知识库生成模板
│   ├── persona_analyzer.md     # 人格分析器
│   ├── persona_builder.md      # 人格生成模板
│   ├── merger.md               # 增量合并逻辑
│   └── correction_handler.md   # 对话纠正处理
├── tools/                      # Python 工具
│   ├── game_data_parser.py     # 游戏资料解析器
│   ├── version_manager.py      # 版本存档与回滚
│   └── skill_writer.py         # Skill 文件管理
└── operators/                  # 生成的 Skill（gitignored）
    └── te-lei-xi-ya/           # 特蕾西娅示例
        ├── knowledge.md
        ├── persona.md
        ├── meta.json
        ├── SKILL.md
        └── versions/
```

---

## 角色标签参考

### 领导风格

- 慈悲型 / 铁腕型 / 谋略型 / 魅力型 / 理想型 / 冷酷型 / 仁义型

### 核心特质

- 温柔 / 慈悲 / 坚定 / 理想主义 / 忠诚
- 冷酷 / 狡诈 / 理性 / 热血 / 隐忍

### MBTI 性格

| MBTI | 适合角色类型 |
|------|-------------|
| INFJ | 调停者 - 慈悲的理想主义者（如特蕾西娅） |
| INTJ | 建筑师 - 冷酷的战略家（如特雷西斯） |
| INFP | 治愈者 - 坚守价值观的理想主义者 |
| ENFP | 竞选者 - 热血的感染者战士（如塔露拉） |
| ENTJ | 指挥官 - 天生的领导者（如银灰） |

---

## 设计原理

本项目参照以下开源项目的设计原理：

- **[ex-skill](https://github.com/perkfly/ex-skill)** - 前任蒸馏技能
- **[colleague-skill](https://github.com/titanwings/colleague-skill)** - 同事蒸馏技能

核心改进：

1. **针对游戏角色的适配**：替换"前任/同事"为人格化的游戏角色
2. **角色哲学的特殊处理**：针对特蕾西娅等角色的核心理念增加了专门的哲学层
3. **阵营与归属**：引入阵营关系和阵营内部政治
4. **常见误解标注**：在知识库中标注社区常见误解，避免错误设定传播
5. **增量合并与冲突解决**：完善的版本管理和合并策略

---

## 常见误解说明

在创建明日方舟角色 Skill 时，以下常见误解需特别注意：

| 角色 | 常见误解 | 正确设定 |
|------|---------|---------|
| 特蕾西娅 | "维多利亚实际统治者" | 卡兹戴尔正统萨卡兹魔王，维多利亚摄政王是她的胞兄特雷西斯 |
| 特蕾西娅 | "整合运动成员" | 巴别塔创始人（罗德岛前身），整合运动是塔露拉领导的独立组织 |
| 特蕾西娅 | "让所有人为我而死，这便是慈悲" | 这不是她的理念或原话，她主张和平重建、尽量减少牺牲 |
| 特雷西斯 | "纯粹的恶人" | 理念与特蕾西娅对立但并非单纯恶人，曾主动放弃魔王之位为胞妹加冕 |

---

## License

MIT License
