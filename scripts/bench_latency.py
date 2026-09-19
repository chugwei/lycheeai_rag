"""
LycheeAI RAG 问答端到端延迟基准脚本

两种运行模式：
  --mode http    以前端视角，通过 HTTP POST /api/query 计时（含网络 + 序列化开销），
                 并读取响应里的 latency（服务端纯计算）与 stage_timings（各阶段拆解）。
  --mode direct  直接调用管线 run()（跳过 HTTP），作为对照，排除网络因素。

可选：
  --stream       仅对 http 模式生效。改为 POST /api/query/stream（SSE），
                 记录首 token 延迟（TTFB）与端到端总耗时（done 事件），
                 更贴近真实前端"边出边看"的体验。

用法示例：
  python scripts/bench_latency.py --mode http   --url http://localhost:18888 --repeat 3
  python scripts/bench_latency.py --mode http   --url http://localhost:18888 --repeat 3 --stream
  python scripts/bench_latency.py --mode direct --repeat 3
  python scripts/bench_latency.py --mode http --query "荔枝霜疫霉病怎么防治？" --repeat 5

输出：
  - 每条问题的端到端耗时（前端 wall 与服务端 latency）
  - 各阶段平均耗时与占服务端总耗时的百分比
  - 延迟主因（耗时最大的阶段）
"""
import argparse
import json
import statistics
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_QUERIES = [
    "荔枝霜疫霉病怎么防治？",
    "桂味和糯米糍哪个更好吃？",
    "现在这个季节荔枝该怎么施肥？",
    "荔枝蒂蛀虫的危害和防治方法是什么？",
    "幼果期遇到连续阴雨要注意什么？",
]


def _stage_order():
    """稳定的阶段展示顺序（按管线执行顺序）"""
    return [
        "query_parse", "image_analysis", "query_prep",
        "retrieval", "retrieval_vector", "retrieval_bm25",
        "rrf_fusion", "rerank", "prompt_build",
        "llm_generate", "post_process", "confidence",
    ]


