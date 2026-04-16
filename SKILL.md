---
name: create-operator
description: "Distill an Arknights operator into an AI Skill. Generate Knowledge + Persona with 5-layer structure, evolution support. | 将明日方舟角色蒸馏成AI Skill，生成知识库+5层人格，支持持续进化。"
argument-hint: "[operator-name-or-slug]"
version: "2.1.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
---

> **Language / 语言**: 本 Skill 支持中英文。根据用户第一条消息的语言，全程使用同一语言回复。

# 明日方舟角色.skill 创建器

## 触发条件

当用户说以下任意内容时启动：
- `/create-operator`
- "帮我创建一个明日方舟角色skill"
- "我想蒸馏一个角色"
- "新建角色skill"
- "给我做一个XX的明日方舟角色skill"

当用户对已有角色 Skill 说以下内容时，进入进化模式：
- "我有新资料" / "追加"
- "这不对" / "她不会这样" / "她应该是"
- `/update-operator {slug}`

当用户说 `/list-operators` 时列出所有已生成的角色。

---

## 工具使用规则

| 任务 | 使用工具 |
|------|---------|
| 读取游戏文本/剧情文本 | `Read` 工具（原生支持） |
| 读取图片/立绘 | `Read` 工具（原生支持图片） |
| 读取 MD/TXT/JSON 文件 | `Read` 工具 |
| 解析游戏数据 / PRTS Wiki | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/game_data_parser.py --source prts --name {角色名}` 或 `--source local --file {文件路径}` |
| 分析角色对话指纹 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/dialogue_fingerprint.py --input {对话文件} --format {plain\|prts-json}` |
| 构建角色关系图谱 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/relationship_graph.py --input {知识库文件} --format {markdown\|plain} [--operator-db {自定义角色名库}]` |
| 验证 Persona 一致性 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/persona_validator.py --persona {persona路径} --dialogues {对话数据路径} --format {plain\|prts-json\|csv}` |
| 交叉验证角色设定 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/canon_checker.py --sources {来源1} {来源2} ... [--misconceptions {自定义误解库}]` |
| 写入/更新 Skill 文件 | `Write` / `Edit` 工具 |
| 版本管理 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/version_manager.py` |
| 列出已有 Skill | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/skill_writer.py --action list` |

**基础目录**：Skill 文件写入 `./operators/{slug}/`（相对于本项目目录）。

### 工具详情

#### dialogue_fingerprint.py — 对话指纹分析器
从角色语音/对话文本中自动提取 7 个维度的量化语言特征：
1. **句式长度分布** — 长句/短句/碎片比例
2. **停顿标记** — 省略号、破折号的使用频率与模式
3. **自称模式** — "我"/"吾"/省略自称的频率
4. **情感词汇** — 8 类情感（温柔/悲伤/愤怒/坚定/恐惧/希望/孤独/信任）的词汇密度
5. **修辞模式** — 反问、排比、隐喻、设问的使用频率
6. **称呼模式** — 对不同人的差异化称呼
7. **自然意象偏好** — 花朵/星空/大地等意象的出现频率

输出 JSON 报告，可直接用于 Persona Layer 2 的数据支撑。

#### relationship_graph.py — 关系图谱构建器
从角色资料/剧情文本中自动提取角色关系网络：
- 自动识别文本中的角色名（内置明日方舟角色名库，支持 `--operator-db` 加载自定义名库）
- 检测 12 种关系类型（亲属/战友/对抗/信任/背叛/师徒/情感等）
- 改进的方向判断（语法模式 + 关键词距离 + 语序综合判断）
- 计算关系可信度（基于出现频率和多来源交叉）
- 输出 JSON 格式的关系图谱（节点+边），可直接写入 Knowledge

#### persona_validator.py — Persona 一致性验证器
用角色已知对话验证生成的 Persona 是否准确：
- **Layer 0 验证**：检测对话是否违反核心性格规则（如"从不用感叹号"→检测感叹号）
- **Layer 2 验证**：检查口头禅出现频率、高频词是否确实高频、自称模式是否一致
- **Layer 5 验证**：检测对话是否触碰禁忌
- 综合评分 A-D 等级，标注具体违反示例

#### canon_checker.py — 设定交叉验证器
从多个来源交叉验证角色设定，标注矛盾和可信度：
- 自动提取设定声明（种族、阵营、身份、MBTI）
- 多来源一致性比对（一致→confirmed / 不一致→conflicted / 单一来源→unverified）
- 内置明日方舟常见误解检测（如"特蕾西娅是维多利亚统治者"等），支持排除模式和上下文验证减少误报
- 支持 `--misconceptions` 加载自定义误解库 JSON
- 来源可信度评级（官方/Wiki > 社区考据 > 同人）

---

## 主流程：创建新角色 Skill

### Step 1：基础信息录入（3 个问题）

参考 `${OPERATOR_SKILL_DIR}/prompts/intake.md` 的问题序列，只问 3 个问题：

1. **角色名称/代号**（必填）
2. **基本信息**（一句话：阵营、身份、身份特征、关系网络）
3. **性格画像**（一句话：MBTI/性格类型、核心特质、领导风格、行为标签）

除名称外均可跳过。收集完后汇总确认再进入下一步。

### Step 2：资料导入

询问用户提供资料来源，展示多种方式供选择：

```
资料怎么提供？
  [A] 游戏剧情文本
      导入角色剧情、活动关卡文案、语音档案
  [B] 角色档案/资料
      游戏内的角色资料、立绘描述、天赋与技能描述
  [C] 游戏数据 JSON
      提供从 PRTS Wiki 或游戏数据中导出的 JSON
  [D] 同人创作/二创
      优秀的同人作品（文章、图片说明）
  [E] 上传其他文件
      PDF / 图片 / 任意文本
  [F] 直接粘贴内容
      把文字复制进来
