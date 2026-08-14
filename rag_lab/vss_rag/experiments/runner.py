from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .. import indexer, lexical, profiles, searcher
from ..embedder import embed_one
from ..store import Store
from .metrics import by_tag, summarize
from .suite import ValidationError, canonical_hash, first_gold_rank, load_questions


ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "data" / "evaluation" / "runs"
REPORTS_DIR = ROOT / "data" / "evaluation" / "reports"


def _read_matrix(path: str | Path) -> tuple[Path, dict]:
    p = Path(path).resolve()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ValidationError([f"matrix 파일이 없습니다: {p}"]) from e
    except json.JSONDecodeError as e:
        raise ValidationError([f"matrix JSON 파싱 실패: {p}:{e.lineno}: {e.msg}"]) from e
    return p, data


def validate_matrix(path: str | Path) -> dict:
    p, matrix = _read_matrix(path)
    errors: list[str] = []
    warnings: list[str] = []
    required = {"schema_version", "name", "repository", "suite", "index_profiles",
                "search_profiles", "cells"}
    if not isinstance(matrix, dict):
        raise ValidationError(["matrix 최상위는 JSON 객체여야 합니다"])
    missing = required - set(matrix)
    if missing:
        errors.append(f"matrix 필수 필드 누락: {', '.join(sorted(missing))}")
    if matrix.get("schema_version") != "1.0":
        errors.append("matrix schema_version은 1.0이어야 합니다")
    unknown_matrix = sorted(set(matrix) - (required | {"require_clean"}))
    if unknown_matrix:
        errors.append(f"matrix의 알 수 없는 필드: {', '.join(unknown_matrix)}")

    repo = Path(str(matrix.get("repository", "")))
    if not repo.is_absolute():
        repo = (p.parent / repo).resolve()
    else:
        repo = repo.resolve()
    if not repo.is_dir():
        errors.append(f"repository가 디렉터리가 아닙니다: {repo}")
    suite = Path(str(matrix.get("suite", "")))
    suite = (p.parent / suite).resolve() if not suite.is_absolute() else suite.resolve()

    resolved_profiles: dict[str, dict] = {}
    ids = matrix.get("index_profiles")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        errors.append("index_profiles는 중복 없는 비어 있지 않은 배열이어야 합니다")
        ids = []
    for pid in ids:
        try:
            resolved_profiles[pid] = profiles.resolve_profile(str(pid))
        except profiles.ProfileError as e:
            errors.append(str(e))

    # rag-v1→v2는 BM25 하나, v2→v3는 context_header 하나만 달라야 합니다.
    if all(k in resolved_profiles for k in ("rag-v1", "rag-v2", "rag-v3")):
        def changed(a, b):
            fa, fb = resolved_profiles[a]["fingerprint"], resolved_profiles[b]["fingerprint"]
            return {k for k in fa if fa[k] != fb[k]}
        if changed("rag-v1", "rag-v2") != {"use_bm25"}:
            errors.append("rag-v1→rag-v2는 use_bm25 하나만 달라야 합니다")
        if changed("rag-v2", "rag-v3") != {"context_header"}:
            errors.append("rag-v2→rag-v3는 context_header 하나만 달라야 합니다")

    search_by_name: dict[str, dict] = {}
    searches = matrix.get("search_profiles")
    if not isinstance(searches, list) or not searches:
        errors.append("search_profiles는 비어 있지 않은 배열이어야 합니다")
        searches = []
    for item in searches:
        if not isinstance(item, dict) or not item.get("name"):
            errors.append("각 search_profile에는 name이 필요합니다")
            continue
        name = str(item["name"])
        unknown_search = sorted(set(item) - {
            "name", "use_bm25", "pool", "top_k", "threshold",
            "use_mmr", "mmr_lambda", "reorder"})
        if unknown_search:
            errors.append(f"search_profile {name}의 알 수 없는 필드: {', '.join(unknown_search)}")
        if name in search_by_name:
            errors.append(f"중복 search_profile: {name}")
            continue
        for key in ("use_bm25", "pool", "top_k", "threshold"):
            if key not in item:
                errors.append(f"search_profile {name}에 {key}가 없습니다")
        if item.get("pool", 0) < item.get("top_k", 0):
            errors.append(f"search_profile {name}: pool은 top_k 이상이어야 합니다")
        search_by_name[name] = {
            "name": name,
            "use_bm25": bool(item.get("use_bm25")),
            "pool": int(item.get("pool", 20)),
            "top_k": int(item.get("top_k", 4)),
            "threshold": float(item.get("threshold", 0.54)),
            "use_mmr": bool(item.get("use_mmr", False)),
            "mmr_lambda": float(item.get("mmr_lambda", 0.7)),
            "reorder": bool(item.get("reorder", False)),
        }

    cells: list[dict] = []
    seen_cells: set[tuple] = set()
    for i, cell in enumerate(matrix.get("cells") or [], 1):
        if not isinstance(cell, dict):
            errors.append(f"cell[{i}]은 객체여야 합니다")
            continue
        ip, sp = cell.get("index_profile"), cell.get("search_profile")
        unknown_cell = sorted(set(cell) - {"index_profile", "search_profile", "modes"})
        if unknown_cell:
            errors.append(f"cell[{i}]의 알 수 없는 필드: {', '.join(unknown_cell)}")
        modes = cell.get("modes")
        if ip not in resolved_profiles:
            errors.append(f"cell[{i}]의 알 수 없는 index_profile: {ip}")
        if sp not in search_by_name:
            errors.append(f"cell[{i}]의 알 수 없는 search_profile: {sp}")
        if not isinstance(modes, list) or not modes or set(modes) - {"retrieval", "pipeline"}:
            errors.append(f"cell[{i}] modes는 retrieval/pipeline 배열이어야 합니다")
            modes = []
        key = (ip, sp, tuple(modes))
        if key in seen_cells:
            errors.append(f"중복 cell: {ip}/{sp}")
        seen_cells.add(key)
        if (ip in resolved_profiles and sp in search_by_name
                and search_by_name[sp]["use_bm25"]
                and not resolved_profiles[ip]["fingerprint"]["use_bm25"]):
            errors.append(f"{ip}/{sp}: BM25를 만들지 않은 인덱스에서 hybrid 검색을 요청했습니다")
        cells.append({"index_profile": ip, "search_profile": sp, "modes": modes})
    if not cells:
        errors.append("실행할 cell이 없습니다")

    questions: list[dict] = []
    if repo.is_dir():
        try:
            questions = load_questions(suite, repository=repo)
        except ValidationError as e:
            errors.extend(e.errors)
            warnings.extend(e.warnings)

    if errors:
        raise ValidationError(errors, warnings)
    return {
        "matrix_path": str(p), "matrix": matrix,
        "matrix_hash": canonical_hash(matrix),
        "repository": str(repo), "suite_path": str(suite),
        "suite_hash": canonical_hash(questions), "questions": questions,
        "profiles": resolved_profiles, "search_profiles": search_by_name,
        "cells": cells, "warnings": warnings,
    }


