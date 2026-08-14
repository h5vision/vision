#!/usr/bin/env python3
"""프로필×검색조건×질문세트를 재현 가능하게 실행하는 매트릭스 CLI."""

from __future__ import annotations

import argparse
import json
import sys

from vss_rag.experiments.runner import (
    make_plan, run_matrix, validate_matrix, write_report,
)
from vss_rag.experiments.suite import ValidationError


def _print_validation(spec: dict) -> None:
    print(f"OK  matrix={spec['matrix']['name']}  hash={spec['matrix_hash']}")
    print(f"    repository={spec['repository']}")
    print(f"    suite={spec['suite_path']}  questions={len(spec['questions'])}  hash={spec['suite_hash']}")
    print(f"    profiles={', '.join(spec['profiles'])}  cells={len(spec['cells'])}")
    for w in spec.get("warnings", []):
        print(f"WARN {w}")


def cmd_validate(args) -> int:
    _print_validation(validate_matrix(args.matrix))
    return 0


def cmd_plan(args) -> int:
    p = make_plan(args.matrix)
    _print_validation(p)
    print(f"    commit={p['commit'] or '(확인 불가)'}  dirty={p['dirty']}")
    print(f"    예상 질의 실행={p['query_invocations']}회")
    print()
    print(f"{'profile':<9} {'project_id':<32} {'action':<8} {'chunks':>8} {'BM25':>8}")
    print("-" * 74)
    for i in p["indexes"]:
        bm = "-" if i["bm25_count"] is None else str(i["bm25_count"])
        print(f"{i['profile_id']:<9} {i['project_id']:<32} {i['action']:<8} "
              f"{i['chunks']:>8} {bm:>8}")
    print("\n실행 셀:")
    for c in p["cells"]:
        print(f"  {c['index_profile']}/{c['search_profile']}  modes={','.join(c['modes'])}")
    return 0


def cmd_run(args) -> int:
    path, result = run_matrix(args.matrix, allow_index=args.allow_index, output=args.output)
    print(f"완료: {path}")
    print(f"run_id={result['run_id']}  cells={len(result['cells'])}")
    return 0


def cmd_report(args) -> int:
    path = write_report(args.target, output=args.output)
    print(f"보고서: {path}")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="rag_lab 평가 매트릭스")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate"); p.add_argument("matrix"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("plan"); p.add_argument("matrix"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("run"); p.add_argument("matrix"); p.set_defaults(fn=cmd_run)
    p.add_argument("--allow-index", action="store_true", help="필요한 전체 인덱싱을 명시적으로 허용")
    p.add_argument("--output")
    p = sub.add_parser("report"); p.add_argument("target", help="matrix 또는 result JSON")
    p.add_argument("--output"); p.set_defaults(fn=cmd_report)
    args = ap.parse_args()
    try:
        return args.fn(args)
    except ValidationError as e:
        for msg in e.errors:
            print(f"ERROR {msg}")
        for msg in e.warnings:
            print(f"WARN  {msg}")
        return 2
    except Exception as e:
        print(f"ERROR {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
