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
from vss_rag import diagnose, embedder, indexer, profiles, searcher
from vss_rag.store import Store


def cmd_health(args):
    print(f"Ollama : {CFG.ollama_url}")
    st = Store()
    rows = diagnose.drift_summary(st)
    try:
        models = embedder.health()
    except embedder.EmbeddingError as e:
        print(f"!! {e}")
        return 1
    print(f"모델   : {models}")

    required = {CFG.embed_model} | {
        r["fingerprint"]["embed_model"] for r in rows if r["fingerprint"]}
    missing = sorted(m for m in required if m not in models)
    if missing:
        print(f"!! 필요한 임베딩 모델 없음: {', '.join(missing)}")
        return 1

    for model in sorted(required):
        expected_dim = next(
            (int(r["fingerprint"]["embed_dim"]) for r in rows
             if r["fingerprint"] and r["fingerprint"]["embed_model"] == model),
            CFG.embed_dim,
        )
        t0 = time.time()
        v = embedder.embed_one("연결 확인", model=model, expected_dim=expected_dim)
        print(f"임베딩 : model={model}  dim={len(v)}  ({time.time()-t0:.2f}s)  OK")

    print(f"인덱스 : {CFG.index_dir}")
    print(f"브리핑 : {CFG.briefings_dir()}")
    print()

    # ── 지문 두 줄로 분리 ────────────────────────────────────
    # ⚠ 예전에는 CFG.fingerprint() 하나만 "지문"이라는 이름으로 찍었습니다.
    #    그건 **이 프로세스의 환경변수**이지 인덱스가 만들어진 값이 아닙니다.
    #    둘이 어긋나면 화면도 같이 틀리므로, 대조가 불가능했습니다.
    fp = CFG.fingerprint()
    print("CFG    : (새 전체 인덱싱의 기본값 — 기존 프로젝트 질의·증분에는 덮어쓰지 않음)")
    print("         " + "  ".join(f"{k}={v}" for k, v in fp.items()))
    print()

    print("인덱스 : (각 프로젝트의 실제 서빙·증분 프로필)")
    if not rows:
        print("         (없음)")
    for r in rows:
        head = f"         {r['name']:<16s}{r['chunks']:>9,}청크  "
        if r["fingerprint"] is None:
            print(head + "지문 없음 (구 방식 인덱스)   🟡 대조 불가")
            continue
        f = r["fingerprint"]
        body = (f"ctx={str(f.get('context_header')):<5s} "
                f"bm25={str(f.get('use_bm25')):<5s} "
                f"chunk={f.get('chunk_size')}/{f.get('chunk_overlap')}")
        if r["drift"]:
            print(head + body + f"  ℹ 새 전체 인덱싱 기본값과 다름: {', '.join(r['drift'])}")
        else:
            print(head + body + "  ✅")
    print()

    print(f"검색   : top_k={CFG.top_k}  threshold={CFG.score_threshold}  "
          f"min_chunk={CFG.min_chunk_chars}  use_mmr={CFG.use_mmr}  "
          f"reorder={CFG.reorder_context}")
    print(f"브리핑 : auto={CFG.auto_briefing}  model={CFG.briefing_model}")

    # ── 저장 프로필과 새 전체 인덱싱 기본값의 차이 ───────────
    drifted = [r for r in rows if r["drift"]]
    if drifted:
        print()
        print(f"ℹ 새 전체 인덱싱 기본값과 다른 프로젝트:  "
              f"{', '.join(r['name'] for r in drifted)}")
        print("   현재 질의와 증분 갱신은 각 프로젝트의 저장 프로필을 사용하므로 정상입니다.")
        print("   환경변수(CFG)는 새 전체 인덱싱을 시작할 때만 적용됩니다.")
    return 0


def _journal_path():
    from pathlib import Path
    return Path(CFG.index_dir).resolve().parent / "journal.jsonl"