def make_plan(path: str | Path, *, store: Store | None = None) -> dict:
    spec = validate_matrix(path)
    st = store or Store()
    existing = set(st.projects())
    root = spec["repository"]
    commit = indexer.git_head(root)
    dirty = indexer.git_dirty(root)
    indexes = []
    for pid, profile in spec["profiles"].items():
        project_id = profiles.project_id_for(root, pid)
        present = project_id in existing
        actual_fp = st.index_fingerprint(project_id) if present else None
        fp_match = actual_fp == profile["fingerprint"]
        state = indexer.get_state(project_id)
        commit_match = bool(commit and state.get("commit") == commit)
        bm25_count = lexical.doc_count(project_id) if present else None
        chunk_count = st.count(project_id) if present else 0
        bm25_ok = (not profile["fingerprint"]["use_bm25"]
                   or bm25_count == chunk_count)
        reusable = present and fp_match and commit_match and bm25_ok
        indexes.append({
            "profile_id": pid, "profile_hash": profile["profile_hash"],
            "project_id": project_id, "present": present,
            "fingerprint_match": fp_match, "commit_match": commit_match,
            "chunks": chunk_count, "bm25_count": bm25_count, "bm25_ok": bm25_ok,
            "action": "reuse" if reusable else ("rebuild" if present else "create"),
            "fingerprint": profile["fingerprint"],
        })
    invocations = sum(len(c["modes"]) for c in spec["cells"]) * len(spec["questions"])
    return {**spec, "commit": commit, "dirty": dirty, "indexes": indexes,
            "question_count": len(spec["questions"]), "cell_count": len(spec["cells"]),
            "query_invocations": invocations}


