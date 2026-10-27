# 产物契约（ARTIFACTS）

> 单一来源：[`tools/artifacts.py`](../tools/artifacts.py)。本文是它的人类可读版；
> 两者不一致时，以代码为准并请提 Issue。自检命令：`python tools/artifacts.py`。

## 1. 为什么需要契约

v3.6.0 之前的三个 P0 缺陷全部源于**契约漂移**——同一个文件名在多个模块里各写
一遍字面量：

| 事故 | 根因 |
|---|---|
| 剧情语料 100% 丢失 | `story_extractor` 写 `story_data.json`，`pipeline` 读 `story.json` |
| 分析结果全丢 | 4 个分析工具只 `print` 不落盘，`data_injector` 按文件名去读 |
| `--resume` 误判 | `analyze` 的完成判据挂在 `context.json`（那是 `annotate` 的产物）上 |

把文件名收敛到 `artifacts.py` 后，`grep ARTIFACT tools/` 即可穷举全部读写点。

## 2. 产物总表

`operators/<slug>/` 下的全部文件：

| 文件 | 写入者 | 主要读取者 | 所属步骤 | 说明 |
|---|---|---|---|---|
| `operator_data.json` | `game_data_parser` | `context_annotator`、`canon_checker` | fetch | PRTS 基础资料 |
| `story_data.json` | `story_extractor` | `context_annotator` | fetch | 结构化剧情对话 |
| `context.json` | `context_annotator` | 4 个分析工具、`data_injector` | annotate | 语境化数据模型；`relationship_graph` 会把 `annotated_relations` **回写**进此文件 |
| `fingerprint.json` | `dialogue_fingerprint` | `data_injector` | analyze | 7 维语言指纹 |
| `speech_act_profile.json` | `speech_act_analyzer` | `data_injector` | analyze | 话语行为画像 |
| `relationship_graph.json` | `relationship_graph` | （报告产物，图本体回写 `context.json`） | analyze | 关系图谱构建报告：边/节点计数、`inferred_edges` |
| `temporal_slices.json` | `temporal_slicer` | `data_injector` | analyze | 时序切片与语言演变 |
| `validation.json` | `canon_checker` | AI Agent | validate | 多来源设定交叉验证 |
| `persona_validation.json` | `persona_validator` | AI Agent | validate | 人格一致性评分 |
| `meta.json` | `skill_writer` / `version_manager` | 全部写入步骤 | write | 元数据；**字段级 merge**（v3.6.0 起），`ARKNIGHTS_META_RESET=1` 恢复覆盖语义 |
| `SKILL.md` | `skill_writer` | Agent 客户端 | write | 可调用入口 |
| `knowledge.md` | **AI Agent**（非脚本） | `context_annotator`、`skill_writer` | 人工步骤 | 依据 `tools/_prompts/knowledge_builder.md` 生成 |
| `persona.md` | **AI Agent**（非脚本） | `persona_validator`、`skill_writer` | 人工步骤 | 五层优先级人格 |
| `versions/` | `version_manager` | 回滚命令 | write | 历史版本归档 |

旧名兼容：`story.json` 是 `story_data.json` 的**只读别名**（`LEGACY_ALIASES`），
读取端双读并告警，写入端永远写新名。

## 3. 步骤 → 产物判据（`--resume` 语义）

| 步骤 | 完成判据（全部存在且非空才跳过） |
|---|---|
| `fetch` | `operator_data.json` |
| `annotate` | `context.json` |
| `analyze` | `fingerprint.json` + `speech_act_profile.json` + `temporal_slices.json` + `relationship_graph.json` |
| `validate` | **空（永不跳过）** |
| `write` | `meta.json` + `SKILL.md` |

`validate` 判据为空的原因：strict 模式下校验可能被合法跳过，用产物判定会误跳。
这是 v3.6.0 修复 P1-2（`--resume` 永远跳过 analyze）时定下的口径。

## 4. analyze 步骤的工具接线

`pipeline` 按 `ANALYZE_TOOLS` 驱动，每个工具结束后校验「文件存在且 `st_size > 0`」：

| 工具 | 输出参数 | 产物 |
|---|---|---|
| `speech_act_analyzer` | `--output-profile`（注意：与其余三个不同） | `speech_act_profile.json` |
| `dialogue_fingerprint` | `--output` | `fingerprint.json` |
| `relationship_graph` | `--output` | `relationship_graph.json` |
| `temporal_slicer` | `--output` | `temporal_slices.json` |

校验失败行为：`--strict` 下该步失败（退出码非 0）；非 strict 下 `logger.warning` 继续。

## 5. 资产与模板（随包分发）

| 目录 | 内容 | 解析入口 | 环境变量覆盖 |
|---|---|---|---|
| `tools/_data/` | 6 个 JSON：`operator_db` / `emotion_lexicon` / `speech_act_rules` / `misconceptions` / `context.schema` / `pinyin_map` | `assets.data_dir()`（四级回退） | `ARKNIGHTS_DATA_DIR` |
| `tools/_prompts/` | 7 个模板 md（v3.6.1 起随 wheel 分发） | `assets.prompts_dir()`（三级回退，兼容旧仓库根 `prompts/`） | `ARKNIGHTS_PROMPTS_DIR` |

CI 与 Release 工作流对两者都有**数量断言**（6 JSON + 7 md），发出一个「装完就崩」
的包会直接失败。

## 6. 关系图谱的边类型（v3.6.1 起）

`context.json` 的 `annotated_relations` 中，边的 `type` 有三类来源，
`sources` 字段统一为**证据台词行 id**（可回溯）：

| type | 证据 | 置信度口径 |
|---|---|---|
| 关键词类型（`trust` / `comrade` / `opponent` 等） | 通用 `RELATIONSHIP_PATTERNS` 命中（需双名共现） | 关键词命中次数 |
| 说话人类型（同上，经 `_SPEAKER_PATTERNS` 第一人称限定） | 「我的战友」「教导我」等说话人表述 | 同上 |
| `dialogue` | 行内 `interlocutor`（元数据级：她直接对谁说） | 证据条数：≥4 high / ≥2 medium |
| `mention` | 同行文本提及已知角色（纯共现） | 证据条数：≥6 high / ≥3 medium |

已有语义边的对不再重复产 `mention`；`dialogue` 保留（直接对话是独立证据）。
输出全为 0 边时 `relationship_graph.json` 会带 `inferred_edges: 0` 并打告警，
便于区分「语料不足」与「运行失败」。
