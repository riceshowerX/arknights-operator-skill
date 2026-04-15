---
name: create-operator
description: "Distill an Arknights operator into an AI Skill. Generate Knowledge + Persona with 5-layer structure, evolution support. | 将明日方舟角色蒸馏成AI Skill，生成知识库+5层人格，支持持续进化。"
argument-hint: "[operator-name-or-slug]"
version: "2.0.0"
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
| 解析游戏数据 JSON | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/game_data_parser.py` |
| 写入/更新 Skill 文件 | `Write` / `Edit` 工具 |
| 版本管理 | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/version_manager.py` |
| 列出已有 Skill | `Bash` → `python3 ${OPERATOR_SKILL_DIR}/tools/skill_writer.py --action list` |

**基础目录**：Skill 文件写入 `./operators/{slug}/`（相对于本项目目录）。

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

#### 方式 C：游戏数据 JSON

```bash
python3 ${OPERATOR_SKILL_DIR}/tools/game_data_parser.py \
  --source local \
  --file {json_path} \
  --output /tmp/operator_data_out.txt
```

然后 `Read /tmp/operator_data_out.txt`

支持格式：
- PRTS Wiki 导出的角色数据 JSON
- 游戏解包数据 JSON
- 自定义格式的角色资料 JSON

---

如果用户说"没有文件"或"跳过"，仅凭 Step 1 的手动信息生成 Skill。

### Step 3：分析资料

将收集到的所有资料和用户填写的基础信息汇总，按以下两条线分析：

**线路 A（Knowledge Skill）**：
- 参考 `${OPERATOR_SKILL_DIR}/prompts/knowledge_analyzer.md` 中的提取维度

**线路 B（Persona）**：
- 参考 `${OPERATOR_SKILL_DIR}/prompts/persona_analyzer.md` 中的提取维度

### Step 4：生成并预览

参考 `${OPERATOR_SKILL_DIR}/prompts/knowledge_builder.md` 生成 Knowledge Skill 内容。
参考 `${OPERATOR_SKILL_DIR}/prompts/persona_builder.md` 生成 Persona 内容（5 层结构）。

向用户展示摘要，询问确认。

### Step 5：写入文件

用户确认后，创建目录并写入：
- `operators/{slug}/knowledge.md`
- `operators/{slug}/persona.md`
- `operators/{slug}/meta.json`
- `operators/{slug}/SKILL.md`

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
