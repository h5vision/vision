# backend_P Agent Guide

이 문서는 새 Chat 또는 자동화 Agent가 `backend_P` 브랜치에서 Snapshot 기능을 구현하기 전에 반드시 읽어야 하는 진입점입니다.

## 작업 범위

- 구현 대상 저장소: `https://github.com/h5vision/vision.git`
- 구현 대상 브랜치: `backend_P`
- 현재 기준 HEAD: `ad17f9c06bdf89a84edaefb2c508569d8ba50cd9`
- 핵심 역할: VS Code Frontend가 보낸 Git 변경 파일을 받아 Model/RAG Lab 규약으로
  전달하고, 독립 Admin Web이 선택한 Repository/Branch별 Snapshot 처리 상태와 이력을
  관리하는 FastAPI Backend

## 필수 읽기 순서

1. `docs/agent/01_REFERENCE_REPOSITORIES.md`
2. `docs/agent/02_EXTERNAL_CONTRACTS.md`
3. `docs/agent/03_TARGET_STRUCTURE.md`
4. `docs/agent/04_REQUIRED_FEATURES.md`
5. `docs/agent/05_IMPLEMENTATION_PLAN.md`
6. `docs/agent/06_READINESS_AND_VERIFICATION.md`

## 규약 권위

외부 통신 규약은 다음 순서로 취급합니다.

1. Frontend `frontend` 브랜치의 실제 TypeScript 요청 코드
2. Model `model` 브랜치의 `rag_lab/API.md`와 실제 Python 검증 코드
3. 이 저장소의 문서와 구현

Frontend 또는 Model의 실제 규약과 이 문서가 충돌하면 상대 브랜치의 최신 코드와 계약을 다시 확인한 뒤 이 문서를 갱신합니다. Backend 편의를 위해 상대 요청 필드명을 바꾸거나 새 필수 필드를 추가하지 않습니다.

## 변경 금지 원칙

- Frontend와 Model 브랜치는 참조 전용입니다. 이 작업에서 수정하지 않습니다.
- `base_revision`과 `target_revision`에는 실제 40자리 Git commit SHA만 허용합니다.
- 임의 UUID, 파일 SHA-256 또는 서버 생성 해시를 Git revision처럼 사용하지 않습니다.
- Frontend에 `snapshot_id`, `content_sha256`, `size_bytes`, `branch`를 필수로 요구하지 않습니다.
- 로컬에서만 존재하는 실제 Git commit SHA도 유효한 revision으로 받습니다.
- Frontend 파일 내용을 diff hunk로 재해석하지 않습니다. 전달된 변경 후 전체 문자열을 사용합니다.
- Model의 `200`, `202`, `400`, `409`와 `reason`, `detail`, `conflict` 의미를 임의로 바꾸지 않습니다.
- FastAPI 안에 Model의 청킹, 임베딩, Chroma, BM25, rollback 구현을 복제하지 않습니다.
- `project_id`를 유사 문자열로 추측하지 않습니다. 명시적인 매핑 또는 Model `/projects`의 exact ID만 사용합니다.

## 구현 경계

```text
VS Code Frontend
    POST /v1/workspace-overlays
             ↓
backend_P
    검증 · project_id 매핑 · Snapshot 기록 · 상태/오류 보존
             ↓
Model/RAG Lab
    POST /index/update/files

독립 Admin Web Server
    /v1/admin/*
             ↓
backend_P
    Repository/Branch binding · Snapshot 이력/재시도 · 인증/감사
```

Snapshot ID가 필요하면 Backend 내부 레코드 식별자로만 생성합니다. 외부 Git SHA와 혼동하지 않으며 Frontend 필수 입력으로 만들지 않습니다.

Admin Web은 VS Code Webview가 아니라 독립 서버에서 제공하며 RAG Lab, PostgreSQL,
Git provider credential에 직접 접근하지 않습니다. 현재 Frontend payload에는
`branch`가 없으므로 Admin의 활성 Repository/Branch/Model binding을 Snapshot 수신
시점에 복사해 과거 이력을 고정합니다. 기존 Frontend에 `branch`를 새 필수 필드로
추가하지 않습니다.

## 런타임 주소 경계

다음 주소는 서로 다른 서비스이므로 바꿔 쓰지 않습니다.

```text
Frontend Snapshot API 기본값  http://192.168.0.7/v1
RAG Lab API 기본 예시         http://127.0.0.1:8200
Frontend AI/Ollama 진입점     http://127.0.0.1:11500
Windows portproxy 실제 대상   http://192.168.0.12:11500
```

`127.0.0.1:11500`은 2026-08-26 KST에 Windows `IP Helper(iphlpsvc)`와
`netsh interface portproxy`를 통해 `192.168.0.12:11500`으로 전달되는 것이
확인된 Frontend 호스트의 로컬 진입점입니다. Snapshot Backend의
`RAG_LAB_BASE_URL`이나 `vision.endpoint`로 사용하지 않습니다. Frontend의 기존
AI 직접 호출 경로는 Snapshot 기능 구현 범위 밖이며 이 작업에서 수정하지 않습니다.

## 작업 안전

- 작업 전 `git status -sb`와 `git diff --check`를 확인합니다.
- 사용자 또는 다른 Agent의 미커밋 파일을 덮어쓰거나 정리하지 않습니다.
- 새 기능은 contract test, unit test, integration test 순으로 검증합니다.
- `docs/agent/06_READINESS_AND_VERIFICATION.md`의 필수 입력값과 중단 조건을
  확인하지 않은 채 실환경 값을 추측하지 않습니다.
- commit/push는 사용자가 명시적으로 요청한 경우에만 수행합니다.
- 비밀키와 토큰은 코드, 문서, 테스트 fixture에 저장하지 않습니다.
