#!/usr/bin/env python3
"""
rag_lab CLI — VSsVscodeEX 검색 실험대

사용 예 (Windows PowerShell)

  # 0) 연결 확인
  python cli.py health

  # 1) 인덱싱
  python cli.py index C:\\Pj\\fest-api --project fest-api

  # 2) 상태 확인
  python cli.py status --project fest-api

  # 3) 검색
  python cli.py search "결제 처리는 어디서 시작되나요?" --project fest-api

  # 4) 프롬프트까지 조립해서 LLM 호출
  python cli.py ask "이 프로젝트 구조를 설명해줘" --project fest-api

  # 5) 파라미터 스윕 (청킹·top-k 비교)
  python cli.py sweep C:\\Pj\\fest-api --project fest-api
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from vss_rag.config import CFG
from vss_rag import embedder, indexer, searcher
from vss_rag.store import Store


def cmd_health(args):
    print(f"Ollama : {CFG.ollama_url}")
    try:
        models = embedder.health()
    except embedder.EmbeddingError as e:
        print(f"!! {e}")
        return 1
    print(f"모델   : {models}")

    if not any(m.startswith(CFG.embed_model.split(':')[0]) for m in models):
        print(f"!! 임베딩 모델 '{CFG.embed_model}' 없음.  ollama pull bge-m3")
        return 1

    t0 = time.time()
    v = embedder.embed_one("연결 확인")
    print(f"임베딩 : dim={len(v)}  ({time.time()-t0:.2f}s)  OK")

    st = Store()
    print(f"인덱스 : {CFG.index_dir}  projects={st.projects()}")
    return 0


def cmd_reset(args):
    print(json.dumps(indexer.clear_state(args.project), ensure_ascii=False))
    print("인덱스 데이터는 재인덱싱 시 자동으로 정리됩니다.")
    return 0


def cmd_index(args):
    check = indexer.is_stale(args.root, args.project)
    print(f"현재 상태: {check}")
    if not check["stale"] and not args.force:
        print("이미 최신입니다. 다시 하려면 --force")
        return 0

    print(f"인덱싱 시작: {args.root}  →  project_id={args.project}")
    t0 = time.time()
    r = indexer.start_index(args.root, args.project, blocking=True, force=args.force)
    if not r.get("accepted"):
        print(f"!! 거부됨: {r}")
        return 1

    st = indexer.get_state(args.project)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    print(f"\n소요 {time.time()-t0:.1f}s / 파일 {st.get('total')} / 청크 {st.get('chunk_count')}")
    return 0


def cmd_status(args):
    print(json.dumps(indexer.get_state(args.project), ensure_ascii=False, indent=2))
    print(json.dumps(indexer.has_index(args.project), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args):
    r = searcher.search(args.query, args.project, top_k=args.top_k,
                        threshold=args.threshold)
    print(f"근거 있음: {r['has_evidence']}  "
          f"(top={r['top_score']:.4f}, 임계값={r['threshold']})  "
          f"reason={r['reason']}\n")

    for i, c in enumerate(r.get("all_hits", []), start=1):
        mark = "✓" if c["score"] >= r["threshold"] else "✗"
        loc = (f"#{c['section']}" if c.get("section")
               else f"L{c.get('line_start')}-{c.get('line_end')}")
        print(f"{mark} [{i}] {c['score']:.4f}  {c['path']} {loc}")
        body = c["text"].replace("\n", " ")[:110]
        print(f"       {body}\n")
    return 0


def cmd_ask(args):
    import urllib.request

    r = searcher.search(args.query, args.project)
    if not r["has_evidence"]:
        print(f"NO_EVIDENCE  (top={r['top_score']}, 임계값={r['threshold']})")
        return 0

    msgs = searcher.render_prompt(args.query, r["contexts"])
    if args.show_prompt:
        print("=" * 60)
        print(msgs[1]["content"][:2000])
        print("=" * 60)

    body = json.dumps({
        "model": args.model, "stream": False, "messages": msgs,
        "options": {"num_ctx": 8192},
    }).encode()
    req = urllib.request.Request(
        f"{CFG.ollama_url}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())

    answer = data["message"]["content"]
    final = searcher.finalize(answer, r["contexts"],
                              cited_only=not args.all_refs, include_text=False)

    print(final["answer"])
    print(f"\n--- {time.time()-t0:.1f}s / 검색 {len(r['contexts'])}건 / "
          f"인용 {final['cited']} ---")

    if final["no_evidence"]:
        print("  (근거 없음)")
        return 0

    for f in final["reference_files"]:
        spans = ", ".join(f"{a}-{b}" for a, b in f["lines"]) or "-"
        print(f"  {f['path']}  [{','.join(map(str, f['citations']))}]  "
              f"L{spans}  score={f['best_score']:.4f}")

    if args.json:
        print("\n" + json.dumps(final, ensure_ascii=False, indent=2))
    return 0


def cmd_sweep(args):
    """청킹 파라미터를 바꿔가며 인덱싱하고 평가셋으로 비교."""
    combos = [(600, 80), (1200, 150), (1600, 200), (2400, 300)]
    queries = args.queries or [
        "이 프로젝트의 진입점은 어디인가요?",
        "에러 처리는 어떻게 하나요?",
        "설정은 어디서 읽나요?",
    ]

    print(f"{'chunk':>6} {'ovlp':>5} {'chunks':>7} {'idx_s':>7}  질문별 top score")
    print("-" * 72)

    for size, ovl in combos:
        CFG.chunk_size, CFG.chunk_overlap = size, ovl
        pid = f"{args.project}-c{size}"
        t0 = time.time()
        indexer.start_index(args.root, pid, blocking=True)
        st = indexer.get_state(pid)
        scores = []
        for q in queries:
            r = searcher.search(q, pid)
            scores.append(r["top_score"] or 0.0)
        print(f"{size:>6} {ovl:>5} {st.get('chunk_count', 0):>7} "
              f"{time.time()-t0:>6.1f}s  "
              + "  ".join(f"{s:.4f}" for s in scores))

    print("\n⚠ top score 만으로는 품질 판정이 불충분합니다.")
    print("   정답 근거가 있는 평가셋으로 Hit@k 를 재야 합니다.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="VSsVscodeEX RAG 실험대")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(fn=cmd_health)

    p = sub.add_parser("reset"); p.set_defaults(fn=cmd_reset)
    p.add_argument("--project", required=True)

    p = sub.add_parser("index"); p.set_defaults(fn=cmd_index)
    p.add_argument("root"); p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p.add_argument("--project", required=True)

    p = sub.add_parser("search"); p.set_defaults(fn=cmd_search)
    p.add_argument("query"); p.add_argument("--project", required=True)
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--threshold", type=float, default=None)

    p = sub.add_parser("ask"); p.set_defaults(fn=cmd_ask)
    p.add_argument("query"); p.add_argument("--project", required=True)
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--show-prompt", action="store_true")
    p.add_argument("--all-refs", action="store_true",
                   help="인용되지 않은 근거도 표시")
    p.add_argument("--json", action="store_true",
                   help="프론트에 보낼 JSON 전체 출력")

    p = sub.add_parser("sweep"); p.set_defaults(fn=cmd_sweep)
    p.add_argument("root"); p.add_argument("--project", required=True)
    p.add_argument("--queries", nargs="*")

    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
