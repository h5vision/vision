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
    max_file_bytes: int = field(default_factory=lambda: _env("VSS_MAX_FILE_BYTES", 1_000_000))

    # ── 검색 (md 실험 대상) ──────────────────────────────────
    top_k: int = field(default_factory=lambda: _env("VSS_TOP_K", 4))
    # FN-B06 근거 없음 판정. D9 실측: answerable 최저 0.5531 / no-answer 최고 0.5306
    score_threshold: float = field(default_factory=lambda: _env("VSS_THRESHOLD", 0.5400))

    # ── 저장 ─────────────────────────────────────────────────
    index_dir: str = field(default_factory=lambda: _env("VSS_INDEX_DIR", "./data/index"))
    state_path: str = field(default_factory=lambda: _env("VSS_STATE_PATH", "./data/state.json"))

    def fingerprint(self) -> dict:
        """인덱스와 함께 저장할 파라미터 지문.

        ⚠ commit 이 같아도 이 값이 다르면 인덱스는 stale 입니다.
           청킹 파라미터를 바꿔가며 실험하므로 반드시 필요합니다.
        """
        return {
            "embed_model": self.embed_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
        }

    def to_dict(self) -> dict:
        return asdict(self)


CFG = Config()
