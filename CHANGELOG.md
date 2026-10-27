# Changelog

本文件记录 arknights-operator-skill 的版本变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [3.6.0] — 2026-10-27

一次**行为保持型**重构：产物字段集合、判定阈值、CLI 参数全部向后兼容；
对外可见变化集中在「产物更全 / 退出码更诚实 / 安装态可用」，其中 3 项为
**minor breaking**（见 §3），已在下方逐条标注。

### 1. 新增（Added）

#### 1.1 产物文件（`--step analyze` / `--step validate` 新增落盘）

改造前分析工具只把结果 print 到 stdout，父进程只截留 200 字符日志，
导致 `data_injector` 的 3 个 section 恒「数据不可用」。现在每个工具都会落盘，
文件名统一由 `tools/artifacts.py` 提供（单一契约源，禁止再写字面量）：

| 产物 | 生产者 | 消费者 |
|---|---|---|
| `fingerprint.json` | `dialogue_fingerprint.py` | `data_injector.py`（fingerprint 段） |
| `speech_act_profile.json` | `speech_act_analyzer.py` | `data_injector.py`（speech_acts 段） |
| `temporal_slices.json` | `temporal_slicer.py` | `data_injector.py`（temporal 段） |
| `relationship_graph.json` | `relationship_graph.py` | `data_injector.py` / `data_injector.py`（relationships 段） |
| `validation.json` | `persona_validator.py`（`--step validate`） | CI / 人工复核 |
| `persona_validation.json` | `canon_checker.py`（`--step validate`） | CI / 人工复核 |

> **minor breaking**：输出目录会多出 4–6 个 json 文件。对目录做 `diff`/`rsync`
> 比对的脚本会看到差异；均为**新增**，不覆盖任何既有文件。

#### 1.2 模块与公共设施

- `tools/artifacts.py`：产物文件名 / 步骤→产物映射 / 分析工具表（唯一契约源）。
- `tools/cli.py`：退出码常量 + `finish()` + `safe_print()` + `require_assets()`。
- `tools/assets.py`：`load_json_or()`（读 JSON 失败回退内建值）、
  `data_dir()` / `data_file()` / `project_root()` / `default_base_dir()` /
  `assert_data_assets()`。
- `shared_utils.read_text_utf8()`：`utf-8-sig` → `utf-8` → `gb18030` 三档解码，
  命中最后一档必 `logger.warning`。全库 32 个读取点改用。
- `shared_utils.atomic_write_text()`：原子写文本（临时文件 + `os.replace`）。
- `shared_utils.split_sentences(text, keep="")`：新增 `keep` 参数，
  让各模块**保留各自的标点集**（实现 1 份、行为 N 份），避免合并标点集改变数值。
- `constants.PHASE_ORDER` 由 3 项扩为 6 项，并新增 `PHASE_SORT_INDEX`。
- `constants.CONFIDENCE_TO_STRENGTH`：`high/medium/low → 0.9/0.6/0.3`。
- `persona_validator.LAYER_WEIGHTS`：六层评分权重提为模块级常量（数值未变）。

### 2. 变更（Changed）

- **`data/` → `tools/_data/`（资产搬迁）**：6 个 JSON 移入包内，wheel 安装后可被
  `assets.data_dir()` 找到。仓库根 `data/` 仍被**优先探测**（用户本地魔改继续生效），
  也支持 `ARKNIGHTS_DATA_DIR` 显式覆盖。四级解析顺序：
  `ARKNIGHTS_DATA_DIR` → `<项目根>/data` → `tools/_data` → `importlib.resources`。
- **退出码统一为 0 / 1 / 2**：`0` 成功（含 `list` 查无结果、`--dry-run`）、
  `1` 运行期失败、`2` 用法/前置错误（含 `confirm_required`、资产自检失败）。
  stdout 的 JSON 内容与格式**完全不变**，只有进程码变化。
  > **minor breaking**：`skill_writer --action delete` 未加 `--force` 由 `exit 0` 变 `exit 2`。
- **`meta.json` 改为字段级 merge**：用户域（`corrections_count` / `impression` /
  `created_at` / `tags` / `knowledge_sources`）已有即保留；工具域（`slug` / `name` /
  `name_en` / `version` / `updated_at`）以本次为准；`profile` 深层 merge。
  逃生口：`ARKNIGHTS_META_RESET=1` 强制覆盖。
