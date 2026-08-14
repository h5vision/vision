from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Mapping

from ..config import CFG
from .errors import ResumeError
from .manifest import Manifest


ACTIVE_STATUSES = ("running", "interrupted")


class CheckpointStore:
    """완성 인덱스와 분리된 SQLite 체크포인트 저장소."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or CFG.resume_db_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    build_collection TEXT NOT NULL,
                    source_revision TEXT,
                    manifest_hash TEXT NOT NULL,
                    fingerprint_json TEXT NOT NULL,
                    profile_id TEXT,
                    profile_hash TEXT,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    total_files INTEGER NOT NULL,
                    completed_files INTEGER NOT NULL DEFAULT 0,
                    completed_chunks INTEGER NOT NULL DEFAULT 0,
                    owner_pid INTEGER,
                    owner_host TEXT,
                    started_at REAL NOT NULL,
                    heartbeat REAL NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_index_runs_project
                    ON index_runs(project_id, started_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS ux_index_runs_active_project
                    ON index_runs(project_id)
                    WHERE status IN ('running','interrupted');
                CREATE TABLE IF NOT EXISTS index_run_files (
                    run_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    completed_at REAL,
                    PRIMARY KEY(run_id, path),
                    FOREIGN KEY(run_id) REFERENCES index_runs(run_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_index_run_files_status
                    ON index_run_files(run_id, status, path);
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        out = dict(row)
        if "fingerprint_json" in out:
            out["fingerprint"] = json.loads(out.pop("fingerprint_json"))
        return out

    def create_run(self, *, run_id: str, project_id: str, manifest: Manifest,
                   build_collection: str, source_revision: str | None,
                   fingerprint: Mapping, profile_id: str | None,
                   profile_hash: str | None) -> dict:
        now = time.time()
        with self._connect() as conn:
            active = conn.execute(
                "SELECT run_id, status FROM index_runs "
                "WHERE project_id=? AND status IN ('running','interrupted') "
                "ORDER BY started_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            if active:
                raise ResumeError(
                    "resumable_run_exists",
                    "기존 체크포인트 실행이 있습니다. resume 또는 restart를 명시하세요.",
                    details={"run_id": active["run_id"],
                             "status": active["status"]},
                )
            try:
                conn.execute(
                    """INSERT INTO index_runs(
                           run_id, project_id, project_root, build_collection,
                           source_revision, manifest_hash, fingerprint_json,
                           profile_id, profile_hash, status, phase, total_files,
                           owner_pid, owner_host, started_at, heartbeat)
                       VALUES(?,?,?,?,?,?,?,?,?,'running','embedding',?,?,?,?,?)""",
                    (run_id, project_id, str(manifest.root), build_collection,
                     source_revision, manifest.digest,
                     json.dumps(dict(fingerprint), ensure_ascii=False, sort_keys=True),
                     profile_id, profile_hash, len(manifest.files), os.getpid(),
                     socket.gethostname(), now, now),
                )
            except sqlite3.IntegrityError as e:
                raise ResumeError(
                    "resumable_run_exists",
                    "동시에 같은 project_id의 체크포인트 실행을 만들 수 없습니다",
                    details={"project_id": project_id},
                ) from e
            conn.executemany(
                """INSERT INTO index_run_files(
                       run_id, path, content_sha256, size_bytes)
                   VALUES(?,?,?,?)""",
                [(run_id, f.path, f.content_sha256, f.size_bytes)
                 for f in manifest.files],
            )
        return self.get_run(run_id) or {}

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            return self._row(conn.execute(
                "SELECT * FROM index_runs WHERE run_id=?", (run_id,)
            ).fetchone())

    def latest(self, project_id: str, *, active_only: bool = False) -> dict | None:
        clause = "AND status IN ('running','interrupted')" if active_only else ""
        with self._connect() as conn:
            return self._row(conn.execute(
                f"SELECT * FROM index_runs WHERE project_id=? {clause} "
                "ORDER BY started_at DESC LIMIT 1", (project_id,)
            ).fetchone())

    def files(self, run_id: str, *, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM index_run_files WHERE run_id=?"
        params: tuple = (run_id,)
        if status:
            sql += " AND status=?"
            params = (run_id, status)
        sql += " ORDER BY path"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def set_run(self, run_id: str, **fields) -> None:
        allowed = {
            "status", "phase", "completed_files", "completed_chunks",
            "owner_pid", "owner_host", "error", "heartbeat",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"허용되지 않은 run 필드: {sorted(bad)}")
        fields.setdefault("heartbeat", time.time())
        assignments = ", ".join(f"{k}=?" for k in fields)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE index_runs SET {assignments} WHERE run_id=?",
                (*fields.values(), run_id),
            )

    def heartbeat(self, run_id: str) -> None:
        self.set_run(run_id, heartbeat=time.time(), owner_pid=os.getpid(),
                     owner_host=socket.gethostname())

    def mark_files_complete(self, run_id: str,
                            rows: Iterable[tuple[str, int]]) -> dict:
        rows = list(rows)
        now = time.time()
        with self._connect() as conn:
            conn.executemany(
                """UPDATE index_run_files
                   SET status='completed', chunk_count=?, completed_at=?
                   WHERE run_id=? AND path=?""",
                [(count, now, run_id, path) for path, count in rows],
            )
            totals = conn.execute(
                """SELECT COUNT(*) AS files, COALESCE(SUM(chunk_count),0) AS chunks
                   FROM index_run_files WHERE run_id=? AND status='completed'""",
                (run_id,),
            ).fetchone()
            conn.execute(
                """UPDATE index_runs
                   SET completed_files=?, completed_chunks=?, heartbeat=?
                   WHERE run_id=?""",
                (totals["files"], totals["chunks"], now, run_id),
            )
        return {"completed_files": totals["files"],
                "completed_chunks": totals["chunks"]}

    @staticmethod
    def _pid_alive(pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def claim(self, run_id: str, *, force: bool = False,
              stale_after: float = 120.0) -> dict:
        run = self.get_run(run_id)
        if not run:
            raise ResumeError("run_not_found", "체크포인트 run_id가 없습니다")
        if run["status"] == "complete":
            return run
        if run["status"] not in ACTIVE_STATUSES:
            raise ResumeError("run_not_resumable",
                              f"재개할 수 없는 상태입니다: {run['status']}")

        same_host = run.get("owner_host") == socket.gethostname()
        owner_alive = same_host and self._pid_alive(run.get("owner_pid"))
        fresh = time.time() - float(run.get("heartbeat") or 0) < stale_after
        if run["status"] == "running" and owner_alive and fresh and not force:
            raise ResumeError(
                "run_still_active",
                "기존 인덱싱 프로세스가 아직 실행 중인 것으로 보입니다",
                details={"owner_pid": run.get("owner_pid")},
            )
        self.set_run(run_id, status="running", owner_pid=os.getpid(),
                     owner_host=socket.gethostname(), error=None)
        return self.get_run(run_id) or run

    def discard(self, run_id: str) -> None:
        self.set_run(run_id, status="discarded", phase="discarded")

    def summary(self, project_id: str) -> dict:
        run = self.latest(project_id)
        if not run:
            return {"project_id": project_id, "resumable": False,
                    "reason": "checkpoint_not_found"}
        return {
            "project_id": project_id,
            "run_id": run["run_id"],
            "status": run["status"],
            "phase": run["phase"],
            "resumable": run["status"] in ACTIVE_STATUSES,
            "completed_files": run["completed_files"],
            "total_files": run["total_files"],
            "completed_chunks": run["completed_chunks"],
            "heartbeat": run["heartbeat"],
            "error": run["error"],
        }
