"""
검색 — top-k + 임계값 기반 근거 없음 판정(FN-B06) + 프롬프트 조립 + 답변 후처리.

임계값은 BGE-M3 + cosine 점수 분포 관찰에서 나온 **잠정 선택값**입니다.

⚠ 분리선이 아닙니다. answerable 과 no-answer 분포는 겹칩니다.
   balanced accuracy 를 근사 최대화하는 지점일 뿐이며 FP·FN 을 수반합니다.
   수치·run_id 는 MEASUREMENTS §2 참조. 이 파일에는 값을 적지 않습니다.

⚠ 임베딩 모델·정규화·거리 함수에 종속됩니다.
   저장소를 바꾸는 건 무관하지만, 임베딩을 바꾸면 재측정해야 합니다.

⚠ 임계값은 "검색 단계" 판정입니다.
   검색은 통과했으나 내용이 질문과 무관한 경우는 모델만 판단할 수 있고,
   그건 NO_EVIDENCE 학습(D-S2, 거절 샘플 15%)이 담당합니다.
"""

from __future__ import annotations

import re
import time
from typing import Mapping

from .config import CFG, normalize_fingerprint
from .embedder import embed_one
from . import lexical, rerank
from .references import build_references, parse_citations
from .store import Store


class ProjectNotFoundError(LookupError):
    pass


def serving_profile(store: Store, project_id: str) -> dict:
    """질의에 사용할 프로젝트별 인덱스 프로필.

    전역 CFG를 쓰면 서로 다른 설정으로 만든 컬렉션 중 하나는 반드시 잘못
    서빙됩니다. 컬렉션 metadata가 정본이고, 구 컬렉션만 state.json을 보조로 씁니다.
    """
    available = store.projects()
    if project_id not in available:
        raise ProjectNotFoundError(
            f"인덱싱된 project_id가 아닙니다: {project_id!r}; "
            f"available={', '.join(available) or '(없음)'}")

    fp = store.index_fingerprint(project_id)
    if fp:
        return fp

    # fingerprint metadata가 없던 구 인덱스 호환. state.json도 없으면 현재 CFG로
    # 추정하지 않습니다. 잘못된 임베딩 모델로 조용히 검색하는 것보다 실패가 안전합니다.
    from . import indexer
    fp = normalize_fingerprint(indexer.get_state(project_id).get("fingerprint"))
    if not fp:
        raise RuntimeError(
            f"인덱스 설정 지문을 확인할 수 없습니다: {project_id!r}. 재인덱싱이 필요합니다.")
    return fp


