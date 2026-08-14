#!/usr/bin/env python3
"""
rag_lab HTTP 서버 — 백엔드 연동용

표준 라이브러리만 사용합니다 (FastAPI 불필요).

실행:
    python server.py                 # 기본 127.0.0.1:8200
    python server.py --host 0.0.0.0  # 팀 접근 허용
    python server.py --port 8300

⚠ 인증 없음. 실험용이므로 기본은 localhost 바인딩입니다.
   외부 노출 시 --token 으로 최소 보호를 켜세요.

설계 결정 (AWS_WORKLOG_2026-08-03 §9)
  · job_id 미사용 — project_id 로 상태 조회 (C안)
  · 비동기 = threading
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from vss_rag.config import CFG
from vss_rag import briefing, diagnose, embedder, indexer, profiles, references, searcher
from vss_rag.store import Store


def _briefing_hook(model: str, url: str):
    """인덱싱이 끝나면 브리핑을 만드는 콜백을 돌려줍니다.

    ⚠ 이것이 rag_lab 에서 LLM 을 부르는 두 지점 중 하나입니다 (다른 하나는 POST /briefing).
       모델과 URL 을 여기서 주입하므로, fine-tuned 모델로 바꿀 때
       백엔드 한 곳만 고치면 브리핑도 따라갑니다 (C' 구조).
    """
    def cb(project_id: str, root: str, commit: str | None) -> dict:
        return briefing.build(root, project_id, model, url, commit=commit)
    return cb

TOKEN: str | None = None
_STORE_LOCK = threading.Lock()
_STORE: Store | None = None


def get_store() -> Store:
    """Store 를 재사용합니다. 매 요청마다 새로 열면 느립니다."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE


class Handler(BaseHTTPRequestHandler):
    server_version = "vss-rag-lab/0.1"

    # ── 공통 ────────────────────────────────────────────────
    def _send_text(self, code: int, text: str, ctype: str = "text/markdown"):
        """원문 텍스트를 그대로 내려줍니다 (JSON 감싸기 없음).

        프론트는 `fetch(url).then(r => r.text())` 한 줄이면 됩니다.
        """
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-VSS-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-VSS-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n == 0:
            return {}
        return json.loads(self.rfile.read(n))

    def _auth_ok(self) -> bool:
        if TOKEN is None:
            return True
        return self.headers.get("X-VSS-Token") == TOKEN

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def do_OPTIONS(self):
        self._send(204, {})

    # ── 라우팅 ──────────────────────────────────────────────
    def do_GET(self):
        try:
            if not self._auth_ok():
                return self._send(401, {"error": "unauthorized"})

            u = urlparse(self.path)
            q = parse_qs(u.query)
            path = u.path.rstrip("/") or "/"

            if path == "/health":
                drift_rows = diagnose.drift_summary(get_store())
                return self._send(200, {
                    "ok": True,
                    "ollama": CFG.ollama_url,
                    "embed_model": CFG.embed_model,
                    "index_dir": CFG.index_dir,
                    "projects": get_store().projects(),
                    "briefings_dir": str(CFG.briefings_dir()),

                    # ⚠ `config` 는 **이 프로세스의 환경변수**입니다.
                    #    인덱스가 무엇으로 만들어졌는지가 아닙니다.
                    #    둘이 다를 수 있어서 `indexes` · `mismatch` 를 함께 냅니다.
                    #    (2026-08-13: config 만 노출해서 불일치를 아무도 못 보던 문제)
                    "indexes": [
                        {"project_id": r["name"], "chunks": r["chunks"],
                         # 검색·증분이 실제로 사용하는 프로젝트별 고정 프로필입니다.
                         "serving_profile": r["fingerprint"],
                         "fingerprint": r["fingerprint"],  # 이전 클라이언트 호환
                         "profile_source": r["fingerprint_source"],
                         # 다음 전체 인덱싱 기본값(CFG)과의 차이일 뿐 서빙 오류가 아닙니다.
                         "default_config_drift": {
                             k: {"index": i, "config": c}
                             for k, (i, c) in r["drift"].items()} or None,
                         "drift": {  # 이전 클라이언트 호환. 의미는 기본값과의 차이
                             k: {"index": i, "config": c}
                             for k, (i, c) in r["drift"].items()} or None}
                        for r in drift_rows
                    ],
                    "mismatch": [
                        r["name"] for r in drift_rows if r["fingerprint"] is None],
                    "default_config_drift": [
                        r["name"] for r in drift_rows if r["drift"]],

                    "config": {
                        **CFG.fingerprint(),
                        "min_chunk_chars": CFG.min_chunk_chars,
                        "top_k": CFG.top_k,
                        "score_threshold": CFG.score_threshold,
                        "use_mmr": CFG.use_mmr,
                        "reorder_context": CFG.reorder_context,
                        "auto_briefing": CFG.auto_briefing,
                        "briefing_model": CFG.briefing_model,
                    },
                })

            if path == "/index/status":
                pid = (q.get("project_id") or [None])[0]
                if not pid:
                    return self._send(400, {"error": "project_id required"})
                return self._send(200, indexer.get_state(pid))

            if path == "/index/exists":
                pid = (q.get("project_id") or [None])[0]
                if not pid:
                    return self._send(400, {"error": "project_id required"})
                return self._send(200, indexer.has_index(pid))

            if path == "/profiles":
                return self._send(200, {"profiles": profiles.list_profiles()})

            # ── 브리핑 원문 (.md) ───────────────────────────
            # 프론트가 마크다운을 그대로 받아 렌더하는 용도입니다.
            # references·structure 같은 구조 정보가 필요하면 /briefing (JSON) 을 쓰세요.
            if path == "/briefing.md":
                pid = (q.get("project_id") or [None])[0]
                if not pid:
                    return self._send(400, {"error": "project_id required"})
                md = briefing.md_path(pid)
                if not md.exists():
                    return self._send(404, {
                        "error": "not_found", "project_id": pid,
                        "detail": "아직 생성되지 않았습니다. POST /briefing 으로 만드세요."})
                return self._send_text(200, md.read_text(encoding="utf-8"))

            if path == "/briefing":
                pid = (q.get("project_id") or [None])[0]
                if not pid:
                    return self._send(400, {"error": "project_id required"})
                rec = briefing.load(pid)
                if not rec:
                    return self._send(404, {"error": "not_generated",
                                            "project_id": pid})
                # 인덱스가 그 사이 갱신됐는지 알려줍니다.
                # ⚠ 자동 재생성은 하지 않습니다 — 커밋마다 23초 생성은 낭비이고,
                #    LLM 은 비결정적이라 코드가 안 바뀌어도 문장이 달라집니다.
                st = indexer.get_state(pid)
                rec["index_commit"] = st.get("commit")
                rec["outdated"] = bool(
                    rec.get("commit") and st.get("commit")
                    and rec["commit"] != st["commit"])
                return self._send(200, rec)

            # ── 인덱싱된 프로젝트 목록 ──────────────────────
            # 프론트가 "어떤 프로젝트를 인덱싱해뒀는지" 화면에 보여주기 위한
            # 엔드포인트입니다. 목록에서 골라 질문하거나, 갱신을 요청할 수
            # 있게 하려면 이 정보가 필요합니다.
            if path == "/projects":
                store = get_store()
                live_projects = set(store.projects())
                out = []
                for st in indexer.list_projects():
                    pid = st.get("project_id")
                    if not pid:
                        continue
                    root = st.get("project_root")

                    # 인덱스가 낡았는지 — git commit 비교
                    stale = None
                    if root and st.get("state") == "done":
                        try:
                            # 질의·증분은 저장된 프로젝트 프로필을 쓰므로 전역 CFG
                            # 차이를 source outdated로 표시하지 않습니다.
                            stale = indexer.is_stale(root, pid, compare_config=False)
                        except Exception:
                            stale = None

                    serving_profile = (searcher.serving_profile(store, pid)
                                       if pid in live_projects else None)
                    out.append({
                        "project_id": pid,
                        "name": (Path(root).name if root else pid),
                        "project_root": root,
                        "state": st.get("state", "none"),
                        "chunk_count": st.get("chunk_count", 0),
                        "actual_chunks": (store.count(pid) if pid in live_projects else 0),
                        "indexed_at": st.get("indexed_at"),
                        "commit": st.get("commit"),
                        "dirty": st.get("dirty"),
                        "elapsed_s": st.get("elapsed_s"),
                        "last_mode": st.get("last_mode", "full"),
                        "profile_id": st.get("profile_id"),
                        "profile_hash": st.get("profile_hash"),
                        "processed": st.get("processed"),
                        "total": st.get("total"),
                        "error": st.get("error"),
                        "has_briefing": briefing.load(pid) is not None,
                        "briefing": st.get("briefing"),
                        "briefing_error": st.get("briefing_error"),
                        "outdated": bool(stale and stale.get("stale")),
                        "outdated_reason": (stale or {}).get("reason"),
                        "fingerprint": serving_profile,
                        "serving_profile": serving_profile,
                    })

                # 인덱싱 안 된 컬렉션도 노출 (state.json 이 지워진 경우 등)
                known = {o["project_id"] for o in out}
                for pid in live_projects:
                    if pid not in known:
                        out.append({
                            "project_id": pid, "name": pid,
                            "state": "orphan",        # 인덱스는 있는데 상태 기록이 없음
                            "chunk_count": 0,
                            "actual_chunks": store.count(pid),
                            "has_briefing": briefing.load(pid) is not None,
                            "briefing": None,
                            "briefing_error": None,
                            "serving_profile": store.index_fingerprint(pid),
                        })

                out.sort(key=lambda x: (x.get("indexed_at") or ""), reverse=True)
                return self._send(200, {"projects": out, "count": len(out)})

            return self._send(404, {"error": "not found", "path": path})

        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        try:
            if not self._auth_ok():
                return self._send(401, {"error": "unauthorized"})

            path = urlparse(self.path).path.rstrip("/") or "/"
            body = self._body()

            # ── 인덱싱 시작 (FN-A01) ─────────────────────────
            if path == "/index":
                root = body.get("project_root")
                pid = body.get("project_id")
                if not root or not pid:
                    return self._send(400, {"error": "project_root, project_id required"})

                selected = None
                if body.get("profile"):
                    try:
                        selected = profiles.resolve_profile(str(body["profile"]))
                    except profiles.ProfileError as e:
                        return self._send(400, {"error": "invalid_profile", "detail": str(e)})

                # ⚠ 브리핑은 LLM 을 씁니다. indexer 는 그 사실을 모르고,
                #    서버가 콜백으로 주입합니다 (C' 구조 유지).
                #    실패해도 인덱싱 state 는 done 으로 남습니다.
                # 제품용 전체 인덱싱은 브리핑까지가 완료 계약입니다.
                # 과거 no_briefing 필드는 호환상 받아도 더는 생성을 건너뛰지 않습니다.
                hook = _briefing_hook(
                    body.get("model", CFG.briefing_model),
                    body.get("ollama_url", CFG.ollama_url),
                )

                r = indexer.start_index(root, pid, blocking=False,
                                        force=bool(body.get("force")),
                                        on_done=hook,
                                        profile=(selected or {}).get("fingerprint"),
                                        profile_id=(selected or {}).get("profile_id"),
                                        profile_hash=(selected or {}).get("profile_hash"))
                return self._send(202 if r.get("accepted") else 409, r)

            # ── 프론트 snapshot 기반 증분 인덱싱 ─────────────
            # 변경 파일의 최종 전체 문자열을 받아 로컬 Git 작업 트리 없이 갱신합니다.
            if path == "/index/update/files":
                result = indexer.start_payload_update(body, blocking=False)
                if result.get("ok"):
                    code = 200 if result.get("already_applied") else 202
                else:
                    code = 409 if result.get("conflict") else 400
                return self._send(code, result)

            # ── 로컬 Git 기반 증분 인덱싱 ────────────────────
            # 바뀐 파일만 다시 처리합니다. 보통 몇 초면 끝납니다.
            # ⚠ 불가능하면 실행하지 않고 이유를 돌려줍니다.
            #    전체 인덱싱(55분)이 예고 없이 시작되지 않도록 하기 위함입니다.
            if path == "/index/update":
                pid = body.get("project_id")
                if not pid:
                    return self._send(400, {"error": "project_id required"})
                root = body.get("project_root") or \
                    indexer.get_state(pid).get("project_root")
                if not root:
                    return self._send(400, {"error": "project_root_unknown"})

                if body.get("dry_run"):
                    return self._send(200, indexer.preview_update(root, pid))

                r = indexer.start_update(root, pid, blocking=False,
                                         force=bool(body.get("force")))
                return self._send(202 if r.get("ok") else 409, r)

            # ── 검색 (FN-B02) ───────────────────────────────
            if path == "/search":
                query = body.get("query")
                pid = body.get("project_id")
                if not query or not pid:
                    return self._send(400, {"error": "query, project_id required"})

                r = searcher.search(
                    query, pid,
                    top_k=body.get("top_k"),
                    threshold=body.get("threshold"),
                    store=get_store(),
                )
                # all_hits 는 디버깅용이라 기본 제외 (응답 크기 절감)
                if not body.get("include_all_hits"):
                    r.pop("all_hits", None)
                return self._send(200, r)

            # ── 검색 + 프롬프트 조립 ─────────────────────────
            # LLM 호출은 백엔드가 합니다. 여기서는 messages 만 만듭니다.
            #
            # ⚠ 이 엔드포인트는 TTFT 임계 경로에 있습니다.
            #    P 가 여기 응답을 받아야 Ollama 호출을 시작할 수 있으므로,
            #    여기서 쓴 시간이 그대로 첫 글자 지연에 더해집니다.
            #    timing 필드로 항상 계측값을 돌려줍니다.
            if path == "/prompt":
                t_start = time.perf_counter()
                query = body.get("query")
                pid = body.get("project_id")
                if not query or not pid:
                    return self._send(400, {"error": "query, project_id required"})

                r = searcher.search(query, pid, top_k=body.get("top_k"),
                                    threshold=body.get("threshold"),
                                    store=get_store())
                r.pop("all_hits", None)

                # 생성 전 미리보기용 출처. LLM 답변이 없으므로 cited 는 비어 있고,
                # 인용 여부와 무관하게 검색된 전부가 들어갑니다.
                # 스트리밍 시작 전에 프론트가 출처 영역을 그릴 수 있습니다.
                pre = references.build_references(
                    r["contexts"], answer=None, cited_only=False,
                    include_text=bool(body.get("include_text")),
                )

                # light=true 면 sources 에서 청크 원문을 뺍니다.
                # 원문은 이미 messages 안에 들어 있어 중복이고,
                # /finalize 는 path·line 만 있으면 동작합니다.
                light = body.get("light", True)
                if light:
                    sources = [{k: v for k, v in c.items() if k != "text"}
                               for c in r["contexts"]]
                else:
                    sources = r["contexts"]

                timing = dict(r.get("timing") or {})
                timing["total_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

                # 단계 표시(FN-B05)용 메타데이터.
                # 실제 단계 전환 신호는 P가 만듭니다 — /prompt 는 345ms 안에
                # 끝나므로 내부 단계를 쪼개 보내도 사용자가 볼 시간이 없습니다.
                # 여기서는 P가 문구에 넣을 "숫자"만 제공합니다.
                n_chunks = len(r["contexts"])
                n_files = len(pre["reference_files"])
                stage = {
                    "retrieved": n_chunks,
                    "files": n_files,
                    "top_score": r["top_score"],
                    "threshold": r["threshold"],
                    # 프론트가 그대로 써도 되고, 직접 조립해도 됩니다
                    "label": (f"근거 {n_chunks}건 확인"
                              + (f" ({n_files}개 파일)" if n_files > 1 else "")
                              if r["has_evidence"] else "관련 근거를 찾지 못했습니다"),
                }

                return self._send(200, {
                    "has_evidence": r["has_evidence"],
                    "messages": searcher.render_prompt(query, r["contexts"]),
                    "sources": sources,                # /finalize 에 되돌려줄 것
                    "references": pre["references"],
                    "reference_files": pre["reference_files"],
                    "stage": stage,                    # 단계 문구용
                    "top_score": r["top_score"],
                    "threshold": r["threshold"],
                    "serving_profile": r["serving_profile"],
                    "bm25_active": r.get("bm25_active", False),
                    "timing": timing,                  # ⚠ TTFT 예산 확인용
                })

            # ── 답변 후처리 ─────────────────────────────────
            # LLM 생성이 끝난 뒤, answer 와 references 를 분리해 돌려줍니다.
            # sources 는 /prompt 에서 받은 것을 그대로 되돌려주세요.
            if path == "/finalize":
                answer = body.get("answer")
                sources = body.get("sources")
                if answer is None or sources is None:
                    return self._send(400, {"error": "answer, sources required"})

                return self._send(200, searcher.finalize(
                    answer, sources,
                    cited_only=body.get("cited_only", True),
                    include_text=bool(body.get("include_text")),
                ))

            # ── 브리핑 생성 (FN-A05) ────────────────────────
            # ⚠ rag_lab 이 LLM 을 호출하는 유일한 지점입니다 (C' 구조).
            #    model 과 ollama_url 을 백엔드가 주입하므로, fine-tuned 모델로
            #    교체할 때 백엔드 한 곳만 고치면 브리핑도 따라갑니다.
            if path == "/briefing":
                pid = body.get("project_id")
                if not pid:
                    return self._send(400, {"error": "project_id required"})

                if not body.get("force"):
                    cached = briefing.load(pid)
                    if cached:
                        cached["cached"] = True
                        return self._send(200, cached)

                st = indexer.get_state(pid)
                root = body.get("project_root") or st.get("project_root")
                if not root:
                    return self._send(400, {
                        "error": "project_root_unknown",
                        "detail": "인덱싱 이력이 없습니다. project_root 를 함께 보내주세요."})

                model = body.get("model", "qwen2.5-coder:7b")
                url = body.get("ollama_url", CFG.ollama_url)

                r = briefing.build(root, pid, model, url, commit=st.get("commit"))
                if not r.get("ok"):
                    # no_material / no_evidence 는 오류가 아니라 정상 결과입니다.
                    # 문서가 부실한 레포에서 지어내는 것보다 낫습니다.
                    return self._send(200, r)
                return self._send(200, r)

            return self._send(404, {"error": "not found", "path": path})

        except searcher.ProjectNotFoundError as e:
            return self._send(404, {"error": "project_not_found", "detail": str(e)})
        except embedder.EmbeddingError as e:
            traceback.print_exc()
            return self._send(503, {"error": "embedding_unavailable", "detail": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    global TOKEN
    ap = argparse.ArgumentParser(description="rag_lab HTTP 서버")
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 으로 하면 같은 LAN 에서 접근 가능")
    ap.add_argument("--port", type=int, default=8200)
    ap.add_argument("--token", default=None,
                    help="설정하면 X-VSS-Token 헤더 검사")
    args = ap.parse_args()
    TOKEN = args.token

    print("=" * 58)
    print(f"  rag_lab server   http://{args.host}:{args.port}")
    print(f"  Ollama           {CFG.ollama_url}")
    print(f"  index_dir        {CFG.index_dir}")
    print(f"  auth             {'ON (X-VSS-Token)' if TOKEN else 'OFF'}")
    print("=" * 58)
    print("  GET  /health")
    print("  GET  /index/status?project_id=...")
    print("  GET  /index/exists?project_id=...")
    print("  GET  /projects")
    print("  GET  /profiles")
    print("  POST /index    {project_root, project_id, profile?, force?}")
    print("  POST /index/update {project_id, dry_run?}  (로컬 Git)")
    print("  POST /index/update/files {project_id, base_revision, target_revision, files, ...}")
    print("  POST /search   {query, project_id, top_k?, threshold?}")
    print("  POST /prompt   {query, project_id}")
    print("  POST /finalize {answer, sources}")
    print("  POST /briefing {project_id, model?, ollama_url?, force?}")
    print("  GET  /briefing?project_id=...")
    print("  GET  /briefing.md?project_id=...   (마크다운 원문)")
    print("=" * 58)

    # ⚠ 워밍업 — 하지 않으면 첫 /prompt 요청이 수 초 걸립니다.
    #    Chroma 인덱스 로드 + 임베딩 모델 적재가 그때 일어나기 때문입니다.
    #    TTFT 임계 경로이므로 기동 시 미리 끝내둡니다.
    print("  워밍업 중...")
    try:
        t = time.perf_counter()
        st = get_store()
        projects = st.projects()
        print(f"    인덱스 로드   {(time.perf_counter()-t)*1000:>7.0f} ms  {projects}")

        # ⚠ 미완성 컬렉션은 **경고만** 합니다. 자동으로 지우지 않습니다.
        #    cli.py 가 별도 프로세스에서 인덱싱 중일 수 있습니다.
        #    정리는 `python repair_collections.py --apply` 로 명시적으로 하세요.
        inc = st.incomplete()
        if inc:
            print("    ⚠ 미완성 인덱스가 있습니다 (조회 대상 아님):")
            for it in inc:
                age = f"{it['age_s']:.0f}s 전 시작" if it["age_s"] else "시작 시각 미상"
                print(f"       {it['name']:24s} {it['chunks']:>7,}청크  {age}")
            print("       진행 중이 아니라면:  python repair_collections.py --apply")

        # 인덱스 지문 ↔ 다음 전체 인덱싱 기본값(CFG) 대조.
        # 질의와 증분은 프로젝트별 저장 프로필을 쓰므로 이 차이는 서빙 오류가 아닙니다.
        rows = diagnose.drift_summary(st)
        drifted = [r for r in rows if r["drift"]]
        if drifted:
            print("    ℹ 프로젝트 프로필과 다음 전체 인덱싱 기본값이 다릅니다:")
            for r in drifted:
                for k, (iv, cv) in r["drift"].items():
                    print(f"       {r['name']:16s} {k}: 인덱스={iv}  CFG={cv}")
            print("       → 현재 질의·증분은 각 프로젝트의 저장 프로필을 사용합니다.")
            print("       → CFG는 새 전체 인덱싱을 시작할 때만 사용합니다.")
            print("       자세히:  python cli.py doctor")
    except Exception as e:
        print(f"    !! 인덱스 로드 실패: {e}")
    try:
        t = time.perf_counter()
        embedder.embed_one("warmup")
        print(f"    임베딩 워밍업 {(time.perf_counter()-t)*1000:>7.0f} ms")
    except Exception as e:
        print(f"    !! 임베딩 워밍업 실패: {e}")
        print("       터널을 확인하세요:  netstat -ano | findstr 11500")
    print("=" * 58)

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