def http_run(base_url, query, repeat, timeout=180, stream=False):
    """HTTP 模式：返回 [(wall, server_latency, stage_timings, ttfb), ...]"""
    path = "/api/query/stream" if stream else "/api/query"
    url = base_url.rstrip("/") + path
    rows = []
    for _ in range(repeat):
        payload = json.dumps({
            "query": query,
            "use_query_expansion": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        t0 = time.perf_counter()
        ttfb = 0.0
        server_latency = 0.0
        stage_timings = {}
        try:
            if not stream:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
                wall = time.perf_counter() - t0
                data = json.loads(body)
                server_latency = data.get("latency", 0.0)
                stage_timings = data.get("stage_timings", {}) or {}
                ttfb = wall
            else:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if not payload:
                            continue
                        evt = json.loads(payload)
                        etype = evt.get("type")
                        if etype == "chunk" and ttfb == 0.0:
                            ttfb = time.perf_counter() - t0
                        elif etype == "done":
                            d = evt.get("data", {})
                            server_latency = d.get("latency", 0.0)
                            stage_timings = d.get("stage_timings", {}) or {}
                wall = time.perf_counter() - t0
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
        rows.append((wall, server_latency, stage_timings, ttfb))
    return rows


def direct_run(query, repeat):
    """直接调用管线（含一次预热以排除模型加载时间）。"""
    from rag_chain import get_pipeline
    pipe = get_pipeline()
    # 预热
    pipe.run(query=DEFAULT_QUERIES[0])
    rows = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        res = pipe.run(query=query)
        wall = time.perf_counter() - t0
        rows.append((wall, res.latency, res.stage_timings or {}, wall))
    return rows


def aggregate(all_rows):
    """all_rows: 所有 (wall, server_latency, stage_timings, ttfb) 的扁平列表"""
    walls = [r[0] for r in all_rows]
    servers = [r[1] for r in all_rows]
    ttfbs = [r[3] for r in all_rows]
    # 汇总各阶段
    stage_acc = {}
    for _, _, st, _ in all_rows:
        for k, v in st.items():
            stage_acc.setdefault(k, []).append(v)
    stage_avg = {k: statistics.mean(v) for k, v in stage_acc.items()}
    return walls, servers, ttfbs, stage_avg


def print_report(mode, base_url, queries, repeat, stream=False):
    all_rows = []
    per_query = []
    for q in queries:
        try:
            if mode == "http":
                rows = http_run(base_url, q, repeat, stream=stream)
            else:
                rows = direct_run(q, repeat)
        except Exception as e:
            print(f"  [!] 问题失败: {q[:30]}... 错误: {e}")
            continue
        all_rows.extend(rows)
        w_avg = statistics.mean(r[0] for r in rows)
        s_avg = statistics.mean(r[1] for r in rows)
        ttfb_avg = statistics.mean(r[3] for r in rows)
        per_query.append((q, w_avg, s_avg, ttfb_avg))
        if stream:
            print(f"  • {q[:30]:<30} 前端={w_avg:6.2f}s  TTFB={ttfb_avg:6.2f}s  服务端={s_avg:6.2f}s")
        else:
            print(f"  • {q[:34]:<34} 前端={w_avg:6.2f}s  服务端={s_avg:6.2f}s")

    if not all_rows:
        print("没有成功的样本，无法汇总。")
        return

    walls, servers, ttfbs, stage_avg = aggregate(all_rows)

    print("\n" + "=" * 64)
    tag = f"{mode} + stream" if (mode == "http" and stream) else mode
    print(f"端到端汇总（{tag} 模式，每问 {repeat} 次，共 {len(all_rows)} 次采样）")
    print("=" * 64)
    print(f"  前端视角 wall-clock : 平均 {statistics.mean(walls):.2f}s  "
          f"(min {min(walls):.2f}s / max {max(walls):.2f}s)")
    print(f"  服务端计算 latency  : 平均 {statistics.mean(servers):.2f}s  "
          f"(min {min(servers):.2f}s / max {max(servers):.2f}s)")
    if mode == "http" and stream:
        print(f"  首 token 延迟 TTFB  : 平均 {statistics.mean(ttfbs):.2f}s  "
              f"(min {min(ttfbs):.2f}s / max {max(ttfbs):.2f}s)")
    overhead = statistics.mean(walls) - statistics.mean(servers)
    print(f"  网络/序列化开销     : 平均 {overhead:+.2f}s")

    # 阶段拆解
    total_server = statistics.mean(servers)
    order = _stage_order()
    keys = [k for k in order if k in stage_avg] + \
           [k for k in stage_avg if k not in order]
    print("\n  阶段拆解（平均耗时 / 占服务端总耗时）:")
    print(f"  {'阶段':<18}{'平均(s)':>10}{'占比':>10}")
    print("  " + "-" * 38)
    ranked = sorted(keys, key=lambda k: stage_avg[k], reverse=True)
    for k in ranked:
        v = stage_avg[k]
        pct = (v / total_server * 100) if total_server > 0 else 0
        bar = "#" * int(pct / 5)
        print(f"  {k:<18}{v:>10.3f}{pct:>9.1f}% {bar}")

    # 胶水/未计入
    accounted = sum(stage_avg[k] for k in keys if k in stage_avg)
    glue = total_server - accounted
    if abs(glue) > 0.01:
        print(f"  {'[其他/胶水]':<18}{glue:>10.3f}"
              f"{(glue/total_server*100 if total_server else 0):>9.1f}%")

    bottleneck = ranked[0]
    print("\n  >>> 延迟主因: " + bottleneck +
          f"  平均 {stage_avg[bottleneck]:.2f}s "
          f"({stage_avg[bottleneck]/total_server*100:.1f}% of 服务端耗时)")

    # 输出 JSON 便于归档
    out = {
        "mode": tag,
        "repeat": repeat,
        "wall_avg": statistics.mean(walls),
        "server_avg": statistics.mean(servers),
        "ttfb_avg": statistics.mean(ttfbs) if stream else None,
        "overhead_avg": overhead,
        "stage_avg": stage_avg,
        "bottleneck": bottleneck,
        "per_query": [{"query": q, "wall": w, "server": s, "ttfb": t}
                      for q, w, s, t in per_query],
    }
    out_path = ROOT / "scripts" / "bench_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已保存: {out_path}")


def main():
    ap = argparse.ArgumentParser(description="LycheeAI RAG 延迟基准")
    ap.add_argument("--mode", choices=["http", "direct"], default="http")
    ap.add_argument("--url", default="http://localhost:18888")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--stream", action="store_true",
                    help="http 模式下改用 /api/query/stream，测量 TTFB")
    ap.add_argument("--query", action="append", default=[],
                    help="自定义问题（可多次）；不填则用内置样例集")
    args = ap.parse_args()

    queries = args.query if args.query else DEFAULT_QUERIES
    print(f"\n[bENCH] 模式={args.mode}  问题数={len(queries)}  每问重复={args.repeat}"
          + ("  [stream]" if args.stream else ""))
    if args.mode == "http":
        ep = "/api/query/stream" if args.stream else "/api/query"
        print(f"[BENCH] 目标服务: {args.url}{ep}")
    print("-" * 64)
    print("  逐问题耗时:")
    print("-" * 64)
    print_report(args.mode, args.url, queries, args.repeat, stream=args.stream)


if __name__ == "__main__":
    main()
