from __future__ import annotations

import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from .. import indexer, lexical
from ..chunker import chunk_file
from ..config import CFG, normalize_fingerprint
from ..embedder import embed_many
from ..store import BUILD_PREFIX, PREV_SUFFIX, Store
from .checkpoint import CheckpointStore
from .errors import ResumeError
from .manifest import Manifest, build_manifest, compare


CompletionHook = Callable[[str, str, str | None], object]


class ResumableIndexer:
    """기존 인덱싱 부품을 조합하는 선택적 파일 단위 체크포인트 엔진."""

    def __init__(self, *, checkpoints: CheckpointStore | None = None,
                 store: Store | None = None,
                 embed_fn: Callable = embed_many,
                 manifest_fn: Callable = build_manifest,
                 batch_chunks: int = 64) -> None:
        self.checkpoints = checkpoints or CheckpointStore()
        self.store = store or Store()
        self.embed_fn = embed_fn
        self.manifest_fn = manifest_fn
        self.batch_chunks = max(1, int(batch_chunks))

    # ── 공개 진입점 ──────────────────────────────────────────

    def start_new(self, project_root: str, project_id: str, *,
                  blocking: bool = False, force: bool = False,
                  on_done: CompletionHook | None = None,
                  profile: Mapping | None = None,
                  profile_id: str | None = None,
                  profile_hash: str | None = None) -> dict:
        del force  # 신규 실행은 기존 체크포인트를 암묵적으로 폐기하지 않습니다.
        root = Path(project_root).resolve()
        if not root.is_dir():
            return {"accepted": False, "reason": "not_a_directory",
                    "path": str(root)}

        fp = normalize_fingerprint(profile) if profile is not None else CFG.fingerprint()
        if not fp:
            return {"accepted": False, "reason": "invalid_profile"}

        active = self.checkpoints.latest(project_id, active_only=True)
        if active:
            return {"accepted": False, "reason": "resumable_run_exists",
                    "project_id": project_id, "run_id": active["run_id"],
                    "state": active["status"]}

        build_name = BUILD_PREFIX + project_id
        if self.store.collection_info(build_name) is not None:
            return {"accepted": False, "reason": "legacy_incomplete",
                    "detail": "체크포인트 없는 building 컬렉션이 있어 자동 삭제하지 않습니다",
                    "project_id": project_id, "collection": build_name}

        # manifest 생성은 파일 읽기만 하며 Chroma/state를 변경하지 않습니다.
        manifest = self.manifest_fn(root, fp)
        run_id = "idx_" + uuid.uuid4().hex
        source_revision = indexer.git_head(root)
        try:
            self.checkpoints.create_run(
                run_id=run_id, project_id=project_id, manifest=manifest,
                build_collection=build_name, source_revision=source_revision,
                fingerprint=fp, profile_id=profile_id,
                profile_hash=profile_hash,
            )
            self.store.begin_build(
                project_id, fingerprint=fp, project_root=str(root),
                profile_id=profile_id, profile_hash=profile_hash,
                run_id=run_id, manifest_hash=manifest.digest,
                replace_existing=False,
            )
        except ResumeError as e:
            return {"accepted": False, "project_id": project_id, **e.as_dict()}
        except Exception as e:
            self.checkpoints.set_run(
                run_id, status="interrupted", error=f"{type(e).__name__}: {e}")
            return {"accepted": False, "reason": "build_create_failed",
                    "detail": f"{type(e).__name__}: {e}",
                    "project_id": project_id, "run_id": run_id}

        indexer.update_state(
            project_id, state="running", phase="embedding", processed=0,
            total=len(manifest.files), chunk_count=0, error=None,
            project_root=str(root), fingerprint=fp, profile_id=profile_id,
            profile_hash=profile_hash, resume_enabled=True,
            resume_run_id=run_id,
        )
        return self._dispatch(run_id, on_done=on_done, blocking=blocking)

    def resume(self, project_id: str, *, run_id: str | None = None,
               blocking: bool = False, force: bool = False,
               on_done: CompletionHook | None = None,
               expected_profile: Mapping | None = None) -> dict:
        run = (self.checkpoints.get_run(run_id) if run_id
               else self.checkpoints.latest(project_id, active_only=True))
        if not run or run.get("project_id") != project_id:
            return {"accepted": False, "reason": "checkpoint_not_found",
                    "project_id": project_id}
        if run.get("status") == "complete":
            return {"accepted": False, "reason": "already_complete",
                    "project_id": project_id, "run_id": run["run_id"],
                    "state": "complete"}
        try:
            run = self.checkpoints.claim(run["run_id"], force=force)
            if expected_profile is not None:
                expected = normalize_fingerprint(expected_profile)
                if expected != run["fingerprint"]:
                    raise ResumeError(
                        "profile_changed",
                        "요청한 프로필이 체크포인트 프로필과 다릅니다",
                        details={"stored_profile": run["fingerprint"],
                                 "requested_profile": expected},
                    )
            current = self.manifest_fn(run["project_root"], run["fingerprint"])
            compare(run["manifest_hash"], current)
        except ResumeError as e:
            return {"accepted": False, "project_id": project_id,
                    "run_id": run.get("run_id"), **e.as_dict()}

        indexer.update_state(
            project_id, state="running", phase=run["phase"],
            processed=run["completed_files"], total=run["total_files"],
            chunk_count=run["completed_chunks"], error=None,
            project_root=run["project_root"], fingerprint=run["fingerprint"],
            profile_id=run.get("profile_id"),
            profile_hash=run.get("profile_hash"), resume_enabled=True,
            resume_run_id=run["run_id"],
        )
        return self._dispatch(run["run_id"], on_done=on_done,
                              blocking=blocking)

    def restart(self, project_root: str, project_id: str, *,
                blocking: bool = False, force: bool = False,
                on_done: CompletionHook | None = None,
                profile: Mapping | None = None,
                profile_id: str | None = None,
                profile_hash: str | None = None) -> dict:
        active = self.checkpoints.latest(project_id, active_only=True)
        if active:
            try:
                self.checkpoints.claim(active["run_id"], force=force)
            except ResumeError as e:
                return {"accepted": False, "project_id": project_id,
                        "run_id": active["run_id"], **e.as_dict()}
            # promote 직후 죽어 target이 새 run이고 prev가 남은 경우에는 먼저
            # 기존 완성본으로 rollback한 뒤 새 run만 폐기합니다.
            target = self.store.collection_info(project_id)
            target_is_run = bool(
                target and (target.get("metadata") or {}).get("run_id") ==
                active["run_id"])
            if target_is_run:
                self.store.rollback_promote(project_id)
                backup = lexical.index_path(project_id).with_name(
                    lexical.index_path(project_id).name + ".resume-prev")
                if backup.exists():
                    backup.replace(lexical.index_path(project_id))

            info = self.store.collection_info(active["build_collection"])
            if info is not None:
                actual = (info.get("metadata") or {}).get("run_id")
                if actual != active["run_id"]:
                    return {"accepted": False, "reason": "run_id_mismatch",
                            "detail": "building 컬렉션이 다른 실행의 소유입니다",
                            "project_id": project_id}
                self.store.reset(active["build_collection"])
            staged = lexical.staging_path(project_id)
            if staged.exists():
                staged.unlink()
            self.checkpoints.discard(active["run_id"])
        elif self.store.collection_info(BUILD_PREFIX + project_id) is not None:
            return {"accepted": False, "reason": "legacy_incomplete",
                    "detail": "체크포인트 없는 building 컬렉션은 자동 삭제하지 않습니다",
                    "project_id": project_id}

        return self.start_new(
            project_root, project_id, blocking=blocking, on_done=on_done,
            profile=profile, profile_id=profile_id,
            profile_hash=profile_hash,
        )

    # ── 실행 ─────────────────────────────────────────────────

    def _dispatch(self, run_id: str, *, on_done: CompletionHook | None,
                  blocking: bool) -> dict:
        run = self.checkpoints.get_run(run_id) or {}
        if blocking:
            self._execute_guarded(run_id, on_done=on_done, raise_errors=True)
            final = self.checkpoints.get_run(run_id) or run
            return {"accepted": True, "project_id": final["project_id"],
                    "run_id": run_id, "state": final["status"],
                    "phase": final["phase"]}

        threading.Thread(
            target=self._execute_guarded,
            kwargs={"run_id": run_id, "on_done": on_done,
                    "raise_errors": False},
            daemon=True,
        ).start()
        return {"accepted": True, "project_id": run["project_id"],
                "run_id": run_id, "state": "running",
                "phase": run["phase"]}

    def _execute_guarded(self, run_id: str, *,
                         on_done: CompletionHook | None,
                         raise_errors: bool) -> None:
        try:
            self._execute(run_id, on_done=on_done)
        except BaseException as e:
            # 강제 종료(SIGKILL/전원 차단)는 이 블록도 실행되지 않지만 SQLite의
            # 마지막 heartbeat와 building 컬렉션이 다음 resume의 근거가 됩니다.
            try:
                self.checkpoints.set_run(
                    run_id, status="interrupted",
                    error=f"{type(e).__name__}: {e}")
                run = self.checkpoints.get_run(run_id) or {}
                indexer.update_state(
                    run.get("project_id", "unknown"), state="interrupted",
                    phase=run.get("phase"), processed=run.get("completed_files", 0),
                    total=run.get("total_files", 0),
                    chunk_count=run.get("completed_chunks", 0),
                    error=f"{type(e).__name__}: {e}",
                    resume_enabled=True, resume_run_id=run_id,
                )
            except Exception:
                pass
            if raise_errors:
                raise
            print(f"!! 재개형 인덱싱 중단: {type(e).__name__}: {e}")

    def _execute(self, run_id: str, *,
                 on_done: CompletionHook | None) -> None:
        run = self.checkpoints.get_run(run_id)
        if not run:
            raise ResumeError("run_not_found", "체크포인트가 없습니다")
        project_id = run["project_id"]

        if run["status"] == "complete":
            return
        if run["phase"] == "briefing":
            self._finish_briefing(run, on_done)
            return

        target = self.store.collection_info(project_id)
        build = self.store.collection_info(run["build_collection"])
        target_is_this_run = bool(
            target and (target.get("metadata") or {}).get("run_id") == run_id)
        if target_is_this_run and build is None:
            self._recover_promoted(run, on_done)
            return

        self.store.open_build(project_id, expected_run_id=run_id)
        self._process_pending_files(run)

        run = self.checkpoints.get_run(run_id) or run
        current = self.manifest_fn(run["project_root"], run["fingerprint"])
        compare(run["manifest_hash"], current)
        if run["completed_files"] != run["total_files"]:
            raise ResumeError("checkpoint_incomplete", "완료되지 않은 파일이 남았습니다")
        actual = self.store.count(run["build_collection"])
        if actual != run["completed_chunks"]:
            raise ResumeError(
                "checkpoint_store_mismatch",
                "체크포인트 청크 수와 building 컬렉션이 다릅니다",
                details={"checkpoint_chunks": run["completed_chunks"],
                         "building_chunks": actual},
            )
        self._finalize(run, on_done)

    def _process_pending_files(self, run: dict) -> None:
        run_id = run["run_id"]
        project_id = run["project_id"]
        root = Path(run["project_root"])
        fp = run["fingerprint"]
        build = run["build_collection"]

        # ledger가 앞서 있는 일은 정상 순서에서는 없지만, 저장소 손상을 조용히
        # 건너뛰지 않도록 완료 파일도 실제 경로 청크 수를 대조합니다.
        for row in self.checkpoints.files(run_id, status="completed"):
            actual = self.store.path_chunk_count(build, row["path"])
            if actual != row["chunk_count"]:
                raise ResumeError(
                    "completed_file_mismatch",
                    f"완료 체크포인트와 Chroma가 다릅니다: {row['path']}",
                    details={"expected_chunks": row["chunk_count"],
                             "actual_chunks": actual},
                )

        batch: list[tuple[dict, list[dict]]] = []
        batch_size = 0

        def flush() -> None:
            nonlocal batch, batch_size
            if not batch:
                return
            self.checkpoints.heartbeat(run_id)
            chunks = [chunk for _, file_chunks in batch for chunk in file_chunks]
            if chunks:
                vectors = self.embed_fn(
                    [c["text"] for c in chunks],
                    model=str(fp["embed_model"]),
                    expected_dim=int(fp["embed_dim"]),
                )
                self.store.add(build, chunks, vectors, id_prefix=project_id)

            committed: list[tuple[str, int]] = []
            for row, file_chunks in batch:
                actual = self.store.path_chunk_count(build, row["path"])
                if actual != len(file_chunks):
                    raise RuntimeError(
                        f"파일 청크 저장 검증 실패: {row['path']} "
                        f"expected={len(file_chunks)} actual={actual}")
                committed.append((row["path"], len(file_chunks)))
            totals = self.checkpoints.mark_files_complete(run_id, committed)
            indexer.update_state(
                project_id, state="running", phase="embedding",
                processed=totals["completed_files"], total=run["total_files"],
                chunk_count=totals["completed_chunks"], error=None,
                resume_enabled=True, resume_run_id=run_id,
            )
            batch = []
            batch_size = 0

        for row in self.checkpoints.files(run_id, status="pending"):
            path = root.joinpath(*row["path"].split("/"))
            # crash가 upsert와 checkpoint 사이에 났다면 이 경로만 다시 씁니다.
            self.store.delete_by_paths(build, [row["path"]])
            chunks = chunk_file(path, root, fp)
            batch.append((row, chunks))
            batch_size += len(chunks)
            if batch_size >= self.batch_chunks:
                flush()
        flush()

    # ── BM25 · 원자 승격 · 브리핑 ───────────────────────────

    def _prepare_bm25(self, run: dict, collection_name: str) -> int:
        project_id = run["project_id"]
        if not bool(run["fingerprint"]["use_bm25"]):
            staged = lexical.staging_path(project_id)
            if staged.exists():
                staged.unlink()
            return 0
        staged = lexical.staging_path(project_id)
        chunks = self.store.all_chunks(collection_name)
        idx = lexical.build(project_id, chunks, path=staged)
        if len(idx.doc_ids) != run["completed_chunks"]:
            raise RuntimeError(
                f"BM25 문서 수 불일치: bm25={len(idx.doc_ids)}, "
                f"chroma={run['completed_chunks']}")
        return len(idx.doc_ids)

    def _finalize(self, run: dict,
                  on_done: CompletionHook | None) -> None:
        run_id = run["run_id"]
        project_id = run["project_id"]
        self.checkpoints.set_run(run_id, phase="indexing_lexical")
        indexer.update_state(project_id, state="indexing_lexical",
                             phase="indexing_lexical")
        bm25_count = self._prepare_bm25(run, run["build_collection"])

        self.checkpoints.set_run(run_id, phase="promoting")
        indexer.update_state(project_id, state="promoting", phase="promoting")
        final_bm25 = lexical.index_path(project_id)
        backup = final_bm25.with_name(final_bm25.name + ".resume-prev")
        if backup.exists():
            backup.unlink()
        if final_bm25.exists():
            shutil.copy2(final_bm25, backup)

        promoted = False
        try:
            self.store.promote_resumable(project_id, expected_run_id=run_id)
            promoted = True
            staged = lexical.staging_path(project_id)
            if bool(run["fingerprint"]["use_bm25"]):
                final_bm25.parent.mkdir(parents=True, exist_ok=True)
                staged.replace(final_bm25)
            elif final_bm25.exists():
                final_bm25.unlink()
            self.store.finish_promote(project_id)
            promoted = False
            if backup.exists():
                backup.unlink()
        except Exception:
            if promoted:
                try:
                    self.store.rollback_promote(project_id)
                    if backup.exists():
                        backup.replace(final_bm25)
                    elif final_bm25.exists():
                        final_bm25.unlink()
                finally:
                    self.checkpoints.set_run(run_id, phase="indexing_lexical")
            raise

        self._mark_index_done(run, bm25_count=bm25_count)
        self._finish_briefing(self.checkpoints.get_run(run_id) or run, on_done)

    def _recover_promoted(self, run: dict,
                          on_done: CompletionHook | None) -> None:
        """승격 직후 프로세스가 죽은 경우 BM25/state/브리핑만 마칩니다."""
        project_id = run["project_id"]
        bm25_count = 0
        if bool(run["fingerprint"]["use_bm25"]):
            staged = lexical.staging_path(project_id)
            idx = lexical.BM25.load(staged)
            if idx is None or len(idx.doc_ids) != run["completed_chunks"]:
                bm25_count = self._prepare_bm25(run, project_id)
            else:
                bm25_count = len(idx.doc_ids)
            staged.replace(lexical.index_path(project_id))
        else:
            final = lexical.index_path(project_id)
            if final.exists():
                final.unlink()
        self.store.finish_promote(project_id)
        backup = lexical.index_path(project_id).with_name(
            lexical.index_path(project_id).name + ".resume-prev")
        if backup.exists():
            backup.unlink()
        self._mark_index_done(run, bm25_count=bm25_count)
        self._finish_briefing(self.checkpoints.get_run(run["run_id"]) or run,
                              on_done)

    def _mark_index_done(self, run: dict, *, bm25_count: int) -> None:
        elapsed = round(time.time() - float(run["started_at"]), 1)
        indexer.update_state(
            run["project_id"], state="done", phase="briefing",
            processed=run["total_files"], total=run["total_files"],
            chunk_count=run["completed_chunks"],
            commit=run.get("source_revision"),
            dirty=indexer.git_dirty(run["project_root"]),
            project_root=run["project_root"], fingerprint=run["fingerprint"],
            profile_id=run.get("profile_id"),
            profile_hash=run.get("profile_hash"),
            bm25_count=(bm25_count if run["fingerprint"]["use_bm25"] else None),
            indexed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            elapsed_s=elapsed, error=None, resume_enabled=True,
            resume_run_id=run["run_id"],
        )
        self.checkpoints.set_run(run["run_id"], phase="briefing")

    def _finish_briefing(self, run: dict,
                         on_done: CompletionHook | None) -> None:
        indexer.run_completion_hook(
            run["project_id"], run["project_root"],
            run.get("source_revision"), on_done,
        )
        self.checkpoints.set_run(run["run_id"], status="complete",
                                 phase="complete", error=None)


def resume_status(project_id: str, *, db_path: str | Path | None = None) -> dict:
    return CheckpointStore(db_path).summary(project_id)
