#!/usr/bin/env python3
"""
평가 하네스 — 검색이 정답 위치를 찾아오는지 채점합니다.

⚠ 이 파일이 재는 것은 **검색 레이어**입니다.
   store.query() 를 직접 호출하므로 임계값·MMR·재배치의 영향을 받지 않습니다.
   그게 의도입니다. 검색이 정답을 몇 위로 올리는가와,
   후처리가 그걸 어떻게 자르는가는 분리해서 봐야 합니다.

사용법
    python eval.py --project fastapi-cli --gold RAG_TEST_fastapi_cli.md
    python eval.py --project fastapi-cli --gold ... --note "AST 청커 적용"

⚠ 레포별로 따로 돌리고 따로 읽으세요.
   청크 수가 다르면 Hit@k 난이도가 다릅니다. 합치면 안 됩니다.
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

from vss_rag.config import CFG          # noqa: E402
from vss_rag.embedder import embed_one  # noqa: E402
from vss_rag.store import Store         # noqa: E402

# ── 채점 규칙 ────────────────────────────────────────────────
POOL = 10           # 검색해 올 후보 수. Hit@5 를 재려면 5보다 커야 함
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


# ── 실행 ─────────────────────────────────────────────────────
def run(project_id: str, questions: list[dict]) -> list[dict]:
    st = Store()
    n = st.count(project_id)
    if n == 0:
        print(f"!! '{project_id}' 인덱스가 비어 있습니다. 먼저 인덱싱하세요.")
        sys.exit(1)
    print(f"인덱스 {project_id}: {n:,} 청크\n")

    rows = []
    for i, q in enumerate(questions, 1):
        t0 = time.perf_counter()
        vec = embed_one(q["question"])
        hits = st.query(project_id, vec, POOL)
        elapsed = (time.perf_counter() - t0) * 1000

        rank = None if q["no_answer"] else rank_of_first_hit(hits, q["gold"])
        rows.append({
            **q,
            "rank": rank,
            "top1_score": hits[0]["score"] if hits else None,
            "top1_path": hits[0]["path"] if hits else None,
            "ms": round(elapsed, 1),
        })
        if not hits:
            print(f"  [{i:3d}/{len(questions)}] !! 검색 결과 없음  {q['question'][:40]}")
            continue
        mark = "--" if q["no_answer"] else ("OK" if rank and rank <= 3 else "XX")
        rank_s = str(rank) if rank else "-"
        print(f"  [{i:3d}/{len(questions)}] {mark} 유형{q['type']} "
              f"rank={rank_s:>3} top1={hits[0]['score']:.4f} {q['question'][:40]}")
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

    ⚠ 벡터 top-1 점수로만 평가합니다. 융합 점수로 바꾸면 기준이 무효입니다.
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
def report(project_id: str, rows: list[dict], note: str) -> dict:
    m = retrieval_metrics(rows)
    tt, dist = threshold_table(rows)

    print("=" * 62)
    print(f"  {project_id}   {note}")
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
        print(f"        정답 {r['gold'][0]['path'] if r['gold'] else '?'} / "
              f"top1 {r['top1_path']}")
    if not misses:
        print("  없음")

    return {"metrics": m, "by_type": by_type(rows), "distribution": dist, "threshold_table": tt}


def save_run(project_id: str, gold_file: str, rows: list[dict],
             summary: dict, note: str) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rec = {
        "run_id": run_id,
        "project_id": project_id,
        "gold_file": gold_file,
        "note": note,
        "signature": {**CFG.fingerprint(), "pool": POOL},
        "n_questions": len(rows),
        "summary": summary,
        "per_question": [
            {k: r[k] for k in ("qid", "type", "no_answer", "rank", "top1_score", "top1_path")}
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
        changed = {k: (prev["signature"].get(k), v)
                   for k, v in rec["signature"].items()
                   if prev["signature"].get(k) != v}
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
    args = ap.parse_args()

    gold_path = Path(args.gold)
    if not gold_path.exists():
        print(f"!! gold 파일 없음: {gold_path}")
        return 1

    questions = parse_gold(gold_path)
    n5 = sum(1 for q in questions if q["no_answer"])
    print(f"질문 {len(questions)}개 로드 (답 없는 질문 {n5}개)")

    bad = [q["qid"] for q in questions if not q["no_answer"] and not q["gold"]]
    if bad:
        print(f"!! 정답 위치가 비어 있음: {', '.join(bad[:10])}")
        print("   이 문항들은 항상 오답으로 집계됩니다. gold 를 확인하세요.\n")

    rows = run(args.project, questions)
    summary = report(args.project, rows, args.note)
    run_id = save_run(args.project, gold_path.name, rows, summary, args.note)
    print(f"\n기록: {RUNS_FILE}  run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
