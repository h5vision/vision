#!/usr/bin/env python3
"""
평가 하네스 — 검색이 정답 위치를 찾아오는지 채점합니다.

⚠ 이 파일이 재는 것은 **검색 레이어**입니다.
   **임계값·MMR·재배치는 일부러 제외합니다.** 그게 의도입니다 —
   검색이 정답을 몇 위로 올리는가와, 후처리가 그걸 어떻게 자르는가는
   분리해서 봐야 합니다.

   ⚠ 단, **BM25 융합은 후처리가 아니라 검색 단계입니다.**
      순위를 바꾸므로 Hit@k 에 직접 영향합니다. 2026-08-13 이전 버전은
      이것까지 같이 빠져 있었고, 그건 경계 설정 오류였습니다.
      → `--bm25` 로 켜고 끕니다. 기본은 프로젝트의 저장 프로필을 따릅니다.

사용법
    python eval.py --project fastapi-cli --gold RAG_TEST_fastapi_cli.md
    python eval.py --project fastapi-cli --gold ... --bm25 off --note "baseline 재측정"
    python eval.py --project fastapi-cli --gold ... --bm25 on  --note "BM25 융합"

⚠ 레포별로 따로 돌리고 따로 읽으세요.
   청크 수가 다르면 Hit@k 난이도가 다릅니다. 합치면 안 됩니다.

⚠ A/B 를 할 때는 `--pool` 을 셀 전체에서 같은 값으로 고정하세요.
   후보 수가 다르면 융합 결과가 달라져 변수가 하나 늘어납니다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vss_rag import lexical, searcher   # noqa: E402
from vss_rag.config import CFG          # noqa: E402
from vss_rag.embedder import embed_one  # noqa: E402
from vss_rag.store import Store         # noqa: E402

# ── 채점 규칙 ────────────────────────────────────────────────
POOL = 10           # 검색해 올 후보 수. Hit@5 를 재려면 5보다 커야 함
                    # ⚠ 2026-08-10 baseline 이 이 값으로 측정됐습니다.
                    #    비교하려면 바꾸지 마세요 (--pool 로 덮어쓸 수는 있음)
K_LIST = (1, 3, 5)  # Hit@k 의 k
TH_LO, TH_HI, TH_STEP = 0.40, 0.70, 0.01

RUNS_FILE = "eval_runs.jsonl"

# ── gold 파싱 ────────────────────────────────────────────────
_LOC = re.compile(r"^\s*-\s+(?P<path>[\w./\\-]+\.\w+)"
                  r"(?:\s+(?P<a>\d+)\s*~\s*(?P<b>\d+)\s*줄"
                  r"|\s+(?P<c>\d+)\s*줄)?", re.M)


def parse_gold(path: Path) -> list[dict]:
    """RAG_TEST_*.md 를 읽어 질문 목록으로 만듭니다."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^## Q", text)[1:]
    out = []

    for i, b in enumerate(blocks, 1):
        m_t = re.search(r"(?m)^- 유형:\s*(\d)", b)
        m_q = re.search(r"(?m)^- 질문:\s*(.+?)\s*$", b)
        if not (m_t and m_q):
            print(f"  !! 블록 {i} 파싱 실패 — 건너뜁니다")
            continue

        qtype = int(m_t.group(1))

        # 정답 위치: "없음" 인지 먼저 본다
        m_loc = re.search(r"(?m)^- 정답 위치:(.*)$", b)
        inline = (m_loc.group(1).strip() if m_loc else "")
        no_answer = (qtype == 5) or ("없음" in inline)

        locs = []
        if not no_answer and m_loc:
            # 정답 위치 줄 다음부터 다음 '- 항목:' 전까지
            tail = b[m_loc.end():]
            stop = re.search(r"(?m)^- \S+:", tail)
            region = tail[:stop.start()] if stop else tail
            for mm in _LOC.finditer(region):
                a = mm.group("a") or mm.group("c")
                bb = mm.group("b") or mm.group("c")
                locs.append({
                    "path": mm.group("path").replace("\\", "/"),
                    "line_start": int(a) if a else None,
                    "line_end": int(bb) if bb else None,
                })

        out.append({
            "qid": f"Q{i}",
            "type": qtype,
            "question": m_q.group(1).strip(),
            "no_answer": no_answer,
            "gold": locs,
        })
    return out