def _retrieval_rows(st: Store, project_id: str, profile: dict, search: dict,
                    questions: list[dict]) -> list[dict]:
    idx = None
    if search["use_bm25"]:
        idx = lexical.BM25.load(lexical.index_path(project_id))
        if idx is None or len(idx.doc_ids) != st.count(project_id):
            raise RuntimeError(f"{project_id}: BM25가 없거나 Chroma 청크 수와 다릅니다")
    rows = []
    for q in questions:
        t0 = time.perf_counter()
        vec = embed_one(q["question"], model=profile["embed_model"],
                        expected_dim=int(profile["embed_dim"]))
        hits = st.query(project_id, vec, search["pool"])
        if idx is not None:
            lex = idx.search(q["question"], search["pool"])
            fused = lexical.rrf_fuse(hits, lex, k=60)
            by_id = {h["_id"]: h for h in hits}
            missing = [cid for cid, _ in lex if cid not in by_id]
            by_id.update(st.get_by_ids(project_id, missing[:search["pool"]]))
            hits = sorted((by_id[cid] for cid in fused if cid in by_id),
                          key=lambda h: -fused[h["_id"]])
        rows.append({
            "id": q["id"], "question": q["question"], "answerable": q["answerable"],
            "tags": q["tags"], "rank": (first_gold_rank(hits, q["gold"])
                                            if q["answerable"] else None),
            "top_score": max((h["score"] for h in hits), default=None),
            "ranked1_path": hits[0]["path"] if hits else None,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        })
    return rows


def _pipeline_rows(st: Store, project_id: str, search: dict,
                   questions: list[dict]) -> list[dict]:
    if search["use_bm25"]:
        idx = lexical.BM25.load(lexical.index_path(project_id))
        if idx is None or len(idx.doc_ids) != st.count(project_id):
            raise RuntimeError(f"{project_id}: BM25가 없거나 Chroma 청크 수와 다릅니다")
    rows = []
    for q in questions:
        t0 = time.perf_counter()
        result = searcher.search(
            q["question"], project_id, top_k=search["top_k"],
            threshold=search["threshold"], store=st, search_profile=search)
        if search["use_bm25"] and result.get("all_hits") and not result.get("bm25_active"):
            raise RuntimeError(f"{project_id}: hybrid 셀인데 bm25_active=false입니다")
        contexts = result["contexts"]
        rows.append({
            "id": q["id"], "question": q["question"], "answerable": q["answerable"],
            "tags": q["tags"], "rank": (first_gold_rank(contexts, q["gold"])
                                            if q["answerable"] else None),
            "has_evidence": result["has_evidence"], "reason": result["reason"],
            "top_score": result["top_score"], "bm25_active": result.get("bm25_active", False),
            "ranked1_path": contexts[0]["path"] if contexts else None,
            "timing": result.get("timing", {}),
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        })
    return rows


