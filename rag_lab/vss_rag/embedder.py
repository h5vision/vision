"""
임베딩 — Ollama bge-m3 호출.

⚠ fallback 없음.
   백엔드의 _local_embedding(sha256 해시 기반 가짜 임베딩)이 조용히 인덱스를
   오염시키는 문제(R18)를 여기서는 구조적으로 차단합니다.
   실패는 예외로 드러납니다.

⚠ BGE-M3 + cosine 은 D9 실측(Hit@3 90%, MRR 0.900, 임계값 0.53~0.55)의 전제입니다.
   모델을 바꾸면 그 수치가 전부 무효가 됩니다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import CFG


class EmbeddingError(RuntimeError):
    pass


def _post(path: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        f"{CFG.ollama_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise EmbeddingError(f"HTTP {e.code}: {e.read()[:300]!r}") from e
    except urllib.error.URLError as e:
        raise EmbeddingError(
            f"Ollama 접속 실패 ({CFG.ollama_url}): {e.reason}\n"
            "  터널이 살아있는지 확인하세요:  netstat -ano | findstr 11500"
        ) from e


def health() -> list[str]:
    """설치된 모델 목록. 접속 확인용."""
    req = urllib.request.Request(f"{CFG.ollama_url}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        raise EmbeddingError(f"Ollama 접속 실패: {e}") from e


def embed_many(texts: list[str]) -> list[list[float]]:
    """여러 문장을 배치로 임베딩. 순서 보존."""
    if not texts:
        return []

    out: list[list[float]] = []
    for i in range(0, len(texts), CFG.embed_batch):
        batch = texts[i:i + CFG.embed_batch]
        data = _post(
            "/api/embed",
            {"model": CFG.embed_model, "input": batch},
            CFG.embed_timeout,
        )

        # Ollama 버전에 따라 키가 다릅니다
        if "embeddings" in data:
            vecs = data["embeddings"]
        elif "embedding" in data:
            vecs = [data["embedding"]]
        else:
            raise EmbeddingError(f"예상 밖 응답 키: {list(data)}")

        if len(vecs) != len(batch):
            raise EmbeddingError(f"개수 불일치: 요청 {len(batch)} / 응답 {len(vecs)}")

        for v in vecs:
            if len(v) != CFG.embed_dim:
                raise EmbeddingError(
                    f"차원 불일치: {len(v)} (기대 {CFG.embed_dim}). "
                    "임베딩 모델이 바뀌지 않았는지 확인하세요."
                )
        out.extend(vecs)

    return out


def embed_one(text: str) -> list[float]:
    return embed_many([text])[0]
