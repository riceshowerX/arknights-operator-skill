#!/usr/bin/env python3
"""
语义匹配原型 — 关键词匹配的语义增强替代方案

设计动机
========
当前工具链（dialogue_fingerprint / speech_act_analyzer / relationship_graph）
依赖关键词与正则匹配，存在天花板：
  - 含蓄表达失效（"她眼里的光熄了" 无法被"悲伤"词典命中）
  - 同义词不共享语义（"痛苦"/"煎熬"/"痛楚" 需逐个收录）
  - 无法理解言外之意

本模块探索「语义嵌入」替代方案，在保持零依赖约束下提供：
  1. SemanticMatcher —— 可插拔的语义匹配后端接口
  2. TfidfBackend   —— 零依赖的 TF-IDF + 余弦相似度后端（默认）
  3. EmbeddingBackend 接口 —— 预留外部嵌入模型（如 sentence-transformers）接入点

使用示例
========
    from semantic_matcher import SemanticMatcher, TfidfBackend

    matcher = SemanticMatcher(backend=TfidfBackend())
    matcher.fit([
        "面对牺牲时她选择沉默",
        "她从不流泪只是更安静",
        "她大声怒吼宣泄情绪",
    ])

    # 语义相似度检索（替代关键词匹配）
    scores = matcher.search("她很悲伤", top_k=2)
    # → [("面对牺牲时她选择沉默", 0.42), ("她从不流泪只是更安静", 0.38)]

    # 语义聚类（发现隐含主题）
    clusters = matcher.cluster(n_clusters=2)

渐进式部署策略
==============
  阶段 1（当前）：TfidfBackend 作为基线，验证接口设计
  阶段 2：接入外部嵌入模型（如 z-ai-web-dev-sdk 的 embedding API）
  阶段 3：在 dialogue_fingerprint / speech_act_analyzer 中可选启用语义模式

注意：本模块为探索性原型，未接入主管线。测试覆盖于 tests/test_multi_faction.py。
"""

import argparse
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Protocol

# ──────────────────────────────────────────────
# 后端接口定义
# ──────────────────────────────────────────────


class EmbeddingBackend(Protocol):
    """语义嵌入后端接口（可插拔设计）"""

    def fit(self, corpus: list[str]) -> None:
        """用语料库训练后端"""
        ...

    def embed(self, text: str) -> list[float]:
        """将文本编码为向量"""
        ...

    def similarity(self, a: str, b: str) -> float:
        """计算两段文本的语义相似度（0.0-1.0）"""
        ...


# ──────────────────────────────────────────────
# TF-IDF 后端（零依赖基线实现）
# ──────────────────────────────────────────────


# 中文分词：基于标点与单字的简单分词（零依赖约束下）
# 实际部署可替换为 jieba 或嵌入模型
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z]+|\d+")


def _tokenize(text: str) -> list[str]:
    """简易分词：单字 + 英文单词 + 数字"""
    return _TOKEN_RE.findall(text.lower())


class TfidfBackend:
    """TF-IDF + 余弦相似度后端（零依赖）

    作为语义匹配的基线实现。虽不如深度嵌入模型，但能捕获
    词汇重叠度与逆文档频率加权的语义近似。

    局限性：
      - 无法理解同义不同字（"痛苦" vs "煎熬"）
      - 无法处理隐喻
      - 优势：可解释、零依赖、训练即用

    适用场景：作为关键词匹配的补充，在词汇重叠层面提供语义打分。
    """

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._doc_vectors: list[dict[str, float]] = []
        self._corpus: list[str] = []
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        """用语料库训练 IDF"""
        self._corpus = list(corpus)
        df: dict[str, int] = defaultdict(int)
        doc_tokens: list[list[str]] = []

        for doc in corpus:
            tokens = _tokenize(doc)
            doc_tokens.append(tokens)
            for token in set(tokens):
                df[token] += 1

        n_docs = max(len(corpus), 1)
        self._idf = {
            token: math.log((1 + n_docs) / (1 + df_count)) + 1
            for token, df_count in df.items()
        }

        # 预计算所有文档向量
        self._doc_vectors = []
        for tokens in doc_tokens:
            self._doc_vectors.append(self._compute_tfidf(tokens))

        self._fitted = True

    def _compute_tfidf(self, tokens: list[str]) -> dict[str, float]:
        """计算单文档的 TF-IDF 向量"""
        if not tokens:
            return {}
        tf = Counter(tokens)
        total = len(tokens)
        return {
            token: (count / total) * self._idf.get(token, 1.0)
            for token, count in tf.items()
        }

    def embed(self, text: str) -> list[float]:
        """将文本编码为 TF-IDF 向量（稀疏字典转密集列表）"""
        if not self._fitted:
            self.fit([text])
        vec = self._compute_tfidf(_tokenize(text))
        # 转为密集向量（按 IDF 字典顺序）
        return [vec.get(token, 0.0) for token in self._idf]

    def similarity(self, a: str, b: str) -> float:
        """余弦相似度"""
        vec_a = self._compute_tfidf(_tokenize(a))
        vec_b = self._compute_tfidf(_tokenize(b))
        if not vec_a or not vec_b:
            return 0.0
        # 余弦相似度
        dot = sum(vec_a.get(t, 0.0) * vec_b.get(t, 0.0) for t in vec_a)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


