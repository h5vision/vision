"""재현 가능한 전체 인덱싱 프로필.

프로필 이름은 사람이 읽는 실험 버전이고, 실제 정본은 완전히 해석된 fingerprint와
그 SHA-256 해시입니다. 환경변수 CFG는 명시적 프로필의 값을 덮어쓰지 않습니다.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

from .config import LEGACY_FINGERPRINT_DEFAULTS, normalize_fingerprint
from .store import MAX_PROJECT_ID


DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "profiles" / "index_profiles.json"
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
FINGERPRINT_KEYS = tuple(LEGACY_FINGERPRINT_DEFAULTS)


class ProfileError(ValueError):
    pass


def load_registry(path: str | Path | None = None) -> dict:
    p = Path(path or DEFAULT_REGISTRY).resolve()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ProfileError(f"프로필 레지스트리가 없습니다: {p}") from e
    except json.JSONDecodeError as e:
        raise ProfileError(f"프로필 JSON 파싱 실패: {p}:{e.lineno}: {e.msg}") from e
    if data.get("schema_version") != "1.0" or not isinstance(data.get("profiles"), dict):
        raise ProfileError("index_profiles.json은 schema_version=1.0과 profiles 객체가 필요합니다")
    return data


def _validate_fingerprint(fp: Mapping) -> dict:
    unknown = sorted(set(fp) - set(FINGERPRINT_KEYS))
    missing = sorted(set(FINGERPRINT_KEYS) - set(fp))
    if unknown:
        raise ProfileError(f"알 수 없는 인덱싱 설정: {', '.join(unknown)}")
    if missing:
        raise ProfileError(f"해석된 프로필에 설정이 빠졌습니다: {', '.join(missing)}")

    out = dict(fp)
    for key in ("embed_dim", "chunk_size", "chunk_overlap", "min_chunk_chars", "max_file_bytes"):
        if isinstance(out[key], bool) or not isinstance(out[key], int) or out[key] < 0:
            raise ProfileError(f"{key}는 0 이상의 정수여야 합니다")
    if out["embed_dim"] <= 0 or out["chunk_size"] <= 0 or out["max_file_bytes"] <= 0:
        raise ProfileError("embed_dim, chunk_size, max_file_bytes는 0보다 커야 합니다")
    if out["chunk_overlap"] >= out["chunk_size"]:
        raise ProfileError("chunk_overlap은 chunk_size보다 작아야 합니다")
    for key in ("context_header", "use_bm25"):
        if not isinstance(out[key], bool):
            raise ProfileError(f"{key}는 boolean이어야 합니다")
    if not isinstance(out["embed_model"], str) or not out["embed_model"].strip():
        raise ProfileError("embed_model은 비어 있지 않은 문자열이어야 합니다")
    if not isinstance(out["exclude_globs"], str):
        raise ProfileError("exclude_globs는 쉼표 구분 문자열이어야 합니다")
    return out


def resolve_profile(profile_id: str, *, registry_path: str | Path | None = None) -> dict:
    """상속을 풀어 완전한 fingerprint와 불변 해시를 돌려줍니다."""
    data = load_registry(registry_path)
    definitions = data["profiles"]
    if profile_id not in definitions:
        raise ProfileError(
            f"등록되지 않은 profile입니다: {profile_id!r}; available={', '.join(definitions)}")
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise ProfileError(f"잘못된 profile id: {profile_id!r}")

    def merge(pid: str, stack: tuple[str, ...] = ()) -> dict:
        if pid in stack:
            raise ProfileError(f"프로필 상속 순환: {' -> '.join((*stack, pid))}")
        item = definitions.get(pid)
        if not isinstance(item, dict):
            raise ProfileError(f"프로필 정의가 객체가 아닙니다: {pid}")
        base = item.get("based_on")
        values = merge(base, (*stack, pid)) if base else dict(LEGACY_FINGERPRINT_DEFAULTS)
        settings = item.get("settings")
        if not isinstance(settings, dict):
            raise ProfileError(f"프로필 settings가 객체가 아닙니다: {pid}")
        unknown = sorted(set(settings) - set(FINGERPRINT_KEYS))
        if unknown:
            raise ProfileError(f"{pid}의 알 수 없는 설정: {', '.join(unknown)}")
        values.update(settings)
        return values

    fp = _validate_fingerprint(normalize_fingerprint(merge(profile_id)) or {})
    canonical = json.dumps(fp, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    item = definitions[profile_id]
    return {
        "profile_id": profile_id,
        "profile_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12],
        "label": item.get("label", profile_id),
        "description": item.get("description", ""),
        "based_on": item.get("based_on"),
        "fingerprint": fp,
    }


def list_profiles(*, registry_path: str | Path | None = None) -> list[dict]:
    data = load_registry(registry_path)
    return [resolve_profile(pid, registry_path=registry_path) for pid in data["profiles"]]


def fingerprint_hash(fp: Mapping) -> str:
    resolved = _validate_fingerprint(normalize_fingerprint(fp) or {})
    raw = json.dumps(resolved, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def project_id_for(repository: str | Path, profile_id: str) -> str:
    """동일 레포 버전 비교용 `<repo>--<profile>` project_id를 만듭니다."""
    repo = Path(repository).resolve().name.lower()
    repo = re.sub(r"[^a-z0-9.-]+", "-", repo).strip("-.") or "repo"
    raw = f"{repo}--{profile_id}"
    if len(raw) <= MAX_PROJECT_ID:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    keep = MAX_PROJECT_ID - len(profile_id) - len(digest) - 4
    return f"{repo[:max(3, keep)].rstrip('-.')}--{profile_id}-{digest}"
