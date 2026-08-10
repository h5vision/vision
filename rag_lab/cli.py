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
    print(f"브리핑 : {CFG.briefings_dir()}")

    # ⚠ fingerprint() 를 그대로 찍습니다.
    #    인덱스 stale 판정에 쓰는 값과 눈으로 보는 값이 같아야 합니다.
    fp = CFG.fingerprint()
    print("지문   : " + "  ".join(f"{k}={v}" for k, v in fp.items()))
    print(f"검색   : top_k={CFG.top_k}  threshold={CFG.score_threshold}  "
          f"min_chunk={CFG.min_chunk_chars}  use_mmr={CFG.use_mmr}  "
          f"reorder={CFG.reorder_context}")
    print(f"브리핑 : auto={CFG.auto_briefing}  model={CFG.briefing_model}")
    return 0


def cmd_briefing(args):
    """브리핑을 만들거나 이미 만든 것을 보여줍니다."""
    from vss_rag import briefing

    if not args.force:
        cached = briefing.load(args.project)
        if cached:
            print(f"이미 있습니다: {briefing.md_path(args.project)}")
            print(f"  생성 {cached.get('generated_at')}  commit {cached.get('commit')}")
            print("  다시 만들려면 --force")
            return 0

    st = indexer.get_state(args.project)
    root = args.root or st.get("project_root")
    if not root:
        print("!! project_root 를 알 수 없습니다. --root 로 지정하세요.")
        return 1

    print(f"브리핑 생성: {args.project}  (모델 {args.model})")
    t0 = time.time()
    r = briefing.build(root, args.project, args.model, CFG.ollama_url,
                       commit=st.get("commit"))
    if not r.get("ok"):
        # no_material / no_evidence 는 오류가 아닙니다.
        # 문서가 부실한 레포에서 지어내는 것보다 낫습니다.
        print(f"작성하지 않음: {r.get('reason')} — {r.get('message')}")
        return 0

    print(f"완료 {time.time()-t0:.1f}s")
    print(f"  {r['md_path']}")
    print(f"  근거 {len(r['reference_files'])}개 파일 / {r['evidence_tokens']} 토큰")
    return 0


def cmd_update(args):
    """증분 인덱싱 — 바뀐 파일만."""
    root = args.root or indexer.get_state(args.project).get("project_root")
    if not root:
        print("!! 레포 경로를 알 수 없습니다. 인자로 주세요.")
        return 1

    # 먼저 무엇이 바뀌었는지 확인
    plan = indexer.preview_update(root, args.project)
    if not plan.get("ok"):
        print(f"증분 불가: {plan.get('reason')}")
        print(f"  {plan.get('detail', '')}")
        if plan.get("reason") in ("params_changed", "too_many_changes"):
            print(f"\n  전체 인덱싱:  python cli.py index {root} --project {args.project} --force")
        return 1

    ch = plan["changes"]
    print(f"{plan['old_commit'][:8]} → {plan['new_commit'][:8]}")
    print(f"  수정 {len(ch['modified'])} / 추가 {len(ch['added'])} / "
          f"삭제 {len(ch['deleted'])} / 이름변경 {len(ch['renamed'])}")
    print(f"  → 재인덱싱 대상 {len(plan['to_index'])}개 (전체 {plan['total_files']})")
    for f in plan["to_index"][:10]:
        print(f"      {f}")
    if len(plan["to_index"]) > 10:
        print(f"      ... 외 {len(plan['to_index']) - 10}개")

    if args.dry_run:
        print("\n(--dry-run 이므로 실행하지 않음)")
        return 0

    print("\n실행 중...")
    t0 = time.time()
    r = indexer.start_update(root, args.project, blocking=True, force=args.force)
    st = indexer.get_state(args.project)
    print(json.dumps({k: st.get(k) for k in
                      ("state", "chunk_count", "commit", "elapsed_s", "error")},
                     ensure_ascii=False, indent=2))
    print(f"\n소요 {time.time()-t0:.1f}s")
    return 0


def cmd_projects(args):
    """인덱싱된 프로젝트 목록."""
    from vss_rag import briefing
    st_all = indexer.list_projects()
    store = Store()

    print(f"{'프로젝트':<22} {'상태':<10} {'청크':>8}  {'브리핑':<6} {'인덱싱 시각'}")
    print("-" * 78)
    known = set()
    for st in sorted(st_all, key=lambda x: x.get("indexed_at") or "", reverse=True):
        pid = st.get("project_id")
        if not pid:
            continue
        known.add(pid)
        b = "있음" if briefing.load(pid) else "-"
        print(f"{pid:<22} {st.get('state','?'):<10} "
              f"{store.count(pid):>8}  {b:<6} {st.get('indexed_at') or '-'}")
        if st.get("project_root"):
            print(f"  └ {st['project_root']}")

    for pid in store.projects():
        if pid not in known:
            print(f"{pid:<22} {'orphan':<10} {store.count(pid):>8}  "
                  f"{'-':<6} (상태 기록 없음)")
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

    # ⚠ 브리핑은 LLM 을 씁니다. indexer 는 그 사실을 모르고,
    #    여기서 콜백으로 주입합니다. 실패해도 인덱싱은 done 으로 남습니다.
    hook = None
    if CFG.auto_briefing and not args.no_briefing:
        from vss_rag import briefing as _brf

        def hook(pid, root, commit):
            print("  브리핑 생성 중...")
            _brf.build(root, pid, args.model, CFG.ollama_url, commit=commit)

    t0 = time.time()
    r = indexer.start_index(args.root, args.project, blocking=True,
                            force=args.force, on_done=hook)
    if not r.get("accepted"):
        print(f"!! 거부됨: {r}")
        return 1

    st = indexer.get_state(args.project)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    print(f"\n소요 {time.time()-t0:.1f}s / 파일 {st.get('total')} / 청크 {st.get('chunk_count')}")
    if st.get("briefing") == "ready":
        from vss_rag import briefing as _brf
        print(f"브리핑 : {_brf.md_path(args.project)}")
    elif st.get("briefing") == "failed":
        print(f"브리핑 : 실패 — {st.get('briefing_error')}")
        print("        인덱싱은 정상입니다. python cli.py briefing 으로 재시도하세요.")
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

    sub.add_parser("projects").set_defaults(fn=cmd_projects)

    p = sub.add_parser("update"); p.set_defaults(fn=cmd_update)
    p.add_argument("root", nargs="?", default=None,
                   help="생략하면 이전 인덱싱 경로를 사용")
    p.add_argument("--project", required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="무엇이 바뀌었는지만 보고 실행하지 않음")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("briefing"); p.set_defaults(fn=cmd_briefing)
    p.add_argument("project")
    p.add_argument("--root", default=None, help="생략하면 인덱싱 기록에서 찾습니다")
    p.add_argument("--model", default=CFG.briefing_model)
    p.add_argument("--force", action="store_true", help="캐시를 무시하고 다시 생성")

    p = sub.add_parser("index"); p.set_defaults(fn=cmd_index)
    p.add_argument("root"); p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--model", default=CFG.briefing_model,
                   help="인덱싱 후 자동 생성할 브리핑의 모델")
    p.add_argument("--no-briefing", action="store_true",
                   help="브리핑 자동 생성을 건너뜁니다 (평가 실험용)")

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