- **slug 兜底改为确定性哈希**：`hash(name)` → `sha1(name)[:8]`，跨进程稳定；
  且降级日志级别由 warning 提升为 error。
- **剧情文件名双读**：写 `story_data.json`；读取时若只有旧名 `story.json` 仍可命中，
  并 `logger.warning` 提示重跑 fetch。
- **`compare_metrics` 与 `compare_metrics_v2` 合一**：`compare_metrics(base, comp, *,
  with_significance=False, base_values=None, comp_values=None)`；
  `compare_metrics_v2` 变薄包装。默认输出字段集合与顺序保持原样。
  话语行为的遍历顺序固定为 **type 字典序**（`sorted()`），消除
  `PYTHONHASHSEED` 导致的输出顺序漂移。
- **关系抽取改倒排索引**：全文分句 1 次 + 「实体→句号集合」索引 1 次，
  复杂度 O(E²·N) → O(N·E + P·S)。实测 30 实体 / 10.1k 字：**268.8 ms → 72.7 ms（3.7×）**；
  真实语料（4.9k 字）：**8.7 ms → 1.3 ms**。分句标点集、共现谓词、方向判定、
  可信度计算逐行未改。
  > 已知上限：剩余耗时集中在 `RELATIONSHIP_PATTERNS`（约 20 条正则）对每个共现对 ×
  > 相关句段的匹配，该表属产品语义（设计明确禁止改动），故不再继续优化。
  > 若需再降一个量级，需另立工序（按关键词前缀预筛）。
- **关系抽取的实体顺序改为确定序（修既存缺陷）**：`extract_entities()` 原先直接迭代
  Aho-Corasick 返回的 `set[str]`，使**多条关系的顺序**（以及 `from`/`to` 朝向）随
  `PYTHONHASHSEED` 漂移，同一输入两次运行会得到不同产物。现改为按模式标签字典序迭代。
  证据：
  - `relationship_graph.py --context-json operators/te-lei-xi-ya/context.json`：
    `PYTHONHASHSEED=1/7/99` 三次输出 **md5 完全相同**（`25d08a8f…`，1 edge / 2 nodes）
  - 30 实体 / 10.1k 字语料：改前 3 个 seed 得到 3 个不同 md5，改后三次完全一致
  - 内容不变：两个真实 context 的边集合与 canonicalize 后逐字段一致；30 实体语料上
    「(无序实体对, type)」多重集合完全一致（仅 1/337 条边的朝向因 `_detect_direction`
    对 (e1, e2) 非对称而变化，而该朝向在改前本就是 seed 随机的）
- **7 个 `analyze_*` 收敛为薄包装**：委托 `_result_*(_collect_all_metrics(...))`
  （生产链路同一实现），公开名、签名、返回结构不变，删除重复实现约 390 行。
- **`analyze_catchphrases` 等价预筛**：分句标点前置判断 + 正则预编译；
  阈值 `_CN_CHAR_FREQ_BASELINE=0.003`、`significance > 2.0` **未改**。
- **`story_extractor` 章节级时期推断**：`infer_phase()` 由「逐条台词」改为
  「按章节推断一次 + 本地场景判断」，最坏情况下的 O(台词数) 次 HTTP 降为 O(章节数)。
- **`context_annotator` 新增 `stats.interlocutor_distribution`**（并双写顶层同名键）；
  `data_injector` 双读 `stats.*` / 顶层。
- **`data_injector` 关系字段双读**：`to`→`target`→`name`；
  `strength` 数字直用，字符串 `confidence` 走 `CONFIDENCE_TO_STRENGTH` 映射；
  证据数 `len(sources)`→`evidence_count`→`count`；优先 `annotated_relations`。
- **`persona_validator` 评分字段**：`violated` 改为 `len(violations)`（不再把
  「不可自动检测」算作违反），新增 `untestable`；`score` 计算式未变。
- **`relationship_graph` 中文引号判断**：引号集合改为 `{"\"", "“", "”", "「", "『"}`，
  修复「两操作数相同 → 中文弯引号永不命中」。