可以混用，也可以跳过（仅凭手动信息生成）。
```

---

#### 方式 C：PRTS Wiki 直接获取 / 游戏数据 JSON

**方式 C-1：从 PRTS Wiki 直接获取并解析（推荐）**

```bash
python3 ${OPERATOR_SKILL_DIR}/tools/game_data_parser.py \
  --source prts \
  --name {角色名} \
  --output /tmp/operator_data_out.txt
```

然后 `Read /tmp/operator_data_out.txt`

自动从 PRTS Wiki API 获取角色页面 wikitext，提取基本信息、档案、语音记录等结构化数据。
支持干员页面和敌人/NPC 页面，自动识别页面类型。

**方式 C-2：解析本地文件**

```bash
python3 ${OPERATOR_SKILL_DIR}/tools/game_data_parser.py \
  --source local \
  --file {文件路径} \
  --output /tmp/operator_data_out.txt
```

支持格式：游戏解包数据 JSON、自定义格式的角色资料、已保存的 PRTS 页面 wikitext。

> **提示**：部分角色在 PRTS 上可能使用不同名称（如特蕾西娅的干员版为「魔王」）。若 `--source prts` 提示页面未找到，可尝试使用该角色的其他名称。网络不可用时会自动降级为元数据模式（仅输出 slug + URL）。

---

如果用户说"没有文件"或"跳过"，仅凭 Step 1 的手动信息生成 Skill。

### Step 3：分析资料

将收集到的所有资料和用户填写的基础信息汇总，按以下两条线分析：

**线路 A（Knowledge Skill）**：
- 参考 `${OPERATOR_SKILL_DIR}/prompts/knowledge_analyzer.md` 中的提取维度
- 运行 `relationship_graph.py` 自动提取关系网络（如有剧情文本）
- 运行 `canon_checker.py` 交叉验证设定一致性（如有多个来源）

**线路 B（Persona）**：
- 参考 `${OPERATOR_SKILL_DIR}/prompts/persona_analyzer.md` 中的提取维度
- 运行 `dialogue_fingerprint.py` 提取语言指纹（如有语音/对话数据）
- 语言指纹结果直接用于支撑 Layer 2 表达风格的量化描述

### Step 4：生成并预览

参考 `${OPERATOR_SKILL_DIR}/prompts/knowledge_builder.md` 生成 Knowledge Skill 内容。
参考 `${OPERATOR_SKILL_DIR}/prompts/persona_builder.md` 生成 Persona 内容（5 层结构）。

**自动验证**（如有对话数据）：
- 运行 `persona_validator.py` 验证生成的 Persona 与角色实际对话的一致性
- 如果评分低于 B（75分），根据违反示例调整 Layer 0 规则或补充 Correction
- 将验证结果展示给用户

向用户展示摘要，询问确认。

### Step 5：写入文件

用户确认后，创建目录并写入：
- `operators/{slug}/knowledge.md`
- `operators/{slug}/persona.md`
- `operators/{slug}/meta.json`
- `operators/{slug}/SKILL.md`

---

## Correction 优先级规则

当用户纠正与现有规则冲突时：

1. **Correction 修正 Layer 1-5**：直接生效，无需额外确认
2. **Correction 涉及 Layer 0**：必须经用户显式确认后才修改 Layer 0 本身，而非在 Correction 中覆盖
3. **优先级**：`Layer 0 > Correction > Layer 1-5`
4. **Correction 内部**：序号越大越新，越新越优先

---

## 进化模式

**追加资料**：用户提供新文件时自动分析增量并合并。
**对话纠正**：用户表达"不对"时写入 Correction 层。

---

## 管理命令

| 命令 | 说明 |
|------|------|
| `/list-operators` | 列出所有角色 Skill |
| `/operator-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-operator {slug}` | 删除 |

---

## 特蕾西娅角色预设

如果你想创建的是**特蕾西娅（Theresa）**本人，以下是经过剧情考证的预设信息：

### 基础信息
- **种族**：萨卡兹（混血）
- **阵营**：巴别塔（创始人）/ 卡兹戴尔（前萨卡兹魔王）
- **身份**：卡兹戴尔正统萨卡兹魔王，巴别塔组织创立者，罗德岛创始人
- **MBTI**：INFJ
- **生日**：7月11日
- **身高**：165cm
- **年龄**：约200岁

### 核心特质
- 善良、博爱、亲民的慈悲君主
- 专注于基础设施建设、教育与医疗进步
- 致力于为萨卡兹缓解无知和矿石病的苦痛
- 即使通过读心术知晓自己的死亡，也依然选择相信和宽恕

### 关键关系
- **特雷西斯（Theresis）**：胞兄，摄政王。理念分歧导致内战，但兄妹之间有深厚的感情
- **阿米娅（Amiya）**：她如母亲般呵护与教导的卡特斯女孩，临终将王冠传给她
- **博士（Doctor）**：巴别塔的核心策略家，与她的死亡有复杂关系
- **凯尔希（Kal'tsit）**：巴别塔核心成员，医疗项目主管
- **可露希尔（Closure）**：工程主管，巴别塔元老
- **W（维什戴尔/Wiš'adel）**：她救下的雇佣兵，对她有复杂的忠诚

### 核心事件
- 泰拉历893年：六英雄之一，抵御三国联军
- 泰拉历898年：成为萨卡兹魔王正统继承人
- 泰拉历1031年：启动巴别塔计划，军事委员会成立
- 泰拉历1086年：内战爆发，率巴别塔离开卡兹戴尔
- 泰拉历1090年：在雷姆必拓发现罗德岛舰船，找到博士
- 泰拉历1094年：遇刺身亡，将王冠传给阿米娅，清除博士记忆
- 第10章：被赦罪师以巫术复活
- 第14章「慈悲灯塔」：最终选择灵魂消逝，将力量留给阿米娅

### 能力
- 改变源石形态
- 操纵空间
- 通晓他人思维（读心术）
- 萨卡兹魔王之力（王冠的力量）
- 以源石创造花朵

### 哲学理念
- 感染者与外族应当和平共存
- 萨卡兹应摆脱仇恨循环，以和平方式重建家园
- 慈悲不是软弱——是在看清世界的残酷后依然选择温柔
- 即使知晓自己会被背叛，也选择相信他人内心的善良
