"""
청킹 — 검색 품질을 결정하는 최대 변수. md 실험의 핵심 대상.

두 가지 전략을 씁니다.
  code : 줄 단위 윈도우 + 오버랩  → line_start / line_end 추적
  doc  : 마크다운 섹션(##) 단위    → section 추적

⚠ 산출 레코드의 필드명은 백엔드의 Source 스키마에 맞췄습니다.
   나중에 모듈로 넘길 때 변환 계층이 필요 없게 하기 위함입니다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from . import context_header
from .config import (CFG, CODE_EXT, DOC_EXT, SKIP_DIRS, SKIP_FILE_PATTERNS,
                     is_excluded, profile_value)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def classify(path: Path) -> str | None:
    """파일 종류 판정. 대상이 아니면 None."""
    ext = path.suffix.lower()
    if ext in DOC_EXT:
        return "doc"
    if ext in CODE_EXT:
        return "code"
    return None


def collect_files(root: str | Path, profile: Mapping | None = None) -> list[Path]:
    """인덱싱 대상 파일 목록.

    제외 순서: SKIP_DIRS(디렉터리 이름) → SKIP_FILE_PATTERNS(파일 이름)
             → VSS_EXCLUDE_GLOBS(경로 패턴) → 확장자 → 크기

    ⚠ `incremental._is_target()` 과 **같은 기준이어야 합니다.**
       한쪽만 고치면 전체 인덱싱과 증분 인덱싱의 대상이 갈립니다.
    """
    root = Path(root).resolve()
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_FILE_PATTERNS:
            continue
        if is_excluded(p.relative_to(root).as_posix(),
                       str(profile_value(profile, "exclude_globs"))):
            continue
        if classify(p) is None:
            continue
        try:
            if p.stat().st_size > int(profile_value(profile, "max_file_bytes")):
                continue
        except OSError:
            continue
        out.append(p)
    return sorted(out)


def _read(path: Path) -> str | None:
    """UTF-8 우선, 실패하면 관대하게. 바이너리로 보이면 버림."""
    for enc in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
        if "\x00" in text[:4096]:
            return None
        return text
    return None


def chunk_code(text: str, rel_path: str,
               profile: Mapping | None = None) -> list[dict]:
    """줄 단위 윈도우. 문자 수 기준으로 자르되 줄 경계를 지킵니다."""
    lines = text.splitlines()
    chunks: list[dict] = []

    i = 0
    n = len(lines)
    while i < n:
        buf: list[str] = []
        size = 0
        j = i
        while j < n and size < int(profile_value(profile, "chunk_size")):
            buf.append(lines[j])
            size += len(lines[j]) + 1
            j += 1

        body = "\n".join(buf).strip()
        if len(body) >= int(profile_value(profile, "min_chunk_chars")):
            # 이 청크를 감싸는 정의(class / def 등)를 위쪽에서 찾습니다.
            # ⚠ 임베딩은 텍스트만 보므로, 이 정보가 텍스트에 들어가야
            #    "결제 처리는 어디서?" 같은 질문과 연결됩니다.
            use_header = bool(profile_value(profile, "context_header"))
            enclosing = context_header.find_enclosing(lines, i) if use_header else []
            if use_header:
                hdr = context_header.build(rel_path, "code", enclosing=enclosing)
                body = context_header.apply(body, hdr)

            chunks.append({
                "type": "code",
                "path": rel_path,
                "line_start": i + 1,      # 1-based
                "line_end": j,
                "section": None,
                "enclosing": enclosing or None,
                "text": body,
            })

        if j >= n:
            break

        # 오버랩 — 문자 수를 줄 수로 환산
        avg = max(1, size // max(1, (j - i)))
        back = max(1, int(profile_value(profile, "chunk_overlap")) // avg)
        i = max(i + 1, j - back)

    return chunks


def chunk_doc(text: str, rel_path: str,
              profile: Mapping | None = None) -> list[dict]:
    """마크다운 섹션 단위. 섹션이 너무 길면 추가 분할."""
    lines = text.splitlines()
    blocks: list[tuple[str, int, list[str]]] = []   # (section, start_line, lines)
    cur_title = "(intro)"
    cur_start = 1
    cur: list[str] = []

    for idx, line in enumerate(lines, start=1):
        m = _HEADING.match(line)
        if m:
            if any(s.strip() for s in cur):
                blocks.append((cur_title, cur_start, cur))
            cur_title = m.group(2).strip()
            cur_start = idx
            cur = [line]
        else:
            cur.append(line)
    if any(s.strip() for s in cur):
        blocks.append((cur_title, cur_start, cur))

    chunks: list[dict] = []
    for title, start, body_lines in blocks:
        body = "\n".join(body_lines).strip()
        if len(body) < int(profile_value(profile, "min_chunk_chars")):
            continue

        if len(body) <= int(profile_value(profile, "chunk_size")) * 1.5:
            if bool(profile_value(profile, "context_header")):
                hdr = context_header.build(rel_path, "doc", section=title)
                body = context_header.apply(body, hdr)
            chunks.append({
                "type": "doc",
                "path": rel_path,
                "line_start": start,
                "line_end": start + len(body_lines) - 1,
                "section": title,
                "enclosing": None,
                "text": body,
            })
        else:
            # 긴 섹션은 다시 자르되 섹션 제목은 유지
            for sub in chunk_code(body, rel_path, profile):
                sub_text = sub["text"]
                if bool(profile_value(profile, "context_header")):
                    sub_text = context_header.strip(sub_text)
                    hdr = context_header.build(rel_path, "doc", section=title)
                    sub_text = context_header.apply(sub_text, hdr)
                chunks.append({
                    "type": "doc",
                    "path": rel_path,
                    "line_start": start + sub["line_start"] - 1,
                    "line_end": start + sub["line_end"] - 1,
                    "section": title,
                    "enclosing": None,
                    "text": sub_text,
                })
    return chunks


def chunk_file(path: Path, root: Path,
               profile: Mapping | None = None) -> list[dict]:
    """파일 하나 → 청크 목록. 실패하면 빈 목록."""
    text = _read(path)
    if not text or not text.strip():
        return []

    rel = path.relative_to(root).as_posix()
    return chunk_text(text, rel, profile)


def chunk_text(text: str, rel_path: str,
               profile: Mapping | None = None) -> list[dict]:
    """프로젝트 상대 경로와 파일 전체 문자열을 기존 청커로 처리합니다.

    Snapshot/Frontend 증분 갱신은 로컬 파일을 만들지 않고 최종 파일 문자열을
    전달합니다. 전체 인덱싱과 증분 인덱싱의 청킹 규칙이 갈라지지 않도록
    ``chunk_file()``도 이 함수를 사용합니다.
    """
    kind = classify(Path(rel_path))
    if kind is None or not isinstance(text, str) or not text.strip():
        return []

    chunks = (chunk_doc(text, rel_path, profile) if kind == "doc"
              else chunk_code(text, rel_path, profile))

    # ⚠ 파일 내 순번. 증분 인덱싱에서 청크 ID 를 안정적으로 만들기 위해 필요합니다.
    #    순번이 없으면 "이 파일의 청크"를 특정할 수 없어 부분 삭제가 불가능합니다.
    for i, c in enumerate(chunks):
        c["chunk_index"] = i
    return chunks


def chunk_repo(root: str | Path,
               profile: Mapping | None = None) -> tuple[list[dict], list[Path]]:
    """레포 전체 청킹. (청크 목록, 처리한 파일 목록) 반환."""
    root = Path(root).resolve()
    files = collect_files(root, profile)
    chunks: list[dict] = []
    for f in files:
        chunks.extend(chunk_file(f, root, profile))
    return chunks, files
