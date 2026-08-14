#!/usr/bin/env python3
"""
MEASUREMENTS 생성기 — `eval_runs.jsonl` 에서 측정 문서를 기계 생성합니다.

⚠ 왜 스크립트인가

    수치를 손으로 문서에 옮기면 **반드시 갈라집니다.**
    0.5531 이 5개 파일로 퍼졌던 사고가 그 결과였습니다.
    측정 기록(jsonl)을 유일한 원본으로 두고, 문서는 거기서 파생시킵니다.

    → 문서가 틀렸으면 문서를 고치지 말고 run 을 다시 도세요.

⚠ 이 스크립트가 하지 않는 것

    · 레포 간 비교          — 청크 수가 다르면 Hit@k 난이도가 다릅니다
    · 조건이 다른 run 비교   — 지문이 하나라도 다르면 "개선"으로 읽으면 안 됩니다
    · 값 해석·결론          — 사람이 씁니다. 여기는 사실만 냅니다

사용법
    python make_measurements.py                        # stdout
    python make_measurements.py --out MEASUREMENTS_generated.md
    python make_measurements.py --project fastapi-cli  # 한 레포만
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

RUNS_FILE = "eval_runs.jsonl"

# 지문에서 "조건"으로 취급할 키. 이 중 하나라도 다르면 비교 불가입니다.
COND_KEYS = ("embed_model", "chunk_size", "chunk_overlap",
             "context_header", "use_bm25", "pool", "eval_bm25")

METRIC_KEYS = ("hit@1", "hit@3", "hit@5", "mrr")


# ── 로드 ─────────────────────────────────────────────────────
def load_runs(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"!! {path} 가 없습니다. eval.py 를 먼저 도세요.")
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"!! {path}:{i} 파싱 실패 — 건너뜁니다 ({e})")
    return out


def cond_of(run: dict) -> tuple:
    sig = run.get("signature") or {}
    return tuple(sig.get(k) for k in COND_KEYS)


def cond_label(run: dict) -> str:
    """조건을 한 줄로. 없는 키는 `?` 로 — 모른다는 걸 숨기지 않습니다."""
    sig = run.get("signature") or {}

    def g(k):
        v = sig.get(k)
        return "?" if v is None else v

    return (f"chunk {g('chunk_size')}/{g('chunk_overlap')} · "
            f"ctx={g('context_header')} · "
            f"색인bm25={g('use_bm25')} · "
            f"eval_bm25={g('eval_bm25')} · "
            f"pool={g('pool')} · "
            f"embed={g('embed_model')}")


# ── 렌더 ─────────────────────────────────────────────────────
def fmt_pct(v) -> str:
    return "—" if v is None else f"{v:.1%}"


def fmt_num(v, nd=3) -> str:
    return "—" if v is None else f"{v:.{nd}f}"


def render_project(pid: str, runs: list[dict]) -> list[str]:
    L = [f"## {pid}", ""]

    n_chunks_note = ""
    L.append(f"run {len(runs)}건." + n_chunks_note)
    L.append("")

    # ── 조건 범례 ────────────────────────────────────────────
    conds: OrderedDict[tuple, str] = OrderedDict()
    for r in runs:
        c = cond_of(r)
        if c not in conds:
            conds[c] = f"C{len(conds) + 1}"

    L.append("### 조건")
    L.append("")
    for c, name in conds.items():
        sample = next(r for r in runs if cond_of(r) == c)
        src = (sample.get("signature") or {}).get("fp_source", "?")
        warn = "  🔴 **지문 출처 불명 — 이 값은 신뢰할 수 없습니다**" if src != "index" else ""
        L.append(f"- **{name}** — {cond_label(sample)}")
        L.append(f"  - 지문 출처: `{src}`{warn}")
    L.append("")

    # ── 결과 표 ──────────────────────────────────────────────
    L.append("### 검색 결과")
    L.append("")
    L.append("| run_id | 조건 | note | n | Hit@1 | Hit@3 | Hit@5 | MRR | 1문항 |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for r in runs:
        m = (r.get("summary") or {}).get("metrics") or {}
        n = m.get("n")
        step = f"{1 / n:.2%}" if n else "—"
        note = (r.get("note") or "").replace("|", "\\|") or "—"
        L.append(
            f"| `{r['run_id']}` | {conds[cond_of(r)]} | {note} | {n or '—'} | "
            f"{fmt_pct(m.get('hit@1'))} | {fmt_pct(m.get('hit@3'))} | "
            f"{fmt_pct(m.get('hit@5'))} | {fmt_num(m.get('mrr'))} | {step} |"
        )
    L.append("")
    L.append("> `n` 은 **답할 수 있는 질문 수**입니다. 답 없는 질문(유형5)은 Hit@k 분모에 없습니다.")
    L.append("> `1문항` = 질문 하나가 움직이는 폭. 이보다 작은 차이는 노이즈입니다.")
    L.append("")

    # ── 유형별 ───────────────────────────────────────────────
    typed = [r for r in runs if (r.get("summary") or {}).get("by_type")]
    if typed:
        L.append("### 질문 유형별 Hit@3")
        L.append("")
        types = sorted({int(t) for r in typed
                        for t in (r["summary"]["by_type"] or {})})
        L.append("| run_id | " + " | ".join(f"유형{t}" for t in types) + " |")
        L.append("|---|" + "---:|" * len(types))
        for r in typed:
            bt = r["summary"]["by_type"] or {}
            cells = []
            for t in types:
                v = bt.get(str(t)) or bt.get(t)
                cells.append(f"{v['hit@3']:.1%} (n={v['n']})" if v else "—")
            L.append(f"| `{r['run_id']}` | " + " | ".join(cells) + " |")
        L.append("")

    # ── 점수 분포 · 임계값 ──────────────────────────────────
    dists = [r for r in runs if (r.get("summary") or {}).get("distribution")]
    if dists:
        L.append("### 점수 분포와 임계값")
        L.append("")
        L.append("⚠ **융합 전 벡터 top-1 점수** 기준입니다. RRF 융합 점수가 아닙니다.")
        L.append("")
        L.append("| run_id | answerable min~max | no-answer min~max | 겹침 | bal.acc 최대 th | 그때 bal.acc |")
        L.append("|---|---|---|---|---:|---:|")
        for r in dists:
            d = r["summary"]["distribution"]
            a, b = d["answerable"], d["no_answer"]
            tt = (r["summary"].get("threshold_table") or [])
            best = max(tt, key=lambda x: x["balanced_acc"]) if tt else None
            L.append(
                f"| `{r['run_id']}` | {a['min']:.4f}~{a['max']:.4f} (n={a['n']}) | "
                f"{b['min']:.4f}~{b['max']:.4f} (n={b['n']}) | "
                f"{'**겹침**' if d['overlap'] else '분리'} | "
                f"{best['threshold']:.2f} | {best['balanced_acc']:.4f} |"
                if best else
                f"| `{r['run_id']}` | {a['min']:.4f}~{a['max']:.4f} | "
                f"{b['min']:.4f}~{b['max']:.4f} | "
                f"{'**겹침**' if d['overlap'] else '분리'} | — | — |"
            )
        L.append("")
        if any(r["summary"]["distribution"]["overlap"] for r in dists):
            L.append("> 🔴 분포가 겹칩니다. **임계값으로 완전 분리할 수 없습니다.**")
            L.append("> bal.acc 최대점은 분리선이 아니라 FP·FN 을 함께 지는 절충점입니다.")
            L.append("")

    # ── 비교 가능 묶음 ──────────────────────────────────────
    L.append("### 비교")
    L.append("")
    groups = defaultdict(list)
    for r in runs:
        # 조건 중 eval_bm25 만 다른 run 끼리는 A/B 로 묶습니다.
        key = (tuple(v for k, v in zip(COND_KEYS, cond_of(r)) if k != "eval_bm25"),
               r.get("gold_file"), (r.get("summary", {}).get("metrics", {}) or {}).get("n"))
        groups[key].append(r)

    ab = [g for g in groups.values() if len(g) > 1]
    if not ab:
        L.append("비교 가능한 run 쌍이 없습니다 — 조건·gold·문항 수가 모두 같아야 합니다.")
        L.append("")
    for g in ab:
        base = g[0]
        L.append(f"**{cond_label(base).split(' · eval_bm25')[0]}** 위에서 `eval_bm25` A/B:")
        L.append("")
        L.append("| eval_bm25 | run_id | Hit@1 | Hit@3 | Hit@5 | MRR |")
        L.append("|---|---|---:|---:|---:|---:|")
        for r in sorted(g, key=lambda x: bool((x.get("signature") or {}).get("eval_bm25"))):
            m = r["summary"]["metrics"]
            flag = (r.get("signature") or {}).get("eval_bm25")
            L.append(f"| {flag} | `{r['run_id']}` | {fmt_pct(m.get('hit@1'))} | "
                     f"{fmt_pct(m.get('hit@3'))} | {fmt_pct(m.get('hit@5'))} | "
                     f"{fmt_num(m.get('mrr'))} |")
        n = base["summary"]["metrics"].get("n")
        if n:
            L.append("")
            L.append(f"> 1문항 = {1 / n:.2%}p. 그보다 작은 차이는 읽지 마세요.")
        L.append("")

    return L


def render(runs: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    L = [
        "<!-- 🤖 자동 생성 — 손으로 고치지 마세요. -->",
        f"<!-- 생성: python make_measurements.py   원본: {RUNS_FILE} -->",
        f"<!-- 생성 시각: {now} · run {len(runs)}건 -->",
        "",
        "---",
        "문서: MEASUREMENTS (생성본)",
        "상태: 자동 생성",
        f"생성_시각: {now}",
        f"원본: {RUNS_FILE}",
        "판단근거로_쓸_범위: 검색 평가 실측값",
        "쓰면_안_되는_범위: 결정 (→ DECISIONS) · 현황 진단 (→ HANDOFF) · 명령어 (→ MANUAL)",
        "---",
        "",
        "# 검색 평가 실측",
        "",
        "⚠ **이 파일은 기계 생성됩니다.** 손으로 고친 값은 다음 생성 때 사라집니다.",
        f"값이 틀렸다고 판단되면 문서가 아니라 `{RUNS_FILE}` 을 만든 run 을 다시 도세요.",
        "",
        "⚠ **레포가 다르면 비교하지 마세요.** 청크 수가 다르면 Hit@k 의 난이도 자체가 다릅니다.",
        "",
    ]

    by_pid = defaultdict(list)
    for r in runs:
        by_pid[r.get("project_id", "?")].append(r)

    for pid in sorted(by_pid):
        L += render_project(pid, by_pid[pid])
        L.append("---")
        L.append("")

    # ── 신뢰도 경고 ─────────────────────────────────────────
    bad = [r for r in runs
           if (r.get("signature") or {}).get("fp_source") != "index"]
    if bad:
        L.append("## 🔴 지문 출처가 불명한 run")
        L.append("")
        L.append("아래 run 은 인덱스 자신의 지문이 아니라 **측정 당시 환경변수(CFG)** 로")
        L.append("조건이 기록됐습니다. 두 값은 얼마든지 어긋날 수 있어, 조건 칸을 믿을 수 없습니다.")
        L.append("")
        L.append("| run_id | project | note |")
        L.append("|---|---|---|")
        for r in bad:
            L.append(f"| `{r['run_id']}` | {r.get('project_id', '?')} | "
                     f"{(r.get('note') or '—')} |")
        L.append("")
        L.append("→ **재측정 대상입니다.** 이 값들을 baseline 으로 삼지 마세요.")
        L.append("")

    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=RUNS_FILE, help=f"측정 기록 (기본 {RUNS_FILE})")
    ap.add_argument("--out", default=None, help="출력 파일. 생략하면 stdout")
    ap.add_argument("--project", default=None, help="이 project_id 만")
    args = ap.parse_args()

    runs = load_runs(Path(args.runs))
    if args.project:
        runs = [r for r in runs if r.get("project_id") == args.project]
    if not runs:
        print("!! 해당하는 run 이 없습니다.")
        return 1

    text = render(runs)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"생성 완료: {args.out}  (run {len(runs)}건)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