# ── 적중 판정 ────────────────────────────────────────────────
def is_hit(hit: dict, gold: list[dict]) -> bool:
    """정답 파일이 같고 줄 범위가 1줄이라도 겹치면 적중.

    청크 경계와 사람이 적은 범위가 정확히 맞을 수 없으므로 겹침으로 봅니다.
    gold 에 줄 번호가 없으면 파일 일치만으로 적중입니다.
    """
    hp = (hit.get("path") or "").replace("\\", "/")
    hs, he = hit.get("line_start"), hit.get("line_end")

    for g in gold:
        if hp != g["path"]:
            continue
        if g["line_start"] is None or hs is None:
            return True                      # 줄 정보가 없으면 파일 일치로 인정
        if hs <= g["line_end"] and he >= g["line_start"]:
            return True
    return False


def rank_of_first_hit(hits: list[dict], gold: list[dict]) -> int | None:
    for i, h in enumerate(hits, 1):
        if is_hit(h, gold):
            return i
    return None


# ── BM25 융합 ────────────────────────────────────────────────
def fuse_bm25(st: Store, project_id: str, query: str,
              hits: list[dict], idx, pool: int) -> list[dict]:
    """벡터 결과에 BM25 를 RRF 로 합쳐 **순서만** 바꿉니다.

    ⚠ `searcher.py` 의 융합 블록과 같은 절차입니다.
       한쪽만 고치면 평가와 제품 동작이 갈립니다. 함께 바꾸세요.

    ⚠ 벡터 점수(`score`)는 건드리지 않습니다.
       BM25 로만 올라온 청크는 `score=0.0` 인 채로 순위에만 참여합니다.
    """
    lex = idx.search(query, pool)
    fused = lexical.rrf_fuse(hits, lex, k=60)

    by_id = {h["_id"]: h for h in hits}
    missing = [i for i, _ in lex if i not in by_id]
    if missing:
        by_id.update(st.get_by_ids(project_id, missing[:pool]))

    return sorted((by_id[i] for i in fused if i in by_id),
                  key=lambda h: -fused[h["_id"]])


def load_bm25_or_die(project_id: str, n_chunks: int):
    """BM25 인덱스를 싣습니다. 없거나 어긋나면 **조용히 넘어가지 않고 멈춥니다.**

    ⚠ 여기서 fallback 하면 '--bm25 on 으로 쟀다'는 기록만 남고
       실제로는 벡터 단독을 잰 run 이 됩니다. 그게 최악입니다.
    """
    p = lexical.index_path(project_id)
    idx = lexical.BM25.load(p)
    if idx is None:
        print(f"!! BM25 인덱스가 없습니다: {p}")
        print("   --bm25 off 로 재거나, 재인덱싱해서 역색인을 만드세요.")
        sys.exit(1)
    if len(idx.doc_ids) != n_chunks:
        print(f"!! BM25 인덱스와 컬렉션이 어긋납니다: "
              f"BM25 {len(idx.doc_ids):,} vs Chroma {n_chunks:,}")
        print("   구 역색인입니다. 재인덱싱 후 다시 돌리세요.")
        sys.exit(1)
    return idx