# ──────────────────────────────────────────────
# 语义匹配器
# ──────────────────────────────────────────────


class SemanticMatcher:
    """语义匹配器 —— 封装嵌入后端，提供检索与聚类接口

    用法:
        matcher = SemanticMatcher(backend=TfidfBackend())
        matcher.fit(corpus)
        scores = matcher.search(query, top_k=5)
    """

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self.backend = backend or TfidfBackend()
        self._corpus: list[str] = []
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        """训练匹配器"""
        self._corpus = list(corpus)
        self.backend.fit(corpus)
        self._fitted = True

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """语义相似度检索

        Args:
            query: 查询文本
            top_k: 返回最相似的前 K 条

        Returns:
            (文本, 相似度) 列表，按相似度降序
        """
        if not self._fitted:
            raise RuntimeError("需先调用 fit() 训练")
        scores = [
            (doc, self.backend.similarity(query, doc))
            for doc in self._corpus
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def cluster(self, n_clusters: int = 2) -> list[list[str]]:
        """简易语义聚类（基于相似度的贪心聚类，零依赖）

        Args:
            n_clusters: 目标簇数

        Returns:
            聚类结果（每个簇的文档列表）
        """
        if not self._fitted:
            raise RuntimeError("需先调用 fit() 训练")
        if not self._corpus:
            return []

        # 贪心聚类：选第一个文档为种子，相似度高的归入同簇
        clusters: list[list[str]] = [[self._corpus[0]]]
        seeds = [self._corpus[0]]

        for doc in self._corpus[1:]:
            best_sim = -1.0
            best_idx = 0
            for i, seed in enumerate(seeds):
                sim = self.backend.similarity(doc, seed)
                if sim > best_sim:
                    best_sim = sim
                    best_idx = i

            # 若与最相似种子相似度 > 0.3 且簇数已满，归入该簇
            # 否则新建簇（若未达 n_clusters）
            if best_sim > 0.3 or len(clusters) >= n_clusters:
                clusters[best_idx].append(doc)
            else:
                clusters.append([doc])
                seeds.append(doc)

        return clusters

    def find_semantic_duplicates(
        self, threshold: float = 0.85
    ) -> list[tuple[str, str, float]]:
        """发现语义重复文档

        Args:
            threshold: 相似度阈值

        Returns:
            (doc_a, doc_b, similarity) 列表
        """
        if not self._fitted:
            raise RuntimeError("需先调用 fit() 训练")
        dups = []
        n = len(self._corpus)
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.backend.similarity(self._corpus[i], self._corpus[j])
                if sim >= threshold:
                    dups.append((self._corpus[i], self._corpus[j], sim))
        return dups


# ──────────────────────────────────────────────
# 关键词匹配增强：语义扩展词典
# ──────────────────────────────────────────────


# 预定义的语义簇（同义词组），替代逐个收录词典
SEMANTIC_GROUPS: dict[str, list[str]] = {
    "悲伤": ["悲伤", "哀伤", "痛苦", "煎熬", "心碎", "黯然", "落寞", "怅然"],
    "愤怒": ["愤怒", "怒火", "愤慨", "恼怒", "暴怒", "震怒", "怒不可遏"],
    "温柔": ["温柔", "柔和", "轻柔", "温和", "慈爱", "体贴", "细腻"],
    "坚定": ["坚定", "坚决", "果决", "毅然", "决然", "毫不犹疑"],
    "沉默": ["沉默", "无言", "缄默", "静默", "不语", "寂然"],
    "信任": ["信任", "信赖", "托付", "倚重", "信服"],
    "背叛": ["背叛", "出卖", "反叛", "倒戈", "背信"],
}


def expand_keyword(keyword: str) -> list[str]:
    """语义扩展：给定关键词，返回同义簇

    替代在词典中逐个收录同义词的做法。
    """
    for group in SEMANTIC_GROUPS.values():
        if keyword in group:
            return list(group)
    return [keyword]


def semantic_keyword_match(
    text: str, keywords: list[str], matcher: SemanticMatcher | None = None
) -> dict[str, float]:
    """语义关键词匹配（增强版）

    对每个关键词，既做精确匹配，又通过语义相似度做模糊匹配。
    替代传统的 `any(kw in text for kw in keywords)` 写法。

    Args:
        text: 待匹配文本
        keywords: 关键词列表
        matcher: 可选的语义匹配器（未提供则仅做精确匹配 + 同义扩展）

    Returns:
        {关键词: 最高匹配分数（0.0-1.0）} 字典
    """
    result: dict[str, float] = {}
    expanded_corpus = " ".join(" ".join(expand_keyword(kw)) for kw in keywords)

    for kw in keywords:
        # 1. 精确匹配 → 1.0
        if kw in text:
            result[kw] = 1.0
            continue

        # 2. 同义扩展匹配
        synonyms = expand_keyword(kw)
        if any(syn in text for syn in synonyms):
            result[kw] = 0.8
            continue

        # 3. 语义相似度匹配（若提供 matcher）
        if matcher is not None:
            sim = matcher.backend.similarity(kw, text)
            # 与扩展语料的最大相似度
            sim_corpus = matcher.backend.similarity(expanded_corpus, text) if expanded_corpus else 0.0
            result[kw] = max(sim, sim_corpus * 0.7)
        else:
            result[kw] = 0.0

    return result


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="语义匹配原型 — 关键词匹配的语义增强替代方案",
    )
    parser.add_argument("--corpus", help="语料库文件（每行一条）")
    parser.add_argument("--query", help="查询文本")
    parser.add_argument("--top-k", type=int, default=5, help="返回前 K 条")
    parser.add_argument(
        "--mode",
        choices=["search", "cluster", "duplicates"],
        default="search",
        help="运行模式",
    )
    args = parser.parse_args()

    if not args.corpus:
        # 演示模式
        corpus = [
            "面对牺牲时她选择沉默，眼里的光熄了",
            "她从不流泪，只是更安静，省略号更多",
            "她大声怒吼，宣泄着所有情绪",
            "她轻声说，我愿意和你一起走",
            "她看着他，目光里没有恨意，只有失望",
        ]
        print("（使用演示语料库）")
    else:
        corpus = Path(args.corpus).read_text(encoding="utf-8").strip().split("\n")

    matcher = SemanticMatcher(backend=TfidfBackend())
    matcher.fit(corpus)

    if args.mode == "search":
        query = args.query or "她很悲伤"
        print(f"\n查询: {query}")
        print("语义检索结果:")
        for text, score in matcher.search(query, top_k=args.top_k):
            print(f"  [{score:.3f}] {text}")

    elif args.mode == "cluster":
        print("\n语义聚类结果:")
        for i, cluster in enumerate(matcher.cluster(n_clusters=2)):
            print(f"\n簇 {i + 1}:")
            for doc in cluster:
                print(f"  - {doc}")

    elif args.mode == "duplicates":
        print("\n语义重复检测:")
        dups = matcher.find_semantic_duplicates(threshold=0.3)
        if not dups:
            print("  无重复")
        for a, b, sim in dups:
            print(f"  [{sim:.3f}] {a}  <==>  {b}")


if __name__ == "__main__":
    main()
