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
from typing import Callable

from . import incremental, lexical
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

def _run(project_root: str, project_id: str, store: Store,
         on_done: "Callable | None" = None) -> None:
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

        # ── BM25 역색인 ─────────────────────────────────────
        # ⚠ 벡터 인덱스가 완성된 뒤에 만듭니다. 저장된 청크를 그대로
        #    읽어서 색인하므로, 청크 텍스트와 항상 일치합니다.
        #    (청킹 단계에서 따로 모으면 중간 실패 시 어긋납니다)
        if CFG.use_bm25:
            _update(project_id, state="indexing_lexical")
            all_c = store.all_chunks(project_id)
            lexical.build(project_id, all_c)

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

    # ── 인덱싱 완료 훅 (FN-A05 브리핑 자동 생성) ─────────────
    # ⚠ indexer 는 여기서 무엇이 실행되는지 모릅니다.
    #    LLM 의존성은 호출자(server/cli)가 주입합니다. briefing 을 import 하지 않습니다.
    # ⚠ 훅 실패가 인덱싱을 실패로 만들면 안 됩니다.
    #    55분짜리 인덱싱이 마지막 LLM 호출 하나 때문에 무효가 되는 상황을 막습니다.
    #    그래서 try 블록 **밖**에 두고, state 는 done 인 채로 둡니다.
    if on_done is not None:
        _update(project_id, briefing="generating", briefing_error=None)
        try:
            on_done(project_id, str(root), git_head(root))
            _update(project_id, briefing="ready")
        except Exception as e:
            _update(project_id, briefing="failed",
                    briefing_error=f"{type(e).__name__}: {e}")


def start_index(project_root: str, project_id: str, blocking: bool = False,
                force: bool = False, on_done: "Callable | None" = None) -> dict:
    """
    인덱싱 시작. 기본은 비동기(즉시 반환).

    ⚠ 같은 project_id 가 이미 running 이면 거부합니다.
       동시 인덱싱이 없다는 전제이므로 job_id 가 불필요합니다 (C안).

    on_done: 인덱싱이 끝난 뒤 호출할 콜백. 시그니처는
             (project_id, project_root, commit) -> None 입니다.
             브리핑 자동 생성에 쓰이며, indexer 는 내용을 알지 못합니다.
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
        _run(str(root), project_id, store, on_done)
        return {"accepted": True, "project_id": project_id, **get_state(project_id)}

    threading.Thread(
        target=_run, args=(str(root), project_id, store, on_done), daemon=True
    ).start()
    return {"accepted": True, "project_id": project_id, "state": "running"}


def start_update(project_root: str, project_id: str,
                 blocking: bool = False, force: bool = False) -> dict:
    """
    증분 인덱싱. 바뀐 파일만 다시 처리합니다.

    ⚠ 불가능한 경우(파라미터 변경·git 아님 등)에는 실행하지 않고
       이유를 돌려줍니다. 자동으로 전체 인덱싱으로 넘어가지 않습니다 —
       55분짜리 작업이 예고 없이 시작되면 곤란하기 때문입니다.
    """
    cur = get_state(project_id)
    if cur.get("state") == "running":
        age = time.time() - (cur.get("heartbeat") or 0)
        if age < STALE_AFTER and not force:
            return {"ok": False, "reason": "already_running",
                    "heartbeat_age_s": round(age, 1)}

    root = Path(project_root or cur.get("project_root") or "").resolve()
    check = incremental.can_update(root, project_id, cur)
    if not check["ok"]:
        # 전체 인덱싱이 필요하다는 안내를 그대로 전달합니다.
        return check

    store = Store()

    def _run_update():
        _update(project_id, state="updating", processed=0,
                total=len(check["to_index"]), error=None)
        try:
            def prog(i, n):
                _update(project_id, processed=i, total=n)

            r = incremental.update(str(root), project_id, store, cur,
                                   on_progress=prog)
            if r.get("ok"):
                _update(project_id, state="done",
                        commit=r["new_commit"],
                        dirty=git_dirty(root),
                        chunk_count=r["chunk_count"],
                        processed=r["files_indexed"],
                        total=r["files_indexed"],
                        indexed_at=r["indexed_at"],
                        elapsed_s=r["elapsed_s"],
                        last_mode="incremental",
                        error=None)
            else:
                _update(project_id, state="done",
                        error=f"update skipped: {r.get('reason')}")
        except Exception as e:
            _update(project_id, state="failed",
                    error=f"{type(e).__name__}: {e}")
            raise

    if blocking:
        _run_update()
        return {"ok": True, "project_id": project_id, **get_state(project_id)}

    threading.Thread(target=_run_update, daemon=True).start()
    return {"ok": True, "project_id": project_id, "state": "updating",
            "to_index": len(check["to_index"]),
            "to_delete": len(check["to_delete"])}


def preview_update(project_root: str, project_id: str) -> dict:
    """실행하지 않고 무엇이 바뀌었는지만 확인합니다."""
    cur = get_state(project_id)
    root = Path(project_root or cur.get("project_root") or "").resolve()
    return incremental.can_update(root, project_id, cur)


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
