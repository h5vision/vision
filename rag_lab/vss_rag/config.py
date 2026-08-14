"""
설정 — 실험에서 바꾸는 값은 전부 여기 모읍니다.

환경변수로도 덮어쓸 수 있습니다. 예:
    set VSS_TOP_K=8
    set VSS_OLLAMA_URL=http://127.0.0.1:11434
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, asdict, field
from functools import lru_cache
from typing import Mapping


def _env(key: str, default):
    v = os.getenv(key)
    if v is None:
        return default
    if isinstance(default, bool):
        return v.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int(v)
    if isinstance(default, float):
        return float(v)
    return v


# 인덱싱 대상 확장자 ─────────────────────────────────────────
CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
    ".sql", ".sh", ".bash", ".yaml", ".yml", ".toml", ".ini",
}
DOC_EXT = {".md", ".mdx", ".rst", ".txt", ".adoc"}

# 제외 디렉터리 ──────────────────────────────────────────────
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", "target", ".next", ".nuxt", "out",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".idea",
    ".vscode", "vendor", "migrations", ".tox", "site-packages",
}
SKIP_FILE_PATTERNS = {
    "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock",
    "pnpm-lock.yaml", "go.sum", "Cargo.lock",
}


# ── 경로 패턴 제외 (VSS_EXCLUDE_GLOBS) ───────────────────────
#
# ⚠ SKIP_DIRS 는 **디렉터리 이름**을 봅니다. `docs/ko` 처럼 하위 경로를
#    지정할 수 없습니다. 그래서 glob 패턴 제외를 따로 둡니다.
#
# ⚠ 왜 필요한가 — 실측 사례
#    FastAPI 레포는 같은 문서를 12개 언어로 갖고 있습니다.
#    BGE-M3 는 다국어 모델이라 한국어 질문이 프랑스어 번역본과도 매칭됩니다.
#    같은 내용이 12벌 있으면 점수가 나뉘고 top_k 를 번역본이 채웁니다.
#
# 규칙
#    *   `/` 를 넘지 않음
#    **  `/` 를 넘음
#    ?   `/` 가 아닌 한 글자
#    glob 문자가 없으면 "그 경로와 그 아래 전부"로 해석합니다
#
# 예)  VSS_EXCLUDE_GLOBS="tests,docs/ko/**,docs/ja/**"

_GLOB_CHARS = set("*?[")


def _glob_to_re(pat: str) -> str:
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                out.append(".*")
                i += 2
                if pat[i:i + 1] == "/":
                    i += 1
            else:
                out.append("[^/]*")
                i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    return "".join(out)


@lru_cache(maxsize=16)
def _compiled(spec: str) -> tuple:
    pats = []
    for raw in spec.split(","):
        p = raw.strip().replace("\\", "/").strip("/")
        if not p:
            continue
        if not (_GLOB_CHARS & set(p)):
            # glob 문자가 없으면 디렉터리 접두어로 봅니다
            pats.append(re.compile(f"^{re.escape(p)}(/.*)?$"))
        else:
            pats.append(re.compile(f"^{_glob_to_re(p)}$"))
    return tuple(pats)


def is_excluded(rel_path: str, spec: str | None = None) -> bool:
    """프로젝트 루트 기준 상대 경로가 제외 대상인가.

    ⚠ 호출자는 **posix 형태 상대 경로**를 넘겨야 합니다 (`docs/ko/foo.md`).
       `chunker` 와 `incremental` 이 같은 기준을 써야 하므로 여기 한 곳에 둡니다.
    """
    s = CFG.exclude_globs if spec is None else spec
    if not s:
        return False
    rel = rel_path.replace("\\", "/").lstrip("./")
    return any(p.match(rel) for p in _compiled(s))


@dataclass
class Config:
    # ── 임베딩 ───────────────────────────────────────────────
    # ⚠ 이 두 값은 확보된 검색 실측 전부의 전제입니다 (D9).
    #    바꾸면 임계값과 Hit@k 를 재측정해야 합니다. 수치는 MEASUREMENTS 참조.
    ollama_url: str = field(default_factory=lambda: _env("VSS_OLLAMA_URL", "http://127.0.0.1:11500"))
    embed_model: str = field(default_factory=lambda: _env("VSS_EMBED_MODEL", "bge-m3:latest"))
    embed_dim: int = 1024
    embed_batch: int = field(default_factory=lambda: _env("VSS_EMBED_BATCH", 16))
    embed_timeout: int = field(default_factory=lambda: _env("VSS_EMBED_TIMEOUT", 120))

    # ── 청킹 (md 실험 대상) ──────────────────────────────────
    # P의 현재 설정은 1600 / 200. 아래는 실험 기본값.
    chunk_size: int = field(default_factory=lambda: _env("VSS_CHUNK_SIZE", 1200))
    chunk_overlap: int = field(default_factory=lambda: _env("VSS_CHUNK_OVERLAP", 150))
    min_chunk_chars: int = field(default_factory=lambda: _env("VSS_MIN_CHUNK", 80))
    # 맥락 헤더 — 청크 앞에 "# 경로 > class X > def y" 를 붙여 임베딩에 포함시킵니다.
    # ⚠ 켜고 끄면 청크 텍스트가 달라지므로 재인덱싱이 필요합니다.
    #    평가셋으로 A/B 비교하기 위해 토글로 만들었습니다. 기본은 꺼짐.
    context_header: bool = field(default_factory=lambda: _env("VSS_CONTEXT_HEADER", False))
    max_file_bytes: int = field(default_factory=lambda: _env("VSS_MAX_FILE_BYTES", 1_000_000))

    # 경로 패턴 제외. 쉼표로 구분. 위 `is_excluded()` 주석 참조.
    # ⚠ 인덱스 내용을 바꾸므로 fingerprint 에 들어갑니다 — 바꾸면 재인덱싱이 필요합니다.
    # ⚠ 질의 동작에는 영향이 없습니다 (인덱싱 전용).
    exclude_globs: str = field(default_factory=lambda: _env("VSS_EXCLUDE_GLOBS", ""))

    # ── 검색 (md 실험 대상) ──────────────────────────────────
    top_k: int = field(default_factory=lambda: _env("VSS_TOP_K", 4))
    # FN-B06 근거 없음 판정.
    # ⚠ 잠정값입니다. 스파이크 v0.5 에서 answerable/no-answer 분포는 겹칩니다
    #    (answerable min 0.5098 / no-answer max 0.5644, overlap=True).
    #    0.54 는 분리선이 아니라 balanced accuracy 근사 최대점이며
    #    FP 3/20 · FN 1/11 을 수반합니다. 평가셋 확보 후 재보정 대상.
    score_threshold: float = field(default_factory=lambda: _env("VSS_THRESHOLD", 0.5400))

    # ── 검색 개선 (전부 토글. 평가셋으로 A/B 비교하기 위함) ──
    #
    # ⚠ 재인덱싱이 필요한 것과 아닌 것을 구분하세요.
    #    context_header, use_bm25  →  재인덱싱 필요 (fingerprint 포함)
    #    use_mmr, reorder_context  →  후처리라 즉시 적용

    # BM25 어휘 검색을 벡터 검색과 합칩니다.
    # 코드의 고유명사(함수명·변수명) 매칭에 강합니다.
    use_bm25: bool = field(default_factory=lambda: _env("VSS_USE_BM25", False))
    # 벡터 : BM25 가중치. 1.0 이면 벡터만, 0.0 이면 BM25 만.
    bm25_weight: float = field(default_factory=lambda: _env("VSS_BM25_WEIGHT", 0.4))
    # 융합 전에 각 경로에서 뽑을 후보 수. top_k 보다 넉넉해야 합니다.
    fusion_pool: int = field(default_factory=lambda: _env("VSS_FUSION_POOL", 20))

    # 같은 파일에 결과가 편중되는 것을 완화합니다.
    use_mmr: bool = field(default_factory=lambda: _env("VSS_USE_MMR", False))
    mmr_lambda: float = field(default_factory=lambda: _env("VSS_MMR_LAMBDA", 0.7))

    # 프롬프트 안에서 근거 배치를 조정합니다 (lost in the middle 완화).
    reorder_context: bool = field(default_factory=lambda: _env("VSS_REORDER", False))

    # ── 브리핑 ───────────────────────────────────────────────
    # 제품용 전체 인덱싱(CLI / POST /index)은 완료 후 브리핑을 항상 만듭니다 (FN-A05).
    # 이 값은 health 응답의 정책 표시용이며 VSS_AUTO_BRIEFING으로 끌 수 없습니다.
    # 반복 실험은 experiment.py가 indexer를 직접 호출해 브리핑 훅을 주입하지 않습니다.
    auto_briefing: bool = True
    briefing_model: str = field(default_factory=lambda: _env("VSS_BRIEFING_MODEL", "qwen2.5-coder:7b"))

    # ── 저장 ─────────────────────────────────────────────────
    index_dir: str = field(default_factory=lambda: _env("VSS_INDEX_DIR", "./data/index"))
    state_path: str = field(default_factory=lambda: _env("VSS_STATE_PATH", "./data/state.json"))

    def briefings_dir(self) -> "Path":
        """브리핑 저장 위치. index_dir 의 **부모** 기준입니다.

        ⚠ VSS_INDEX_DIR 을 바꾸면 브리핑 위치도 함께 움직입니다.
           예) VSS_INDEX_DIR=/tmp/x/index  →  /tmp/x/briefings
        """
        from pathlib import Path
        return Path(self.index_dir).resolve().parent / "briefings"

    def fingerprint(self) -> dict:
        """인덱스와 함께 저장할 파라미터 지문.

        ⚠ commit 이 같아도 이 값이 다르면 인덱스는 stale 입니다.
           청킹 파라미터를 바꿔가며 실험하므로 반드시 필요합니다.
        """
        return {
            "embed_model": self.embed_model,
            "embed_dim": self.embed_dim,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "min_chunk_chars": self.min_chunk_chars,
            "max_file_bytes": self.max_file_bytes,
            "context_header": self.context_header,
            "use_bm25": self.use_bm25,
            "exclude_globs": self.exclude_globs,
        }

    def to_dict(self) -> dict:
        return asdict(self)


CFG = Config()


# ── 저장된 인덱스 지문 호환성 ─────────────────────────────────
#
# fingerprint 키를 추가할 때 구 인덱스에는 그 키가 없습니다. 단순 dict 비교를 하면
# 의미상 같은 기본값도 `None != ""` 로 판정되어 모든 증분 갱신이 막힙니다.
# 아래 값은 각 키가 처음 도입되기 전 실제 기본값입니다. 현재 환경변수 값을 쓰면
# 과거 인덱스의 설정을 조용히 바꾸는 셈이 되므로 반드시 상수여야 합니다.
LEGACY_FINGERPRINT_DEFAULTS = {
    "embed_model": "bge-m3:latest",
    "embed_dim": 1024,
    "chunk_size": 1200,
    "chunk_overlap": 150,
    "min_chunk_chars": 80,
    "max_file_bytes": 1_000_000,
    "context_header": False,
    "use_bm25": False,
    "exclude_globs": "",
}


def normalize_fingerprint(fp: Mapping | None) -> dict | None:
    """구 fingerprint를 현재 스키마로 보완합니다.

    저장된 값이 있으면 항상 그것을 우선하고, 과거에 존재하지 않던 키만 당시
    기본값으로 채웁니다. 따라서 새 키 추가가 기존 인덱스를 `params_changed`로
    오판하는 일을 막으면서도 실제 설정 차이는 보존합니다.
    """
    if not fp:
        return None
    out = dict(LEGACY_FINGERPRINT_DEFAULTS)
    out.update(dict(fp))
    if out.get("exclude_globs") is None:
        out["exclude_globs"] = ""
    return out


def profile_value(profile: Mapping | None, key: str):
    """명시적 인덱스 프로필의 값. 없을 때만 현재 CFG를 사용합니다."""
    if profile is not None and key in profile:
        return profile[key]
    return getattr(CFG, key)