def _snapshot(st) -> dict:
    """지금 상태를 기계가 읽을 수 있는 형태로. **사람 손을 타지 않는 부분입니다.**"""
    snap = {"cfg": CFG.fingerprint(), "indexes": {}}
    for r in diagnose.drift_summary(st):
        snap["indexes"][r["name"]] = {
            "chunks": r["chunks"],
            "fingerprint": r["fingerprint"],
        }
    # 마지막 평가 run
    from pathlib import Path
    p = Path("eval_runs.jsonl")
    if p.exists():
        lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            last = json.loads(lines[-1])
            snap["last_eval"] = {"run_id": last.get("run_id"),
                                 "project_id": last.get("project_id"),
                                 "note": last.get("note")}
    return snap


def cmd_journal(args):
    """작업 기록. **상태는 자동으로 찍고, 사람은 한 줄만 씁니다.**

    ⚠ 이 도구의 목적은 "무엇이 바뀌었는가"를 사람이 손으로 안 적게 하는 것입니다.
       상태 스냅샷은 기계가 뜨고, `--render` 가 **직전과 달라진 것만** 보여줍니다.
       그래서 세션 정리가 명령 하나가 됩니다.

    ⚠ 판단·이유는 여기 적지 마세요. 그건 DECISIONS 와 STATE 의 몫입니다.
       여기는 "언제 무엇을 했고 그때 상태가 어땠는가" 만 담습니다.
    """
    from datetime import datetime, timezone
    from pathlib import Path

    p = _journal_path()

    if args.render:
        return _render_journal(p, args.since)

    if not args.note:
        print("!! 기록할 한 줄을 주세요:  python cli.py journal \"무엇을 했는지\"")
        print("   또는 지금까지 기록 보기:  python cli.py journal --render")
        return 1

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": args.note,
        "snapshot": _snapshot(Store()),
    }
    if args.cmd:
        rec["cmd"] = args.cmd

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"기록: {p}")
    print(f"  {rec['ts']}  {args.note}")
    return 0


def _fmt_fp(fp) -> str:
    if not fp:
        return "지문없음"
    return (f"ctx={fp.get('context_header')} bm25={fp.get('use_bm25')} "
            f"chunk={fp.get('chunk_size')}/{fp.get('chunk_overlap')}"
            + (f" excl={len([x for x in (fp.get('exclude_globs') or '').split(',') if x.strip()])}패턴"
               if fp.get("exclude_globs") else ""))


def _render_journal(p, since: str | None) -> int:
    """직전 항목과 **달라진 것만** 출력합니다. 그게 이 도구의 전부입니다."""
    if not p.exists():
        print(f"!! 기록이 없습니다: {p}")
        return 1

    recs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    if since:
        recs = [r for r in recs if r["ts"] >= since]
    if not recs:
        print("해당 기간 기록이 없습니다.")
        return 1

    print(f"# 작업 기록 — {recs[0]['ts'][:10]} ~ {recs[-1]['ts'][:10]}  ({len(recs)}건)\n")

    prev = None
    day = None
    for r in recs:
        d = r["ts"][:10]
        if d != day:
            print(f"\n## {d}\n")
            day = d
        print(f"- **{r['ts'][11:16]}**  {r['note']}")
        if r.get("cmd"):
            print(f"  - `{r['cmd']}`")

        snap = r["snapshot"]
        if prev is None:
            for name, v in snap["indexes"].items():
                print(f"  - {name}: {v['chunks']:,}청크  {_fmt_fp(v['fingerprint'])}")
        else:
            # ── 달라진 것만 ──────────────────────────────────
            po, no = prev["indexes"], snap["indexes"]
            for name in sorted(set(po) | set(no)):
                a, b = po.get(name), no.get(name)
                if a is None:
                    print(f"  - 🆕 {name}: {b['chunks']:,}청크  {_fmt_fp(b['fingerprint'])}")
                elif b is None:
                    print(f"  - 🗑 {name} 사라짐")
                elif a != b:
                    if a["chunks"] != b["chunks"]:
                        diff = b["chunks"] - a["chunks"]
                        print(f"  - 📊 {name}: {a['chunks']:,} → {b['chunks']:,}청크 ({diff:+,})")
                    if a["fingerprint"] != b["fingerprint"]:
                        print(f"  - ⚙ {name}: {_fmt_fp(a['fingerprint'])}")
                        print(f"       → {_fmt_fp(b['fingerprint'])}")
            if prev.get("cfg") != snap.get("cfg"):
                changed = {k: (prev["cfg"].get(k), v)
                           for k, v in snap["cfg"].items() if prev["cfg"].get(k) != v}
                for k, (o, n) in changed.items():
                    print(f"  - 🔧 CFG {k}: {o} → {n}")
            pe = (prev.get("last_eval") or {}).get("run_id")
            ne = (snap.get("last_eval") or {}).get("run_id")
            if ne and ne != pe:
                le = snap["last_eval"]
                print(f"  - 📈 평가 run `{le['run_id']}` ({le.get('project_id')}) "
                      f"{le.get('note') or ''}")
        prev = snap

    print("\n---")
    print("*수치는 MEASUREMENTS, 판단은 DECISIONS, 현황은 STATE 를 보세요.*")
    print("*이 기록은 \"언제 무엇을 했는가\" 만 담습니다.*")
    return 0


