"""
후처리 — 검색 결과를 LLM 에게 넘기기 전에 다듬습니다.

두 가지를 담당합니다.

    MMR      같은 파일에 편중된 결과를 분산시킵니다
    reorder  프롬프트 안에서 근거의 배치 순서를 조정합니다

⚠ 둘 다 **재인덱싱이 필요 없습니다.** 검색 후처리라서 토글만으로 켜고 끕니다.
   그래서 A/B 비교가 가장 쉬운 개선안입니다.
"""

from __future__ import annotations

from .config import CFG


# ── MMR (Maximal Marginal Relevance) ────────────────────────

def mmr(hits: list[dict], top_k: int, lambda_: float = 0.7) -> list[dict]:
    """
    점수와 다양성을 함께 고려해 top_k 를 고릅니다.

    ⚠ 왜 필요한가 — 실제로 관측된 문제입니다.

        검색 단위가 파일이 아니라 청크이므로, 한 파일에서 관련 청크가
        여러 개 걸리면 상위가 그 파일로 채워집니다.

            [1] translate.py L53-98    0.72
            [2] translate.py L101-150  0.66
            [3] translate.py L200-240  0.59
            [4] utils.py     L10-40    0.55
                 ↑ 한 파일에 편중. 다른 관점의 근거가 없음

        MMR 은 "이미 고른 것과 얼마나 다른가"를 함께 봅니다.

            [1] translate.py L53-98    0.72
            [2] utils.py     L10-40    0.55   ← 다른 파일이라 가산
            [3] config.py    L5-30     0.54
            [4] translate.py L101-150  0.66

    lambda_ 가 클수록 점수 중심, 작을수록 다양성 중심입니다.
        1.0  →  원래 순서 그대로 (MMR 끔과 동일)
        0.7  →  기본. 점수를 우선하되 편중은 완화
        0.5  →  다양성 강조

    ⚠ 임베딩 벡터를 다시 계산하지 않습니다.
       벡터 간 유사도 대신 **경로 기반 근사**를 씁니다.
       같은 파일 > 같은 디렉터리 > 무관 순으로 페널티를 줍니다.
       정확한 MMR 은 청크 벡터가 필요한데, 저장소에서 다시 꺼내는
       비용이 이득보다 큽니다.
    """
    if not hits or top_k <= 0:
        return hits[:top_k]
    if lambda_ >= 1.0:
        return hits[:top_k]

    def similarity(a: dict, b: dict) -> float:
        """경로 기반 근사 유사도. 0(무관) ~ 1(동일 파일)."""
        pa, pb = a.get("path", ""), b.get("path", "")
        if not pa or not pb:
            return 0.0
        if pa == pb:
            return 1.0
        da = pa.rsplit("/", 1)[0] if "/" in pa else ""
        db = pb.rsplit("/", 1)[0] if "/" in pb else ""
        if da and da == db:
            return 0.5                      # 같은 디렉터리
        # 상위 디렉터리 공유
        sa, sb = pa.split("/"), pb.split("/")
        common = 0
        for x, y in zip(sa[:-1], sb[:-1]):
            if x != y:
                break
            common += 1
        return min(0.35, common * 0.15)

    selected: list[dict] = [hits[0]]
    pool = hits[1:]

    while pool and len(selected) < top_k:
        best_i, best_v = 0, float("-inf")
        for i, cand in enumerate(pool):
            max_sim = max(similarity(cand, s) for s in selected)
            value = lambda_ * cand.get("score", 0.0) - (1 - lambda_) * max_sim
            if value > best_v:
                best_i, best_v = i, value
        selected.append(pool.pop(best_i))

    return selected


# ── 컨텍스트 배치 순서 ───────────────────────────────────────

def reorder_for_attention(contexts: list[dict]) -> list[dict]:
    """
    프롬프트 안에서 근거의 배치를 조정합니다.

    ⚠ LLM 은 긴 입력의 **중간** 정보를 상대적으로 덜 활용하는 경향이
       알려져 있습니다 (lost in the middle). 앞과 뒤를 더 주목합니다.

       그래서 점수가 높은 근거를 **양 끝**에 배치합니다.

           점수순:   1위  2위  3위  4위  5위
           재배치:   1위  3위  5위  4위  2위
                     ↑              ↑
                   가장 중요       두 번째

    ⚠ [N] 번호는 **재배치 후 순서로 다시 매겨집니다.**
       즉 프롬프트의 [1] 은 여전히 contexts[0] 입니다.
       배치가 바뀌는 것이지 대응이 깨지는 것이 아닙니다.

    ⚠ 근거가 4개 이하이면 "중간"이 거의 없어 효과가 미미합니다.
       기본을 5개 이상일 때만 적용하도록 했습니다.
    """
    n = len(contexts)
    if n < 5:
        return contexts

    head: list[dict] = []
    tail: list[dict] = []
    for i, c in enumerate(contexts):
        (head if i % 2 == 0 else tail).append(c)
    tail.reverse()
    return head + tail


# ── 진입점 ───────────────────────────────────────────────────

def postprocess(hits: list[dict], top_k: int, *,
                use_mmr: bool | None = None,
                mmr_lambda: float | None = None,
                reorder: bool | None = None) -> list[dict]:
    """검색 결과 → LLM 에 넘길 최종 목록. 설정에 따라 MMR·재배치 적용."""
    out = hits
    mmr_on = CFG.use_mmr if use_mmr is None else use_mmr
    reorder_on = CFG.reorder_context if reorder is None else reorder
    lambda_ = CFG.mmr_lambda if mmr_lambda is None else mmr_lambda
    if mmr_on:
        out = mmr(out, top_k, lambda_)
    else:
        out = out[:top_k]
    if reorder_on:
        out = reorder_for_attention(out)
    return out
