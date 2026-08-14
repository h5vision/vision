"""Frontend가 전달한 변경 파일 전체 문자열 기반 증분 인덱싱.

로컬 Git과 작업 트리를 읽는 기존 ``incremental.py`` 경로와 분리합니다.
이 경로의 정본은 ``base_revision``/``target_revision``과 각 파일의 최종
문자열입니다. ``content_sha256``이 오면 전송 내용을 검증하고, 생략되면
백엔드가 계산합니다. diff hunk 자체는 인덱싱 입력으로 사용하지 않습니다.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping

from . import lexical
from .chunker import chunk_text, classify
from .config import (SKIP_DIRS, SKIP_FILE_PATTERNS, is_excluded,
                     normalize_fingerprint, profile_value)
from .embedder import embed_many
from .incremental import FULL_REINDEX_RATIO
from .store import Store

_SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_STATUSES = {"added", "modified", "renamed"}
_ENCODINGS = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "utf-8-sig": "utf-8-sig",
    "utf8-sig": "utf-8-sig",
    "cp949": "cp949",
    "euc-kr": "cp949",
    "latin-1": "latin-1",
    "latin1": "latin-1",
    "iso-8859-1": "latin-1",
}


class PayloadUpdateError(ValueError):
    """요청 계약 또는 현재 인덱스 revision이 맞지 않을 때 발생합니다."""

    def __init__(self, code: str, detail: str, *, conflict: bool = False):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.conflict = conflict

    def as_dict(self) -> dict:
        return {"ok": False, "reason": self.code, "detail": self.detail,
                "conflict": self.conflict}


class PayloadApplyError(RuntimeError):
    """갱신 실행 실패와 직전 인덱스 복구 성공 여부를 함께 전달합니다."""

    def __init__(self, detail: str, *, rollback_ok: bool):
        super().__init__(detail)
        self.rollback_ok = rollback_ok


def _revision(value, field: str) -> str:
    if not isinstance(value, str) or not _SHA1.fullmatch(value):
        raise PayloadUpdateError(
            "invalid_revision", f"{field}는 40자리 Git SHA여야 합니다")
    return value.lower()


def _path(value, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise PayloadUpdateError("invalid_path", f"{field}가 비어 있거나 너무 깁니다")
    if "\x00" in value or "\\" in value or value.startswith(("/", "//")) \
            or _DRIVE.match(value):
        raise PayloadUpdateError(
            "invalid_path", f"{field}는 프로젝트 상대 POSIX 경로여야 합니다: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PayloadUpdateError(
            "invalid_path", f"{field}에 빈 구간, '.' 또는 '..'를 쓸 수 없습니다: {value!r}")
    normalized = PurePosixPath(value).as_posix()
    if normalized != value:
        raise PayloadUpdateError("invalid_path", f"정규화되지 않은 경로입니다: {value!r}")
    return normalized


def _encoding(value) -> str:
    if value is None:
        return "utf-8"
    if not isinstance(value, str):
        raise PayloadUpdateError("invalid_encoding", "encoding은 문자열이어야 합니다")
    enc = _ENCODINGS.get(value.strip().lower().replace("_", "-"))
    if not enc:
        raise PayloadUpdateError(
            "unsupported_encoding",
            "지원 encoding은 utf-8, utf-8-sig, cp949, latin-1입니다")
    return enc


def _optional_text(value, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise PayloadUpdateError(
            "invalid_payload", f"{field}는 1~512자의 문자열이어야 합니다")
    return value.strip()


def _indexable(path: str, size_bytes: int, profile: Mapping) -> bool:
    parts = path.split("/")
    if any(part in SKIP_DIRS for part in parts):
        return False
    if PurePosixPath(path).name in SKIP_FILE_PATTERNS:
        return False
    if is_excluded(path, str(profile_value(profile, "exclude_globs"))):
        return False
    if classify(Path(path)) is None:
        return False
    return size_bytes <= int(profile_value(profile, "max_file_bytes"))


def prepare(payload: dict, state: dict, store: Store) -> dict:
    """payload 전체를 검증하고 실행 가능한 불변 plan으로 바꿉니다."""
    if not isinstance(payload, dict):
        raise PayloadUpdateError("invalid_payload", "JSON object가 필요합니다")

    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise PayloadUpdateError("project_id_required", "project_id가 필요합니다")
    project_id = project_id.strip()

    base = _revision(payload.get("base_revision"), "base_revision")
    target = _revision(payload.get("target_revision"), "target_revision")

    if state.get("state") != "done":
        raise PayloadUpdateError(
            "not_indexed", "완료된 인덱스가 없습니다. 전체 인덱싱이 필요합니다",
            conflict=True)
    if project_id not in set(store.projects()):
        raise PayloadUpdateError(
            "index_missing", "state는 있지만 완성된 Chroma 컬렉션이 없습니다",
            conflict=True)

    current = state.get("commit")
    if not isinstance(current, str) or not _SHA1.fullmatch(current):
        raise PayloadUpdateError(
            "revision_unknown", "현재 인덱스의 40자리 revision을 확인할 수 없습니다",
            conflict=True)
    current = current.lower()

    if target == current:
        return {"already_applied": True, "project_id": project_id,
                "base_revision": base, "target_revision": target}
    if base != current:
        raise PayloadUpdateError(
            "base_revision_mismatch",
            f"현재 인덱스 revision={current}, 요청 base_revision={base}",
            conflict=True)

    profile = normalize_fingerprint(
        store.index_fingerprint(project_id) or state.get("fingerprint"))
    if not profile:
        raise PayloadUpdateError(
            "fingerprint_unknown",
            "인덱스 설정 지문이 없어 안전한 증분 갱신을 할 수 없습니다",
            conflict=True)

    raw_files = payload.get("files", [])
    raw_deleted = payload.get("deleted_paths", [])
    raw_renames = payload.get("renames", [])
    if not isinstance(raw_files, list) or not isinstance(raw_deleted, list) \
            or not isinstance(raw_renames, list):
        raise PayloadUpdateError(
            "invalid_payload", "files, deleted_paths, renames는 배열이어야 합니다")

    files: list[dict] = []
    file_paths: set[str] = set()
    for i, item in enumerate(raw_files):
        if not isinstance(item, dict):
            raise PayloadUpdateError("invalid_file", f"files[{i}]는 object여야 합니다")
        status = str(item.get("status") or "").strip().lower()
        if status not in _STATUSES:
            raise PayloadUpdateError(
                "invalid_status",
                f"files[{i}].status는 added|modified|renamed 중 하나여야 합니다")
        path = _path(item.get("path"), f"files[{i}].path")
        if path in file_paths:
            raise PayloadUpdateError("duplicate_path", f"중복 파일 경로입니다: {path}")
        content = item.get("content")
        if not isinstance(content, str):
            raise PayloadUpdateError(
                "invalid_content", f"files[{i}].content는 파일 전체 문자열이어야 합니다")
        encoding = _encoding(item.get("encoding"))
        try:
            raw = content.encode(encoding)
        except UnicodeEncodeError as e:
            raise PayloadUpdateError(
                "encoding_mismatch", f"{path}: {encoding}으로 인코딩할 수 없습니다: {e}") from e
        expected = item.get("content_sha256")
        if expected is not None and (
                not isinstance(expected, str) or not _SHA256.fullmatch(expected)):
            raise PayloadUpdateError(
                "invalid_content_sha256",
                f"{path}: content_sha256은 생략하거나 64자리 SHA-256이어야 합니다")
        actual = hashlib.sha256(raw).hexdigest()
        if expected is not None and actual != expected.lower():
            raise PayloadUpdateError(
                "content_sha256_mismatch",
                f"{path}: expected={expected.lower()}, actual={actual}", conflict=True)
        supplied_size = item.get("size_bytes")
        if supplied_size is not None and supplied_size != len(raw):
            raise PayloadUpdateError(
                "size_mismatch",
                f"{path}: size_bytes={supplied_size}, actual={len(raw)}", conflict=True)

        file_paths.add(path)
        files.append({
            "status": status, "path": path, "content": content,
            "encoding": encoding, "content_sha256": actual,
            "size_bytes": len(raw),
            "indexable": (
                "\x00" not in content[:4096]
                and _indexable(path, len(raw), profile)
            ),
        })

    deleted: list[str] = []
    for i, value in enumerate(raw_deleted):
        deleted.append(_path(value, f"deleted_paths[{i}]"))
    if len(set(deleted)) != len(deleted):
        raise PayloadUpdateError("duplicate_path", "deleted_paths에 중복 경로가 있습니다")

    renames: list[dict] = []
    rename_old: set[str] = set()
    rename_new: set[str] = set()
    for i, item in enumerate(raw_renames):
        if not isinstance(item, dict):
            raise PayloadUpdateError("invalid_rename", f"renames[{i}]는 object여야 합니다")
        old_path = _path(item.get("old_path"), f"renames[{i}].old_path")
        new_path = _path(item.get("new_path"), f"renames[{i}].new_path")
        if old_path == new_path or old_path in rename_old or new_path in rename_new:
            raise PayloadUpdateError("invalid_rename", f"중복되거나 동일한 rename입니다: {item}")
        if new_path not in file_paths:
            raise PayloadUpdateError(
                "rename_content_required",
                f"rename 대상 {new_path}의 최종 전체 content를 files에 넣어야 합니다")
        rename_old.add(old_path)
        rename_new.add(new_path)
        renames.append({"old_path": old_path, "new_path": new_path})

    deleted_set = set(deleted)
    if deleted_set & file_paths:
        both = sorted(deleted_set & file_paths)
        raise PayloadUpdateError(
            "path_conflict", f"삭제와 추가/수정에 동시에 들어간 경로입니다: {both}")

    indexed_paths = store.indexed_paths(project_id)
    total_paths = len(indexed_paths)
    indexable_files = [f for f in files if f["indexable"]]
    to_clear_set = file_paths | deleted_set | rename_old
    new_indexable = {
        f["path"] for f in indexable_files if f["path"] not in indexed_paths
    }
    changed_count = len(to_clear_set & indexed_paths) + len(new_indexable)
    ratio = (changed_count / total_paths) if total_paths else 1.0
    if changed_count and ratio > FULL_REINDEX_RATIO:
        raise PayloadUpdateError(
            "too_many_changes",
            f"인덱스 영향 파일이 {changed_count}/{total_paths}개입니다. "
            "전체 인덱싱이 필요합니다",
            conflict=True)

    to_clear = sorted(to_clear_set)
    return {
        "already_applied": False,
        "project_id": project_id,
        "base_revision": base,
        "target_revision": target,
        "snapshot_id": _optional_text(payload.get("snapshot_id"), "snapshot_id"),
        "branch": _optional_text(payload.get("branch"), "branch"),
        "files": files,
        "indexable_files": indexable_files,
        "ignored_paths": [f["path"] for f in files if not f["indexable"]],
        "deleted_paths": deleted,
        "renames": renames,
        "to_clear": to_clear,
        "fingerprint": profile,
        "total_paths": total_paths,
    }


def apply(plan: dict, store: Store,
          on_progress: Callable[[int, int], None] | None = None) -> dict:
    """검증된 plan을 파일 단위로 교체하고 실패 시 기존 청크를 복원합니다."""
    t0 = time.perf_counter()
    project_id = plan["project_id"]
    profile = plan["fingerprint"]
    files = plan["indexable_files"]

    new_chunks: list[dict] = []
    for i, file in enumerate(files, start=1):
        new_chunks.extend(chunk_text(file["content"], file["path"], profile))
        if on_progress:
            on_progress(i, len(files))

    pending: list[tuple[list[dict], list[list[float]]]] = []
    batch_size = 64
    for i in range(0, len(new_chunks), batch_size):
        batch = new_chunks[i:i + batch_size]
        vectors = embed_many(
            [chunk["text"] for chunk in batch],
            model=str(profile["embed_model"]),
            expected_dim=int(profile["embed_dim"]),
        )
        pending.append((batch, vectors))

    # 원격 임베딩이 전부 성공한 뒤에만 기존 인덱스를 건드립니다.
    before = store.snapshot_by_paths(project_id, plan["to_clear"])
    staged_bm25 = lexical.staging_path(project_id)
    final_bm25 = lexical.index_path(project_id)
    bm25_backup = final_bm25.with_name(final_bm25.name + ".payload-prev")
    bm25_committed = False
    keep_bm25_backup = False

    try:
        store.delete_by_paths(project_id, plan["to_clear"])
        remaining = store.snapshot_by_paths(project_id, plan["to_clear"])
        if remaining["ids"]:
            raise RuntimeError(
                f"기존 청크 삭제 불완전: {len(remaining['ids'])}개가 남았습니다")

        chunks_added = 0
        for batch, vectors in pending:
            store.add(project_id, batch, vectors)
            chunks_added += len(batch)

        replaced = store.snapshot_by_paths(project_id, plan["to_clear"])
        if len(replaced["ids"]) != len(new_chunks):
            raise RuntimeError(
                f"교체 청크 수 불일치: expected={len(new_chunks)}, "
                f"actual={len(replaced['ids'])}")

        if bool(profile["use_bm25"]):
            expected_bm25 = store.count(project_id)
            idx = lexical.build(
                project_id,
                store.iter_chunks(project_id),
                path=staged_bm25,
                expected_count=expected_bm25,
            )
            if len(idx.doc_ids) != expected_bm25:
                raise RuntimeError(
                    f"BM25 문서 수 불일치: bm25={len(idx.doc_ids)}, "
                    f"chroma={expected_bm25}")
            if bm25_backup.exists():
                bm25_backup.unlink()
            if final_bm25.exists():
                shutil.copy2(final_bm25, bm25_backup)
            staged_bm25.replace(final_bm25)
            bm25_committed = True

        store.set_index_fingerprint(project_id, profile)
    except Exception as original:
        # 새/부분 저장분을 지우고 직전 ID·원문·metadata·embedding을 그대로 복원합니다.
        # BM25와 Chroma 중 한쪽 복구가 실패해도 다른 쪽 복구는 반드시 시도합니다.
        rollback_errors: list[str] = []
        try:
            if staged_bm25.exists():
                staged_bm25.unlink()
            if bm25_committed:
                if bm25_backup.exists():
                    bm25_backup.replace(final_bm25)
                elif final_bm25.exists():
                    final_bm25.unlink()
        except Exception as e:
            keep_bm25_backup = True
            rollback_errors.append(f"BM25 rollback: {type(e).__name__}: {e}")

        try:
            store.delete_by_paths(project_id, plan["to_clear"])
            store.restore_snapshot(project_id, before)
            restored = store.snapshot_by_paths(project_id, plan["to_clear"])
            if len(restored["ids"]) != len(before["ids"]):
                raise RuntimeError(
                    f"복원 청크 수 불일치: expected={len(before['ids'])}, "
                    f"actual={len(restored['ids'])}")
        except Exception as e:
            rollback_errors.append(f"Chroma rollback: {type(e).__name__}: {e}")

        detail = f"{type(original).__name__}: {original}"
        if rollback_errors:
            detail += "; " + "; ".join(rollback_errors)
        raise PayloadApplyError(
            detail, rollback_ok=not rollback_errors) from original
    finally:
        # BM25 rollback 자체가 실패했다면 수동 복구용 직전 파일을 보존합니다.
        if bm25_backup.exists() and not keep_bm25_backup:
            bm25_backup.unlink()

    return {
        "ok": True,
        "mode": "payload_incremental",
        "old_commit": plan["base_revision"],
        "new_commit": plan["target_revision"],
        "snapshot_id": plan.get("snapshot_id"),
        "branch": plan.get("branch"),
        "files_received": len(plan["files"]),
        "files_indexed": len(files),
        "files_deleted": len(plan["deleted_paths"]),
        "files_renamed": len(plan["renames"]),
        "ignored_paths": plan["ignored_paths"],
        "paths_cleared": len(plan["to_clear"]),
        "chunks_added": sum(len(batch) for batch, _ in pending),
        "chunk_count": store.count(project_id),
        "elapsed_s": round(time.perf_counter() - t0, 1),
        "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fingerprint": profile,
    }
