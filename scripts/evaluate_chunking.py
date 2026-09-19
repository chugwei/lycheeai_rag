"""可重复的 chunking 质量评估与生产门禁。"""
import argparse
import json
import math
import pickle
import re
import statistics
import sys
import types
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_bm25_chunks(path: Path):
    try:
        from rank_bm25 import BM25Okapi  # noqa: F401
    except ImportError:
        module = types.ModuleType("rank_bm25")
        module.BM25Okapi = type("BM25Okapi", (object,), {})
        sys.modules["rank_bm25"] = module
    with path.open("rb") as handle:
        return pickle.load(handle)["corpus_meta"]


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * fraction))]


def evaluate(chunks, configured_size=768):
    texts = [item.get("text", item.get("content", "")) for item in chunks]
    bodies = [re.sub(r"^【[^】]+】", "", text) for text in texts]
    lengths = [len(text) for text in texts]
    n = max(1, len(texts))
    exact_duplicates = len(texts) - len(set(texts))
    lowercase_start = sum(bool(re.match(r"^[a-z]", t)) for t in bodies if t)
    punctuation_start = sum(bool(re.match(r"^[,.;:，。；：)\]}]", t)) for t in bodies if t)
    bad_end = sum(bool(re.search(r"[A-Za-z(\[{]$", t)) for t in bodies if t)
    topic_prefix = sum(t.startswith("【") for t in texts)
    tiny = sum(length < 100 for length in lengths)
    oversize = sum(length > configured_size for length in lengths)
    metadata = [item.get("metadata", {}) for item in chunks]
    traceable = sum(bool(
        m.get("chunker_version") and isinstance(m.get("chunk_index"), int)
        and m.get("chunk_length") is not None
    ) for m in metadata)
    by_source_page = Counter(
        (item.get("source") or item.get("metadata", {}).get("source", ""),
         item.get("metadata", {}).get("page", 0)) for item in chunks
    )
    metrics = {
        "total_chunks": len(texts),
        "length": {
            "min": min(lengths, default=0), "p10": percentile(lengths, .1) if lengths else 0,
            "p50": statistics.median(lengths) if lengths else 0,
            "p90": percentile(lengths, .9) if lengths else 0,
            "max": max(lengths, default=0), "mean": round(statistics.mean(lengths), 2) if lengths else 0,
        },
        "tiny_rate": tiny / n,
        "oversize_rate": oversize / n,
        # 小写开头在 overlap 场景可能是完整英文单词，单独报告但不误判为损坏。
        "lowercase_start_rate": lowercase_start / n,
        "punctuation_start_rate": punctuation_start / n,
        "bad_end_rate": bad_end / n,
        "exact_duplicate_rate": exact_duplicates / n,
        "topic_prefix_rate": topic_prefix / n,
        "traceability_rate": traceable / n,
        "source_page_groups": len(by_source_page),
    }
    gates = {
        "no_oversize": metrics["oversize_rate"] <= .02,
        "tiny_rate_le_2pct": metrics["tiny_rate"] <= .02,
        "exact_duplicate_rate_le_0_5pct": metrics["exact_duplicate_rate"] <= .005,
        "punctuation_start_rate_le_2pct": metrics["punctuation_start_rate"] <= .02,
        "bad_end_rate_le_8pct": metrics["bad_end_rate"] <= .08,
        "traceability_100pct": metrics["traceability_rate"] == 1,
    }
    return {"metrics": metrics, "gates": gates, "passed": all(gates.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=PROJECT_ROOT / "indexes" / "bm25_index.pkl")
    parser.add_argument("--chunk-size", type=int, default=768)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = evaluate(load_bm25_chunks(args.index), args.chunk_size)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if args.strict and not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
