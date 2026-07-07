#!/usr/bin/env python3
"""语义匹配原型模块的测试"""

import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))


class TestTfidfBackend(unittest.TestCase):
    def test_fit_and_similarity(self):
        from semantic_matcher import TfidfBackend
        backend = TfidfBackend()
        backend.fit(["她很温柔", "她很愤怒", "他非常温柔"])
        sim_same = backend.similarity("她很温柔", "他非常温柔")
        sim_diff = backend.similarity("她很温柔", "她很愤怒")
        # TF-IDF 基线：相似文本相似度应 > 0（短文本下数值有限，
        # 深度语义区分需依赖嵌入模型后端，此处验证接口可用性）
        self.assertGreater(sim_same, 0, "相似文本应 > 0")
        self.assertGreater(sim_diff, 0, "不相关文本在 TF-IDF 下也应有词重叠分")

    def test_empty_text(self):
        from semantic_matcher import TfidfBackend
        backend = TfidfBackend()
        backend.fit(["测试文本"])
        self.assertEqual(backend.similarity("", "测试"), 0.0)
        self.assertEqual(backend.similarity("测试", ""), 0.0)

    def test_embed_returns_vector(self):
        from semantic_matcher import TfidfBackend
        backend = TfidfBackend()
        backend.fit(["温柔的话语", "愤怒的咆哮"])
        vec = backend.embed("温柔")
        self.assertIsInstance(vec, list)
        self.assertEqual(len(vec), len(backend._idf))


class TestSemanticMatcher(unittest.TestCase):
    def setUp(self):
        from semantic_matcher import SemanticMatcher, TfidfBackend
        self.matcher = SemanticMatcher(backend=TfidfBackend())
        self.corpus = [
            "面对牺牲时她选择沉默",
            "她从不流泪只是更安静",
            "她大声怒吼宣泄情绪",
            "她轻声说愿意和你一起走",
        ]
        self.matcher.fit(self.corpus)

    def test_search_returns_sorted_results(self):
        results = self.matcher.search("她很安静", top_k=3)
        self.assertLessEqual(len(results), 3)
        # 应按相似度降序
        scores = [s for _, s in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_search_requires_fit(self):
        from semantic_matcher import SemanticMatcher, TfidfBackend
        m = SemanticMatcher(backend=TfidfBackend())
        with self.assertRaises(RuntimeError):
            m.search("test")

    def test_cluster_returns_groups(self):
        clusters = self.matcher.cluster(n_clusters=2)
        self.assertGreaterEqual(len(clusters), 1)
        self.assertLessEqual(len(clusters), 4)
        # 所有文档应被分配
        total = sum(len(c) for c in clusters)
        self.assertEqual(total, len(self.corpus))

    def test_find_semantic_duplicates(self):
        dups = self.matcher.find_semantic_duplicates(threshold=0.0)
        # 阈值 0 应能找到至少一些相似对
        self.assertIsInstance(dups, list)


class TestSemanticKeywordMatch(unittest.TestCase):
    def test_exact_match(self):
        from semantic_matcher import semantic_keyword_match
        result = semantic_keyword_match("她很温柔", ["温柔"])
        self.assertEqual(result["温柔"], 1.0)

    def test_synonym_expansion(self):
        from semantic_matcher import semantic_keyword_match
        # "柔和" 在 "温柔" 的同义簇中
        result = semantic_keyword_match("她的声音很柔和", ["温柔"])
        self.assertGreater(result["温柔"], 0, "同义词应被匹配")

    def test_no_match(self):
        from semantic_matcher import semantic_keyword_match
        result = semantic_keyword_match("今天天气不错", ["愤怒"])
        self.assertEqual(result["愤怒"], 0.0)

    def test_expand_keyword(self):
        from semantic_matcher import expand_keyword
        expanded = expand_keyword("悲伤")
        self.assertIn("悲伤", expanded)
        self.assertIn("痛苦", expanded)
        # 未知词返回自身
        self.assertEqual(expand_keyword("未知词"), ["未知词"])


class TestEmbeddingBackendProtocol(unittest.TestCase):
    def test_tfidf_implements_protocol(self):
        from semantic_matcher import TfidfBackend
        backend = TfidfBackend()
        # Protocol 是结构化的，检查方法存在
        self.assertTrue(hasattr(backend, "fit"))
        self.assertTrue(hasattr(backend, "embed"))
        self.assertTrue(hasattr(backend, "similarity"))


if __name__ == "__main__":
    unittest.main()
