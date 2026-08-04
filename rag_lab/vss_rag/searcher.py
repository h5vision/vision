"""
검색 — top-k + 임계값 기반 근거 없음 판정(FN-B06) + 프롬프트 조립 + 답변 후처리.

D9 실측 (2026-07-27, BGE-M3 + cosine)
  answerable 최저 점수  0.5531
  no-answer  최고 점수  0.5306
  → 임계값 0.53~0.55 로 분리 가능

⚠ 이 값은 임베딩 모델·정규화·거리 함수에 종속됩니다.
   저장소를 바꾸는 건 무관하지만, 임베딩을 바꾸면 재측정해야 합니다.

⚠ 임계값은 "검색 단계" 판정입니다.
   검색은 통과했으나 내용이 질문과 무관한 경우는 모델만 판단할 수 있고,
   그건 NO_EVIDENCE 학습(D-S2, 거절 샘플 15%)이 담당합니다.
"""

from __future__ import annotations

import re

from .config import CFG
from .embedder import embed_one
from .references import build_references, parse_citations
from .store import Store


def search(query: str, project_id: str, top_k: int | None = None,
           threshold: float | None = None, store: Store | None = None) -> dict:
    """
    반환의 contexts 는 백엔드 Source 스키마와 호환됩니다.

    ⚠ contexts 순서가 곧 프롬프트의 [1] [2] [3] 번호입니다.
       이 배열을 정렬하거나 필터링하면 인용 대응이 깨집니다.
    """
    k = top_k if top_k is not None else CFG.top_k
    th = threshold if threshold is not None else CFG.score_threshold
    st = store or Store()

    vec = embed_one(query)
    hits = st.query(project_id, vec, k)

    if not hits:
        return {"has_evidence": False, "contexts": [], "all_hits": [],
                "top_score": None, "threshold": th, "reason": "empty_index"}

    top = hits[0]["score"]
    passed = [h for h in hits if h["score"] >= th]

    return {
        "has_evidence": bool(passed),
        "contexts": passed,
        "all_hits": hits,          # 임계값 튜닝용. 탈락한 것도 확인 가능
        "top_score": top,
        "threshold": th,
        "reason": "ok" if passed else "below_threshold",
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
