"""
설정 — 실험에서 바꾸는 값은 전부 여기 모읍니다.

환경변수로도 덮어쓸 수 있습니다. 예:
    set VSS_TOP_K=8
    set VSS_OLLAMA_URL=http://127.0.0.1:11434
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict, field


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


@dataclass
class Config:
    # ── 임베딩 ───────────────────────────────────────────────
    # ⚠ 이 두 값은 D9 실측(Hit@3 90%, 임계값 0.53~0.55)의 전제입니다.
    #    바꾸면 임계값을 재측정해야 합니다.
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
    # 인덱싱이 끝나면 프로젝트 브리핑을 자동으로 만듭니다 (FN-A05).
    # ⚠ 브리핑은 LLM 을 호출합니다. indexer 는 그 사실을 모르고,
    #    호출자(server/cli)가 on_done 콜백으로 주입합니다.
    # ⚠ 평가 실험에서 재인덱싱을 반복할 때는 0 으로 꺼두세요. 매번 20초 이상 붙습니다.
    auto_briefing: bool = field(default_factory=lambda: _env("VSS_AUTO_BRIEFING", True))
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
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "context_header": self.context_header,
            "use_bm25": self.use_bm25,
        }

    def to_dict(self) -> dict:
        return asdict(self)


CFG = Config()
