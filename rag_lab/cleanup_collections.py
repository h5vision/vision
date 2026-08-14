#!/usr/bin/env python3
"""
Chroma 컬렉션 청소 — 고아 · 실패 잔존 컬렉션 제거.

⚠ 이 스크립트는 md 가 직접 실행합니다.
   Chroma 는 PersistentClient 가 sqlite 를 잡고 있어서,
   서버가 떠 있는 상태에서 외부 프로세스가 건드리면 인덱스가 깨질 수 있습니다.
   **rag_lab 서버를 먼저 내리고 실행하세요.**

사용법
    python cleanup_collections.py            # 무엇을 지울지 보여주기만 함 (dry-run)
    python cleanup_collections.py --apply    # 실제 삭제

근거: PROJECT_ID_OPTIONS_20260812.md §4-1
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from vss_rag.config import CFG

# 삭제 대상과 사유 ─────────────────────────────────────────────
TARGETS = {
    "fest-api": "고아. state.json 에 없음. 201청크 = 중단된 run (fest-api-v2 로 대체됨)",
    "fest-api-c600": "고아. state.json 에 없음. 200청크 = 중단된 run. 21,104청크와 비교 불가",
    "sqlmodel": "고아. 0청크 빈 껍데기. get_or_create 자동 생성 흔적으로 추정",
    "sqlalchemy-v2": "state=failed(429/692). 반쪽 인덱스가 살아서 검색됨 — 가장 위험",
}

KEEP = {"fastapi-cli", "fest-api-v2", "sqlalchemy"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 삭제")
    args = ap.parse_args()

    try:
        import chromadb
    except ImportError:
        print("!! chromadb 가 없습니다. .venv 를 활성화하고 실행하세요.")
        return 1

    path = Path(CFG.index_dir).resolve()
    print(f"인덱스: {path}\n")

    client = chromadb.PersistentClient(path=str(path))
    cols = {c.name: c for c in client.list_collections()}

    # ── 현황 ──────────────────────────────────────────────
    print(f"{'컬렉션':20s} {'청크':>9s}  조치")
    print("-" * 60)
    total_before = total_delete = 0
    plan: list[str] = []

    for name in sorted(cols):
        n = cols[name].count()
        total_before += n
        if name in TARGETS:
            plan.append(name)
            total_delete += n
            print(f"{name:20s} {n:9,}  🔴 삭제 — {TARGETS[name]}")
        elif name in KEEP:
            print(f"{name:20s} {n:9,}  ✅ 유지")
        else:
            print(f"{name:20s} {n:9,}  ⚠ 목록에 없는 컬렉션 — 확인 필요. 건드리지 않음")

    unknown_targets = set(TARGETS) - set(cols)
    if unknown_targets:
        print(f"\n⚠ 삭제 대상인데 존재하지 않음 (이미 지워졌거나 이름이 다름): {sorted(unknown_targets)}")

    print("-" * 60)
    print(f"{'현재':20s} {total_before:9,}")
    print(f"{'삭제 예정':20s} {total_delete:9,}")
    print(f"{'남는 것':20s} {total_before - total_delete:9,}\n")

    if not plan:
        print("삭제할 것이 없습니다.")
        return 0

    if not args.apply:
        print("dry-run 입니다. 실제로 지우려면 --apply 를 붙이세요.")
        return 0

    # ── 실행 ──────────────────────────────────────────────
    print("🔴 되돌릴 수 없습니다. 서버를 내렸는지 확인하세요.")
    if input("계속하려면 정확히 'DELETE' 입력: ").strip() != "DELETE":
        print("취소했습니다.")
        return 1

    log = {"executed_at": datetime.now().isoformat(), "deleted": []}
    for name in plan:
        n = cols[name].count()
        client.delete_collection(name)
        log["deleted"].append({"name": name, "embeddings": n, "reason": TARGETS[name]})
        print(f"  삭제됨  {name}  ({n:,}청크)")

    logp = path.parent.parent / f"cleanup_log_{datetime.now():%Y%m%d_%H%M%S}.json"
    logp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n기록: {logp}")

    remain = sum(c.count() for c in client.list_collections())
    print(f"남은 컬렉션 청크 합계: {remain:,}")

    print("\n⚠ 다음 할 일")
    print("  1. state.json 에서 sqlalchemy-v2 항목 제거 (failed 기록)")
    print("  2. data/index/ 아래 고아 세그먼트 디렉터리는 Chroma 가 정리합니다.")
    print("     즉시 안 줄면 서버 재기동 후 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
