#!/usr/bin/env python3
"""
bench_ttft.py — 첫 글자까지 걸리는 시간(TTFT) 실측

스트리밍을 붙였을 때 사용자가 실제로 체감하는 지연을 구간별로 잽니다.

    [질문]
       ↓  ① /prompt      검색 + 프롬프트 조립   ← rag_lab (md)
       ↓  ② Ollama 연결
       ↓  ③ prefill      근거를 읽는 시간
       ↓
    [첫 글자]  ← TTFT
       ↓  ④ decode       나머지 생성
    [완료]

⚠ ①이 TTFT 임계 경로에 있습니다.
   /prompt 가 2초 걸리면 스트리밍을 써도 TTFT 는 3초입니다.

사용:
    python bench_ttft.py --project fest-api
    python bench_ttft.py --project fest-api --repeat 5
    python bench_ttft.py --project fest-api --no-stream    # 비교용
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request

DEFAULT_QUERIES = [
    "이 프로젝트의 진입점은 어디인가요?",
    "에러 처리는 어떻게 하나요?",
    "설정 파일은 어디서 읽나요?",
]


def post(url: str, payload: dict, timeout: int = 120, stream: bool = False):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp if stream else json.loads(resp.read())


def pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def run_once(args, query: str) -> dict | None:
    # ── ① /prompt ────────────────────────────────────────────
    t0 = time.perf_counter()
    d = post(f"{args.rag_lab}/prompt",
             {"query": query, "project_id": args.project, "light": True},
             timeout=60)
    t_prompt = (time.perf_counter() - t0) * 1000

    if not d["has_evidence"]:
        print(f"  (근거 없음) top={d['top_score']} — 건너뜀")
        return None

    server_timing = d.get("timing", {})

    # ── ②③ Ollama 첫 토큰 ───────────────────────────────────
    t1 = time.perf_counter()
    payload = {
        "model": args.model,
        "messages": d["messages"],
        "stream": not args.no_stream,
        "options": {"num_ctx": 8192},
    }
    resp = post(f"{args.ollama}/api/chat", payload, timeout=180,
                stream=not args.no_stream)

    if args.no_stream:
        # 비교용: 전체 완성까지 대기
        t_total = (time.perf_counter() - t1) * 1000
        return {
            "prompt_ms": t_prompt,
            "first_token_ms": None,
            "gen_total_ms": t_total,
            "ttft_ms": t_prompt + t_total,     # 스트리밍이 없으면 완성이 곧 첫 글자
            "server": server_timing,
            "tokens": None,
        }

    first_ms = None
    n_tok = 0
    for line in resp:
        if not line.strip():
            continue
        chunk = json.loads(line)
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            n_tok += 1
            if first_ms is None:
                first_ms = (time.perf_counter() - t1) * 1000
        if chunk.get("done"):
            break
    gen_total = (time.perf_counter() - t1) * 1000

    return {
        "prompt_ms": t_prompt,
        "first_token_ms": first_ms,
        "gen_total_ms": gen_total,
        "ttft_ms": t_prompt + (first_ms or 0),
        "server": server_timing,
        "tokens": n_tok,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag-lab", default="http://127.0.0.1:8200")
    ap.add_argument("--ollama", default="http://127.0.0.1:11500")
    ap.add_argument("--project", required=True)
    ap.add_argument("--model", default="qwen2.5-coder:7b")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--queries", nargs="*")
    ap.add_argument("--no-stream", action="store_true",
                    help="스트리밍 없이 측정 (비교용)")
    args = ap.parse_args()

    queries = args.queries or DEFAULT_QUERIES
    mode = "비스트리밍" if args.no_stream else "스트리밍"

    print("=" * 68)
    print(f"  TTFT 측정 ({mode})   model={args.model}")
    print(f"  rag_lab {args.rag_lab}   ollama {args.ollama}")
    print("=" * 68)

    rows = []
    for q in queries:
        print(f"\n[{q}]")
        for i in range(args.repeat):
            try:
                r = run_once(args, q)
            except Exception as e:
                print(f"  {i+1}회차 실패: {type(e).__name__}: {e}")
                continue
            if r is None:
                break
            rows.append(r)
            sv = r["server"]
            ft = f"{r['first_token_ms']:>7.0f}" if r["first_token_ms"] else "      -"
            print(f"  {i+1}회차  /prompt {r['prompt_ms']:>7.0f}ms "
                  f"(embed {sv.get('embed_ms', 0):>6.0f} / search {sv.get('search_ms', 0):>5.0f})"
                  f"  첫토큰 {ft}ms  → TTFT {r['ttft_ms']:>7.0f}ms")

    if not rows:
        print("\n측정된 샘플이 없습니다.")
        return

    print("\n" + "=" * 68)
    print("  구간별 요약 (p50 / p95)")
    print("=" * 68)

    def line(label, vals):
        if not vals:
            return
        print(f"  {label:<26} {pct(vals, .5):>8.0f} ms   {pct(vals, .95):>8.0f} ms")

    line("① /prompt 전체", [r["prompt_ms"] for r in rows])
    line("   ├ 임베딩", [r["server"].get("embed_ms", 0) for r in rows])
    line("   └ 검색", [r["server"].get("search_ms", 0) for r in rows])
    if not args.no_stream:
        line("②③ Ollama 첫 토큰", [r["first_token_ms"] for r in rows if r["first_token_ms"]])
    line("── TTFT (체감 첫 글자)", [r["ttft_ms"] for r in rows])
    line("④ 생성 완료까지", [r["gen_total_ms"] for r in rows])

    ttft = pct([r["ttft_ms"] for r in rows], .95)
    print("\n" + "=" * 68)
    if ttft <= 3000:
        print(f"  ✅ TTFT p95 {ttft:.0f}ms — 3초 목표 통과")
    else:
        print(f"  🔴 TTFT p95 {ttft:.0f}ms — 3초 초과")
        pm = pct([r["prompt_ms"] for r in rows], .95)
        em = pct([r["server"].get("embed_ms", 0) for r in rows], .95)
        if pm > 1000:
            print(f"     /prompt 가 {pm:.0f}ms 를 차지합니다.")
            if em > pm * 0.6:
                print(f"     그중 임베딩이 {em:.0f}ms — 로컬 임베딩 전환을 검토하세요.")
    print("=" * 68)

    if rows and rows[0]["tokens"]:
        toks = [r["tokens"] for r in rows if r["tokens"]]
        gens = [r["gen_total_ms"] for r in rows if r["tokens"]]
        avg_tok = statistics.fmean(toks)
        avg_gen = statistics.fmean(gens)
        print(f"\n  평균 출력 {avg_tok:.0f} 조각 / {avg_gen/1000:.1f}초 "
              f"= {avg_tok/(avg_gen/1000):.1f} 조각/초")
        print("  ⚠ 답변이 길수록 완료까지 오래 걸립니다. 150~250 토큰 통제 권장.")


if __name__ == "__main__":
    main()
