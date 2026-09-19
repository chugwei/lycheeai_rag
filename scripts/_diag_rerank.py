"""reranker GPU/CPU/fp16 对比基准（本地，无需网络）。"""
import os, time, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import torch
print("cuda.is_available():", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

from FlagEmbedding import FlagReranker

pairs = [("荔枝霜疫霉病怎么防治？",
          "霜疫霉病主要危害果实和苗木，高温高湿条件下传播迅速，"
          "防治以农业措施为主，结合喷施代森锰锌、甲霜灵等药剂，"
          "及时清除病果病枝减少侵染源。") for _ in range(20)]

def bench(label, **kw):
    t0 = time.perf_counter()
    rr = FlagReranker("BAAI/bge-reranker-base", **kw)
    load = time.perf_counter() - t0
    try:
        dev = next(rr.model.parameters()).device
    except Exception:
        dev = "?"
    t1 = time.perf_counter()
    sc = rr.compute_score(pairs, normalize=True)
    inf = time.perf_counter() - t1
    print(f"[{label}] load={load:.2f}s device={dev} infer={inf:.3f}s scores[0]={float(list(sc)[0]):.3f}")

# 1) 默认（与 standalone 之前一致：use_fp16=True，未指定 device）
bench("fp16=True,device=auto", use_fp16=True)
# 2) 服务端当前配置：use_fp16=False（CPU fp32）
bench("fp16=False,device=auto", use_fp16=False)
# 3) 强制 GPU
if torch.cuda.is_available():
    bench("fp16=True,device=cuda:0", use_fp16=True, devices=["cuda:0"])
    bench("fp16=False,device=cuda:0", use_fp16=False, devices=["cuda:0"])
print("DONE")
