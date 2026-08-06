"""
프로젝트 브리핑 (FN-A05) — 인덱싱 완료 후 프로젝트 개요를 생성합니다.

⚠ 일반 질의와 구조가 근본적으로 다릅니다.

    일반 질의:  질문 있음 → 임베딩 → 벡터 검색 → top-k
    브리핑:     질문 없음 → ???

"프로젝트 전체를 요약해라"에는 검색할 질문이 없습니다. 벡터 검색은 "구체적
질문에 맞는 조각"을 찾는 도구이지 개요를 만드는 도구가 아닙니다.

그래서 근거를 **검색하지 않고 결정적으로 수집**합니다. 필요한 재료가 무엇인지
이미 알고 있기 때문입니다.

    README        파일명으로 직접 읽기
    디렉터리 트리   파일 시스템 순회
    진입점        파일명 규칙 (main.py, app.py, index.js ...)
    설정 파일      pyproject.toml, package.json ...
    docs/         사내 문서가 여기 들어옴

⚠ README 가 없어도 동작해야 합니다.
   사내 레포는 README 가 부실한 경우가 많고, 오히려 그것이 이 제품이 필요한
   이유입니다. 없는 것을 지어내지 않고 "확인되지 않음"으로 처리합니다.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import CFG, CODE_EXT, DOC_EXT, SKIP_DIRS

# ─────────────────────────────────────────────────────────────
# 토큰 예산
#
# 실측(2026-08-04): 한국어 혼합 마크다운 1.52 자/토큰
#   num_ctx        8,192
#   답변 예약      -1,200  (브리핑 목표 길이)
#   시스템 프롬프트 -  200
#   ──────────────────────
#   근거 예산       6,792 토큰
#
# ⚠ 여유가 크지 않으므로 수집 중 총합을 재면서 자릅니다.
# ─────────────────────────────────────────────────────────────
BUDGET_TOKENS = 6_500

# 재료별 상한 (자 단위). 우선순위 순으로 채웁니다.
LIMIT_README = 2_500
LIMIT_TREE_LINES = 60
LIMIT_ENTRY_FILES = 4
LIMIT_ENTRY_LINES = 30
LIMIT_CONFIG = 800
LIMIT_DOC_FILES = 2
LIMIT_DOC_CHARS = 1_200


def est_tokens(text: str) -> int:
    """
    토큰 수 추정. 한국어와 그 외를 나눠 계산합니다.

    ⚠ 어디까지나 추정입니다. 정확한 값은 토크나이저를 거쳐야 하지만,
       예산 관리 목적으로는 충분합니다. 보수적으로(크게) 잡습니다.
    """
    ko = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    return int(ko / 1.4 + (len(text) - ko) / 3.2)


# ── 진입점 판정 ──────────────────────────────────────────────
ENTRY_NAMES = {
    # Python
    "main.py", "app.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py",
    "server.py", "run.py", "cli.py",
    # JS / TS
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "server.ts",
    "app.js", "app.ts", "index.tsx", "App.tsx",
    # 기타
    "Main.java", "Application.java", "main.go", "main.rs", "Program.cs",
}

CONFIG_NAMES = [
    "pyproject.toml", "package.json", "setup.py", "requirements.txt",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "composer.json",
    "Gemfile", "tsconfig.json",
]

README_NAMES = ["README.md", "readme.md", "README.MD", "README.rst", "README.txt", "README"]

# 진입점의 강한 증거
ENTRY_MARKERS = [
    'if __name__ == "__main__"', "if __name__ == '__main__'",
    "def main(", "func main(", "public static void main",
    "createApp", "create_app", "FastAPI(", "express(", "app.listen(",
]


@dataclass
class Material:
    """수집된 근거 한 덩어리. 프롬프트에서 [N] 번호가 붙습니다."""
    kind: str                       # readme | tree | entry | config | doc | stats
    label: str                      # 사람이 읽을 제목
    text: str
    path: str | None = None         # 실제 파일이면 상대경로
    line_start: int | None = None
    line_end: int | None = None
    type: str = "doc"               # references.py 호환 (code | doc)


@dataclass
class Collected:
    materials: list[Material] = field(default_factory=list)
    structure: dict = field(default_factory=dict)
    known_paths: set = field(default_factory=set)
    known_dirs: set = field(default_factory=set)
    used_tokens: int = 0
    truncated: list[str] = field(default_factory=list)   # 예산 때문에 잘린 항목


# ── 파일 읽기 ────────────────────────────────────────────────

def _read(path: Path, limit: int | None = None) -> str | None:
    for enc in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            t = path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
        if "\x00" in t[:2048]:
            return None
        return t[:limit] if limit else t
    return None


# ── 수집 ─────────────────────────────────────────────────────

def _walk(root: Path) -> tuple[list[Path], dict[str, int]]:
    """대상 파일 목록 + 디렉터리별 파일 수."""
    files: list[Path] = []
    dir_counts: dict[str, int] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        ext = p.suffix.lower()
        if ext not in CODE_EXT and ext not in DOC_EXT and p.name not in CONFIG_NAMES:
            continue
        files.append(p)
        rel_dir = p.parent.relative_to(root).as_posix() or "."
        dir_counts[rel_dir] = dir_counts.get(rel_dir, 0) + 1
    return files, dir_counts


def _build_tree(root: Path, dir_counts: dict[str, int], max_lines: int) -> str:
    """디렉터리 2단계 트리. 파일 수를 함께 표시합니다."""
    entries: list[tuple[int, str, int]] = []   # (depth, path, file_count)
    for d, n in dir_counts.items():
        if d == ".":
            entries.append((0, "(root)", n))
            continue
        depth = d.count("/")
        if depth > 1:                          # 2단계까지
            continue
        entries.append((depth, d, n))

    entries.sort(key=lambda x: (x[1] != "(root)", x[1]))
    lines = []
    for depth, d, n in entries[:max_lines]:
        indent = "  " * depth
        lines.append(f"{indent}{d}/  ({n} files)")
    if len(entries) > max_lines:
        lines.append(f"... 외 {len(entries) - max_lines}개 디렉터리")
    return "\n".join(lines)


def _find_entry_points(root: Path, files: list[Path]) -> list[tuple[Path, str]]:
    """
    진입점 후보. (파일, 판정 이유) 목록.

    ⚠ 못 찾을 수 있습니다. 그때는 빈 목록을 돌려주고, 프롬프트에서
       "진입점 미확인"으로 처리합니다. 억지로 추측하면 틀린 정보가 됩니다.
    """
    cands: list[tuple[Path, str, int]] = []    # (path, reason, score)
    for f in files:
        score = 0
        reasons = []
        if f.name in ENTRY_NAMES:
            score += 10
            reasons.append(f"파일명 규칙({f.name})")
        depth = len(f.relative_to(root).parts) - 1
        if depth <= 1:
            score += 3
            reasons.append("최상위 근처")
        if score == 0:
            continue
        head = _read(f, 4000) or ""
        for m in ENTRY_MARKERS:
            if m in head:
                score += 8
                reasons.append(f"'{m}' 포함")
                break
        cands.append((f, " · ".join(reasons), score))

    cands.sort(key=lambda x: -x[2])
    return [(f, r) for f, r, _ in cands[:LIMIT_ENTRY_FILES]]


def collect(project_root: str | Path) -> Collected:
    """
    검색 없이 결정적으로 근거를 수집합니다.

    ⚠ 우선순위 순으로 채우며 예산을 초과하면 자릅니다.
       README > 트리 > 진입점 > 설정 > docs
    """
    root = Path(project_root).resolve()
    out = Collected()
    files, dir_counts = _walk(root)

    out.known_paths = {f.relative_to(root).as_posix() for f in files}
    out.known_dirs = {d for d in dir_counts if d != "."} | {d + "/" for d in dir_counts if d != "."}

    def add(m: Material) -> bool:
        """예산 안에서만 추가. 초과하면 False."""
        t = est_tokens(m.text) + 20            # 헤더 여유
        if out.used_tokens + t > BUDGET_TOKENS:
            out.truncated.append(m.label)
            return False
        out.materials.append(m)
        out.used_tokens += t
        return True

    # ── 1. README ────────────────────────────────────────────
    readme_path = None
    for name in README_NAMES:
        p = root / name
        if p.is_file():
            readme_path = p
            break
    if readme_path:
        txt = _read(readme_path, LIMIT_README)
        if txt and txt.strip():
            rel = readme_path.relative_to(root).as_posix()
            add(Material("readme", f"{rel} (프로젝트 설명)", txt.strip(),
                         path=rel, type="doc"))

    # ── 2. 디렉터리 구조 ──────────────────────────────────────
    tree = _build_tree(root, dir_counts, LIMIT_TREE_LINES)
    if tree:
        add(Material("tree", "디렉터리 구조", tree, path=None, type="doc"))

    # ── 3. 진입점 ────────────────────────────────────────────
    entries = _find_entry_points(root, files)
    for f, reason in entries:
        txt = _read(f)
        if not txt:
            continue
        lines = txt.splitlines()[:LIMIT_ENTRY_LINES]
        body = "\n".join(lines).strip()
        if not body:
            continue
        rel = f.relative_to(root).as_posix()
        add(Material("entry", f"{rel} (진입점 후보 — {reason})", body,
                     path=rel, line_start=1, line_end=len(lines), type="code"))

    # ── 4. 설정 파일 ─────────────────────────────────────────
    for name in CONFIG_NAMES:
        p = root / name
        if not p.is_file():
            continue
        txt = _read(p, LIMIT_CONFIG)
        if txt and txt.strip():
            add(Material("config", f"{name} (프로젝트 설정)", txt.strip(),
                         path=name, type="code"))
        break                                   # 하나면 충분

    # ── 5. docs/ ────────────────────────────────────────────
    # ⚠ 사내 문서(INHOUSE_DOCS)가 여기 들어옵니다.
    #    README 가 부실한 레포에서 이것이 브리핑 품질을 좌우합니다.
    doc_dir = root / "docs"
    if doc_dir.is_dir():
        docs = sorted(p for p in doc_dir.rglob("*")
                      if p.is_file() and p.suffix.lower() in DOC_EXT)
        for p in docs[:LIMIT_DOC_FILES]:
            txt = _read(p, LIMIT_DOC_CHARS)
            if txt and txt.strip():
                rel = p.relative_to(root).as_posix()
                add(Material("doc", f"{rel} (프로젝트 문서)", txt.strip(),
                             path=rel, type="doc"))

    # ── 6. 통계 (항상 작음) ──────────────────────────────────
    ext_counts: dict[str, int] = {}
    for f in files:
        ext_counts[f.suffix.lower()] = ext_counts.get(f.suffix.lower(), 0) + 1
    top_ext = sorted(ext_counts.items(), key=lambda x: -x[1])[:6]
    stats_txt = (
        f"전체 파일 {len(files)}개 / 디렉터리 {len(dir_counts)}개\n"
        + "확장자 분포: " + ", ".join(f"{e or '(없음)'} {n}" for e, n in top_ext)
    )
    add(Material("stats", "파일 통계", stats_txt, path=None, type="doc"))

    # ── structure (프론트가 파일 트리를 그리는 데 직접 사용) ──
    out.structure = {
        "entry_points": [
            {"path": f.relative_to(root).as_posix(), "reason": r}
            for f, r in entries
        ],
        "key_dirs": sorted(
            ({"path": d, "file_count": n} for d, n in dir_counts.items() if d != "."),
            key=lambda x: -x["file_count"],
        )[:15],
        "docs": [m.path for m in out.materials if m.kind in ("readme", "doc") and m.path],
        "config": [m.path for m in out.materials if m.kind == "config" and m.path],
        "total_files": len(files),
        "total_dirs": len(dir_counts),
    }
    return out


# ── 프롬프트 ─────────────────────────────────────────────────

SYSTEM = (
    "당신은 신입 개발자에게 프로젝트를 소개하는 온보딩 도우미입니다.\n"
    "제공된 근거만 사용해 한국어 Markdown 으로 프로젝트 브리핑을 작성합니다.\n"
    "근거에 없는 파일·동작·목적은 추측하지 않습니다.\n"
    "각 주장 끝에 사용한 근거 번호를 [1], [2] 형식으로 표기합니다.\n"
    "\n"
    "다음 구성을 따릅니다.\n"
    "  ## 이 프로젝트는\n"
    "  ## 디렉터리 구조\n"
    "  ## 실행 흐름\n"
    "  ## 처음 볼 파일\n"
    "\n"
    "확인되지 않는 항목은 '문서에서 확인되지 않음' 이라고 적고 넘어갑니다.\n"
    "근거가 전혀 부족하면 다른 설명 없이 정확히 다음 한 줄만 출력합니다: NO_EVIDENCE"
)


def render_prompt(c: Collected) -> list[dict]:
    """수집 결과 → LLM messages. [N] 번호는 materials 순서와 1:1."""
    parts = ["프로젝트 정보:"]
    for i, m in enumerate(c.materials, start=1):
        parts.append(f"[{i}] {m.label}\n{m.text}")
    parts.append("위 정보를 바탕으로 프로젝트 브리핑을 작성해주세요.")
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def to_contexts(c: Collected) -> list[dict]:
    """references.py 가 쓸 수 있는 형태로 변환."""
    return [
        {
            "path": m.path or "",
            "type": m.type,
            "line_start": m.line_start,
            "line_end": m.line_end,
            "section": None if m.path else m.label,
            "text": m.text,
            "score": 1.0,          # 검색이 아니므로 점수 개념이 없습니다
        }
        for m in c.materials
    ]


# ── 본문에 언급된 파일 추출 ──────────────────────────────────

def extract_mentioned(text: str, known_paths: set, known_dirs: set) -> list[dict]:
    """
    브리핑 본문에 등장한 파일·디렉터리 경로를 찾습니다.

    ⚠ 정규식으로 뽑지 않고 **실제 존재하는 경로와 대조**합니다.
       모델이 없는 파일을 지어낼 수 있기 때문입니다.
       프론트가 없는 파일을 클릭 가능하게 만드는 것을 막습니다.
    """
    found: list[dict] = []
    seen: set[str] = set()

    # 긴 경로부터 — src/main.py 가 main.py 보다 먼저 잡히게
    for p in sorted(known_paths | known_dirs, key=len, reverse=True):
        if not p or p in seen:
            continue
        if p in text:
            # 이미 잡힌 더 긴 경로의 일부이면 건너뜁니다
            if any(p in s and p != s for s in seen):
                continue
            seen.add(p)
            found.append({
                "path": p.rstrip("/"),
                "is_dir": p.endswith("/") or p in known_dirs,
                "exists": True,
            })
    return found


# ── LLM 호출 (C' 구조: 모델·주소를 호출자가 주입) ─────────────

def generate(messages: list[dict], model: str, ollama_url: str,
             timeout: int = 300) -> str:
    """
    ⚠ rag_lab 이 LLM 을 호출하는 유일한 지점입니다.

       원칙은 "LLM 호출은 백엔드가" 이지만, 브리핑은 예외로 둡니다.
         · 스트리밍 불필요 (1회 생성 후 캐싱)
         · 백엔드 구현 부담이 3단계 → 1단계로 감소

       대신 model 과 ollama_url 을 호출자가 주입합니다.
       그래야 나중에 fine-tuned 모델로 교체할 때 한 곳만 고치면 됩니다.
    """
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": 8192, "temperature": 0.2},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


# ── 저장 / 조회 ──────────────────────────────────────────────

def _dir() -> Path:
    p = Path(CFG.index_dir).resolve().parent / "briefings"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(project_id: str) -> Path:
    safe = re.sub(r"[^\w\-.]", "_", project_id)
    return _dir() / f"{safe}.json"


def save(project_id: str, text: str, c: Collected,
         commit: str | None = None) -> dict:
    from .references import build_references

    contexts = to_contexts(c)
    refs = build_references(contexts, answer=text, cited_only=True,
                            include_text=False)
    mentioned = extract_mentioned(text, c.known_paths, c.known_dirs)

    rec = {
        "project_id": project_id,
        "briefing": text,
        "references": refs["references"],
        "reference_files": refs["reference_files"],
        "cited": refs["cited"],
        "mentioned_files": mentioned,
        "structure": c.structure,
        "commit": commit,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "materials": [m.label for m in c.materials],
        "truncated": c.truncated,
        "evidence_tokens": c.used_tokens,
        "briefing_tokens": est_tokens(text),
    }
    _path(project_id).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def load(project_id: str) -> dict | None:
    p = _path(project_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def build(project_root: str, project_id: str, model: str, ollama_url: str,
          commit: str | None = None) -> dict:
    """수집 → 프롬프트 → 생성 → 저장. 한 번에."""
    t0 = time.perf_counter()
    c = collect(project_root)

    if not c.materials:
        return {"ok": False, "reason": "no_material",
                "message": "프로젝트 문서를 찾을 수 없습니다"}

    msgs = render_prompt(c)
    text = generate(msgs, model, ollama_url)

    if text.strip() == "NO_EVIDENCE":
        return {"ok": False, "reason": "no_evidence",
                "message": "브리핑을 작성할 근거가 부족합니다",
                "structure": c.structure}

    rec = save(project_id, text, c, commit=commit)
    rec["elapsed_s"] = round(time.perf_counter() - t0, 1)
    rec["ok"] = True
    return rec
