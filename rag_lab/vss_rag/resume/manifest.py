from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..chunker import collect_files


@dataclass(frozen=True)
class ManifestFile:
    path: str
    absolute_path: Path
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class Manifest:
    root: Path
    files: tuple[ManifestFile, ...]
    digest: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def build_manifest(project_root: str | Path,
                   profile: Mapping | None = None) -> Manifest:
    """인덱싱 대상과 내용을 고정하는 manifest를 만듭니다."""
    root = Path(project_root).resolve()
    rows: list[ManifestFile] = []
    for path in collect_files(root, profile):
        rel = path.relative_to(root).as_posix()
        rows.append(ManifestFile(
            path=rel,
            absolute_path=path,
            content_sha256=_sha256(path),
            size_bytes=path.stat().st_size,
        ))
    rows.sort(key=lambda x: x.path)

    digest = hashlib.sha256()
    for row in rows:
        digest.update(row.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(row.content_sha256.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(row.size_bytes).encode("ascii"))
        digest.update(b"\n")
    return Manifest(root=root, files=tuple(rows), digest=digest.hexdigest())


def compare(expected_digest: str, current: Manifest) -> None:
    if current.digest != expected_digest:
        from .errors import ResumeError
        raise ResumeError(
            "source_changed",
            "인덱싱 시작 이후 대상 파일의 내용 또는 목록이 변경됐습니다. "
            "중간 재개 대신 새 실행이 필요합니다.",
            details={"expected_manifest": expected_digest,
                     "current_manifest": current.digest},
        )