def cmd_doctor(args):
    """상태 정합성 전수 점검. **읽기만 합니다.**

    ⚠ 고치지 않습니다. 무엇을 고칠지는 사람이 정합니다.
    """
    st = Store()
    print(f"인덱스   {CFG.index_dir}")
    print(f"상태파일 {CFG.state_path}")
    if not args.deep:
        print("⚠ 빠른 점검입니다. 역색인 내용까지 대조하려면  --deep")
    print()

    rep = diagnose.scan(st, deep=args.deep)

    # ── 인덱스 한 줄 요약 ───────────────────────────────────
    print(f"{'인덱스':<18s}{'청크':>9s} {'state':>9s}  {'BM25':>9s}  지문")
    print("-" * 78)
    for p in rep["projects"]:
        s = p["state"] or {}
        sc = s.get("chunk_count")
        f = p["fingerprint"]
        fpv = "없음" if not f else (f"ctx={f.get('context_header')} "
                                  f"bm25={f.get('use_bm25')}")
        bm = p["bm25_docs"]
        bms = (f"{bm:,}" if isinstance(bm, int)
               else ("없음" if bm is None else "있음"))
        mark = "ℹ" if p["drift"] else ("🟡" if f is None else "✅")
        print(f"{p['name']:<18s}{p['chunks']:>9,} "
              f"{(f'{sc:,}' if isinstance(sc, int) else '—'):>9s}  "
              f"{bms:>9s}  {mark} {fpv}")
    for c in rep["internal"]:
        print(f"{c['name']:<18s}{c['chunks']:>9,} {'—':>9s}  {'—':>9s}  🟡 미완성")
    print("-" * 78)
    print()

    # ── 문제 목록 ───────────────────────────────────────────
    if not rep["issues"]:
        print("✅ 어긋난 곳이 없습니다.")
        return 0

    print(f"발견 {len(rep['issues'])}건 — 🔴 {rep['red']}  🟡 {rep['yellow']}")
    print()
    print("🔴 = 조회 결과가 달라집니다 / 🟡 = 기록만 어긋납니다 (동작 무영향)")
    print()
    for sev in (diagnose.RED, diagnose.YELLOW):
        for it in rep["issues"]:
            if it["sev"] != sev:
                continue
            print(f"{sev} [{it['where']}] {it['msg']}")
            if it["fix"]:
                print(f"     → {it['fix']}")

    print()
    print("⚠ 이 명령은 아무것도 고치지 않았습니다. 수리는 명시적으로 하세요.")
    # 🔴 가 있으면 종료 코드 1 — CI·스크립트에서 걸 수 있게
    return 1 if rep["red"] else 0


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


def cmd_profiles(args):
    rows = profiles.list_profiles()
    print(f"{'profile':<12} {'hash':<12} {'BM25':<6} {'ctx':<5} 설명")
    print("-" * 78)
    for p in rows:
        fp = p["fingerprint"]
        print(f"{p['profile_id']:<12} {p['profile_hash']:<12} "
              f"{str(fp['use_bm25']):<6} {str(fp['context_header']):<5} "
              f"{p['description']}")
    return 0


