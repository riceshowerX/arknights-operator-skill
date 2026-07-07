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

## 当前基线（v3.5.0）

| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `constants.py` | 100% | 纯常量定义 |
| `shared_utils.py` | ~76% | 通用工具，核心路径已覆盖 |
| `context_annotator.py` | ~67% | 语境标注核心 |
| `dialogue_fingerprint.py` | ~53% | 8 维度指纹分析 |
| `phase_inferrer.py` | ~52% | 时期推断 |
| `story_extractor.py` | ~52% | 剧情提取 |
| `temporal_slicer.py` | ~41% | 时序切片 |
| `skill_writer.py` | ~36% | 文件管理（CLI 主流程未测） |
| `speech_act_analyzer.py` | ~36% | 话语行为分析 |
| `version_manager.py` | ~35% | 版本管理 |
| `game_data_parser.py` | ~34% | PRTS 解析（网络代码未测） |
| `data_injector.py` | ~33% | 数据注入 |
| `prts_client.py` | ~33% | PRTS API 客户端（网络代码未测） |
| `pipeline.py` | ~31% | 管线编排（subprocess 模式未测） |
| `relationship_graph.py` | ~31% | 关系图谱 |
| `persona_validator.py` | ~18% | Persona 验证器 |
| `canon_checker.py` | ~24% | 设定验证器 |
| **总计** | **~40%** | 基线值 |

## 提升方向

1. **网络代码**：`prts_client.py` / `game_data_parser.py` 的网络请求逻辑可通过 mock 提升覆盖
2. **CLI 主流程**：`pipeline.py` / `skill_writer.py` 的 main() 可通过 function 模式测试
3. **验证器**：`persona_validator.py` / `canon_checker.py` 可补充更多边界用例

## CI 集成

GitHub Actions（`.github/workflows/ci.yml`）在 Python 3.12 任务中自动运行覆盖率并上传至 Codecov。

## 注意事项

- 覆盖率是**必要非充分**指标——高覆盖率不等于高质量
- 重点关注分支覆盖率（Branch）而非仅行覆盖率（Stmts）
- 未经测试的代码视为技术债，应逐步补充用例
