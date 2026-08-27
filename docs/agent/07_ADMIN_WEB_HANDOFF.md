# 독립 Admin Web Phase 2 인계 계약

최종 확인일: 2026-08-27 KST

이 문서는 VS Code Webview가 아닌 독립 Admin Web 서버가 Backend 관리 API를 구현할
때 사용하는 Phase 2 인계 기준입니다. 현재 Phase에서는 schema와 fixture만 고정하며
실제 Admin HTTP router와 UI 서버는 아직 구현하지 않습니다.

## 서비스 경계

```text
Browser
  ↓ HTTPS
Independent Admin Web Server
  ↓ JSON + 관리자 인증
Snapshot Backend /v1/admin/*
  ↓
PostgreSQL / RAG Lab / 선택적 Git provider
```

- Admin Web은 RAG Lab, PostgreSQL, Git provider에 직접 접근하지 않습니다.
- RAG Lab token, DATABASE_URL과 Git credential을 browser bundle, local storage 또는
  API response에 포함하지 않습니다.
- Admin Web 배포 origin과 인증/RBAC는 `LIVE-09`, `LIVE-10` 확정 전에는 production에
  노출하지 않습니다.

## Phase 2 schema 위치

| 경계 | 구현 위치 |
|---|---|
| VS Code Workspace Overlay | `backend/features/workspace_overlays/schemas.py` |
| Frontend → Model 명시적 변환 | `backend/features/workspace_overlays/mapper.py` |
| Model/RAG Lab | `backend/integrations/rag_lab/schemas.py` |
| Repository/Branch binding | `backend/features/repositories/schemas.py` |
| Snapshot 목록·상세·재시도 | `backend/features/snapshots/schemas.py` |
| Admin 공통 오류·mutation | `backend/features/admin/schemas.py` |

고정 JSON fixture는 `tests/fixtures/frontend`, `tests/fixtures/model`,
`tests/fixtures/admin`에 있습니다. Admin Web은 문서 예시를 다시 작성하기보다 이
fixture와 Backend OpenAPI를 기준으로 client type을 생성하거나 검증합니다.

## 예정 관리 API

| Method | Path | 화면 동작 | 구현 Phase |
|---|---|---|---:|
| `GET` | `/v1/admin/repositories` | Repository 목록 | 3 |
| `POST` | `/v1/admin/repositories` | Repository 등록 | 3 |
| `PATCH` | `/v1/admin/repositories/{repository_id}` | 표시값·기본 Branch 변경 | 3 |
| `DELETE` | `/v1/admin/repositories/{repository_id}` | 물리 삭제가 아닌 비활성화 | 3 |
| `GET` | `/v1/admin/repositories/{repository_id}/branches` | Branch 선택 목록 | 3 |
| `GET/POST` | `/v1/admin/branch-bindings` | binding 목록·등록 | 3 |
| `PATCH/DELETE` | `/v1/admin/branch-bindings/{binding_id}` | binding 변경·비활성화 | 3 |
| `GET` | `/v1/admin/snapshots` | Repository/Branch별 이력 | 4 |
| `GET` | `/v1/admin/snapshots/{snapshot_id}` | 상세와 attempt | 4 |
| `POST` | `/v1/admin/snapshots/{snapshot_id}/retry` | 동일 Snapshot 재시도 | 5 |

Branch에는 `/`가 포함될 수 있으므로 Snapshot 목록은 `branch_ref` query parameter로
필터링합니다. 목록은 opaque cursor 기반 `next_cursor`를 사용하며 offset 내부 형식을
Admin Web이 해석하지 않습니다.

## 화면 상태 모델

| 상태 | 진입 조건 | 표시 및 허용 동작 |
|---|---|---|
| `loading` | 최초 조회·필터 변경 | 중복 mutation 비활성화 |
| `empty` | Repository 또는 Snapshot 없음 | 등록 또는 필터 초기화 안내 |
| `ready` | 목록·상세 조회 성공 | 권한에 따른 관리 동작 허용 |
| `validation_error` | `400/422` | `detail`과 안전한 필드 오류 표시 |
| `binding_required` | `409 SNAPSHOT_DESTINATION_REQUIRED` | Repository/Branch/Model binding 설정 이동 |
| `binding_ambiguous` | `409 SNAPSHOT_DESTINATION_AMBIGUOUS` | 활성 binding 정리 안내 |
| `unauthenticated` | `401 ADMIN_AUTHENTICATION_REQUIRED` | 로그인 이동, mutation 금지 |
| `forbidden` | `403 ADMIN_PERMISSION_DENIED` | 권한 부족 표시, mutation 금지 |
| `unavailable` | `500/502/504` | `reason`, `detail`, `retryable` 표시 |
| `retrying` | Snapshot retry 접수 중 | 같은 Snapshot의 중복 클릭 방지 |

HTTP status만으로 문구를 추측하지 않고 JSON의 `reason`, `detail`, `retryable`을
사용합니다. 응답 `X-Request-ID`와 body의 `request_id`는 장애 문의와 감사 화면에서
동일한 값으로 표시합니다.

## Repository/Branch 선택 규칙

- `repository_id`는 Backend가 발급한 UUID입니다.
- provider상의 `owner/name`은 별도 `canonical_name`이며 표시 이름과도 분리합니다.
- `branch_ref` 정본은 `refs/heads/...` full ref입니다.
- 현재 VS Code payload에는 Branch가 없으므로 `frontend_project_id`당 활성 binding을
  하나만 허용합니다.
- binding은 exact `model_project_id`를 포함하며 유사 이름을 자동 선택하지 않습니다.
- binding 변경은 이후 Snapshot에만 적용되고 과거 Snapshot의 Repository/Branch 값은
  바뀌지 않습니다.
- 동시 다중 Branch가 필요하면 Frontend 선택 필드 계약이 확정되기 전까지 지원됨으로
  표시하지 않습니다.

## Snapshot 변경 제한

- Snapshot 생성은 VS Code의 `/v1/workspace-overlays` 요청으로만 시작합니다.
- Admin은 Snapshot revision이나 파일 본문을 수정하지 않습니다.
- Retry는 같은 `snapshot_id`를 유지하고 `attempt_count`만 증가시킵니다.
- Snapshot 물리 삭제는 `LIVE-07` 보존 정책 확정 전까지 제공하지 않습니다.
- Repository와 binding의 `DELETE`는 초기에는 `active=false` 비활성화입니다.

## Phase 2 저장 결정

MVP Snapshot 본문과 이력은 PostgreSQL에 저장하는 안전 기본값으로 고정합니다.
Repository/Branch는 이력을 분류하는 namespace이며 실제 Git remote 쓰기를 의미하지
않습니다. Object Storage 전환은 locator 기반 후속 확장으로 남깁니다.

실제 Git remote에 commit/ref를 생성하거나 push하지 않습니다. 제품 요구가 별도로
확정되면 provider adapter, credential 소유권, expected branch head,
non-fast-forward, 부분 실패와 멱등성 계약을 먼저 추가합니다.

## Phase 3 진입 전 확인값

- Admin Web 소스 저장소와 배포 담당자
- 개발·운영 Admin origin
- 인증 제공자, 관리자 역할과 session 방식
- Repository branch catalog를 수동 등록할지 provider API로 동기화할지
- 초기 `frontend_project_id`별 exact Repository/Branch/Model binding

이 값들은 schema와 mock test 작성을 막지 않지만 Admin mutation을 production에
노출하기 전에는 반드시 확정합니다.
