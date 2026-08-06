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

    @staticmethod
    def _chunk_id(project_id: str, chunk: dict, fallback: int) -> str:
        """
        경로 + 파일 내 순번 기반 안정 ID.

        ⚠ 이전 구현은 컬렉션 전체 순번(project_id:0, :1, ...)이었습니다.
           그 방식은 "이 파일의 청크"를 특정할 수 없어 증분 인덱싱이 불가능합니다.
           경로를 ID 에 넣으면 파일 단위 삭제·교체가 가능해집니다.
        """
        idx = chunk.get("chunk_index", fallback)
        return f"{project_id}:{chunk.get('path', '?')}:{idx}"

    def add(self, project_id: str, chunks: list[dict], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        col = self._collection(project_id)
        col.upsert(          # ⚠ add 가 아니라 upsert — 재인덱싱 시 중복 방지
            ids=[self._chunk_id(project_id, c, i) for i, c in enumerate(chunks)],
            embeddings=vectors,
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "path": c["path"],
                    "type": c["type"],
                    "line_start": c.get("line_start") or 0,
                    "line_end": c.get("line_end") or 0,
                    "section": c.get("section") or "",
                    "chunk_index": c.get("chunk_index", 0),
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
        ids = res.get("ids", [[]])[0] or [""] * len(docs)
        for cid, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append({
                "_id": cid,          # BM25 결과와 합칠 때 쓰는 키
                "text": doc,
                "path": meta.get("path", ""),
                "type": meta.get("type", "code"),
                "line_start": meta.get("line_start") or None,
                "line_end": meta.get("line_end") or None,
                "section": meta.get("section") or None,
                "score": 1.0 - float(dist),      # ⚠ 거리 → 유사도
            })
        return out

    def delete_by_paths(self, project_id: str, paths: list[str]) -> int:
        """
        특정 파일들의 청크를 전부 삭제합니다. 증분 인덱싱의 핵심 연산입니다.

            git diff --name-only <old> HEAD  →  바뀐 파일 목록
                 ↓
            delete_by_paths(pid, 목록)       →  기존 청크 제거
                 ↓
            add(pid, 새 청크, 새 벡터)        →  교체 완료

        반환: 삭제 시도한 경로 수 (Chroma 가 실제 삭제 건수를 주지 않음)
        """
        if not paths:
            return 0
        col = self._collection(project_id)
        try:
            col.delete(where={"path": {"$in": list(paths)}})
        except Exception:
            # $in 미지원 버전 대비 — 경로별로 개별 삭제
            for p in paths:
                try:
                    col.delete(where={"path": p})
                except Exception:
                    pass
        return len(paths)

    def indexed_paths(self, project_id: str) -> set[str]:
        """현재 인덱싱된 파일 경로 집합. 삭제된 파일 감지에 씁니다."""
        col = self._collection(project_id)
        if col.count() == 0:
            return set()
        try:
            res = col.get(include=["metadatas"])
            return {m.get("path", "") for m in (res.get("metadatas") or []) if m.get("path")}
        except Exception:
            return set()

    def get_by_ids(self, project_id: str, ids: list[str]) -> dict[str, dict]:
        """
        ID 로 청크를 직접 가져옵니다.

        ⚠ BM25 가 찾았는데 벡터 상위에 없는 청크가 있을 수 있습니다.
           융합 결과에 넣으려면 그 청크의 내용을 꺼내야 합니다.
        """
        if not ids:
            return {}
        col = self._collection(project_id)
        try:
            res = col.get(ids=list(ids), include=["documents", "metadatas"])
        except Exception:
            return {}
        out: dict[str, dict] = {}
        got = res.get("ids") or []
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        for cid, doc, meta in zip(got, docs, metas):
            meta = meta or {}
            out[cid] = {
                "_id": cid,
                "text": doc,
                "path": meta.get("path", ""),
                "type": meta.get("type", "code"),
                "line_start": meta.get("line_start") or None,
                "line_end": meta.get("line_end") or None,
                "section": meta.get("section") or None,
                "score": 0.0,       # 벡터 점수 없음 — 융합 순위로만 사용
            }
        return out

    def all_chunks(self, project_id: str) -> list[dict]:
        """BM25 색인을 만들 때 씁니다. 전체를 메모리에 올립니다."""
        col = self._collection(project_id)
        if col.count() == 0:
            return []
        try:
            res = col.get(include=["documents", "metadatas"])
        except Exception:
            return []
        out = []
        for cid, doc, meta in zip(res.get("ids") or [],
                                  res.get("documents") or [],
                                  res.get("metadatas") or []):
            meta = meta or {}
            out.append({
                "_id": cid, "text": doc,
                "path": meta.get("path", ""),
                "section": meta.get("section") or None,
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
