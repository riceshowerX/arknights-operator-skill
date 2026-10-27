# 测试覆盖率报告

本项目使用 [pytest-cov](https://pytest-cov.readthedocs.io/) 进行覆盖率测量。

## 快速运行

\`\`\`bash
# 安装开发依赖（含 pytest-cov）
pip install -e ".[dev]"

# 运行测试并输出覆盖率到终端
python -m pytest tests/ --cov=tools --cov-report=term-missing

# 生成 HTML 覆盖率报告（htmlcov/index.html）
python -m pytest tests/ --cov=tools --cov-report=html

# 生成 XML 覆盖率报告（供 CI/Codecov 使用）
python -m pytest tests/ --cov=tools --cov-report=xml
\`\`\`

## 配置

覆盖率配置位于 `pyproject.toml` 的 `[tool.coverage.run]` 与 `[tool.coverage.report]` 段：

- **分支覆盖率**：`branch = true`（同时统计分支覆盖，而非仅行覆盖）
- **统计范围**：`source = ["tools"]`（仅统计 tools 目录）
- **排除项**：`__init__.py`、`if __name__ == "__main__"`、`pragma: no cover` 标记的代码

## 当前基线（v3.6.1 · 实测快照）

> 数字由 `python -m pytest tests/ --cov=tools --cov-branch` 实测生成，口径与
> `pyproject.toml` 的 `branch = true` 一致。**不要手改数字**：测试增删后请重跑并整体替换本表。
> 快照时间：v3.6.1 收口时（含 `tests/test_regression_v360.py` 与 `tests/test_regression_v361.py`）。

| 指标 | 实测 | 说明 |
|---|---|---|
| 用例数 | **327 passed** | v3.6.0 为 311 |
| 行覆盖（Stmts） | **54.71%**（2888 / 5279） | 语句覆盖 |
| 分支覆盖（Branch） | **43.59%**（1081 / 2480） | 需 `branch = true` 才统计 |
| **综合（Cover）** | **51.15%** | `(2888 + 1081) / (5279 + 2480)`，即 CI 门禁口径 |

**CI 门禁：`--cov-fail-under=44`**，是「地板值」（floor）：低于 44% 说明有实质回退，必须修复；
高于 44% 属正常波动，不设上行门禁，真实提升由后续用例自然完成。
（v3.6.0 之前 CI 无覆盖率门禁。定门禁时实测综合为 44.87%，取 45 会卡在边界上成为假门槛，
故取 44 留出缓冲；随后 QA 补充 `test_regression_v360.py` 后已升至 47.04%，余量充足。）

### 模块明细（综合覆盖率降序）

| 模块 | 行覆盖 | 分支覆盖 | 综合 | 语句数 |
|---|---|---|---|---|
| `constants.py` | 100% | 100% | 100.00% | 47 |
| `artifacts.py` | 82% | 100% | 81.82% | 11 |
| `shared_utils.py` | 77% | 75% | 76.45% | 242 |
| `data_injector.py` | 80% | 66% | 75.29% | 281 |
| `semantic_matcher.py` | 74% | 62% | 70.39% | 165 |
| `context_annotator.py` | 70% | 65% | 68.20% | 209 |
| `assets.py` | 72% | 50% | 67.00% | 78 |
| `skill_writer.py` | 64% | 53% | 60.28% | 144 |
| `dialogue_fingerprint.py` | 64% | 52% | 59.95% | 511 |
| `story_extractor.py` | 58% | 48% | 54.65% | 219 |
| `phase_inferrer.py` | 56% | 46% | 52.58% | 274 |
| `temporal_slicer.py` | 55% | 36% | 49.21% | 266 |
| `pipeline.py` | 53% | 34% | 48.69% | 296 |
| `speech_act_analyzer.py` | 44% | 38% | 41.67% | 240 |
| `relationship_graph.py` | 39% | 28% | 35.20% | 537 |
| `version_manager.py` | 37% | 28% | 34.51% | 179 |
| `game_data_parser.py` | 39% | 23% | 34.40% | 437 |
| `prts_client.py` | 40% | 15% | 33.33% | 110 |
| `cli.py` | 32% | 0% | 26.00% | 40 |
| `canon_checker.py` | 26% | 19% | 23.74% | 288 |
| `persona_validator.py` | 25% | 18% | 22.55% | 577 |

## 提升方向

1. **网络代码**：`prts_client.py` / `game_data_parser.py` 的网络请求逻辑可通过 mock 提升覆盖
2. **CLI 主流程**：`pipeline.py` / `skill_writer.py` 的 main() 可通过 function 模式测试
3. **验证器**：`persona_validator.py` / `canon_checker.py` 可补充更多边界用例

## CI 集成

GitHub Actions（`.github/workflows/ci.yml`）的 `test` job 在全部矩阵任务（Ubuntu 3.10/3.11/3.12 与
Windows 3.12）上运行覆盖率门禁 `--cov-fail-under=44`，并在 Ubuntu 3.12 任务中上传 Codecov。

## 注意事项

- 覆盖率是**必要非充分**指标——高覆盖率不等于高质量
- 重点关注分支覆盖率（Branch）而非仅行覆盖率（Stmts）
- 未经测试的代码视为技术债，应逐步补充用例
