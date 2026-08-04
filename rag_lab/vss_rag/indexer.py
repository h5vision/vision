"""
인덱싱 — git commit 기반 버전 관리 + project_id 기반 상태 (8/3 결정).

설계 결정 (AWS_WORKLOG_2026-08-03 §9)
  · 인덱스 최신 여부 = git commit 비교 + 파라미터 지문 비교
  · job_id 미사용 — project_id 로 상태 조회 (C안)
  · 비동기 = threading (Redis 불필요)
  · 상태 저장 = 1단계 JSON → 2단계 SQLite

⚠ 1단계는 프로세스 재시작 시 진행 중이던 작업 상태가 소실됩니다.
   인덱스 자체는 Chroma에 남으므로 재인덱싱하면 복구됩니다.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import CFG
from .chunker import chunk_file, collect_files
from .embedder import embed_many
from .store import Store

_LOCK = threading.Lock()

# running 상태가 이 시간(초) 이상 갱신되지 않으면 죽은 작업으로 간주합니다.
# 프로세스가 중단되면 state 가 running 으로 고착되기 때문입니다.
STALE_AFTER = 120


def clear_state(project_id: str) -> dict:
    """고착된 상태를 강제로 지웁니다. 인덱스 데이터는 재인덱싱 시 정리됩니다."""
    with _LOCK:
        data = _load_all()
        removed = data.pop(project_id, None)
        _save_all(data)
    return {"cleared": removed is not None, "project_id": project_id}


# ── git ─────────────────────────────────────────────────────

def git_head(root: str | Path) -> str | None:
    """현재 커밋 해시. git 레포가 아니면 None."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def git_dirty(root: str | Path) -> bool | None:
    """커밋 안 된 변경 존재 여부. git 레포가 아니면 None."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True, timeout=15,
        )
        return bool(r.stdout.strip()) if r.returncode == 0 else None
    except Exception:
        return None


# ── 상태 저장 (1단계: JSON) ──────────────────────────────────

def _state_file() -> Path:
    p = Path(CFG.state_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_all() -> dict:
    p = _state_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all(data: dict) -> None:
    tmp = _state_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_state_file())


def get_state(project_id: str) -> dict:
    """project_id 로 상태 조회 (C안). 없으면 state='none'."""
    with _LOCK:
        return _load_all().get(project_id, {"state": "none", "project_id": project_id})


def _update(project_id: str, **fields) -> None:
    with _LOCK:
        data = _load_all()
        cur = data.get(project_id, {"project_id": project_id})
        cur.update(fields)
        cur["heartbeat"] = time.time()
        data[project_id] = cur
        _save_all(data)


def list_projects() -> list[dict]:
    with _LOCK:
        return list(_load_all().values())


# ── 최신 여부 판정 ───────────────────────────────────────────

def is_stale(project_root: str | Path, project_id: str) -> dict:
    """
    인덱스가 낡았는지 판정.

    ⚠ commit 만 보면 안 됩니다. 청킹 파라미터를 바꿔가며 실험하므로
       같은 커밋이라도 fingerprint 가 다르면 재인덱싱이 필요합니다.
    """
    st = get_state(project_id)
    if st.get("state") != "done":
        return {"stale": True, "reason": "not_indexed"}

    cur_commit = git_head(project_root)
    if cur_commit and st.get("commit") and cur_commit != st["commit"]:
        return {"stale": True, "reason": "commit_changed",
                "indexed": st["commit"][:8], "current": cur_commit[:8]}

    if st.get("fingerprint") != CFG.fingerprint():
        return {"stale": True, "reason": "params_changed",
                "indexed": st.get("fingerprint"), "current": CFG.fingerprint()}

    if git_dirty(project_root):
        # 경고만. 재인덱싱 여부는 사용자 판단 (C안)
        return {"stale": False, "reason": "clean", "warning": "uncommitted_changes"}

    return {"stale": False, "reason": "clean"}


# ── 인덱싱 실행 ──────────────────────────────────────────────

def _run(project_root: str, project_id: str, store: Store) -> None:
    root = Path(project_root).resolve()
    t0 = time.time()
    try:
        files = collect_files(root)
        _update(project_id, state="running", processed=0, total=len(files),
                chunk_count=0, error=None)

        store.reset(project_id)

        total_chunks = 0
        buf: list[dict] = []

        for i, f in enumerate(files, start=1):
            buf.extend(chunk_file(f, root))

            # 일정량 모이면 임베딩 + 저장
            if len(buf) >= 64:
                vecs = embed_many([c["text"] for c in buf])
                store.add(project_id, buf, vecs)
                total_chunks += len(buf)
                buf = []

            _update(project_id, processed=i, chunk_count=total_chunks)

        if buf:
            vecs = embed_many([c["text"] for c in buf])
            store.add(project_id, buf, vecs)
            total_chunks += len(buf)

        _update(
            project_id,
            state="done",
            processed=len(files),
            total=len(files),
            chunk_count=total_chunks,
            commit=git_head(root),
            dirty=git_dirty(root),
            project_root=str(root),
            fingerprint=CFG.fingerprint(),
            indexed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            elapsed_s=round(time.time() - t0, 1),
            error=None,
        )
    except Exception as e:
        _update(project_id, state="failed", error=f"{type(e).__name__}: {e}",
                elapsed_s=round(time.time() - t0, 1))
        raise


def start_index(project_root: str, project_id: str, blocking: bool = False,
                force: bool = False) -> dict:
    """
    인덱싱 시작. 기본은 비동기(즉시 반환).

    ⚠ 같은 project_id 가 이미 running 이면 거부합니다.
       동시 인덱싱이 없다는 전제이므로 job_id 가 불필요합니다 (C안).
    """
    cur = get_state(project_id)
    if cur.get("state") == "running":
        age = time.time() - (cur.get("heartbeat") or 0)
        if age < STALE_AFTER and not force:
            return {"accepted": False, "reason": "already_running",
                    "project_id": project_id, "heartbeat_age_s": round(age, 1)}
        _update(project_id, state="aborted",
                error=f"stale running (heartbeat {age:.0f}s ago)")

    root = Path(project_root).resolve()
    if not root.is_dir():
        return {"accepted": False, "reason": "not_a_directory", "path": str(root)}

    store = Store()

    if blocking:
        _run(str(root), project_id, store)
        return {"accepted": True, "project_id": project_id, **get_state(project_id)}

    threading.Thread(
        target=_run, args=(str(root), project_id, store), daemon=True
    ).start()
    return {"accepted": True, "project_id": project_id, "state": "running"}


def has_index(project_id: str) -> dict:
    """FN-A03 미인덱싱 감지."""
    st = get_state(project_id)
    exists = st.get("state") == "done" and (st.get("chunk_count") or 0) > 0
    return {
        "exists": exists,
        "project_id": project_id,
        "chunk_count": st.get("chunk_count", 0),
        "indexed_at": st.get("indexed_at"),
        "commit": st.get("commit"),
    }
