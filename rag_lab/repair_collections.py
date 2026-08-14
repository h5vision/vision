#!/usr/bin/env python3
"""
Chroma 네임스페이스 복구 — 잘못 조회되는 컬렉션 문제를 고칩니다.

⚠ **rag_lab 서버를 먼저 내리고 실행하세요.**
   Chroma PersistentClient 가 sqlite 를 잡고 있어서 동시 접근 시 인덱스가 깨질 수 있습니다.

사용법
    python repair_collections.py            # 진단만 (dry-run)
    python repair_collections.py --apply    # 실제 수정

무엇을 고치나
    ① fest-api-v2  →  fest-api  로 이름 변경   (폴더명과 일치시킴)
    ② 중단된 run 이 남긴 고아 컬렉션 삭제
    ③ state.json 키 동기화 (+ 백업)

근거: 폴더는 C:\\Pj\\fest-api 인데 정상 인덱스는 fest-api-v2 로 저장돼 있어,
      폴더명으로 조회하면 40파일(1.5%)짜리 중단 run 이 걸립니다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from vss_rag.config import CFG

# ── 계획 ─────────────────────────────────────────────────────
RENAMES = {
    # 현재이름: 새이름
    # 2026-08-13: fest-api-v3(ctx_header·bm25 적용본)를 폴더명 fest-api 로 승격.
    #             구 fest-api(구 설정)를 지우고 자리를 내줍니다.
    "fest-api-v3": "fest-api",
}

DELETES = {
    "fest-api": "구 설정본(context_header=False · use_bm25=False). fest-api-v3 로 대체됨",
}

KEEP = {"fastapi-cli", "sqlalchemy"}


def collection_stats(client, name):
    """청크 수 + 고유 파일 수."""
    try:
        col = client.get_collection(name)
    except Exception:
        return None
    n = col.count()
    try:
        got = col.get(include=["metadatas"], limit=n or 1)
        paths = {m.get("path") for m in (got.get("metadatas") or []) if m}
        paths.discard(None)
    except Exception:
        paths = set()
    return {"chunks": n, "files": len(paths)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        import chromadb
    except ImportError:
        print("!! chromadb 가 없습니다. .venv 를 활성화하세요.")
        return 1

    index_dir = Path(CFG.index_dir).resolve()
    state_path = Path(CFG.state_path).resolve()
    print(f"인덱스   {index_dir}")
    print(f"상태파일 {state_path}\n")

    client = chromadb.PersistentClient(path=str(index_dir))
    existing = {c.name for c in client.list_collections()}

    # ── 진단 ──────────────────────────────────────────────
    print(f"{'컬렉션':18s} {'청크':>8s} {'파일':>7s}  조치")
    print("-" * 72)
    for name in sorted(existing):
        s = collection_stats(client, name) or {"chunks": "?", "files": "?"}
        if name in RENAMES:
            act = f"🔵 이름변경 → {RENAMES[name]}"
        elif name in DELETES:
            act = f"🔴 삭제 — {DELETES[name]}"
        elif name in KEEP:
            act = "✅ 유지"
        else:
            act = "⚠ 계획에 없음 — 건드리지 않음"
        print(f"{name:18s} {s['chunks']:>8,} {s['files']:>7,}  {act}"
              if isinstance(s["chunks"], int) else
              f"{name:18s} {'?':>8s} {'?':>7s}  {act}")
    print("-" * 72)

    # ── 순서 검증 ─────────────────────────────────────────
    problems = []
    for old, new in RENAMES.items():
        if old not in existing:
            problems.append(f"이름변경 원본 없음: {old}")
        if new in existing and new not in DELETES:
            problems.append(f"이름변경 대상이 이미 있고 삭제 목록에도 없음: {new}")
    if problems:
        print("\n🔴 계획에 문제가 있습니다. 중단합니다.")
        for p in problems:
            print("   -", p)
        return 1

    if not args.apply:
        print("\ndry-run 입니다. 실제 적용은 --apply")
        print("⚠ 적용 전에 rag_lab 서버를 반드시 내리세요.")
        return 0

    print("\n🔴 되돌릴 수 없습니다. 서버를 내렸는지 확인하세요.")
    if input("계속하려면 정확히 'REPAIR' 입력: ").strip() != "REPAIR":
        print("취소했습니다.")
        return 1

    log = {"executed_at": datetime.now().isoformat(), "deleted": [], "renamed": []}

    # ── ① 삭제 (rename 자리 확보를 위해 먼저) ──────────────
    for name, reason in DELETES.items():
        if name not in existing:
            continue
        s = collection_stats(client, name) or {}
        client.delete_collection(name)
        log["deleted"].append({"name": name, **s, "reason": reason})
        print(f"  삭제    {name}  ({s.get('chunks', '?'):,}청크)")

    # ── ② 이름 변경 ────────────────────────────────────────
    for old, new in RENAMES.items():
        col = client.get_collection(old)
        col.modify(name=new)
        log["renamed"].append({"from": old, "to": new})
        print(f"  이름변경 {old} → {new}")

    # ── ③ state.json 동기화 ────────────────────────────────
    if state_path.exists():
        backup = state_path.with_name(f"state.backup_{datetime.now():%Y%m%d_%H%M%S}.json")
        shutil.copy2(state_path, backup)
        print(f"  state 백업 → {backup.name}")

        data = json.loads(state_path.read_text(encoding="utf-8"))
        for old, new in RENAMES.items():
            if old in data:
                entry = data.pop(old)
                entry["project_id"] = new
                data[new] = entry
                print(f"  state 키   {old} → {new}")
        for name in DELETES:
            if name in data and name not in RENAMES.values():
                data.pop(name)
                print(f"  state 제거 {name}")
        state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    # ── ④ 부수 파일 확인 ───────────────────────────────────
    bm25_dir = index_dir.parent / "bm25"
    brief_dir = CFG.briefings_dir()
    for old, new in RENAMES.items():
        for d, exts in ((bm25_dir, [".json"]), (brief_dir, [".json", ".md"])):
            for ext in exts:
                src = d / f"{old}{ext}"
                if src.exists():
                    src.rename(d / f"{new}{ext}")
                    print(f"  파일이동 {src.name} → {new}{ext}")

    logp = index_dir.parent.parent / f"repair_log_{datetime.now():%Y%m%d_%H%M%S}.json"
    logp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록: {logp}")

    print("\n남은 컬렉션:")
    for c in sorted(client.list_collections(), key=lambda x: x.name):
        print(f"  {c.name:18s} {c.count():>8,}")

    print("\n⚠ 다음 확인")
    print("  1. 서버 재기동 후 GET /projects 로 fest-api 가 21,104청크인지 확인")
    print("  2. GET /health 의 config 에서 use_bm25 · use_mmr 상태 확인")
    print("  3. fest-api 는 BM25 역색인이 없습니다. 필요하면 재인덱싱(약 57분)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
