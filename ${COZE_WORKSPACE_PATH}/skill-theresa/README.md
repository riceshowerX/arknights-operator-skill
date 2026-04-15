# 特蕾西娅.skill

> 将明日方舟角色蒸馏成 AI Skill，创建慈悲而坚定的角色人格

*「让所有人为我而死，这便是慈悲。」*

---

## 简介

特蕾西娅.skill 是一个基于角色蒸馏原理的 AI Skill 创建工具，专门用于《明日方舟》中的角色。虽然名字叫"特蕾西娅"，但它实际上可以用于创建**任何明日方舟角色**的 Skill，包括但不限于：

- 整合运动：特蕾西娅、塔露拉、W、梅菲斯特、浮士德、阿丽娜
- 罗德岛：阿米娅、凯尔希、银灰、煌、博士
- 龙门：陈sir、星熊、诗怀雅
- 其他阵营：棘刺、极境、塞雷娅、伊芙利特 等

**设计原理**：参照 [ex-skill](https://github.com/perkfly/ex-skill) 和 [colleague-skill](https://github.com/titanwings/colleague-skill) 的蒸馏架构，将角色的**知识库**与**人格**分离，通过 5 层 Persona 结构实现真实感的角色扮演。

---

## 核心架构

每个角色 Skill 由两部分组成：

| 部分 | 内容 |
|------|------|
| **Part A — Knowledge** | 背景故事、阵营关系、核心事件、哲学理念、能力与弱点 |
| **Part B — Persona** | 5 层性格结构：核心性格 → 身份 → 表达风格 → 决策判断 → 关系行为 |

**运行逻辑**：`接收消息 → Persona 判断态度 → Knowledge 提供背景 → 用角色的语气输出`

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
git clone https://github.com/your-repo/skill-theresa .claude/skills/create-theresa

# 或安装到全局
git clone https://github.com/your-repo/skill-theresa ~/.claude/skills/create-theresa
```

### OpenClaw

```bash
git clone https://github.com/your-repo/skill-theresa ~/.openclaw/workspace/skills/create-theresa
```

---

## 使用

### 创建新角色 Skill

在 Claude Code 中输入：

```
/create-theresa
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
| `/list-theresas` | 列出所有角色 Skill |
| `/theresa-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-theresa {slug}` | 删除 |

---

## 效果示例

### 特蕾西娅角色扮演

**场景一：面对追随者的牺牲**

```
用户 > 报告，前线部队全灭...

角色 > ...我知道了。
     他们会为我而死，这便是慈悲。
     将他们的名字记下，总有一天，我们会建立一个新的家园，
     让他们不必再为我们而死。
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

**场景三：与塔露拉的对话**

```
用户 > 塔露拉，我有些话想对你说...

角色 > （语气变得更加温柔）
     怎么了，我亲爱的孩子。
     你不必像在众人面前那样，在我面前你可以放下那副担子。
```

---

## 项目结构

```
skill-theresa/
├── SKILL.md                    # Skill 入口
├── README.md                   # 说明文档
├── prompts/                    # Prompt 模板
│   ├── intake.md               # 信息录入脚本
│   ├── knowledge_analyzer.md    # 知识库分析器
│   ├── knowledge_builder.md     # 知识库生成模板
│   ├── persona_analyzer.md     # 人格分析器
│   ├── persona_builder.md      # 人格生成模板
│   ├── merger.md               # 增量合并逻辑
│   └── correction_handler.md   # 对话纠正处理
├── tools/                      # Python 工具
│   ├── version_manager.py      # 版本存档与回滚
│   └── skill_writer.py         # Skill 文件管理
└── knowledge/                   # 生成的 Skill（gitignored）
```

---

## 角色标签参考

### 领导风格

- 慈悲型 / 铁腕型 / 谋略型 / 魅力型 / 理想型 / 冷酷型 / 仁义型

### 核心特质

- 温柔 / 慈悲 / 坚定 / 理想主义 / 牺牲
- 冷酷 / 狡诈 / 理性 / 热血

### MBTI 性格

| MBTI | 适合角色类型 |
|------|-------------|
| INFJ | 调停者 - 慈悲的理想主义者 |
| INTJ | 建筑师 - 冷酷的战略家 |
| INFP | 治愈者 - 坚守价值观的理想主义者 |
| ENFP | 竞选者 - 热血的感染者战士 |
| ENTJ | 指挥官 - 天生的领导者 |

---

## 设计原理

本项目参照以下开源项目的设计原理：

- **[ex-skill](https://github.com/perkfly/ex-skill)** - 前任蒸馏技能
- **[colleague-skill](https://github.com/titanwings/colleague-skill)** - 同事蒸馏技能

核心改进：

1. **针对游戏角色的适配**：替换"前任/同事"为人格化的游戏角色
2. **慈悲哲学的特殊处理**：针对特蕾西娅等角色的核心特质增加了专门的哲学层
3. **阵营与归属**：引入阵营关系和阵营内部政治

---

## License

MIT License
