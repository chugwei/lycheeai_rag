import unittest
from unittest.mock import patch

from data_pipeline.chunker import RuleChunker
from data_pipeline.models import Document


class RuleChunkerV3Tests(unittest.TestCase):
    def make_doc(self, text, source="demo_栽培技术_test.md", page=1):
        return Document(text, {"source": source, "page": page, "domain": "cultivation"})

    def test_invalid_parameters_fail_fast(self):
        with self.assertRaises(ValueError):
            RuleChunker(chunk_size=100)
        with self.assertRaises(ValueError):
            RuleChunker(chunk_size=256, overlap=256)

    def test_recursive_split_descends_after_heading(self):
        text = "## 第一节\n\n" + "。".join(["这是一个足够长的中文句子" * 4] * 12) + "。\n\n## 第二节\n内容。"
        chunker = RuleChunker(chunk_size=256, overlap=32, merge_threshold=1)
        chunks = chunker.chunk([self.make_doc(text)])
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(c.content) <= 256 for c in chunks))

    def test_english_hard_split_uses_word_boundary(self):
        sentence = "Lychee downy blight affects fruit quality and orchard productivity. "
        chunker = RuleChunker(chunk_size=220, overlap=30, merge_threshold=1)
        chunks = chunker.chunk([self.make_doc(sentence * 15, source="paper.pdf")])
        self.assertGreater(len(chunks), 2)
        vocabulary = {word.lower() for word in sentence.replace(".", "").split()}
        for chunk in chunks:
            body = chunk.content.split("】", 1)[-1]
            first_word = body.split()[0].strip(".,;:!?").lower()
            self.assertIn(first_word, vocabulary, body[:40])
            self.assertLessEqual(len(chunk.content), 220)

    @patch("data_pipeline.chunker._compute_similarity", return_value=1.0)
    def test_small_chunk_merge_respects_hard_limit(self, _similarity):
        text = "## A\n" + "甲" * 170 + "\n\n## B\n" + "乙" * 100
        chunks = RuleChunker(chunk_size=256, overlap=20, merge_threshold=180).chunk(
            [self.make_doc(text)]
        )
        self.assertTrue(all(len(c.content) <= 256 for c in chunks))

    def test_metadata_is_traceable_and_topic_is_injected(self):
        chunks = RuleChunker(chunk_size=256, overlap=20, merge_threshold=1).chunk(
            [self.make_doc("桂味荔枝适宜及时采收。", source="桂味荔枝栽培技术.md")]
        )
        self.assertTrue(chunks[0].content.startswith("【品种：桂味】"))
        self.assertEqual(chunks[0].metadata["chunker_version"], "rule-v3")
        self.assertEqual(chunks[0].metadata["chunk_index"], 0)
        self.assertEqual(chunks[0].metadata["chunk_length"], len(chunks[0].content))


if __name__ == "__main__":
    unittest.main()