def search(query: str, project_id: str, top_k: int | None = None,
           threshold: float | None = None, store: Store | None = None,
           *, search_profile: Mapping | None = None) -> dict:
    """
    반환의 contexts 는 백엔드 Source 스키마와 호환됩니다.

    ⚠ contexts 순서가 곧 프롬프트의 [1] [2] [3] 번호입니다.
       이 배열을 정렬하거나 필터링하면 인용 대응이 깨집니다.
    """
    k = top_k if top_k is not None else CFG.top_k
    th = threshold if threshold is not None else CFG.score_threshold
    st = store or Store()
    profile = serving_profile(st, project_id)

    # ⚠ 이 두 단계가 TTFT 임계 경로입니다.
    #    스트리밍을 써도 여기가 끝나야 LLM 호출이 시작됩니다.
    t0 = time.perf_counter()
    vec = embed_one(
        query,
        model=str(profile["embed_model"]),
        expected_dim=int(profile["embed_dim"]),
    )
    t1 = time.perf_counter()

    # 개선 기능이 켜져 있으면 후보를 넉넉히 뽑습니다.
    # MMR·융합은 후보가 많아야 고를 여지가 생깁니다.
    options = dict(search_profile or {})
    use_bm25 = bool(options.get("use_bm25", profile["use_bm25"]))
    use_mmr = bool(options.get("use_mmr", CFG.use_mmr))
    pool = int(options.get("pool", CFG.fusion_pool)) if (use_bm25 or use_mmr) else k
    hits = st.query(project_id, vec, max(pool, k))
    t2 = time.perf_counter()

    timing = {
        "embed_ms": round((t1 - t0) * 1000, 1),
        "search_ms": round((t2 - t1) * 1000, 1),
    }

    if not hits:
        return {"has_evidence": False, "contexts": [], "all_hits": [],
                "top_score": None, "threshold": th,
                "reason": "empty_index", "timing": timing,
                "serving_profile": profile, "bm25_active": False,
                "search_profile": {
                    "use_bm25": use_bm25, "pool": pool, "top_k": k,
                    "threshold": th, "use_mmr": use_mmr,
                    "mmr_lambda": float(options.get("mmr_lambda", CFG.mmr_lambda)),
                    "reorder": bool(options.get("reorder", CFG.reorder_context)),
                }}

    # ── BM25 융합 ────────────────────────────────────────────
    # ⚠ 벡터 점수(score)는 그대로 유지합니다.
    #    융합 점수로 덮어쓰면 임계값 0.54 판정이 불가능해집니다.
    #    융합은 "순서"만 바꾸고, 임계값은 벡터 점수로 판단합니다.
    bm25_active = False
    if use_bm25:
        t_bm = time.perf_counter()
        idx = lexical.BM25.load(lexical.index_path(project_id))
        if idx:
            bm25_active = True
            lex = idx.search(query, pool)
            fused = lexical.rrf_fuse(hits, lex, k=60)

            by_id = {h["_id"]: h for h in hits}
            missing = [i for i, _ in lex if i not in by_id]
            if missing:
                by_id.update(st.get_by_ids(project_id, missing[:pool]))

            hits = sorted(
                (by_id[i] for i in fused if i in by_id),
                key=lambda h: -fused[h["_id"]],
            )
        timing["bm25_ms"] = round((time.perf_counter() - t_bm) * 1000, 1)

    # ⚠ **융합 후 hits[0] 의 점수를 쓰면 안 됩니다.**
    #    RRF 는 순서를 바꾸므로 hits[0] 이 최고 벡터 점수가 아닙니다.
    #    그렇게 하면 아래 판정과 어긋나 "top < 임계값인데 has_evidence=True"
    #    같은 모순된 출력이 나옵니다 (2026-08-13 관측).
    #
    #    판정은 pool 전체를 보므로(`any(score >= th)`), 표시도 **최대 벡터 점수**여야
    #    `top_score >= threshold ⟺ has_evidence` 가 성립합니다.
    top = max(h["score"] for h in hits)
    ranked1 = hits[0]["score"]          # 융합 후 1위의 벡터 점수 (참고용)

    # ── 임계값 판정 ─────────────────────────────────────────
    # ⚠ 벡터 점수 기준입니다. BM25 로만 올라온 청크는 score 가 0 이라
    #    임계값을 못 넘습니다. 의도된 동작입니다 —
    #    D9 실측(0.53~0.55)은 벡터 점수 분포에서 나온 값이기 때문입니다.
    passed = [h for h in hits if h["score"] >= th]

    # ── MMR · 배치 조정 ─────────────────────────────────────
    if passed:
        passed = rerank.postprocess(
            passed, k,
            use_mmr=use_mmr,
            mmr_lambda=float(options.get("mmr_lambda", CFG.mmr_lambda)),
            reorder=bool(options.get("reorder", CFG.reorder_context)),
        )
    else:
        hits = hits[:k]

    return {
        "has_evidence": bool(passed),
        "contexts": passed,
        "all_hits": hits[:max(k * 2, 10)],   # 임계값 튜닝용. 탈락한 것도 확인 가능
        # ⚠ top_score = pool 안의 **최대 벡터 점수**. 융합 후 1위의 점수가 아닙니다.
        #    `top_score >= threshold` 와 `has_evidence` 는 항상 같은 값입니다.
        "top_score": top,
        "ranked1_score": ranked1,            # 융합 후 1위의 벡터 점수 (진단용)
        "threshold": th,
        "reason": "ok" if passed else "below_threshold",
        "timing": timing,
        "serving_profile": profile,
        "bm25_active": bm25_active,
        "search_profile": {
            "use_bm25": use_bm25, "pool": pool, "top_k": k, "threshold": th,
            "use_mmr": use_mmr,
            "mmr_lambda": float(options.get("mmr_lambda", CFG.mmr_lambda)),
            "reorder": bool(options.get("reorder", CFG.reorder_context)),
        },
    }