- **`relationship_graph` 时期排序**：消除 `phases_sorted.index()` 的位置硬编码，
  改用 `PHASE_SORT_INDEX`（避免未知时期抛 `ValueError`）。
  > **minor breaking**：`temporal_slices.json` 内 `slices` 的键顺序可能变化，键集合不变。
- **写盘统一原子化**：`--output` 的 7 处 `Path.write_text` 全部改 `atomic_write_text`
  （临时文件 + `os.replace`，中断不再产生半截文件）。
- **`--base-dir` 默认值不再依赖 CWD**：`None` → `assets.default_base_dir()`
  （`ARKNIGHTS_OPERATORS_DIR` → `<项目根>/operators` → `./operators`）。
  CLI 显式传参仍最高优先。
- **`pipeline` 子进程调用**：补 `encoding="utf-8"`、`errors="replace"`、
  `timeout`（`PipelineConfig.tool_timeout`，默认 1800s）。
- **`--resume` 判据更诚实**：`analyze` 检查 4 个自身产物（存在且 `size>0`），
  不再因 `context.json` 存在而误跳过。

### 3. 修复（Fixed）

- 分析产物不落盘 → `data_injector` 恒「数据不可用」（P0）。
- `story_data.json` / `story.json` 文件名错配 → 剧情对话 100% 丢失（P0）。
- `meta.json` 无条件重写 → 用户 `corrections_count` 从 7 被清零（P0）。
- `_STEP_ARTIFACTS["analyze"] = ["context.json"]` → `--resume` 必跳过分析（P1）。
- `step_validate` 忽略子工具返回值、无条件 `return True` → `--strict` 承诺失效（P1）。
- UTF-8 BOM / GBK 文件读取崩溃（32 处读取点）。
- GBK 控制台遇 `⚠️`（U+26A0）`UnicodeEncodeError` 崩溃。
- `mkdir(exist_ok=True)` 缺 `parents=True`（深层路径创建失败）。
- `version_manager` 归档副本 meta 不自洽（`backup_at`/`version` 缺失 → `list` 恒 `unknown`）。
- `game_data_parser` 的 `except RuntimeError` 是死分支（取数链路从不抛该异常），
  断网时直接崩溃；改为 `except (urllib.error.URLError, OSError)` 真实降级。
- `game_data_parser` 的 `report["missing_fields"]` 与 `expected_fields` 同一列表对象，
  后续 `append` 会污染常量，改为 `list(...)` 拷贝。
- `context_annotator._get_default_phase(operator_data=None)` /
  `dialogue_fingerprint._lines_to_dialogues(source_filter=None)` 的类型标注与默认值不一致。

### 4. 打包 / 配置 / 门禁

- `pyproject.toml`：`version = 3.6.0`；新增 `[tool.setuptools.package-data]`
  `tools = ["_data/*.json"]`。
- 新增 `MANIFEST.in`（sdist 含 `tools/_data/*.json`、`prompts/*.md`、`docs/*.md`）。
- `tests/test_comprehensive.py`：`DATA_DIR` 改为 `assets.data_dir()`（唯一测试改动）。
- `.gitignore`：新增 `.ruff_cache/`。
- CI：新增 `windows-latest`（仅 3.12）、`timeout-minutes: 30`、
  覆盖率门禁 `--cov-fail-under=44`（地板值）、wheel 资产冒烟 job。

### 5. 已知限制（Known limitations）

- `atomic_write_text` 以 `newline=""` 写出，即**文本产物统一 LF**（Windows 上不再被翻译成
  `\r\n`）。字符内容与旧实现逐字相同，仅换行字节在 Windows 上变化；换来的是
  Linux/Windows 产物可直接逐字节比对。
- 覆盖率（`branch = true`）：定门禁时实测行覆盖 49.02% / 分支 36.12% / 综合 **44.87%**，
  故 CI 门禁取 `--cov-fail-under=44`（地板值，保留缓冲；取 45 会卡在边界上成为假门槛）。
  随后 QA 补充 `tests/test_regression_v360.py`，综合已升至 **47.04%**（行 51.00% / 分支 38.70%，
  310 passed），余量充足。详见 `tests/COVERAGE.md`。

---

## [3.5.1] — 之前

见仓库 git 历史与 `README.md` 的功能章节。