# ── 실행 ─────────────────────────────────────────────────────
def run(project_id: str, questions: list[dict], *,
        pool: int = POOL, use_bm25: bool = False,
        store: Store | None = None,
        index_fp: dict | None = None) -> list[dict]:
    st = store or Store()
    n = st.count(project_id)
    if n == 0:
        print(f"!! '{project_id}' 인덱스가 비어 있습니다. 먼저 인덱싱하세요.")
        sys.exit(1)

    idx = load_bm25_or_die(project_id, n) if use_bm25 else None
    profile = index_fp or st.index_fingerprint(project_id)
    if not profile:
        print(f"!! '{project_id}' 인덱스 설정 지문을 확인할 수 없습니다.")
        sys.exit(1)

    mode = "벡터 + BM25(RRF)" if use_bm25 else "벡터 단독"
    print(f"인덱스 {project_id}: {n:,} 청크   검색: {mode}   pool={pool}\n")

    rows = []
    for i, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        vec = embed_one(
            q["question"], model=str(profile["embed_model"]),
            expected_dim=int(profile["embed_dim"]))
        hits = st.query(project_id, vec, pool)

        # ⚠ 임계값 분석용 점수는 **융합 전 벡터 top-1** 입니다.
        #    searcher.py 는 pool 전체의 벡터 점수로 통과 여부를 정하므로
        #    (`passed = [h for h in hits if h["score"] >= th]`),
        #    pool 안의 최대 벡터 점수가 곧 has_evidence 를 가르는 값입니다.
        #    융합 후 1위는 BM25 로만 올라온 score=0.0 청크일 수 있어
        #    그걸 쓰면 임계값 표가 무의미해집니다.
        v_top = hits[0] if hits else None

        if use_bm25 and hits:
            hits = fuse_bm25(st, project_id, q["question"], hits, idx, pool)

        elapsed = (time.perf_counter() - t0) * 1000

        rank = None if q["no_answer"] else rank_of_first_hit(hits, q["gold"])
        rows.append({
            **q,
            "rank": rank,
            "top1_score": v_top["score"] if v_top else None,   # 벡터. 임계값 전용
            "top1_path": v_top["path"] if v_top else None,     # 벡터 1위
            "ranked1_path": hits[0]["path"] if hits else None,  # 최종 순위 1위
            "ms": round(elapsed, 1),
        })
        if not hits:
            print(f"  [{i:3d}/{len(questions)}] !! 검색 결과 없음  {q['question'][:40]}")
            continue
        mark = "--" if q["no_answer"] else ("OK" if rank and rank <= 3 else "XX")
        rank_s = str(rank) if rank else "-"
        print(f"  [{i:3d}/{len(questions)}] {mark} 유형{q['type']} "
              f"rank={rank_s:>3} vec1={v_top['score']:.4f} {q['question'][:40]}")
    print()
    return rows


# ── 집계 ─────────────────────────────────────────────────────
def retrieval_metrics(rows: list[dict]) -> dict:
    ans = [r for r in rows if not r["no_answer"]]
    if not ans:
        return {}
    out = {"n": len(ans)}
    for k in K_LIST:
        out[f"hit@{k}"] = sum(1 for r in ans if r["rank"] and r["rank"] <= k) / len(ans)
    out["mrr"] = sum(1 / r["rank"] for r in ans if r["rank"]) / len(ans)
    return out


def by_type(rows: list[dict]) -> dict:
    out = {}
    for t in (1, 2, 3, 4):
        sub = [r for r in rows if r["type"] == t and not r["no_answer"]]
        if sub:
            out[t] = {
                "n": len(sub),
                "hit@3": sum(1 for r in sub if r["rank"] and r["rank"] <= 3) / len(sub),
                "mrr": sum(1 / r["rank"] for r in sub if r["rank"]) / len(sub),
            }
    return out


