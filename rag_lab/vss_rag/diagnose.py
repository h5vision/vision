"""
상태 대조 — 인덱스의 "정본"이 네 곳에 흩어져 있어서 생기는 문제를 잡습니다.

⚠ 왜 필요한가

    한 프로젝트의 상태가 네 군데에 있습니다.

        ① Chroma 컬렉션 이름          building-<pid> · <pid>-prev · <pid>
        ② Chroma metadata            fingerprint · status · target · project_root
        ③ data/state.json            처리 파일 수 · 청크 수 · commit · fingerprint
        ④ 부수 파일                   data/bm25/<pid>.json · data/briefings/<pid>.*

    그리고 **질의는 위 넷 중 어느 것도 아닌 `CFG`(환경변수)로 돕니다.**

    이 다섯이 갈라진 결과가 2026-08 의 사고들이었습니다 —
    `-v2`·`-v3` 오조회, 고아 컬렉션, 반쪽 인덱스, 조건이 틀린 측정 기록.

⚠ 이 모듈은 **읽기만 합니다.** 고치지 않습니다.
   무엇을 고칠지는 사람이 정합니다. 자동 수리는 `repair_collections.py` 로 명시적으로.

⚠ 수치를 판단하지 않습니다. "몇 청크가 적정한가" 같은 건 여기 없습니다.
   "두 곳에 적힌 값이 다르다" 만 봅니다.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import lexical
from .config import CFG, normalize_fingerprint
from .store import BUILD_PREFIX, PREV_SUFFIX, Store, is_internal

# 지문 키 → 환경변수 이름. 어긋났을 때 맞추는 명령을 만들어 주기 위함입니다.
ENV_OF = {
    "embed_model": "VSS_EMBED_MODEL",
    "embed_dim": None,
    "chunk_size": "VSS_CHUNK_SIZE",
    "chunk_overlap": "VSS_CHUNK_OVERLAP",
    "min_chunk_chars": "VSS_MIN_CHUNK",
    "max_file_bytes": "VSS_MAX_FILE_BYTES",
    "context_header": "VSS_CONTEXT_HEADER",
    "use_bm25": "VSS_USE_BM25",
    "exclude_globs": "VSS_EXCLUDE_GLOBS",
}

# 검색과 증분 갱신은 2026-08-13부터 컬렉션별 fingerprint를 명시적으로 사용합니다.
# 따라서 CFG와의 차이는 "다음 전체 인덱싱의 기본값이 다르다"는 정보일 뿐,
# 현재 질의 동작이나 증분 가능 여부를 바꾸지 않습니다.
QUERY_KEYS: set[str] = set()

# 심각도
RED = "🔴"      # 조회 결과가 달라집니다
YELLOW = "🟡"   # 기록만 어긋납니다. 동작에는 영향 없음
OK = "✅"


# ── 지문 대조 ────────────────────────────────────────────────
def fingerprint_drift(index_fp: dict | None,
                      cfg_fp: dict | None = None) -> dict[str, tuple]:
    """인덱스 지문과 CFG 가 다른 키만 `{key: (인덱스값, CFG값)}` 로.

    ⚠ 인덱스에 지문이 없으면(구 방식) 빈 dict 를 돌려줍니다.
       "다르지 않다"가 아니라 "비교할 수 없다"입니다. 호출자가 구분해야 합니다.
    """
    index_fp = normalize_fingerprint(index_fp)
    if not index_fp:
        return {}
    cfg = cfg_fp if cfg_fp is not None else CFG.fingerprint()
    return {k: (index_fp.get(k), v) for k, v in cfg.items()
            if index_fp.get(k) != v}


def env_fix_lines(drift: dict[str, tuple]) -> list[str]:
    """어긋난 지문을 CFG 에 맞추는 PowerShell 명령.

    ⚠ 반대 방향(재인덱싱)도 선택지입니다. 어느 쪽이 맞는지는 사람이 정합니다.
       여기서는 "인덱스에 CFG 를 맞추는" 쪽만 냅니다 — 그게 재인덱싱 없이 되니까.

    🔴 **이 명령은 다른 인덱스를 깨뜨릴 수 있습니다.** 반드시 `conflicts()` 로
       먼저 확인하세요. CFG 는 전역이고 지문은 인덱스별이라, 인덱스들이 서로 다른
       설정으로 만들어져 있으면 **하나의 CFG 로 전부 만족시킬 수 없습니다.**
    """
    out = []
    for k, (idx_v, _) in drift.items():
        env = ENV_OF.get(k)
        if not env:
            continue
        v = int(idx_v) if isinstance(idx_v, bool) else idx_v
        out.append(f"$env:{env}={v}")
    return out


def conflicts(rows: list[dict]) -> dict[str, dict]:
    """인덱스들끼리 지문이 갈리는 키를 찾습니다.

    반환: `{key: {값: [그 값을 가진 인덱스들]}}` — 값이 2종류 이상인 키만.

    ⚠ 이게 비어 있지 않으면 **CFG 를 어떻게 놔도 누군가는 어긋납니다.**
       환경변수로 해결할 수 없는 상황이며, 선택지는 재인덱싱이거나
       "지금 작업하는 인덱스에만 맞추고 나머지는 건드리지 않기" 입니다.

    ⚠ `rows` 는 `drift_summary()` 의 결과를 넣으세요.
    """
    buckets: dict[str, dict] = {}
    for r in rows:
        fp = r.get("fingerprint")
        if not fp:
            continue                      # 지문 없는 구 인덱스는 판단 대상 아님
        for k in ENV_OF:
            if k not in fp:
                continue
            buckets.setdefault(k, {}).setdefault(fp[k], []).append(r["name"])
    return {k: v for k, v in buckets.items() if len(v) > 1}


def safe_fix(rows: list[dict]) -> tuple[list[str], dict[str, dict]]:
    """전역으로 안전한 CFG 수정안과, 충돌 때문에 못 고치는 키를 함께 돌려줍니다.

    안전 = 그 키의 값이 **모든 인덱스에서 같음**. 그러면 CFG 만 바꾸면 전부 맞습니다.
    """
    conf = conflicts(rows)
    cfg = CFG.fingerprint()
    lines = []
    for r in rows:
        for k, (idx_v, _) in (r.get("drift") or {}).items():
            if k in conf:
                continue                  # 충돌 키는 CFG 로 해결 불가
            env = ENV_OF.get(k)
            if not env or cfg.get(k) == idx_v:
                continue
            v = int(idx_v) if isinstance(idx_v, bool) else idx_v
            line = f"$env:{env}={v}"
            if line not in lines:
                lines.append(line)
    return lines, conf


# ── 프로젝트 단위 점검 ───────────────────────────────────────
def _load_state() -> dict:
    p = Path(CFG.state_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _bm25_doc_count(project_id: str) -> int | None:
    """역색인의 문서 수. 없으면 None.

    ⚠ 대용량 JSON 을 통째로 읽습니다(2만 청크에 16MB). 빠른 경로에서 쓰지 마세요.
    """
    idx = lexical.BM25.load(lexical.index_path(project_id))
    return len(idx.doc_ids) if idx else None


def scan(store: Store | None = None, *, deep: bool = False) -> dict:
    """전체 상태를 모아 문제 목록과 함께 돌려줍니다.

    deep=True 면 BM25 역색인을 실제로 열어 문서 수까지 대조합니다 (느립니다).
    """
    st = store or Store()
    cols = st.raw_collections()
    state = _load_state()
    cfg_fp = CFG.fingerprint()

    by_name = {c["name"]: c for c in cols}
    live = [c for c in cols if not is_internal(c["name"])]
    internal = [c for c in cols if is_internal(c["name"])]

    projects: list[dict] = []
    issues: list[dict] = []

    def add(sev, where, msg, fix=None):
        issues.append({"sev": sev, "where": where, "msg": msg, "fix": fix})

    # ── 조회 가능한 인덱스 ──────────────────────────────────
    for c in sorted(live, key=lambda x: x["name"]):
        name = c["name"]
        meta = c["metadata"]
        raw_fp = meta.get("fingerprint")
        try:
            parsed = json.loads(raw_fp) if isinstance(raw_fp, str) else (raw_fp or None)
            collection_fp = normalize_fingerprint(parsed)
        except Exception:
            collection_fp = None

        s = state.get(name)
        state_fp = normalize_fingerprint((s or {}).get("fingerprint"))
        fp = collection_fp or state_fp
        drift = fingerprint_drift(fp, cfg_fp)

        rec = {
            "name": name,
            "chunks": c["chunks"],
            "fingerprint": fp,
            "fingerprint_source": "collection" if collection_fp else (
                "state" if state_fp else None),
            "drift": drift,
            "status": meta.get("status"),
            "target": meta.get("target"),
            "state": s,
            "bm25_path": lexical.index_path(name),
            "bm25_docs": None,
        }

        # ① 지문 ↔ CFG. 차이는 현재 서빙 오류가 아니라 다음 전체 인덱싱 기본값 차이입니다.
        if fp is None:
            add(YELLOW, name,
                "인덱스에 지문이 없습니다 (구 방식으로 만든 인덱스). CFG 와 대조할 수 없습니다")
        elif drift:
            add(YELLOW, name,
                f"저장된 프로젝트 프로필과 새 전체 인덱싱 기본값이 다릅니다 "
                f"({', '.join(sorted(drift))}). 현재 질의·증분은 저장된 프로필을 사용합니다")
        if collection_fp is None and state_fp is not None:
            add(YELLOW, name,
                "컬렉션 metadata에 지문이 없어 state.json 지문으로 서빙합니다. 다음 증분 성공 시 metadata에 보완됩니다")

        # ② state.json ↔ Chroma
        if s is None:
            add(RED, name, "Chroma 에는 있는데 state.json 에 없습니다")
        else:
            if s.get("state") != "done":
                add(RED, name, f"state.json 의 상태가 '{s.get('state')}' 입니다 (done 아님)")
            sc = s.get("chunk_count")
            if isinstance(sc, int) and sc != c["chunks"]:
                add(RED, name,
                    f"청크 수가 다릅니다 — Chroma {c['chunks']:,} / state.json {sc:,}")
            sfp = normalize_fingerprint(s.get("fingerprint"))
            if collection_fp and sfp and sfp != collection_fp:
                add(YELLOW, name, "state.json 의 지문과 컬렉션 지문이 다릅니다")

        # ③ metadata 위생
        if meta.get("status") and meta["status"] != "ready":
            add(YELLOW, name,
                f"컬렉션 metadata 의 status 가 '{meta['status']}' 입니다. "
                f"이름은 정상이라 조회에는 영향 없습니다")
        if meta.get("target") and meta["target"] != name:
            add(YELLOW, name,
                f"metadata 의 target 이 '{meta['target']}' 로 이름과 다릅니다 "
                f"(이름을 나중에 바꾼 흔적)")

        # ④ 부수 파일
        bm_exists = rec["bm25_path"].exists()
        wants_bm = bool((fp or {}).get("use_bm25"))
        if wants_bm and not bm_exists:
            add(RED, name, "지문은 use_bm25=True 인데 역색인 파일이 없습니다")
        if deep and bm_exists:
            n = _bm25_doc_count(name)
            rec["bm25_docs"] = n
            if n is not None and n != c["chunks"]:
                add(RED, name,
                    f"역색인과 컬렉션이 어긋납니다 — BM25 {n:,} / Chroma {c['chunks']:,}")
        elif bm_exists:
            rec["bm25_docs"] = "미확인 (--deep)"

        projects.append(rec)

    # ── state.json 에만 있는 것 ────────────────────────────
    for pid in state:
        if pid not in by_name:
            add(RED, pid, "state.json 에는 있는데 Chroma 컬렉션이 없습니다")

    # ── 미완성 컬렉션 ──────────────────────────────────────
    for c in internal:
        kind = "인덱싱 중이거나 중단됨" if c["name"].startswith(BUILD_PREFIX) \
            else f"교체 도중 남은 백업 ({PREV_SUFFIX})"
        add(YELLOW, c["name"],
            f"미완성 컬렉션 — {kind}. 조회 대상이 아닙니다 ({c['chunks']:,}청크)",
            fix="진행 중이 아니라면  python repair_collections.py --apply")

    return {
        "projects": projects,
        "internal": internal,
        "issues": issues,
        "cfg_fingerprint": cfg_fp,
        # 프로젝트별 프로필을 쓰므로 전역 CFG 수정 제안은 더 이상 내지 않습니다.
        "safe_fix": [],
        "conflicts": {},
        "red": sum(1 for i in issues if i["sev"] == RED),
        "yellow": sum(1 for i in issues if i["sev"] == YELLOW),
    }


# ── 빠른 경로 — health 용 ────────────────────────────────────
def drift_summary(store: Store | None = None) -> list[dict]:
    """인덱스별 지문과 CFG 차이만. BM25 파일을 열지 않아 빠릅니다."""
    st = store or Store()
    cfg_fp = CFG.fingerprint()
    state = _load_state()
    out = []
    for c in sorted(st.raw_collections(), key=lambda x: x["name"]):
        if is_internal(c["name"]):
            continue
        raw = c["metadata"].get("fingerprint")
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or None)
            collection_fp = normalize_fingerprint(parsed)
        except Exception:
            collection_fp = None
        state_fp = normalize_fingerprint((state.get(c["name"]) or {}).get("fingerprint"))
        fp = collection_fp or state_fp
        out.append({
            "name": c["name"],
            "chunks": c["chunks"],
            "fingerprint": fp,
            "fingerprint_source": "collection" if collection_fp else (
                "state" if state_fp else None),
            "drift": fingerprint_drift(fp, cfg_fp),
        })
    return out
