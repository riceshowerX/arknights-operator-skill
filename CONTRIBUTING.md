# 贡献指南

感谢你愿意参与。这个项目同时是「一个 Python 工具链」和「一份角色档案数据集」，所以贡献分两类：**改代码** 与 **加档案**。两类的要求不同，请先读对应章节。

---

## 环境准备

```bash
git clone https://github.com/riceshowerX/arknights-operator-skill
cd arknights-operator-skill

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

要求 Python **3.10+**。运行期不依赖任何第三方库；`[dev]` 只装 pytest / pytest-cov / ruff / mypy。

### 提交前必须跑

```bash
python -m pytest tests/ -q            # 必须全绿（当前 311 passed）
python -m ruff check tools/ tests/    # 必须 0 违规
```

CI 会在 Linux 与 Windows、Python 3.10–3.13 上重复这两步，并带覆盖率门禁。本地没跑通就提 PR，基本会被打回。

---

## 测试政策（重要）

**不接受为了让 CI 变绿而修改测试断言、放宽阈值或跳过用例的 PR。**

如果改动导致测试失败，只有两种正确处理方式：

1. 改源码，让行为回到原本的契约；
2. 如果行为**本来就应该变**（例如修了一个 bug），在 PR 描述里写清「原行为 → 新行为 → 为什么旧断言是错的」，并同步更新 CHANGELOG。

新增缺陷修复时，请附一个**能复现原缺陷的用例**（先让它红，再修到绿）。本仓库的 [`tests/test_regression_v360.py`](tests/test_regression_v360.py) 就是这样攒出来的。

---

## 代码约定

### 必须遵守的几条

| 约定 | 原因 |
|---|---|
| 产物文件名一律引用 `tools/artifacts.py`，不要硬编码字符串 | 生产者和消费者曾因文件名不一致而静默丢数据 |
| 读文本用 `shared_utils.read_text_utf8()`，读 JSON 用 `load_json_safe()` / `assets.load_json_or()` | 直接 `read_text(encoding="utf-8")` 会在带 BOM 的文件上崩 |
| 写文件用 `atomic_write_json()` / `atomic_write_text()` | 中途失败会留下半截 JSON |
| CLI 结束用 `cli.finish(result)` | 统一退出码：0 成功 / 1 失败 / 2 参数错误或待确认 |
| 尊重 `--strict` | 降级处理在 strict 下必须变成失败 |
| 新增产物要同时更新 `artifacts.py` 与 `SKILL.md` 的产物表 | 否则 `--resume` 判据和文档会对不上 |

### 不要做的事

- 不要引入运行期第三方依赖（标准库足够；确有必要的，先开 Issue 讨论）。
- 不要改评分/判定阈值来让输出「看起来更好」——阈值是产品决策，需要单独讨论。
- 不要在 `tools/` 里写平台相关的路径分隔符或硬编码绝对路径。

### 代码风格

- 行宽 120，ruff 规则见 `pyproject.toml`（`E,F,W,I,N,UP,B,SIM`）。
- `tools/*.py` 与 `tests/*.py` 允许 `E402`：这些脚本需要先 `sys.path.insert` 再导入，是「可从任意目录直接运行」的设计代价。
- 注释写「为什么」，不写「是什么」。复杂分支请说明它防的是什么问题。

---

## 加一个角色档案

1. 用 CLI 跑全流程（需要网络）：

   ```bash
   arknights-distill --name <角色名>
   ```

2. 检查产物目录 `operators/<slug>/`：
   - `context.json` 里 `stats.source_distribution` 的 `story` 计数不应为 0；
   - `fingerprint.json`、`speech_act_profile.json`、`temporal_slices.json` 非空；
   - `relationship_graph.json` 允许为空（已知限制），但要在 PR 里说明。

3. 用 AI Agent 按 `tools/_prompts/` 下的模板生成 `knowledge.md` 与 `persona.md`，并跑：

   ```bash
   python tools/persona_validator.py --persona operators/<slug>/persona.md \
       --context-json operators/<slug>/context.json
   ```

4. PR 中附：角色名、数据来源页面、`source_distribution` 数字、验证分数。

> 只提交你确实跑通过的数据。不要手工编造 `knowledge.md` 里的事实——那会污染整个档案的可信度。

---

## 加一个数据源

现有抓取器针对 PRTS Wiki。若要接入别的来源：

1. 在 `tools/` 下新建模块，或在现有 `game_data_parser` / `story_extractor` 中扩展；
2. 输出必须能落到既有契约（`operator_data.json` / `story_data.json` 的字段），否则下游全部要改；
3. 必须处理：编码（BOM / GBK）、超时、HTTP 非 200、页面结构变更导致的空结果；
4. 补一个**不依赖网络**的用例（把 HTML 片段存成 fixture），否则 CI 会不稳定。

---

## 提交与 PR

### 提交信息

采用 Conventional Commits 的简化版：

```text
fix: 修正 story_extractor 在 --discover 时 chapters 为 null
feat: 支持从本地 HTML 快照解析剧情
refactor: 合并 compare_metrics 与 compare_metrics_v2
docs: 补充 macOS 上的安装说明
test: 为 meta 字段级合并补回归用例
```

标题写「做了什么」，正文写「为什么」以及「对用户可见的影响」。

### PR 描述请包含

- 关联 Issue（如有）
- 改动类型：bug 修复 / 新功能 / 重构 / 文档
- **是否影响接口或产物**（文件名、JSON 字段、CLI 参数、退出码）
- 验证方式：跑了什么命令、结果如何；涉及行为变更的，附改前/改后对比
- 若为重构：说明如何证明行为未变（golden 文件、差分脚本、新增回归用例）

### 评审会看什么

1. 有没有偷偷改测试或阈值；
2. 错误处理是否吞掉了失败（`except: pass`、失败仍返回成功）；
3. 新增产物/字段是否同步到 `artifacts.py` 与文档；
4. 是否引入平台相关行为（路径、编码、换行符）。

---

## 报告问题

- **Bug** → 用 [Bug 模板](.github/ISSUE_TEMPLATE/bug_report.yml)，请附 `python --version`、操作系统、完整命令与日志尾部。
- **功能建议** → 用 [Feature 模板](.github/ISSUE_TEMPLATE/feature_request.yml)，说明使用场景而不是只给方案。
- **安全漏洞** → 不要开公开 Issue，按 [SECURITY.md](SECURITY.md) 私下报告。

## 行为准则

参与本项目即表示同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