def threshold_table(rows: list[dict]) -> tuple[list[dict], dict]:
    """임계값 후보별 confusion matrix.

    ⚠ **융합 전** 벡터 top-1 점수로만 평가합니다 (`top1_score`).
       융합 점수로 바꾸면 기준이 무효입니다. RRF 는 척도를 버리기 때문입니다.

    ⚠ 그래서 이 표는 `--bm25 on/off` 에 **영향받지 않습니다.**
       두 셀에서 같은 값이 나오는 게 정상입니다. 달라지면 버그입니다.
    """
    pos = [r["top1_score"] for r in rows if not r["no_answer"] and r["top1_score"] is not None]
    neg = [r["top1_score"] for r in rows if r["no_answer"] and r["top1_score"] is not None]
    if not pos or not neg:
        return [], {}

    dist = {
        "answerable": {"n": len(pos), "min": min(pos), "mean": sum(pos) / len(pos), "max": max(pos)},
        "no_answer": {"n": len(neg), "min": min(neg), "mean": sum(neg) / len(neg), "max": max(neg)},
        "overlap": min(pos) < max(neg),
    }

    table = []
    th = TH_LO
    while th <= TH_HI + 1e-9:
        tp = sum(1 for s in pos if s >= th)
        fn = len(pos) - tp
        fp = sum(1 for s in neg if s >= th)
        tn = len(neg) - fp
        recall = tp / len(pos)
        spec = tn / len(neg)
        table.append({
            "threshold": round(th, 2), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "recall": round(recall, 3), "specificity": round(spec, 3),
            "balanced_acc": round((recall + spec) / 2, 4),
        })
        th += TH_STEP
    return table, dist


# ── 출력 ─────────────────────────────────────────────────────
def report(project_id: str, rows: list[dict], note: str,
           mode: str = "벡터 단독") -> dict:
    m = retrieval_metrics(rows)
    tt, dist = threshold_table(rows)

    print("=" * 62)
    print(f"  {project_id}   [{mode}]   {note}")
    print("=" * 62)

    print(f"\n[검색] 답할 수 있는 질문 {m['n']}개")
    for k in K_LIST:
        print(f"  Hit@{k}   {m[f'hit@{k}']:.1%}")
    print(f"  MRR     {m['mrr']:.3f}")

    print("\n[유형별]")
    for t, v in by_type(rows).items():
        print(f"  유형 {t}  n={v['n']:<3} Hit@3 {v['hit@3']:.1%}  MRR {v['mrr']:.3f}")

    if dist:
        a, b = dist["answerable"], dist["no_answer"]
        print(f"\n[점수 분포]")
        print(f"  answerable  n={a['n']:<3} min {a['min']:.4f}  mean {a['mean']:.4f}  max {a['max']:.4f}")
        print(f"  no-answer   n={b['n']:<3} min {b['min']:.4f}  mean {b['mean']:.4f}  max {b['max']:.4f}")
        print(f"  분포 겹침: {dist['overlap']}"
              + ("   ← 완전 분리 불가" if dist["overlap"] else "   ← 분리 가능"))

        print(f"\n[임계값 후보 — balanced accuracy 상위 8]")
        print(f"  {'th':>5} {'tp':>3} {'fn':>3} {'fp':>3} {'tn':>3} "
              f"{'recall':>7} {'spec':>6} {'bal.acc':>8}")
        for r in sorted(tt, key=lambda x: -x["balanced_acc"])[:8]:
            cur = " ←현재" if abs(r["threshold"] - CFG.score_threshold) < 1e-6 else ""
            print(f"  {r['threshold']:>5.2f} {r['tp']:>3} {r['fn']:>3} {r['fp']:>3} {r['tn']:>3} "
                  f"{r['recall']:>7.3f} {r['specificity']:>6.3f} {r['balanced_acc']:>8.4f}{cur}")
        print("\n  ⚠ 관찰값입니다. 자동 적용하지 마세요.")

    print("\n[실패한 질문 — rank 3 밖]")
    misses = [r for r in rows if not r["no_answer"] and (r["rank"] is None or r["rank"] > 3)]
    for r in misses[:15]:
        print(f"  {r['qid']:<5} 유형{r['type']} rank={r['rank'] or '없음':>4}  {r['question'][:44]}")
        line = (f"        정답 {r['gold'][0]['path'] if r['gold'] else '?'} / "
                f"벡터1위 {r['top1_path']}")
        # 융합으로 1위가 바뀐 경우만 따로 보여줍니다 — BM25 가 무엇을 끌어올렸는지 보려고
        if r.get("ranked1_path") and r["ranked1_path"] != r["top1_path"]:
            line += f" / 융합1위 {r['ranked1_path']}"
        print(line)
    if not misses:
        print("  없음")

    return {"metrics": m, "by_type": by_type(rows), "distribution": dist, "threshold_table": tt}


