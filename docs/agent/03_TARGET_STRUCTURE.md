# 권장 폴더 구조

## 설계 원칙

기능별 디렉터리를 만들고, 각 기능 안에서 HTTP, schema, service, persistence 역할을 분리합니다. 엔드포인트마다 파일 하나를 만드는 방식과 모든 기능을 하나의 대형 `main.py`에 넣는 방식을 모두 피합니다.

## 목표 구조

```text
backend_P/
├─ AGENTS.md
├─ backend/
│  ├─ __init__.py
│  ├─ app.py
│  │
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ config.py
│  │  ├─ errors.py
│  │  └─ logging.py
│  │
│  ├─ features/
│  │  ├─ health/
│  │  │  ├─ __init__.py
│  │  │  ├─ router.py
│  │  │  └─ service.py
│  │  │
│  │  ├─ workspace_overlays/
│  │  │  ├─ __init__.py
│  │  │  ├─ router.py
│  │  │  ├─ schemas.py
│  │  │  ├─ validation.py
│  │  │  ├─ mapper.py
│  │  │  └─ service.py
│  │  │
│  │  ├─ snapshots/
│  │  │  ├─ __init__.py
│  │  │  ├─ models.py
│  │  │  ├─ schemas.py
│  │  │  ├─ repository.py
│  │  │  ├─ service.py
│  │  │  └─ state.py
│  │  │
│  │  ├─ projects/
│  │  │  ├─ __init__.py
│  │  │  ├─ router.py
│  │  │  ├─ schemas.py
│  │  │  ├─ mapping.py
│  │  │  ├─ repository.py
│  │  │  └─ service.py
│  │  │
│  │  └─ indexing/
│  │     ├─ __init__.py
│  │     ├─ router.py
│  │     ├─ schemas.py
│  │     └─ service.py
│  │
│  ├─ integrations/
│  │  └─ rag_lab/
│  │     ├─ __init__.py
│  │     ├─ client.py
│  │     ├─ schemas.py
│  │     ├─ errors.py
│  │     └─ health.py
│  │
│  └─ infrastructure/
│     └─ database/
│        ├─ __init__.py
│        ├─ session.py
│        └─ migrations/
│
├─ tests/
│  ├─ unit/
│  │  ├─ workspace_overlays/
│  │  ├─ snapshots/
│  │  └─ projects/
│  ├─ contract/
│  │  ├─ test_frontend_contract.py
│  │  └─ test_rag_lab_contract.py
│  └─ integration/
│     └─ test_workspace_overlay_flow.py
│
├─ docs/
│  └─ agent/
├─ main.py
├─ requirements.txt
└─ README.md
```

## 파일별 책임

| 파일명 | 책임 |
|---|---|
| `app.py` | FastAPI 생성과 router 조립만 담당 |
| `router.py` | HTTP path, status code, dependency injection |
| `schemas.py` | 해당 경계의 Pydantic request/response |
| `service.py` | 기능 처리 순서와 use case |
| `validation.py` | Git SHA, 상대경로, 충돌 등 업무 검증 |
| `mapper.py` | Frontend 계약을 Model 계약으로 명시적으로 변환 |
| `models.py` | Snapshot, 변경 파일, 전달 attempt 등 SQLAlchemy DB 모델 |
| `repository.py` | DB 저장과 조회 |
| `state.py` | Snapshot 상태 enum과 전이 규칙 |
| `client.py` | 외부 RAG Lab HTTP 호출 |
| `errors.py` | 외부 연결 및 도메인 오류 타입 |
| `config.py` | 환경변수 로딩과 설정 검증 |

## 외부 계약 분리

양쪽 JSON 구조가 유사해도 같은 schema class를 공유하지 않습니다.

```text
features/workspace_overlays/schemas.py
    Frontend가 보내는 계약의 정본

integrations/rag_lab/schemas.py
    Model이 받거나 반환하는 계약의 정본

features/workspace_overlays/mapper.py
    두 계약 사이의 명시적 변환
```

이렇게 해야 Frontend 또는 Model 한쪽 규약만 바뀌어도 다른 경계를 깨뜨리지 않습니다.

## 피해야 할 구조

```text
backend/utils.py
backend/helpers.py
backend/common.py
backend/manager.py
backend/legacy_app.py
```

책임을 알기 어려운 공용 파일이나 대형 단일 파일을 만들지 않습니다. 공통화는 실제 중복이 확인된 뒤 `core` 또는 `infrastructure`의 구체적인 이름으로 수행합니다.

## 초기 구현 최소 파일

첫 구현에서는 다음 범위만 만들어도 됩니다.

```text
backend/app.py
backend/core/config.py
backend/core/errors.py
backend/features/health/router.py
backend/features/workspace_overlays/router.py
backend/features/workspace_overlays/schemas.py
backend/features/workspace_overlays/validation.py
backend/features/workspace_overlays/mapper.py
backend/features/workspace_overlays/service.py
backend/features/snapshots/models.py
backend/features/snapshots/repository.py
backend/features/snapshots/service.py
backend/features/snapshots/state.py
backend/features/projects/mapping.py
backend/features/projects/repository.py
backend/features/projects/service.py
backend/features/indexing/router.py
backend/features/indexing/schemas.py
backend/features/indexing/service.py
backend/integrations/rag_lab/client.py
backend/integrations/rag_lab/schemas.py
backend/integrations/rag_lab/errors.py
backend/infrastructure/database/session.py
backend/infrastructure/database/migrations/
```

이 범위는 Workspace Overlay 수신, Snapshot/attempt 영속화, project 매핑과
`/v1/index/status` 프록시까지 포함하는 MVP 최소 경계입니다. 관리자 UI, Snapshot 목록
API와 background stale 재시도 worker는 핵심 proxy 흐름이 통과한 뒤 추가합니다.