def render_prompt(question: str, contexts: list[dict]) -> list[dict]:
    """
    검색 결과 → LLM messages.

    ⚠ 백엔드 generation.py 의 현행 형식을 따릅니다.
       학습 데이터도 같은 형식이어야 fine-tuning 효과가 샙니다.
       (PROMPT_DATA_FORMAT_SPEC §0 "렌더러 하나" 원칙)

    ⚠ [N] 번호는 contexts 배열 인덱스+1 과 1:1 대응합니다.
    """
    system = (
        "제공된 근거만 사용해 한국어로 답한다. 근거에 없는 파일·동작은 추측하지 않는다.\n"
        "각 주장 끝에 사용한 근거 번호를 [1], [2] 형식으로 표기한다.\n"
        "근거가 질문에 답하기 부족하면 다른 설명 없이 정확히 다음 한 줄만 출력한다: NO_EVIDENCE"
    )

    if contexts:
        parts = ["프로젝트 검색 결과:"]
        for i, c in enumerate(contexts, start=1):
            if c.get("type") == "doc" and c.get("section"):
                head = f"[{i}] {c['path']} #{c['section']}"
            elif c.get("line_start"):
                head = f"[{i}] {c['path']} lines {c['line_start']}-{c['line_end']}"
            else:
                head = f"[{i}] {c['path']}"
            parts.append(f"{head}\n{c['text']}")
        parts.append(f"질문:\n{question}")
        user = "\n\n".join(parts)
    else:
        user = f"프로젝트 검색 결과:\n검색된 프로젝트 문서가 없습니다.\n\n질문:\n{question}"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ── 답변 후처리 ──────────────────────────────────────────────

_NO_EVIDENCE = re.compile(r"^\s*NO_EVIDENCE\s*$", re.MULTILINE)


def is_no_evidence(answer: str) -> bool:
    """
    모델이 거절했는지 판정 (FN-B06).

    ⚠ 프롬프트는 'NO_EVIDENCE 한 줄만' 을 요구하지만, base 모델은
       앞뒤에 설명을 붙이는 경우가 있습니다. 관대하게 판정합니다.
       (거절 형식 안정화는 D-S2 학습이 담당)
    """
    if not answer:
        return True
    a = answer.strip()
    return a == "NO_EVIDENCE" or bool(_NO_EVIDENCE.search(a))


def finalize(answer: str, contexts: list[dict],
             cited_only: bool = True, include_text: bool = True) -> dict:
    """
    LLM 답변 + 검색 근거 → 프론트 최종 응답.
    answer 와 references 를 분리해서 돌려줍니다.

        {
          "answer": "translate_page 함수는 ... [1].",
          "references": [
            {"n": 1, "path": "scripts/translate.py",
             "line": 53, "line_start": 53, "line_end": 98, ...}
          ],
          "reference_files": [
            {"path": "scripts/translate.py", "citations": [1, 3],
             "lines": [[53, 98], [200, 240]], "line": 53}
          ],
          "cited": [1, 3],
          "no_evidence": false
        }

    ⚠ cited_only=True 여도 n 번호는 원래 값을 유지합니다.
       재번호를 매기면 답변 본문의 [N] 이 가리킬 대상을 잃습니다.
    """
    if is_no_evidence(answer):
        return {
            "answer": "NO_EVIDENCE",
            "references": [],
            "reference_files": [],
            "cited": [],
            "no_evidence": True,
        }

    r = build_references(contexts, answer=answer,
                         cited_only=cited_only, include_text=include_text)
    return {
        "answer": answer,
        "references": r["references"],
        "reference_files": r["reference_files"],
        "cited": r["cited"],
        "no_evidence": False,
    }