def save_run(project_id: str, gold_file: str, rows: list[dict],
             summary: dict, note: str, *,
             pool: int = POOL, use_bm25: bool = False,
             index_fp: dict | None = None) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # ── signature — 무엇을 쟀는지의 정본 ────────────────────
    # ⚠ 청킹 계열 값은 **인덱스 자신의 지문**을 씁니다. CFG 가 아닙니다.
    #    CFG 는 이 프로세스의 환경변수일 뿐이라, 인덱싱 때와 다를 수 있습니다.
    #    (2026-08-10 baseline 이 실제와 다르게 기록된 원인)
    #
    # ⚠ `use_bm25`(인덱스 지문) 와 `eval_bm25`(이번 측정) 는 다른 것입니다.
    #      use_bm25   — 이 인덱스를 만들 때 역색인도 함께 만들었는가
    #      eval_bm25  — 이번 run 에서 융합을 켜고 쟀는가 (검색 시점 스위치)
    sig = dict(index_fp) if index_fp else dict(CFG.fingerprint())
    sig["pool"] = pool
    sig["eval_bm25"] = use_bm25
    sig["fp_source"] = "index" if index_fp else "config(⚠추정)"

    rec = {
        "run_id": run_id,
        "project_id": project_id,
        "gold_file": gold_file,
        "note": note,
        "signature": sig,
        "n_questions": len(rows),
        "summary": summary,
        "per_question": [
            {k: r.get(k) for k in
             ("qid", "type", "no_answer", "rank", "top1_score", "top1_path", "ranked1_path")}
            for r in rows
        ],
    }

    p = Path(RUNS_FILE)
    prev = None
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["project_id"] == project_id:
                prev = r

    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if prev:
        # ⚠ fp_source 는 "어떻게 기록했는가"이지 "무엇을 쟀는가"가 아닙니다.
        #    조건 비교에서 뺍니다 — 넣으면 구 run 과 항상 다르다고 나옵니다.
        changed = {k: (prev["signature"].get(k), v)
                   for k, v in rec["signature"].items()
                   if k != "fp_source" and prev["signature"].get(k) != v}
        if changed or prev["n_questions"] != rec["n_questions"]:
            print(f"\n{'=' * 62}")
            print(f"  ⚠ 직전 run({prev['run_id']}) 과 조건이 다릅니다")
            for k, (o, n) in changed.items():
                print(f"      {k}: {o} → {n}")
            if prev["n_questions"] != rec["n_questions"]:
                print(f"      질문 수: {prev['n_questions']} → {rec['n_questions']}")
            print("  전체 수치 차이를 '개선'으로 해석하지 마세요.")
            print("  질문별 rank 변화를 직접 보십시오.")
            print("=" * 62)
        else:
            pm, cm = prev["summary"]["metrics"], summary["metrics"]
            print(f"\n[직전 run {prev['run_id']} 대비 — 조건 동일]")
            for k in ("hit@1", "hit@3", "hit@5", "mrr"):
                d = cm[k] - pm[k]
                print(f"  {k:<7} {pm[k]:.3f} → {cm[k]:.3f}  ({d:+.3f})")

    return run_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="인덱싱된 project_id")
    ap.add_argument("--gold", required=True, help="RAG_TEST_*.md 경로")
    ap.add_argument("--note", default="", help="이번 run 설명 (예: 'AST 청커 적용')")
    ap.add_argument("--bm25", choices=("auto", "on", "off"), default="auto",
                    help="BM25 융합 여부. auto = CFG.use_bm25 를 따름 (기본)")
    ap.add_argument("--pool", type=int, default=POOL,
                    help=f"검색 후보 수 (기본 {POOL}). ⚠ A/B 셀 전체에서 같은 값을 쓰세요")
    args = ap.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.exists():
        print(f"!! gold 파일 없음: {gold_path}")
        return 1

    st = Store()

    # ⚠ 존재 확인을 **먼저** 합니다.
    #    Store 의 접근자는 전부 get_or_create_collection 을 거치므로,
    #    없는 이름으로 조회하면 빈 컬렉션이 조용히 생깁니다.
    #    오타 한 번이 유령 컬렉션을 남기는 경로라 여기서 끊습니다.
    avail = st.projects()
    if args.project not in avail:
        print(f"!! '{args.project}' 인덱스가 없습니다.")
        print(f"   있는 것: {', '.join(avail) if avail else '(없음)'}")
        return 1

    index_fp = searcher.serving_profile(st, args.project)

    # auto는 전역 CFG가 아니라 이 프로젝트가 실제로 가진 BM25 프로필을 따릅니다.
    use_bm25 = (bool((index_fp or {}).get("use_bm25"))
                if args.bm25 == "auto" else (args.bm25 == "on"))
    mode = "벡터 + BM25(RRF)" if use_bm25 else "벡터 단독"

    # ⚠ 제품 경로(searcher.py)는 융합 시 CFG.fusion_pool 을 씁니다.
    #    평가에서 다른 값을 쓰면 절대 수치가 제품 성능과 다릅니다.
    if use_bm25 and args.pool != CFG.fusion_pool:
        print(f"⚠ pool={args.pool} 로 잽니다. searcher.py 는 fusion_pool={CFG.fusion_pool} 을 씁니다.")
        print("   이 run 의 절대 수치를 제품 성능으로 읽지 마세요 — 셀 간 비교용입니다.\n")

    # ⚠ CFG 와 인덱스 지문이 어긋나면 큰 소리로 알립니다.
    #    조용히 넘어가면 "무엇을 쟀는지 모르는 숫자"가 문서로 흘러갑니다.
    if index_fp:
        drift = {k: (index_fp.get(k), v) for k, v in CFG.fingerprint().items()
                 if index_fp.get(k) != v}
        if drift:
            print("⚠ 환경변수(CFG)와 인덱스 지문이 다릅니다 — 기록은 인덱스 쪽을 씁니다:")
            for k, (i, c) in drift.items():
                print(f"    {k}: 인덱스={i}  /  CFG={c}")
            print("   재인덱싱 없이 CFG 만 바꿔도 인덱스는 그대로입니다.\n")
    else:
        print(f"⚠ '{args.project}' 인덱스에 지문이 없습니다 (구 방식으로 만든 인덱스).")
        print("   signature 를 CFG 로 추정해 기록합니다 — 정확하지 않을 수 있습니다.\n")

    questions = parse_gold(gold_path)
    n5 = sum(1 for q in questions if q["no_answer"])
    print(f"질문 {len(questions)}개 로드 (답 없는 질문 {n5}개)")

    bad = [q["qid"] for q in questions if not q["no_answer"] and not q["gold"]]
    if bad:
        print(f"!! 정답 위치가 비어 있음: {', '.join(bad[:10])}")
        print("   이 문항들은 항상 오답으로 집계됩니다. gold 를 확인하세요.\n")

    rows = run(args.project, questions, pool=args.pool,
               use_bm25=use_bm25, store=st, index_fp=index_fp)
    summary = report(args.project, rows, args.note, mode)
    run_id = save_run(args.project, gold_path.name, rows, summary, args.note,
                      pool=args.pool, use_bm25=use_bm25, index_fp=index_fp)
    print(f"\n기록: {RUNS_FILE}  run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