def cmd_index(args):
    selected = None
    if args.profile:
        try:
            selected = profiles.resolve_profile(args.profile)
        except profiles.ProfileError as e:
            print(f"!! {e}")
            return 1
    fp = selected["fingerprint"] if selected else None
    resume_mode = bool(args.resumable or args.resume or args.restart or
                       CFG.resume_index_enabled)
    if not args.resume and not args.root:
        print("!! 신규·재시작 인덱싱에는 레포 경로가 필요합니다.")
        return 1
    if not args.resume:
        check = indexer.is_stale(args.root, args.project, profile=fp)
        print(f"현재 상태: {check}")
        if not check["stale"] and not args.force and not args.restart:
            print("이미 최신입니다. 다시 하려면 --force 또는 --restart")
            return 0

    if selected:
        print(f"프로필: {selected['profile_id']}  hash={selected['profile_hash']}")
        print("해석값: " + "  ".join(f"{k}={v}" for k, v in fp.items()))
        recommended = (profiles.project_id_for(args.root, selected["profile_id"])
                       if args.root else None)
        if recommended and args.project != recommended:
            print(f"ℹ 동일 레포 버전 비교 권장 project_id: {recommended}")
    print(f"인덱싱 시작: {args.root or '(체크포인트 경로)'}  →  project_id={args.project}")

    # ⚠ 브리핑은 LLM 을 씁니다. indexer 는 그 사실을 모르고,
    #    여기서 콜백으로 주입합니다. 실패해도 인덱싱은 done 으로 남습니다.
    if args.no_briefing:
        print("ℹ --no-briefing은 더 이상 브리핑 생성을 건너뛰지 않습니다. "
              "반복 평가는 experiment.py를 사용하세요.")
    from vss_rag import briefing as _brf

    def hook(pid, root, commit):
        print("  브리핑 생성 중...")
        return _brf.build(root, pid, args.model, CFG.ollama_url, commit=commit)

    t0 = time.time()
    if resume_mode:
        from vss_rag.resume import ResumableIndexer
        engine = ResumableIndexer()
        if args.resume:
            r = engine.resume(
                args.project, blocking=True, force=args.force, on_done=hook,
                expected_profile=fp,
            )
        elif args.restart:
            r = engine.restart(
                args.root, args.project, blocking=True, force=args.force,
                on_done=hook, profile=fp,
                profile_id=(selected or {}).get("profile_id"),
                profile_hash=(selected or {}).get("profile_hash"),
            )
        else:
            r = engine.start_new(
                args.root, args.project, blocking=True, force=args.force,
                on_done=hook, profile=fp,
                profile_id=(selected or {}).get("profile_id"),
                profile_hash=(selected or {}).get("profile_hash"),
            )
    else:
        r = indexer.start_index(args.root, args.project, blocking=True,
                                force=args.force, on_done=hook,
                                profile=fp,
                                profile_id=(selected or {}).get("profile_id"),
                                profile_hash=(selected or {}).get("profile_hash"))
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


def cmd_resume_status(args):
    from vss_rag.resume import resume_status
    print(json.dumps(resume_status(args.project), ensure_ascii=False, indent=2))
    return 0


