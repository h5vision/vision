"""
증분 인덱싱 — 바뀐 파일만 다시 처리합니다.

⚠ 왜 필요한가

    전체 인덱싱은 파일 2,870개 기준 55분이 걸립니다.
    대부분은 임베딩 호출(청크 21,104개)이 차지합니다.

    그런데 커밋 하나에서 바뀌는 파일은 보통 1~5개입니다.

        전체:  21,104 청크 임베딩  →  55분
        증분:      30 청크 임베딩  →   5초

⚠ 전제 조건

    이 기능은 청크 ID 가 **경로 기반**이어야 동작합니다.

        예전:  demo:0, demo:1, ...        ← "이 파일의 청크"를 특정 불가
        지금:  demo:src/main.py:0, ...    ← 파일 단위 삭제 가능

    2026-08-03 에 store.py 의 ID 체계를 바꾼 것이 이 기능의 전제였습니다.

⚠ 증분이 불가능한 경우

    · 파라미터 변경 (chunk_size, 임베딩 모델, 맥락 헤더 등)
      → 모든 청크의 내용이 달라지므로 전체 재인덱싱
    · git 레포가 아님
    · 이전 인덱싱 기록 없음
    · 변경 파일이 너무 많음 (전체보다 느려질 수 있음)
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import lexical
from .chunker import chunk_file, classify, collect_files
from .config import CFG, SKIP_DIRS, SKIP_FILE_PATTERNS
from .embedder import embed_many
from .store import Store

# 변경 비율이 이보다 크면 전체 인덱싱이 낫습니다.
# 증분은 파일 단위 삭제·재삽입 오버헤드가 있어서, 절반 이상이 바뀌면
# 처음부터 다시 만드는 쪽이 단순하고 빠릅니다.
FULL_REINDEX_RATIO = 0.5


# ── git 변경 감지 ────────────────────────────────────────────

def _git(root: str | Path, *args: str, timeout: int = 30) -> str | None:
    """git 명령 실행. 실패하면 None."""
    try:
        r = subprocess.run(
            # ⚠ quotepath=false 가 없으면 한글 파일명이
            #    "\355\225\234\352\270\200" 처럼 이스케이프되어 나옵니다.
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(root), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def detect_changes(root: str | Path, old_commit: str) -> dict | None:
    """
    old_commit 이후 바뀐 파일 목록.

    ⚠ 커밋된 변경뿐 아니라 **작업 트리의 미커밋 변경도** 포함합니다.
       `git diff <commit>` 은 커밋과 작업 트리를 비교하기 때문입니다.
       추적되지 않는 새 파일은 별도로 조회합니다.

    반환:
        {"modified": [...], "added": [...], "deleted": [...],
         "renamed": [(옛경로, 새경로), ...]}
    """
    out = _git(root, "diff", "--name-status", "-M", "--find-renames", old_commit)
    if out is None:
        return None

    res: dict = {"modified": [], "added": [], "deleted": [], "renamed": []}

    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0].strip()

        if code.startswith("R") and len(parts) >= 3:
            res["renamed"].append((parts[1], parts[2]))
        elif code.startswith("A") and len(parts) >= 2:
            res["added"].append(parts[1])
        elif code.startswith("D") and len(parts) >= 2:
            res["deleted"].append(parts[1])
        elif code.startswith(("M", "T")) and len(parts) >= 2:
            # T = 타입 변경(파일↔심볼릭링크). 재처리하면 됩니다.
            res["modified"].append(parts[1])
        elif code.startswith("C") and len(parts) >= 3:
            # C = 복사. 새 경로만 추가하면 됩니다.
            res["added"].append(parts[2])

    # 추적되지 않는 새 파일 (git diff 에 안 나옴)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if untracked:
        for p in untracked.splitlines():
            if p.strip():
                res["added"].append(p.strip())

    return res


def _is_target(root: Path, rel: str) -> bool:
    """인덱싱 대상 파일인지. chunker 의 필터와 같은 기준."""
    p = root / rel
    parts = Path(rel).parts
    if any(part in SKIP_DIRS for part in parts):
        return False
    if Path(rel).name in SKIP_FILE_PATTERNS:
        return False
    if classify(Path(rel)) is None:
        return False
    if p.is_file():
        try:
            if p.stat().st_size > CFG.max_file_bytes:
                return False
        except OSError:
            return False
    return True


# ── 증분 가능 여부 판정 ──────────────────────────────────────

def can_update(project_root: str | Path, project_id: str, state: dict) -> dict:
    """
    증분 인덱싱이 가능한지 판정합니다.

    반환: {"ok": bool, "reason": str, ...}
    """
    if state.get("state") != "done":
        return {"ok": False, "reason": "not_indexed",
                "detail": "완료된 인덱스가 없습니다. 전체 인덱싱이 필요합니다."}

    if state.get("fingerprint") != CFG.fingerprint():
        return {"ok": False, "reason": "params_changed",
                "detail": "청킹·임베딩 설정이 바뀌었습니다. 모든 청크를 다시 만들어야 합니다.",
                "indexed": state.get("fingerprint"),
                "current": CFG.fingerprint()}

    old = state.get("commit")
    if not old:
        return {"ok": False, "reason": "no_commit",
                "detail": "이전 인덱싱의 git 커밋 정보가 없습니다."}

    root = Path(project_root).resolve()
    if not root.is_dir():
        return {"ok": False, "reason": "not_a_directory", "path": str(root)}

    head = _git(root, "rev-parse", "HEAD")
    if head is None:
        return {"ok": False, "reason": "not_a_git_repo",
                "detail": "git 레포가 아니거나 git 명령을 쓸 수 없습니다."}

    changes = detect_changes(root, old)
    if changes is None:
        return {"ok": False, "reason": "diff_failed",
                "detail": f"커밋 {old[:8]} 을 찾을 수 없습니다. 히스토리가 바뀌었을 수 있습니다."}

    # 대상 파일만 추립니다
    to_index = [p for p in (changes["modified"] + changes["added"]
                            + [new for _, new in changes["renamed"]])
                if _is_target(root, p)]
    to_delete = list({*changes["deleted"],
                      *changes["modified"],
                      *[old_p for old_p, _ in changes["renamed"]]})

    total_now = len(collect_files(root))
    ratio = (len(to_index) / total_now) if total_now else 1.0

    if ratio > FULL_REINDEX_RATIO:
        return {"ok": False, "reason": "too_many_changes",
                "detail": f"변경 파일이 {len(to_index)}/{total_now} 개입니다. "
                          f"전체 인덱싱이 더 빠릅니다.",
                "changed": len(to_index), "total": total_now}

    return {
        "ok": True,
        "reason": "ok",
        "old_commit": old,
        "new_commit": head.strip(),
        "to_index": to_index,
        "to_delete": to_delete,
        "changes": changes,
        "total_files": total_now,
    }


# ── 증분 실행 ────────────────────────────────────────────────

def update(project_root: str, project_id: str, store: Store,
           state: dict, on_progress=None) -> dict:
    """
    바뀐 파일만 다시 인덱싱합니다.

    ⚠ 순서가 중요합니다.
       ① 옛 청크 삭제  →  ② 새 청크 삽입
       반대로 하면 같은 파일의 청크가 중복됩니다.
       (ID 가 같으면 upsert 로 덮이지만, 청크 수가 줄어든 경우
        남는 옛 청크가 생깁니다)
    """
    t0 = time.perf_counter()
    root = Path(project_root).resolve()

    plan = can_update(root, project_id, state)
    if not plan["ok"]:
        return plan

    to_index = plan["to_index"]
    to_delete = plan["to_delete"]

    # ── ① 삭제 ──────────────────────────────────────────────
    # 수정된 파일도 여기 포함됩니다. 청크 수가 줄었을 수 있으므로
    # 지우고 다시 넣는 것이 안전합니다.
    deleted_n = store.delete_by_paths(project_id, to_delete) if to_delete else 0

    # ── ② 재청킹 + 임베딩 ───────────────────────────────────
    new_chunks: list[dict] = []
    for i, rel in enumerate(to_index, start=1):
        f = root / rel
        if not f.is_file():
            continue
        new_chunks.extend(chunk_file(f, root))
        if on_progress:
            on_progress(i, len(to_index))

    embedded = 0
    if new_chunks:
        # 배치로 나눠 임베딩
        B = 64
        for i in range(0, len(new_chunks), B):
            batch = new_chunks[i:i + B]
            vecs = embed_many([c["text"] for c in batch])
            store.add(project_id, batch, vecs)
            embedded += len(batch)

    # ── ③ BM25 역색인 재구축 ────────────────────────────────
    # ⚠ 역색인은 부분 갱신이 까다롭습니다 (df 값이 전역이라).
    #    다만 임베딩 호출이 없어 전체 재구축도 수 초면 끝납니다.
    if CFG.use_bm25:
        lexical.build(project_id, store.all_chunks(project_id))

    elapsed = round(time.perf_counter() - t0, 1)
    return {
        "ok": True,
        "mode": "incremental",
        "old_commit": plan["old_commit"],
        "new_commit": plan["new_commit"],
        "files_indexed": len(to_index),
        "files_deleted": len(plan["changes"]["deleted"]),
        "files_renamed": len(plan["changes"]["renamed"]),
        "paths_cleared": deleted_n,
        "chunks_added": embedded,
        "chunk_count": store.count(project_id),
        "elapsed_s": elapsed,
        "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
