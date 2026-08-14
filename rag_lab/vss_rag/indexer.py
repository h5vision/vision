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
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from . import incremental, lexical, payload_incremental
from .config import CFG, normalize_fingerprint
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
            ["git", "-c", f"safe.directory={Path(root).resolve()}",
             "rev-parse", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def git_dirty(root: str | Path) -> bool | None:
    """커밋 안 된 변경 존재 여부. git 레포가 아니면 None."""
    try:
        r = subprocess.run(
            ["git", "-c", f"safe.directory={Path(root).resolve()}",
             "status", "--porcelain"],
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


def _save_all(data: dict, *, retries: int = 5) -> None:
    """상태 저장.

    ⚠ Windows 에서 `replace()` 가 간헐적으로 `PermissionError [WinError 5]` 를 냅니다
       (바이러스 검사·에디터·다른 프로세스가 대상 파일을 잠깐 잡을 때).

    ⚠ **상태 기록 실패가 인덱싱을 죽이면 안 됩니다.**
       2026-08 사고: 파일마다 상태를 쓰다가(694회) 한 번의 WinError 5 로
       55분짜리 인덱싱이 통째로 실패하고 반쪽 인덱스가 남았습니다.
       이제는 재시도하고, 그래도 안 되면 경고만 남기고 진행합니다.
    """
    tmp = _state_file().with_suffix(".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    for attempt in range(retries):
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(_state_file())
            return
        except OSError as e:
            if attempt == retries - 1:
                print(f"!! state.json 저장 실패 ({type(e).__name__}: {e}) — 인덱싱은 계속합니다.")
                return
            time.sleep(0.1 * (2 ** attempt))     # 0.1 · 0.2 · 0.4 · 0.8초


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


def update_state(project_id: str, **fields) -> None:
    """선택 기능이 private state 구현에 의존하지 않도록 한 public adapter."""
    _update(project_id, **fields)


def _reserve_payload_update(project_id: str, base_revision: str,
                            total: int) -> dict | None:
    """검증과 worker 시작 사이의 동시 요청을 원자적으로 차단합니다."""
    with _LOCK:
        data = _load_all()
        cur = data.get(project_id, {"state": "none", "project_id": project_id})
        if cur.get("state") in ("running", "updating"):
            age = time.time() - (cur.get("heartbeat") or 0)
            return {
                "ok": False,
                "reason": "already_running" if age < STALE_AFTER else "stale_active_state",
                "detail": "같은 project_id의 인덱싱 작업 상태를 먼저 확인해야 합니다",
                "project_id": project_id,
                "heartbeat_age_s": round(age, 1),
                "conflict": True,
            }
        if cur.get("state") != "done" or str(cur.get("commit") or "").lower() != base_revision:
            return {
                "ok": False,
                "reason": "base_revision_mismatch",
                "detail": "검증 후 인덱스 revision이 변경되었습니다. 상태를 다시 조회하세요",
                "project_id": project_id,
                "conflict": True,
            }
        cur.update({
            "state": "updating",
            "update_source": "frontend_files",
            "processed": 0,
            "total": total,
            "update_error": None,
            "error": None,
            "heartbeat": time.time(),
        })
        data[project_id] = cur
        _save_all(data)
    return None


def list_projects() -> list[dict]:
    with _LOCK:
        return list(_load_all().values())


# ── 최신 여부 판정 ───────────────────────────────────────────

def is_stale(project_root: str | Path, project_id: str, *,
             compare_config: bool = True,
             profile: Mapping | None = None) -> dict:
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

    indexed_fp = normalize_fingerprint(st.get("fingerprint"))
    target_fp = normalize_fingerprint(profile) if profile is not None else CFG.fingerprint()
    if compare_config and indexed_fp != target_fp:
        return {"stale": True, "reason": "params_changed",
                "indexed": indexed_fp, "current": target_fp}

    if git_dirty(project_root):
        # 경고만. 재인덱싱 여부는 사용자 판단 (C안)
        return {"stale": False, "reason": "clean", "warning": "uncommitted_changes"}

    return {"stale": False, "reason": "clean"}


# ── 인덱싱 실행 ──────────────────────────────────────────────

def run_completion_hook(project_id: str, project_root: str,
                        commit: str | None,
                        on_done: "Callable | None") -> None:
    """완료 후 브리핑 같은 부수 작업을 실행하되 완성 인덱스는 보존합니다."""
    if on_done is None:
        return
    _update(project_id, briefing="generating", briefing_error=None)
    try:
        result = on_done(project_id, project_root, commit)
        # briefing.build()는 자료 부족 같은 정상적인 미생성도 예외 대신
        # {ok: false}로 돌려줍니다. 이를 ready로 기록하면 프론트 상태가 거짓이 됩니다.
        if isinstance(result, Mapping) and result.get("ok") is False:
            reason = result.get("reason") or "not_generated"
            message = result.get("message") or "브리핑이 생성되지 않았습니다"
            raise RuntimeError(f"{reason}: {message}")
        _update(project_id, briefing="ready", briefing_error=None)
    except Exception as e:
        _update(project_id, briefing="failed",
                briefing_error=f"{type(e).__name__}: {e}")


def _run(project_root: str, project_id: str, store: Store,
         on_done: "Callable | None" = None,
         profile: Mapping | None = None,
         profile_id: str | None = None,
         profile_hash: str | None = None) -> None:
    root = Path(project_root).resolve()
    t0 = time.time()
    build: str | None = None      # 임시 컬렉션 이름. 실패 메시지에서 씁니다
    promoted = False
    bm25_backup: Path | None = None
    final_bm25: Path | None = None
    fp = normalize_fingerprint(profile) if profile is not None else CFG.fingerprint()
    if not fp:
        raise ValueError("전체 인덱싱 프로필을 해석할 수 없습니다")
    try:
        files = collect_files(root, fp)
        # ⚠ fingerprint 를 **시작 시점에** 기록합니다.
        #    done 일 때만 쓰면 실패한 인덱스가 어떤 설정이었는지 알 수 없습니다.
        _update(project_id, state="running", processed=0, total=len(files),
                chunk_count=0, error=None,
                project_root=str(root), fingerprint=fp,
                profile_id=profile_id, profile_hash=profile_hash)

        # ── 🔴 선삭제하지 않습니다 ───────────────────────────
        # 임시 컬렉션에 쌓고 완료 시 교체합니다. 도중에 죽어도
        #   · 기존 인덱스가 그대로 살아 있고
        #   · building-<pid> 가 남아 **이름만으로 중단이 드러납니다**
        # (구 구현은 store.reset() 으로 먼저 지워서, 임베딩이 실패하면
        #  반쪽 인덱스가 정상인 척 검색되는 사고가 있었습니다)
        build = store.begin_build(
            project_id, fingerprint=fp, project_root=str(root),
            profile_id=profile_id, profile_hash=profile_hash)

        total_chunks = 0
        buf: list[dict] = []
        last_report = 0.0

        for i, f in enumerate(files, start=1):
            buf.extend(chunk_file(f, root, fp))

            # 일정량 모이면 임베딩 + 저장
            if len(buf) >= 64:
                vecs = embed_many(
                    [c["text"] for c in buf],
                    model=str(fp["embed_model"]), expected_dim=int(fp["embed_dim"]))
                store.add(build, buf, vecs, id_prefix=project_id)
                total_chunks += len(buf)
                buf = []

            # ⚠ 파일마다 쓰지 않습니다. state.json 은 매번 전체가 다시 써지므로
            #    2,870개 파일이면 2,870회 쓰기가 되고, 그중 한 번의 실패가
            #    인덱싱 전체를 죽였습니다. 2초 간격이면 진행률 표시에 충분합니다.
            now = time.time()
            if now - last_report >= 2.0 or i == len(files):
                _update(project_id, processed=i, chunk_count=total_chunks)
                last_report = now

        if buf:
            vecs = embed_many(
                [c["text"] for c in buf],
                model=str(fp["embed_model"]), expected_dim=int(fp["embed_dim"]))
            store.add(build, buf, vecs, id_prefix=project_id)
            total_chunks += len(buf)

        # ── BM25 역색인 ─────────────────────────────────────
        # 요청한 하이브리드 프로필이 벡터 전용으로 조용히 완료되면 안 됩니다.
        # 임시 컬렉션의 실제 청크로 먼저 만들고 문서 수를 검증한 뒤에만 승격합니다.
        staged_bm25 = None
        bm25_count = 0
        if bool(fp["use_bm25"]):
            _update(project_id, state="indexing_lexical")
            staged_bm25 = lexical.staging_path(project_id)
            chunks_for_bm25 = store.all_chunks(build)
            idx = lexical.build(project_id, chunks_for_bm25, path=staged_bm25)
            bm25_count = len(idx.doc_ids)
            if bm25_count != total_chunks:
                raise RuntimeError(
                    f"BM25 문서 수 불일치: bm25={bm25_count}, chroma={total_chunks}")

        # ── 교체 ────────────────────────────────────────────
        # BM25까지 준비된 뒤에만 벡터 컬렉션을 승격합니다.
        _update(project_id, state="promoting", chunk_count=total_chunks)
        final_bm25 = lexical.index_path(project_id)
        bm25_backup = final_bm25.with_name(final_bm25.name + ".prev")
        if bm25_backup.exists():
            bm25_backup.unlink()
        if final_bm25.exists():
            shutil.copy2(final_bm25, bm25_backup)

        # Chroma의 직전 컬렉션은 BM25 파일 커밋이 끝날 때까지 보존합니다.
        store.promote(project_id, keep_previous=True)
        promoted = True

        if staged_bm25 is not None:
            final_bm25.parent.mkdir(parents=True, exist_ok=True)
            staged_bm25.replace(final_bm25)
        elif final_bm25.exists():
            # 같은 project_id를 벡터 프로필로 교체했을 때 옛 역색인이 남지 않게 합니다.
            final_bm25.unlink()

        store.finish_promote(project_id)
        if bm25_backup.exists():
            bm25_backup.unlink()
        build = None

        _update(
            project_id,
            state="done",
            processed=len(files),
            total=len(files),
            chunk_count=total_chunks,
            commit=git_head(root),
            dirty=git_dirty(root),
            project_root=str(root),
            fingerprint=fp,
            profile_id=profile_id,
            profile_hash=profile_hash,
            bm25_count=bm25_count if fp["use_bm25"] else None,
            indexed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            elapsed_s=round(time.time() - t0, 1),
            error=None,
        )
    except Exception as e:
        if promoted:
            try:
                store.rollback_promote(project_id)
                build = f"building-{project_id}"
                if bm25_backup and bm25_backup.exists() and final_bm25:
                    bm25_backup.replace(final_bm25)
                elif final_bm25 and final_bm25.exists():
                    final_bm25.unlink()
            except Exception as rollback_error:
                print(f"!! 승격 rollback 실패: {type(rollback_error).__name__}: {rollback_error}")
        # ⚠ building-<pid> 를 일부러 남깁니다.
        #    기존 인덱스는 무사하고, 남은 임시 컬렉션이 **중단의 증거**가 됩니다.
        #    자동으로 지우면 왜 실패했는지 알 방법이 사라집니다.
        #    정리는 `repair_collections.py` 또는 Store.cleanup_incomplete() 로 명시적으로 합니다.
        _update(project_id, state="failed", error=f"{type(e).__name__}: {e}",
                elapsed_s=round(time.time() - t0, 1))
        print(f"!! 인덱싱 실패: {type(e).__name__}: {e}")
        if build:
            print(f"   기존 인덱스는 그대로입니다. 임시 컬렉션 '{build}' 가 남았습니다.")
        elif promoted:
            print("   승격 후 rollback 상태를 doctor로 확인하세요.")
        raise

    # ── 인덱싱 완료 훅 (FN-A05 브리핑 자동 생성) ─────────────
    # ⚠ indexer 는 여기서 무엇이 실행되는지 모릅니다.
    #    LLM 의존성은 호출자(server/cli)가 주입합니다. briefing 을 import 하지 않습니다.
    # ⚠ 훅 실패가 인덱싱을 실패로 만들면 안 됩니다.
    #    55분짜리 인덱싱이 마지막 LLM 호출 하나 때문에 무효가 되는 상황을 막습니다.
    #    그래서 try 블록 **밖**에 두고, state 는 done 인 채로 둡니다.
    run_completion_hook(project_id, str(root), git_head(root), on_done)


def start_index(project_root: str, project_id: str, blocking: bool = False,
                force: bool = False, on_done: "Callable | None" = None,
                profile: Mapping | None = None,
                profile_id: str | None = None,
                profile_hash: str | None = None) -> dict:
    """
    인덱싱 시작. 기본은 비동기(즉시 반환).

    ⚠ 같은 project_id 가 이미 running 이면 거부합니다.
       동시 인덱싱이 없다는 전제이므로 job_id 가 불필요합니다 (C안).

    on_done: 인덱싱이 끝난 뒤 호출할 콜백. 시그니처는
             (project_id, project_root, commit) -> None 입니다.
             브리핑 자동 생성에 쓰이며, indexer 는 내용을 알지 못합니다.
    """
    cur = get_state(project_id)
    if cur.get("state") in ("running", "updating"):
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
        _run(str(root), project_id, store, on_done, profile, profile_id, profile_hash)
        return {"accepted": True, "project_id": project_id, **get_state(project_id)}

    threading.Thread(
        target=_run,
        args=(str(root), project_id, store, on_done, profile, profile_id, profile_hash),
        daemon=True,
    ).start()
    return {"accepted": True, "project_id": project_id, "state": "running",
            "profile_id": profile_id, "profile_hash": profile_hash}


def start_update(project_root: str, project_id: str,
                 blocking: bool = False, force: bool = False) -> dict:
    """
    증분 인덱싱. 바뀐 파일만 다시 처리합니다.

    ⚠ 불가능한 경우(파라미터 변경·git 아님 등)에는 실행하지 않고
       이유를 돌려줍니다. 자동으로 전체 인덱싱으로 넘어가지 않습니다 —
       55분짜리 작업이 예고 없이 시작되면 곤란하기 때문입니다.
    """
    cur = get_state(project_id)
    if cur.get("state") in ("running", "updating"):
        age = time.time() - (cur.get("heartbeat") or 0)
        if age < STALE_AFTER and not force:
            return {"ok": False, "reason": "already_running",
                    "heartbeat_age_s": round(age, 1)}

    root = Path(project_root or cur.get("project_root") or "").resolve()
    store = Store()
    check = incremental.can_update(
        root, project_id, cur, index_fp=store.index_fingerprint(project_id))
    if not check["ok"]:
        # 전체 인덱싱이 필요하다는 안내를 그대로 전달합니다.
        return check

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
                        fingerprint=r["fingerprint"],
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


def start_payload_update(payload: dict, blocking: bool = False) -> dict:
    """프론트가 보낸 최종 파일 문자열로 commit 단위 증분 인덱싱을 시작합니다.

    로컬 Git 작업 트리를 읽는 ``start_update()``와 의도적으로 분리합니다.
    요청의 base revision이 현재 인덱스 revision과 정확히 같을 때만 실행하며,
    실패 시 rollback에 성공한 기존 인덱스는 계속 검색할 수 있게 둡니다.
    """
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "invalid_payload",
                "detail": "JSON object가 필요합니다", "conflict": False}

    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        return {"ok": False, "reason": "project_id_required",
                "detail": "project_id가 필요합니다", "conflict": False}
    project_id = project_id.strip()

    cur = get_state(project_id)
    if cur.get("state") in ("running", "updating"):
        age = time.time() - (cur.get("heartbeat") or 0)
        return {
            "ok": False,
            "reason": "already_running" if age < STALE_AFTER else "stale_active_state",
            "detail": "같은 project_id의 인덱싱 작업 상태를 먼저 확인해야 합니다",
            "project_id": project_id,
            "heartbeat_age_s": round(age, 1),
            "conflict": True,
        }

    store = Store()
    try:
        plan = payload_incremental.prepare(payload, cur, store)
    except payload_incremental.PayloadUpdateError as e:
        return {"project_id": project_id, **e.as_dict()}

    if plan.get("already_applied"):
        return {
            "ok": True,
            "already_applied": True,
            "project_id": project_id,
            "state": "done",
            "commit": plan["target_revision"],
        }

    reservation_error = _reserve_payload_update(
        project_id, plan["base_revision"], len(plan["indexable_files"]))
    if reservation_error:
        return reservation_error

    def _run_payload_update():
        try:
            def prog(i, n):
                _update(project_id, processed=i, total=n)

            result = payload_incremental.apply(plan, store, on_progress=prog)
        except payload_incremental.PayloadApplyError as e:
            # rollback이 끝났다면 기존 base revision 인덱스는 정상 서빙 가능합니다.
            _update(
                project_id,
                state="done" if e.rollback_ok else "failed",
                commit=plan["base_revision"],
                last_mode="payload_incremental_failed",
                update_error=str(e),
                error=None if e.rollback_ok else str(e),
            )
            return
        except Exception as e:
            # 청킹·임베딩·rollback snapshot 준비 중 실패한 경우입니다.
            # 실제 교체 try 블록에 들어가기 전이므로 기존 인덱스는 온전합니다.
            _update(
                project_id,
                state="done",
                commit=plan["base_revision"],
                last_mode="payload_incremental_failed",
                update_error=f"{type(e).__name__}: {e}",
                error=None,
            )
            return

        # apply가 성공한 뒤 상태 기록 오류를 위 실패 처리와 섞지 않습니다.
        _update(
            project_id,
            state="done",
            commit=result["new_commit"],
            dirty=False,
            chunk_count=result["chunk_count"],
            processed=result["files_indexed"],
            total=result["files_indexed"],
            indexed_at=result["indexed_at"],
            elapsed_s=result["elapsed_s"],
            fingerprint=result["fingerprint"],
            last_mode="payload_incremental",
            snapshot_id=result.get("snapshot_id"),
            branch=result.get("branch"),
            files_received=result["files_received"],
            files_deleted=result["files_deleted"],
            files_renamed=result["files_renamed"],
            ignored_paths=result["ignored_paths"],
            update_error=None,
            error=None,
        )

    if blocking:
        _run_payload_update()
        state = get_state(project_id)
        return {
            "ok": state.get("state") == "done" and not state.get("update_error"),
            "project_id": project_id,
            **state,
        }

    try:
        threading.Thread(target=_run_payload_update, daemon=True).start()
    except Exception as e:
        _update(
            project_id,
            state="done",
            commit=plan["base_revision"],
            update_error=f"worker_start_failed: {type(e).__name__}: {e}",
            error=None,
        )
        return {
            "ok": False,
            "reason": "worker_start_failed",
            "detail": f"{type(e).__name__}: {e}",
            "project_id": project_id,
            "conflict": False,
        }
    return {
        "ok": True,
        "project_id": project_id,
        "state": "updating",
        "base_revision": plan["base_revision"],
        "target_revision": plan["target_revision"],
        "files_received": len(plan["files"]),
        "files_indexed": len(plan["indexable_files"]),
        "files_deleted": len(plan["deleted_paths"]),
        "files_renamed": len(plan["renames"]),
        "ignored_paths": plan["ignored_paths"],
    }


def preview_update(project_root: str, project_id: str) -> dict:
    """실행하지 않고 무엇이 바뀌었는지만 확인합니다."""
    cur = get_state(project_id)
    root = Path(project_root or cur.get("project_root") or "").resolve()
    store = Store()
    return incremental.can_update(
        root, project_id, cur, index_fp=store.index_fingerprint(project_id))


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
