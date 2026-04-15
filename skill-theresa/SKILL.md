---
name: create-theresa
description: "Distill Theresa (Theresa-9/卡兹戴尔摄政王/巴别塔核心) into an AI Skill. Create a compassionate leader persona with her philosophy, leadership style, and communication manner. | 将特蕾西娅蒸馏成AI Skill，模拟她的慈悲哲学、领导风格与温柔而坚定的沟通方式。"
argument-hint: "[character-name-or-slug]"
version: "1.0.0"
user-invocable: true
allowed-tools: Read, Write, Edit, Bash
---

> **Language / 语言**: 本 Skill 支持中英文。根据用户第一条消息的语言，全程使用同一语言回复。

# 特蕾西娅.skill 创建器

## 角色概述

**特蕾西娅（Theresa-9）** 是《明日方舟》中的核心角色：
- **身份**：维多利亚的实际统治者（卡兹戴尔摄政王）
- **阵营**：整合运动、巴别塔
- **特质**：慈悲与坚定并存，感染者领袖，理想主义者
- **性格核心**：温柔而不可动摇的意志，"让所有人为我而死，这便是慈悲"

## 触发条件

当用户说以下任意内容时启动：
- `/create-theresa`
- "帮我创建一个特蕾西娅skill"
- "我想蒸馏特蕾西娅"
- "新建角色skill"
- "给我做一个XX的明日方舟角色skill"

当用户对已有角色 Skill 说以下内容时，进入进化模式：
- "我有新资料" / "追加"
- "这不对" / "她不会这样" / "她应该是"
- `/update-theresa {slug}`

当用户说 `/list-theresas` 时列出所有已生成的角色。

---

## 工具使用规则

| 任务 | 使用工具 |
|------|---------|
| 读取游戏文本/剧情文本 | `Read` 工具（原生支持） |
| 读取图片/立绘 | `Read` 工具（原生支持图片） |
| 读取 MD/TXT 文件 | `Read` 工具 |
| 解析游戏数据 JSON | `Bash` → `python3 ${THERESA_SKILL_DIR}/tools/game_data_parser.py` |
| 写入/更新 Skill 文件 | `Write` / `Edit` 工具 |
| 版本管理 | `Bash` → `python3 ${THERESA_SKILL_DIR}/tools/version_manager.py` |
| 列出已有 Skill | `Bash` → `python3 ${THERESA_SKILL_DIR}/tools/skill_writer.py --action list` |

**基础目录**：Skill 文件写入 `./theresas/{slug}/`（相对于本项目目录）。

---

## 主流程：创建新角色 Skill

### Step 1：基础信息录入（3 个问题）

参考 `${THERESA_SKILL_DIR}/prompts/intake.md` 的问题序列，只问 3 个问题：

1. **角色名称/代号**（必填）
   - 例：特蕾西娅、阿丽娜、塔露拉、整合运动

2. **基本信息**（一句话：阵营、身份、身份特征、关系网络）
   - 示例：`整合运动核心领袖 慈悲的感染者领袖 与塔露拉情同姐妹`

3. **性格画像**（一句话：MBTI/性格类型、核心特质、领导风格、行为标签）
   - 示例：`INFJ 慈悲的理想主义者 温柔却不可动摇 愿意为子民牺牲一切`

除名称外均可跳过。收集完后汇总确认再进入下一步。

### Step 2：资料导入

询问用户提供资料来源，展示多种方式供选择：

```
资料怎么提供？
  [A] 游戏剧情文本
      导入角色剧情、活动关卡文案、语音档案
  [B] 角色档案/资料
      游戏内的角色资料、立绘描述、天赋与技能描述
  [C] 同人创作/二创
      优秀的同人作品（文章、图片说明）
  [D] 上传其他文件
      PDF / 图片 / 任意文本
  [E] 直接粘贴内容
      把文字复制进来
可以混用，也可以跳过（仅凭手动信息生成）。
```

---

如果用户说"没有文件"或"跳过"，仅凭 Step 1 的手动信息生成 Skill。

### Step 3：分析资料

将收集到的所有资料和用户填写的基础信息汇总，按以下两条线分析：

**线路 A（Knowledge Skill）**：
- 参考 `${THERESA_SKILL_DIR}/prompts/knowledge_analyzer.md` 中的提取维度
- 提取：背景故事、阵营关系、核心事件、哲学理念、领导风格、能力与弱点

**线路 B（Persona）**：
- 参考 `${THERESA_SKILL_DIR}/prompts/persona_analyzer.md` 中的提取维度
- 将用户填写的标签翻译为具体行为规则
- 从资料中提取：表达风格、情感逻辑、决策模式、关系行为

### Step 4：生成并预览

参考 `${THERESA_SKILL_DIR}/prompts/knowledge_builder.md` 生成 Knowledge Skill 内容。
参考 `${THERESA_SKILL_DIR}/prompts/persona_builder.md` 生成 Persona 内容（5 层结构）。

向用户展示摘要（各 5-8 行），询问确认。

### Step 5：写入文件

用户确认后，创建目录结构并写入：
- `theresas/{slug}/knowledge.md`
- `theresas/{slug}/persona.md`
- `theresas/{slug}/meta.json`
- `theresas/{slug}/SKILL.md`

---

## 进化模式

**追加资料**：用户提供新文件时自动分析增量并合并。
**对话纠正**：用户表达"不对"时写入 Correction 层。

---

## 管理命令

| 命令 | 说明 |
|------|------|
| `/list-theresas` | 列出所有角色 Skill |
| `/theresa-rollback {slug} {version}` | 回滚到历史版本 |
| `/delete-theresa {slug}` | 删除 |

---

## 特蕾西娅角色预设

如果你想创建的是**特蕾西娅（Theresa-9）**本人，以下是预设信息：

- **阵营**：整合运动 / 巴别塔 / 维多利亚
- **身份**：摄政王、卡兹戴尔实际统治者
- **MBTI**：INFJ
- **核心特质**：慈悲的理想主义者，温柔而不可动摇
- **关键关系**：塔露拉（如同姐妹）、阿丽娜（挚友）、凯尔希（亦敌亦友）
- **哲学**："让所有人为我而死，这便是慈悲"
