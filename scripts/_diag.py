"""临时诊断：验证 reranker 设备/耗时 与 LLM stream 是否返回内容。"""
import os, time, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=== A. Reranker device + timing (GPU vs CPU) ===")
import torch
print("torch:", torch.__version__, "cuda.is_available():", torch.cuda.is_available())
from FlagEmbedding import FlagReranker
t0 = time.perf_counter()
rr = FlagReranker("BAAI/bge-reranker-base", use_fp16=True)
print("load time: %.2fs" % (time.perf_counter()-t0))
# 打印模型所在设备
try:
    dev = next(rr.model.parameters()).device
    print("model device:", dev)
except Exception as e:
    print("device check err:", e)
pairs = [("荔枝霜疫霉病怎么防治？", "霜疫霉病危害果实和苗木，湿度大时传播快。") for _ in range(20)]
t1 = time.perf_counter()
scores = rr.compute_score(pairs, normalize=True)
print("rerank 20 pairs: %.3fs" % (time.perf_counter()-t1))
print("scores sample:", [round(float(s),3) for s in list(scores)[:3]])

print("\n=== B. LLM stream vs invoke content ===")
from llm_factory import create_llm
llm = create_llm()
msgs = [{"role": "user", "content": "用一句话回答：荔枝霜疫霉病怎么防治？"}]
# invoke
t0 = time.perf_counter()
resp = llm.invoke(msgs)
print("[invoke] time=%.2fs content_len=%d content_head=%r" % (
    time.perf_counter()-t0, len(resp.content), resp.content[:60]))
# stream
t0 = time.perf_counter()
buf = ""
n = 0
for chunk in llm.stream(msgs):
    c = getattr(chunk, "content", "") or ""
    buf += c
    n += 1
print("[stream] time=%.2fs chunks=%d content_len=%d content_head=%r" % (
    time.perf_counter()-t0, n, len(buf), buf[:60]))
print("DONE")
