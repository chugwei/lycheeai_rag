import unittest

from scripts.evaluate_chunking import evaluate


class ChunkQualityTests(unittest.TestCase):
    def item(self, text, index=0):
        return {"text": text, "source": "x.md", "metadata": {
            "chunker_version": "rule-v3", "chunk_index": index,
            "chunk_length": len(text), "page": 0,
        }}

    def test_topic_prefix_does_not_hide_punctuation_boundary(self):
        report = evaluate([self.item("【主题：测试】,broken boundary")], 768)
        self.assertEqual(report["metrics"]["punctuation_start_rate"], 1.0)
        self.assertFalse(report["gates"]["punctuation_start_rate_le_2pct"])

    def test_clean_corpus_passes_all_gates(self):
        chunks = [self.item("【主题：测试】这是完整的技术说明。" + "内容" * 60, i) for i in range(10)]
        # 保持文本不重复，避免重复率门禁。
        for i, chunk in enumerate(chunks):
            chunk["text"] += str(i)
            chunk["metadata"]["chunk_length"] = len(chunk["text"])
        self.assertTrue(evaluate(chunks, 768)["passed"])


if __name__ == "__main__":
    unittest.main()
