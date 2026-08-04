"""
벡터 저장소 — Chroma.

⚠ 저장소를 바꿔도(SQLite / Qdrant) 임계값은 유효합니다.
   점수 분포를 결정하는 건 임베딩 모델과 거리 함수이지 저장 위치가 아닙니다.
   그래서 이 파일 하나만 갈아끼우면 됩니다.

⚠ Chroma는 cosine "거리"를 돌려줍니다.  similarity = 1 - distance
   D9 임계값(0.53~0.55)은 similarity 기준이므로 반드시 변환해야 합니다.
"""

from __future__ import annotations

from pathlib import Path

from .config import CFG


class Store:
    def __init__(self, index_dir: str | None = None):
        try:
            import chromadb
        except ImportError as e:
            raise RuntimeError(
                "chromadb 가 없습니다.  pip install chromadb"
            ) from e

        path = Path(index_dir or CFG.index_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))

    def _collection(self, project_id: str):
        return self._client.get_or_create_collection(
            name=project_id,
            metadata={"hnsw:space": "cosine"},   # ⚠ D9 전제
        )

    def reset(self, project_id: str) -> None:
        """재인덱싱 전 기존 컬렉션 삭제."""
        try:
            self._client.delete_collection(project_id)
        except Exception:
            pass   # 없으면 그만

    def add(self, project_id: str, chunks: list[dict], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        col = self._collection(project_id)
        col.add(
            ids=[f"{project_id}:{i}" for i in range(len(chunks))]
            if col.count() == 0
            else [f"{project_id}:{col.count() + i}" for i in range(len(chunks))],
            embeddings=vectors,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "path": c["path"],
                    "type": c["type"],
                    "line_start": c.get("line_start") or 0,
                    "line_end": c.get("line_end") or 0,
                    "section": c.get("section") or "",
                }
                for c in chunks
            ],
        )

    def query(self, project_id: str, vector: list[float], top_k: int) -> list[dict]:
        """상위 top_k 반환. score 는 cosine similarity (높을수록 유사)."""
        col = self._collection(project_id)
        if col.count() == 0:
            return []

        res = col.query(
            query_embeddings=[vector],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )

        out: list[dict] = []
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({
                "text": doc,
                "path": meta.get("path", ""),
                "type": meta.get("type", "code"),
                "line_start": meta.get("line_start") or None,
                "line_end": meta.get("line_end") or None,
                "section": meta.get("section") or None,
                "score": 1.0 - float(dist),      # ⚠ 거리 → 유사도
            })
        return out

    def count(self, project_id: str) -> int:
        try:
            return self._collection(project_id).count()
        except Exception:
            return 0

    def projects(self) -> list[str]:
        try:
            return [c.name for c in self._client.list_collections()]
        except Exception:
            return []
