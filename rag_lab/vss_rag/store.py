"""
벡터 저장소 — Chroma.

⚠ 저장소를 바꿔도(SQLite / Qdrant) 임계값은 유효합니다.
   점수 분포를 결정하는 건 임베딩 모델과 거리 함수이지 저장 위치가 아닙니다.
   그래서 이 파일 하나만 갈아끼우면 됩니다.

⚠ Chroma는 cosine "거리"를 돌려줍니다.  similarity = 1 - distance
   D9 임계값(0.53~0.55)은 similarity 기준이므로 반드시 변환해야 합니다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .config import CFG, normalize_fingerprint

# ── 미완성 인덱스 표시 규약 ──────────────────────────────────
#
# ⚠ 이 두 접두어/접미어가 **인덱스 상태의 정본**입니다.
#    state.json 이 통째로 날아가도 컬렉션 이름만 보고 판정할 수 있어야 합니다.
#
#      building-<pid>   인덱싱 중이거나 중단됨. 조회 대상이 아님
#      <pid>-prev       교체 도중. 직전 인덱스의 백업
#      <pid>            완성된 인덱스. 이것만 조회됨
#
# ⚠ Chroma 이름 규칙상 ASCII 영숫자로 시작해야 해서 `__building__` 은 쓸 수 없습니다.
#    이름 길이 상한이 63자이므로 project_id 는 최대 54자입니다.
BUILD_PREFIX = "building-"
PREV_SUFFIX = "-prev"
MAX_PROJECT_ID = 63 - len(BUILD_PREFIX)


def is_internal(name: str) -> bool:
    """조회 대상이 아닌 내부 컬렉션인가."""
    return name.startswith(BUILD_PREFIX) or name.endswith(PREV_SUFFIX)


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
        """컬렉션 삭제.

        ⚠ 전체 인덱싱에서는 쓰지 마세요. `begin_build()` → `promote()` 를 씁니다.
           선삭제 후 임베딩이 실패하면 인덱스가 반쪽으로 남습니다 (2026-08 사고).
        """
        try:
            self._client.delete_collection(project_id)
        except Exception:
            pass   # 없으면 그만

    # ── 원자적 교체 ──────────────────────────────────────────

    def begin_build(self, project_id: str, *, fingerprint: dict | None = None,
                    project_root: str | None = None,
                    profile_id: str | None = None,
                    profile_hash: str | None = None,
                    run_id: str | None = None,
                    manifest_hash: str | None = None,
                    replace_existing: bool = True) -> str:
        """임시 컬렉션을 만들고 그 이름을 돌려줍니다.

        인덱싱은 여기에 쌓고, 끝나면 `promote()` 로 교체합니다.
        도중에 죽으면 `building-<pid>` 가 남아 **이름만으로 중단이 드러납니다.**
        """
        if len(project_id) > MAX_PROJECT_ID:
            raise ValueError(
                f"project_id 가 {MAX_PROJECT_ID}자를 넘습니다: {len(project_id)}자"
            )
        name = BUILD_PREFIX + project_id
        if replace_existing:
            self.reset(name)                  # 기존 엔진 호환: 이전 시도 잔재 제거
        elif self.collection_info(name) is not None:
            raise RuntimeError(
                f"기존 building 컬렉션을 덮어쓰지 않습니다: {name}")
        meta = {
            "hnsw:space": "cosine",           # ⚠ D9 전제
            "status": "building",
            "target": project_id,
            "started_at": time.time(),
        }
        if project_root:
            meta["project_root"] = str(project_root)
        if fingerprint:
            # ⚠ Chroma metadata 는 스칼라만 받습니다. dict 는 JSON 문자열로.
            meta["fingerprint"] = json.dumps(fingerprint, ensure_ascii=False)
        if profile_id:
            meta["profile_id"] = profile_id
        if profile_hash:
            meta["profile_hash"] = profile_hash
        if run_id:
            meta["run_id"] = run_id
            meta["resumable"] = True
        if manifest_hash:
            meta["manifest_hash"] = manifest_hash
        self._client.create_collection(name=name, metadata=meta)
        return name

    def collection_info(self, name: str) -> dict | None:
        """컬렉션을 생성하지 않고 이름·청크 수·metadata를 조회합니다."""
        try:
            col = self._client.get_collection(name)
            return {"name": name, "chunks": col.count(),
                    "metadata": dict(col.metadata or {})}
        except Exception:
            return None

    def open_build(self, project_id: str, *, expected_run_id: str) -> str:
        """체크포인트와 일치하는 기존 building 컬렉션만 엽니다."""
        name = BUILD_PREFIX + project_id
        info = self.collection_info(name)
        if info is None:
            raise RuntimeError(f"재개할 임시 컬렉션이 없습니다: {name}")
        meta = info["metadata"]
        if meta.get("status") != "building" or meta.get("target") != project_id:
            raise RuntimeError(f"임시 컬렉션 metadata가 올바르지 않습니다: {name}")
        if meta.get("run_id") != expected_run_id:
            raise RuntimeError(
                f"run_id가 다른 임시 컬렉션입니다: expected={expected_run_id}, "
                f"actual={meta.get('run_id')}")
        return name

    def path_chunk_count(self, collection_name: str, path: str) -> int:
        """파일 체크포인트 확정 전에 해당 경로의 실제 청크 수를 셉니다."""
        col = self._client.get_collection(collection_name)
        try:
            row = col.get(where={"path": path}, include=[])
            return len(row.get("ids") or [])
        except Exception:
            return 0

    def promote_resumable(self, project_id: str, *, expected_run_id: str) -> None:
        """중단 후 다시 호출해도 이어갈 수 있는 promote 1·2단계입니다.

        ``<pid>-prev``는 외부 BM25 커밋이 끝날 때까지 보존하며,
        최종 정리는 기존 ``finish_promote()``가 담당합니다.
        """
        build = BUILD_PREFIX + project_id
        prev = project_id + PREV_SUFFIX
        names = {c.name for c in self._client.list_collections()}

        # 이미 2단계까지 끝난 뒤 프로세스만 죽은 경우입니다.
        if build not in names and project_id in names:
            info = self.collection_info(project_id) or {}
            if (info.get("metadata") or {}).get("run_id") != expected_run_id:
                raise RuntimeError("완성 이름에 다른 run_id 컬렉션이 있습니다")
        else:
            if build not in names:
                raise RuntimeError(f"승격할 임시 컬렉션이 없습니다: {build}")
            build_info = self.collection_info(build) or {}
            if (build_info.get("metadata") or {}).get("run_id") != expected_run_id:
                raise RuntimeError("승격 대상 building 컬렉션의 run_id가 다릅니다")

            if project_id in names and prev not in names:
                self._client.get_collection(project_id).modify(name=prev)
            names = {c.name for c in self._client.list_collections()}
            if project_id not in names:
                self._client.get_collection(build).modify(name=project_id)

        col = self._client.get_collection(project_id)
        meta = dict(col.metadata or {})
        if meta.get("run_id") != expected_run_id:
            raise RuntimeError("승격 후 target run_id 검증에 실패했습니다")
        meta.pop("hnsw:space", None)
        meta.update({"status": "ready", "promoted_at": time.time()})
        col.modify(metadata=meta)

    def promote(self, project_id: str, *, keep_previous: bool = False) -> None:
        """`building-<pid>` 를 `<pid>` 로 승격합니다. 3단계라 중간에 죽어도 복구 가능합니다.

            ① <pid>          → <pid>-prev      (기존 것 보존)
            ② building-<pid> → <pid>           (새 것 승격)
            ③ <pid>-prev 삭제

        어느 단계에서 죽든 데이터가 최소 한 벌은 남고, **이름만 보고 판정**됩니다.
        """
        build = BUILD_PREFIX + project_id
        prev = project_id + PREV_SUFFIX
        names = {c.name for c in self._client.list_collections()}

        if build not in names:
            raise RuntimeError(f"승격할 임시 컬렉션이 없습니다: {build}")

        self.reset(prev)                      # 지난 교체의 잔재
        if project_id in names:               # ①
            self._client.get_collection(project_id).modify(name=prev)
        self._client.get_collection(build).modify(name=project_id)      # ②
        try:                                                            # ③
            col = self._client.get_collection(project_id)
            meta = dict(col.metadata or {})
            # ⚠ hnsw:space 를 넣으면 Chroma 가 거부합니다.
            #    "Changing the distance function of a collection once it is
            #     created is not supported" — 생성 시점에 이미 cosine 으로 고정돼
            #    있으므로 빼고 갱신해도 거리 함수는 그대로입니다 (D9 유지).
            meta.pop("hnsw:space", None)
            meta.update({"status": "ready", "promoted_at": time.time()})
            col.modify(metadata=meta)
        except Exception as e:
            # ⚠ 조용히 넘기지 않습니다. 이전 구현이 pass 로 삼켜서
            #    status 가 building 인 채로 남는 걸 아무도 몰랐습니다.
            print(f"!! 컬렉션 metadata 갱신 실패 ({type(e).__name__}: {e}) "
                  f"— 인덱스 자체는 정상입니다.")
        if not keep_previous:
            self.reset(prev)

    def finish_promote(self, project_id: str) -> None:
        """외부 부수 파일까지 커밋된 뒤 직전 컬렉션 백업을 제거합니다."""
        self.reset(project_id + PREV_SUFFIX)

    def rollback_promote(self, project_id: str) -> None:
        """승격 후 부수 파일 커밋이 실패하면 새 컬렉션을 증거로 남기고 이전 것을 복원합니다."""
        build = BUILD_PREFIX + project_id
        prev = project_id + PREV_SUFFIX
        names = {c.name for c in self._client.list_collections()}
        if build in names:
            raise RuntimeError(f"rollback 대상 이름이 이미 존재합니다: {build}")
        if project_id in names:
            self._client.get_collection(project_id).modify(name=build)
        names = {c.name for c in self._client.list_collections()}
        if prev in names:
            self._client.get_collection(prev).modify(name=project_id)

    def incomplete(self) -> list[dict]:
        """미완성 컬렉션 목록. 정상이면 빈 리스트입니다."""
        out = []
        for c in self._client.list_collections():
            if not is_internal(c.name):
                continue
            meta = c.metadata or {}
            started = meta.get("started_at")
            out.append({
                "name": c.name,
                "kind": "building" if c.name.startswith(BUILD_PREFIX) else "prev",
                "target": meta.get("target") or c.name.removesuffix(PREV_SUFFIX),
                "chunks": c.count(),
                "started_at": started,
                "age_s": round(time.time() - started, 1) if started else None,
            })
        return out

    def cleanup_incomplete(self, min_age_s: float = 0.0) -> list[str]:
        """미완성 컬렉션을 지웁니다.

        ⚠ 자동 호출하지 마세요. 다른 프로세스(cli.py)가 인덱싱 중일 수 있습니다.
           서버 기동 시에는 **경고만** 하고, 삭제는 명시적 명령으로만 합니다.
        """
        removed = []
        for item in self.incomplete():
            if item["age_s"] is not None and item["age_s"] < min_age_s:
                continue
            self.reset(item["name"])
            removed.append(item["name"])
        return removed

    # ────────────────────────────────────────────────────────

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

    def add(self, project_id: str, chunks: list[dict], vectors: list[list[float]],
            id_prefix: str | None = None) -> None:
        """청크 저장.

        ⚠ `id_prefix` 는 임시 컬렉션(`building-<pid>`)에 쌓을 때 씁니다.
           컬렉션 이름은 임시여도 **청크 ID 는 최종 project_id 기준**이어야
           승격 후 ID 체계가 일관됩니다.
        """
        if not chunks:
            return
        col = self._collection(project_id)
        pfx = id_prefix or project_id
        col.upsert(          # ⚠ add 가 아니라 upsert — 재인덱싱 시 중복 방지
            ids=[self._chunk_id(pfx, c, i) for i, c in enumerate(chunks)],
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
            meta = meta or {}
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

    def snapshot_by_paths(self, project_id: str, paths: list[str]) -> dict:
        """파일 단위 갱신 전 rollback용 원본 청크를 메모리에 보관합니다.

        문서·metadata뿐 아니라 기존 embedding도 함께 읽습니다. 원격 payload
        증분 갱신이 저장 또는 BM25 단계에서 실패하면 재임베딩 없이 직전 상태를
        복원하는 용도이며, 영속적인 백업 파일을 만들지는 않습니다.
        """
        unique = list(dict.fromkeys(paths))
        empty = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
        if not unique:
            return empty

        col = self._collection(project_id)
        rows: list[dict] = []
        try:
            rows.append(col.get(
                where={"path": {"$in": unique}},
                include=["documents", "metadatas", "embeddings"],
            ))
        except Exception:
            # 구 Chroma의 $in 미지원에 대비합니다.
            for path in unique:
                try:
                    rows.append(col.get(
                        where={"path": path},
                        include=["documents", "metadatas", "embeddings"],
                    ))
                except Exception:
                    continue

        out = {k: [] for k in empty}
        seen: set[str] = set()
        for row in rows:
            ids = row.get("ids") or []
            docs = row.get("documents") or []
            metas = row.get("metadatas") or []
            embeddings = row.get("embeddings")
            if embeddings is None:
                embeddings = []
            for cid, doc, meta, vec in zip(ids, docs, metas, embeddings):
                if cid in seen:
                    continue
                seen.add(cid)
                out["ids"].append(cid)
                out["documents"].append(doc)
                out["metadatas"].append(meta or {})
                out["embeddings"].append(vec)
        return out

    def restore_snapshot(self, project_id: str, snapshot: dict) -> None:
        """``snapshot_by_paths()`` 결과를 같은 ID와 벡터로 복원합니다."""
        ids = list(snapshot.get("ids") or [])
        if not ids:
            return
        col = self._collection(project_id)
        batch_size = 256
        for i in range(0, len(ids), batch_size):
            sl = slice(i, i + batch_size)
            col.upsert(
                ids=ids[sl],
                documents=list(snapshot["documents"])[sl],
                metadatas=list(snapshot["metadatas"])[sl],
                embeddings=list(snapshot["embeddings"])[sl],
            )

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

    def index_fingerprint(self, project_id: str) -> dict | None:
        """**인덱스 자신이** 들고 있는 파라미터 지문. 없으면 None.

        ⚠ `CFG.fingerprint()` 와 헷갈리지 마세요.
           CFG 는 "지금 이 프로세스의 환경변수"이고, 이건 "그 인덱스를 만들 때
           실제로 쓴 값"입니다. 둘은 얼마든지 어긋날 수 있습니다.

           2026-08-10 baseline run 이 `context_header=true` 로 기록됐지만
           실제 인덱스는 `false` 였던 사고가 여기서 나왔습니다.
           측정 기록에는 **반드시 이 값**을 쓰세요.
        """
        # ⚠ `_collection()` 을 쓰지 않습니다. get_or_create 라서
        #    없는 이름으로 부르면 빈 컬렉션이 생깁니다.
        meta = None
        try:
            for c in self._client.list_collections():
                if c.name == project_id:
                    meta = dict(c.metadata or {})
                    break
        except Exception:
            return None
        if meta is None:
            return None
        raw = meta.get("fingerprint")
        if not raw:
            return None
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else dict(raw)
            return normalize_fingerprint(parsed)
        except Exception:
            return None

    def set_index_fingerprint(self, project_id: str, fingerprint: dict) -> None:
        """기존 컬렉션의 인덱스 지문만 갱신합니다.

        증분 갱신이 구 fingerprint를 현재 스키마로 보완한 뒤 저장할 때 사용합니다.
        거리 함수는 Chroma에서 변경할 수 없으므로 metadata 갱신 payload에서 뺍니다.
        """
        col = self._client.get_collection(project_id)
        meta = dict(col.metadata or {})
        meta.pop("hnsw:space", None)
        meta["fingerprint"] = json.dumps(
            normalize_fingerprint(fingerprint), ensure_ascii=False)
        col.modify(metadata=meta)

    def raw_collections(self) -> list[dict]:
        """모든 컬렉션의 이름·청크수·metadata. **아무것도 생성하지 않습니다.**

        ⚠ 진단 전용입니다. `projects()` 와 달리 내부 컬렉션도 전부 포함합니다.
           `_collection()` 을 거치지 않으므로 없는 이름을 만들 위험이 없습니다.
        """
        try:
            return [{"name": c.name,
                     "chunks": c.count(),
                     "metadata": dict(c.metadata or {})}
                    for c in self._client.list_collections()]
        except Exception:
            return []

    def projects(self) -> list[str]:
        """조회 가능한 프로젝트 목록.

        ⚠ 미완성 컬렉션(`building-*` · `*-prev`)은 제외합니다.
           반쪽 인덱스가 정상인 척 노출되던 것이 2026-08 사고의 원인이었습니다.
           미완성 목록이 필요하면 `incomplete()` 를 쓰세요.
        """
        try:
            return [c.name for c in self._client.list_collections()
                    if not is_internal(c.name)]
        except Exception:
            return []