def run_matrix(path: str | Path, *, allow_index: bool = False,
               output: str | Path | None = None) -> tuple[Path, dict]:
    plan = make_plan(path)
    require_clean = bool(plan["matrix"].get("require_clean", True))
    if require_clean and plan["dirty"] is not False:
        state = "dirty" if plan["dirty"] else "확인 불가"
        raise RuntimeError(f"재현 가능한 실험을 위해 clean git repository가 필요합니다: {state}")
    needed = [i for i in plan["indexes"] if i["action"] != "reuse"]
    if needed and not allow_index:
        names = ", ".join(f"{i['project_id']}({i['action']})" for i in needed)
        raise RuntimeError(f"필요한 인덱스가 준비되지 않았습니다: {names}; --allow-index로 명시하세요")

    st = Store()
    for item in needed:
        p = plan["profiles"][item["profile_id"]]
        indexer.start_index(
            plan["repository"], item["project_id"], blocking=True, force=True,
            on_done=None, profile=p["fingerprint"], profile_id=p["profile_id"],
            profile_hash=p["profile_hash"])
        if p["fingerprint"]["use_bm25"] and lexical.doc_count(item["project_id"]) != st.count(item["project_id"]):
            raise RuntimeError(f"{item['project_id']}: 인덱싱 후 BM25 정합성 검증 실패")

    project_of = {i["profile_id"]: i["project_id"] for i in plan["indexes"]}
    cells_out = []
    for cell in plan["cells"]:
        pid = project_of[cell["index_profile"]]
        ip = plan["profiles"][cell["index_profile"]]
        sp = plan["search_profiles"][cell["search_profile"]]
        for mode in cell["modes"]:
            rows = (_retrieval_rows(st, pid, ip["fingerprint"], sp, plan["questions"])
                    if mode == "retrieval" else
                    _pipeline_rows(st, pid, sp, plan["questions"]))
            cells_out.append({
                "cell_id": f"{cell['index_profile']}/{cell['search_profile']}/{mode}",
                "index_profile": cell["index_profile"], "profile_hash": ip["profile_hash"],
                "project_id": pid, "search_profile": sp, "mode": mode,
                "metrics": summarize(rows, mode), "by_tag": by_tag(rows, mode),
                "questions": rows,
            })

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + plan["matrix_hash"][:6]
    result = {
        "schema_version": "1.0", "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "matrix_name": plan["matrix"]["name"], "matrix_hash": plan["matrix_hash"],
        "matrix_path": plan["matrix_path"], "repository": plan["repository"],
        "commit": plan["commit"], "dirty": plan["dirty"],
        "suite_path": plan["suite_path"], "suite_hash": plan["suite_hash"],
        "cells": cells_out,
    }
    target = Path(output).resolve() if output else RUNS_DIR / f"{run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target, result


def latest_result(matrix_or_result: str | Path) -> tuple[Path, dict]:
    p = Path(matrix_or_result).resolve()
    data = json.loads(p.read_text(encoding="utf-8"))
    if "run_id" in data and "cells" in data:
        return p, data
    mh = canonical_hash(data)
    candidates = []
    for f in RUNS_DIR.glob("*.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            if r.get("matrix_hash") == mh:
                candidates.append((f.stat().st_mtime, f, r))
        except Exception:
            continue
    if not candidates:
        raise RuntimeError("이 matrix의 실행 결과가 없습니다")
    _, f, r = max(candidates, key=lambda x: x[0])
    return f, r


def render_report(result: dict) -> str:
    lines = [f"# RAG 실험 보고서 — {result['matrix_name']}", "",
             f"- run_id: `{result['run_id']}`", f"- commit: `{result.get('commit')}`",
             f"- suite_hash: `{result['suite_hash']}`", "",
             "| cell | mode | Hit@1 | Hit@3 | Hit@5 | MRR | no-evidence recall | p95 ms |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    def pct(v): return "—" if v is None else f"{v:.1%}"
    def num(v): return "—" if v is None else f"{v:.3f}"
    for c in result["cells"]:
        m = c["metrics"]
        lines.append(
            f"| `{c['index_profile']}/{c['search_profile']['name']}` | {c['mode']} | "
            f"{pct(m.get('hit@1'))} | {pct(m.get('hit@3'))} | {pct(m.get('hit@5'))} | "
            f"{num(m.get('mrr'))} | {pct(m.get('no_evidence_recall'))} | "
            f"{m.get('latency_ms', {}).get('p95') or '—'} |")
    lines += ["", "## 실패·거절 관측", ""]
    for c in result["cells"]:
        misses = [q for q in c["questions"] if q["answerable"] and not q.get("rank")]
        false_evidence = [q for q in c["questions"] if not q["answerable"] and q.get("has_evidence")]
        if misses or false_evidence:
            lines.append(f"### {c['cell_id']}")
            for q in misses:
                lines.append(f"- 정답 미검색: `{q['id']}` — 1위 `{q.get('ranked1_path')}`")
            for q in false_evidence:
                lines.append(f"- 잘못된 근거 통과: `{q['id']}` — `{q.get('ranked1_path')}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(matrix_or_result: str | Path, *, output: str | Path | None = None) -> Path:
    _, result = latest_result(matrix_or_result)
    target = Path(output).resolve() if output else REPORTS_DIR / f"{result['run_id']}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(result), encoding="utf-8")
    return target
