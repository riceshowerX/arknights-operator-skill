# 语义匹配设计文档

## 背景

当前工具链（`dialogue_fingerprint` / `speech_act_analyzer` / `relationship_graph`）依赖**关键词与正则匹配**，存在天花板：

| 局限 | 举例 |
|------|------|
| 含蓄表达失效 | "她眼里的光熄了" 无法被"悲伤"词典命中 |
| 同义词不共享语义 | "痛苦"/"煎熬"/"痛楚" 需逐个收录 |
| 无法理解言外之意 | "你确定吗？" 的质问/关心/质疑需上下文判断 |

README「提升方向」已将「深层语义分析——从关键词匹配升级到语义嵌入」列为长期目标。

## 设计目标

1. **零依赖约束不变**：核心实现仅用 Python 标准库
2. **可插拔后端**：支持从 TF-IDF 基线平滑升级到深度嵌入模型
3. **渐进式部署**：原型不破坏现有管线，可独立验证后再接入

## 架构

```
SemanticMatcher（封装层）
  search() / cluster() / find_duplicates()
        │ 委托
        ▼
EmbeddingBackend（Protocol 接口）
  fit() / embed() / similarity()
        │ 实现
   ┌────┴────┐
   ▼         ▼
TfidfBackend  ExternalEmbedding（预留）
(零依赖基线)   (接入点)
```

## 实现现状（v3.5 原型）

### `tools/semantic_matcher.py`

| 组件 | 说明 |
|------|------|
| `EmbeddingBackend` | Protocol 接口，定义 fit/embed/similarity 三方法 |
| `TfidfBackend` | 零依赖 TF-IDF + 余弦相似度基线实现 |
| `SemanticMatcher` | 封装层，提供检索/聚类/去重 |
| `SEMANTIC_GROUPS` | 预定义同义簇（7 类情感），替代逐词收录 |
| `expand_keyword` | 关键词语义扩展 |
| `semantic_keyword_match` | 三级匹配：精确 → 同义 → 语义相似度 |

### 测试覆盖

`tests/test_semantic_matcher.py`（12 用例）覆盖 TfidfBackend、SemanticMatcher、同义扩展、Protocol 接口。

## 渐进式部署路线

### 阶段 1（当前 v3.5）
- 接口设计完成，TfidfBackend 作为基线
- `semantic_keyword_match` 提供三级匹配
- `SEMANTIC_GROUPS` 替代逐词收录
- **未接入主管线**，仅独立原型验证

### 阶段 2（规划中）
- 接入外部嵌入模型后端（如 z-ai-web-dev-sdk 的 embedding API）
- 实现 `ExternalEmbeddingBackend`
- 基准测试对比 TF-IDF vs 深度嵌入

### 阶段 3（规划中）
- `dialogue_fingerprint` 新增「语义模式」开关
- `speech_act_analyzer` 用语义相似度替代部分规则
- `relationship_graph` 用语义匹配发现隐含关系

## 预期收益

| 场景 | 关键词匹配 | TF-IDF 基线 | 深度嵌入（预期） |
|------|-----------|------------|----------------|
| "她眼里的光熄了" → 悲伤 | 失败 | 失败（无词重叠） | 成功 |
| "煎熬" ≈ "痛苦" | 失败（需收录） | 部分 | 成功 |
| "你确定吗？" 语气判断 | 失败 | 失败 | 成功（上下文） |
| 大规模去重 | 成功 | 成功 | 成功 |

## 风险与权衡

1. **零依赖 vs 语义质量**：TF-IDF 在短文本上效果有限，深度语义需外部模型
2. **性能**：嵌入模型调用有网络开销，需缓存
3. **可解释性**：TF-IDF 可解释，深度嵌入是黑盒
4. **接入复杂度**：阶段 3 接入主管线需谨慎，避免破坏现有验证

## 结论

本原型验证了「可插拔语义后端」的接口设计可行性。TfidfBackend 作为零依赖基线可用于词汇重叠层面的语义打分与去重；真正的深度语义理解待阶段 2 接入外部嵌入模型后实现。接口设计保证平滑升级路径——切换后端无需改动 SemanticMatcher 上层代码。
