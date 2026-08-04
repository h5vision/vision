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
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from vss_rag.config import CFG
from vss_rag import embedder, indexer, references, searcher
from vss_rag.store import Store

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
                return self._send(200, {
                    "ok": True,
                    "ollama": CFG.ollama_url,
                    "embed_model": CFG.embed_model,
                    "index_dir": CFG.index_dir,
                    "projects": get_store().projects(),
                    "config": {
                        "chunk_size": CFG.chunk_size,
                        "chunk_overlap": CFG.chunk_overlap,
                        "top_k": CFG.top_k,
                        "score_threshold": CFG.score_threshold,
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

            if path == "/projects":
                return self._send(200, {"projects": indexer.list_projects()})

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

                r = indexer.start_index(root, pid, blocking=False,
                                        force=bool(body.get("force")))
                return self._send(202 if r.get("accepted") else 409, r)

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
            if path == "/prompt":
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

                return self._send(200, {
                    "has_evidence": r["has_evidence"],
                    "messages": searcher.render_prompt(query, r["contexts"]),
                    "sources": r["contexts"],          # 하위 호환
                    "references": pre["references"],
                    "reference_files": pre["reference_files"],
                    "top_score": r["top_score"],
                    "threshold": r["threshold"],
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

            return self._send(404, {"error": "not found", "path": path})

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
    print("  POST /index    {project_root, project_id, force?}")
    print("  POST /search   {query, project_id, top_k?, threshold?}")
    print("  POST /prompt   {query, project_id}")
    print("  POST /finalize {answer, sources}")
    print("=" * 58)

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