def cmd_status(args):
    print(json.dumps(indexer.get_state(args.project), ensure_ascii=False, indent=2))
    print(json.dumps(indexer.has_index(args.project), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args):
    try:
        r = searcher.search(args.query, args.project, top_k=args.top_k,
                            threshold=args.threshold)
    except searcher.ProjectNotFoundError as e:
        print(f"!! {e}")
        return 1
    hits = r.get("all_hits", [])
    fused = bool(r.get("bm25_active"))
    profile = r.get("serving_profile") or {}

    top_s = f"{r['top_score']:.4f}" if r["top_score"] is not None else "없음"
    print(f"근거 있음: {r['has_evidence']}  "
          f"(최고 벡터점수={top_s}, 임계값={r['threshold']})  "
          f"reason={r['reason']}")
    print(f"서빙 프로필: model={profile.get('embed_model')}  "
          f"bm25={profile.get('use_bm25')}  ctx={profile.get('context_header')}  "
          f"(project={args.project})")
    if fused:
        # ⚠ 융합이 켜져 있으면 **표시 순서 = RRF 순위**입니다. 점수 내림차순이 아닙니다.
        #    이걸 안 적어두면 "3번이 1번보다 점수가 높은데?" 로 읽힙니다.
        print(f"   ⚠ BM25 융합 ON — 아래 순서는 **RRF 순위**입니다 (점수순 아님). "
              f"융합 1위의 벡터점수={r.get('ranked1_score', 0):.4f}")
        print("   ⚠ 점수 0.0000 = 벡터 상위에 없고 BM25 로만 올라온 청크. "
              "설계상 임계값을 넘지 못합니다")
    print()

    passed = sum(1 for h in hits if h["score"] >= r["threshold"])
    for i, c in enumerate(hits, start=1):
        mark = "✓" if c["score"] >= r["threshold"] else "✗"
        loc = (f"#{c['section']}" if c.get("section")
               else f"L{c.get('line_start')}-{c.get('line_end')}")
        print(f"{mark} [{i}] {c['score']:.4f}  {c['path']} {loc}")
        body = c["text"].replace("\n", " ")[:110]
        print(f"       {body}\n")

    used_k = args.top_k if args.top_k is not None else CFG.top_k
    print(f"임계값 통과 {passed}/{len(hits)} — 이 중 앞의 top_k={used_k}개만 "
          f"프롬프트에 들어갑니다")
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
    # Windows 기본 CP949 콘솔에서도 진단 기호와 한글을 손실 없이 출력합니다.
    # errors="replace"만 쓰면 중단은 막아도 ✅/ℹ/—가 전부 '?'로 보여 진단 의미가 사라집니다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="VSsVscodeEX RAG 실험대")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(fn=cmd_health)

    p = sub.add_parser("doctor"); p.set_defaults(fn=cmd_doctor)
    p.add_argument("--deep", action="store_true",
                   help="역색인을 열어 문서 수까지 대조 (2만 청크에 수 초)")

    p = sub.add_parser("journal"); p.set_defaults(fn=cmd_journal)
    p.add_argument("note", nargs="?", default=None, help="무엇을 했는지 한 줄")
    p.add_argument("--cmd", default=None, help="실행한 명령 (선택)")
    p.add_argument("--render", action="store_true", help="마크다운으로 출력")
    p.add_argument("--since", default=None, help="이 날짜 이후만 (예: 2026-08-13)")

    p = sub.add_parser("reset"); p.set_defaults(fn=cmd_reset)
    p.add_argument("--project", required=True)

    sub.add_parser("projects").set_defaults(fn=cmd_projects)
    sub.add_parser("profiles").set_defaults(fn=cmd_profiles)

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
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--project", required=True)
    p.add_argument("--profile",
                   help="명시적 인덱싱 프로필(rag-v1/v2/v3). 생략하면 현재 CFG 사용")
    p.add_argument("--force", action="store_true")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--resumable", action="store_true",
                      help="새 파일 체크포인트 실행으로 시작")
    mode.add_argument("--resume", action="store_true",
                      help="중단된 체크포인트 실행 재개(root 생략 가능)")
    mode.add_argument("--restart", action="store_true",
                      help="소유권이 확인된 체크포인트를 폐기하고 새로 시작")
    p.add_argument("--model", default=CFG.briefing_model,
                   help="인덱싱 후 자동 생성할 브리핑의 모델")
    p.add_argument("--no-briefing", action="store_true",
                   help="폐기된 호환 옵션(무시됨). 반복 평가는 experiment.py 사용")

    p = sub.add_parser("resume-status"); p.set_defaults(fn=cmd_resume_status)
    p.add_argument("--project", required=True)

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
