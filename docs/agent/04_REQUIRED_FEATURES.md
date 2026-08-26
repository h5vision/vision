# 필요한 기능

## P0 — 필수 통신 기능

### 1. Workspace Overlay 수신

```http
POST /v1/workspace-overlays
```

- Frontend의 현재 JSON을 변경 없이 수신합니다.
- 새로운 필수 필드를 요구하지 않습니다.
- 빈 배열을 허용합니다. `files`, `deleted_paths`, `renames`가 모두 비어 있어도
  실제 40자리 `base_revision`과 `target_revision`이 다른 Git empty commit일 수
  있으므로 revision-only update로 Model에 전달합니다. Model 현행 구현은 이 경우
  인덱스 내용을 바꾸지 않고 성공 뒤 target revision을 승격할 수 있습니다.
- HTTP 상태 코드와 함께 항상 구조화된 JSON body를 반환합니다. Frontend가 현재
  비정상 status에서도 JSON만 읽으므로 빈 body나 HTML 오류 페이지를 반환하지 않습니다.

### 2. Git revision 검증

- `base_revision`, `target_revision`은 40자리 hexadecimal Git SHA만 허용합니다.
- SHA를 Backend에서 임의 생성하거나 교체하지 않습니다.
- 로컬 commit인지 remote commit인지 여부는 revision 유효성과 분리합니다.

### 3. 파일 경로 및 내용 검증

- 상대 POSIX 경로만 허용합니다.
- 절대경로, Windows drive, `..`, 빈 path segment, NUL을 거부합니다.
- rename의 새 경로는 최종 파일 content와 함께 전달되어야 합니다.
- 같은 경로가 수정과 삭제에 동시에 등장하면 거부합니다.
- 파일 content를 diff patch로 변환하지 않습니다.

### 4. Project ID 매핑

- Frontend project ID와 Model exact project ID를 별도 저장합니다.
- Model `GET /projects` 결과를 동기화합니다.
- 자동 매핑은 exact match만 허용합니다.
- leaf name 또는 유사 문자열은 후보로만 제공하고 자동 확정하지 않습니다.

### 5. Model 전달

```http
POST /index/update/files
```

- 요청 body의 파일 내용과 revision을 보존합니다.
- 선택적인 내부 `snapshot_id`만 추가할 수 있습니다.
- `X-VSS-Token`은 환경변수로 관리합니다.
- Model 청킹과 임베딩을 Backend에 복제하지 않습니다.
- 현재 Frontend POST timeout이 10초이므로 접수 경로의 총 timeout budget 기본값은
  8초로 둡니다. 실제 인덱싱 완료를 기다리지 않고 Model의 `200` 또는 `202`를 받으면
  즉시 Frontend에 반환합니다.

### 6. 상태 코드와 오류 보존

- upstream `200`, `202`, `400`, `409`를 의미 그대로 반환합니다.
- Model의 `reason`, `detail`, `conflict`, `already_applied`를 제거하지 않습니다.
- Model의 `200`, `202`, `400`, `409`는 보존합니다. 연결 실패, token 설정 오류,
  유효하지 않은 응답과 upstream `5xx`는 `502`, timeout은 `504` 구조화 오류로
  변환하며 원래 status와 body는 내부 attempt에 저장합니다.
- Backend 자체 오류는 `ok`, 안정적인 `reason`, 사람이 읽을 수 있는 `detail`,
  `retryable`을 포함합니다.
- 모든 응답에 `X-Request-ID`를 반환하고 Snapshot 생성 뒤에는 내부
  `snapshot_id`로 요청, DB 기록과 upstream 응답을 연결합니다.

### 7. 상태 조회 프록시

```http
GET /v1/index/status?project_id=...
```

- Frontend ID를 Model exact ID로 매핑합니다.
- Model `/index/status` body를 보존합니다.
- 권장 polling 주기는 Model 계약에 따라 2~3초입니다.

## P1 — Snapshot 내부 관리

### Snapshot 레코드

권장 최소 필드:

```text
snapshot_id
request_id
frontend_project_id
model_project_id
base_revision
target_revision
source_type
state
attempt_count
upstream_status_code
upstream_reason
upstream_detail
created_at
updated_at
```

`snapshot_id`는 내부 레코드 ID이며 Git SHA가 아닙니다.

### 변경 파일 레코드

```text
snapshot_id
status
path
encoding
content
deleted
old_path
created_at
```

초기 MVP에서는 PostgreSQL에 저장할 수 있습니다. 대용량 정책이 확정되면 파일 본문을 Object Storage에 두고 DB에는 locator와 metadata만 저장하는 구조로 교체할 수 있어야 합니다.

### 전달 attempt 레코드

Model 호출과 재시도를 Snapshot 본체에 덮어쓰지 않고 별도 attempt로 남깁니다.

```text
attempt_id
snapshot_id
request_id
attempt_number
started_at
finished_at
upstream_status_code
upstream_reason
upstream_detail
retryable
latency_ms
response_body_json
```

`response_body_json`은 Model의 구조화된 body를 보존하되 token과 파일 content를
포함하지 않습니다. 같은 Snapshot의 attempt number에는 unique constraint를 둡니다.

### Snapshot 상태와 전이

| 현재 상태 | 다음 상태 | 전이 조건 |
|---|---|---|
| `received` | `validated` | request schema와 업무 검증 성공 |
| `received` | `rejected` | 복구 불가능한 request 검증 실패 |
| `validated` | `mapping_required` | exact 또는 명시적 project 매핑이 없음 |
| `validated` | `forwarding` | Model exact project ID 확정 및 DB 수신 기록 commit 완료 |
| `mapping_required` | `forwarding` | 관리자가 명시적 매핑을 확정하고 재처리 |
| `forwarding` | `accepted` | Model `202` |
| `forwarding` | `already_applied` | Model `200`과 `already_applied: true` |
| `forwarding` | `rejected` | Model `400` 또는 재시도 불가능한 `409` |
| `forwarding` | `failed` | 연결 실패, timeout 또는 응답 기록 실패 |
| `accepted` | `completed` | Model `state=done`, `commit=target_revision`, `update_error` 없음 |
| `accepted` | `failed` | Model `state=failed` 또는 `update_error` 존재 |

정의되지 않은 역방향 전이는 허용하지 않습니다. 재시도는 기존 Snapshot에 attempt를
추가하고 같은 `snapshot_id`를 유지하며, 새 Git Snapshot처럼 만들지 않습니다.

Model이 `202`를 반환했다고 완료로 기록하면 안 됩니다. Model은 증분 작업이 실패해도
rollback에 성공하면 기존 인덱스를 계속 제공하려고 `state=done`, `commit=base_revision`,
`update_error=<실패 원인>`으로 남길 수 있습니다. 따라서 완료는 다음 조건을 모두
확인합니다.

```text
state == done
commit == target_revision
update_error is null or absent
```

### 멱등성

같은 프로젝트와 같은 `target_revision`의 재전송은 중복 Snapshot과 중복 Model 작업을 만들지 않아야 합니다.

권장 unique 기준:

```text
(model_project_id, target_revision)
```

단, project 매핑이 확정되기 전에는 Frontend project ID와 target revision으로 임시 수신 레코드를 구분합니다.

- 매핑 전에는 `(frontend_project_id, target_revision)` unique 기준을 사용합니다.
- 매핑 뒤에는 `(model_project_id, target_revision)` unique 기준을 사용합니다.
- 동시 요청은 DB unique constraint와 transaction으로 하나만 생성되게 합니다.
- 기존 상태가 `accepted`, `completed`, `already_applied`이면 새 Model 작업을 만들지
  않고 현재 Snapshot 결과를 반환합니다.
- 기존 상태가 `forwarding`이면 즉시 중복 호출하지 않고 진행 상태를 반환하거나
  recovery 절차로 보냅니다.

### DB 기록과 upstream 호출 순서

부분 성공을 숨기지 않기 위해 다음 순서를 고정합니다.

```text
request 검증
→ project 매핑 확정
→ Snapshot과 변경 파일을 DB에 저장하고 transaction commit
→ forwarding 상태 commit
→ Model 호출
→ Model status/body/latency와 최종 접수 상태 commit
→ Frontend 응답
```

- 최초 DB commit이 실패하면 Model을 호출하지 않습니다.
- Model 응답을 받은 뒤 DB 결과 기록이 실패하면 성공으로 가장하지 않고
  `SNAPSHOT_RESULT_PERSIST_FAILED`로 반환하며 request ID를 로그에 남깁니다.
- 프로세스 재시작 시 오래된 `forwarding`과 `accepted`를 조회해 Model 상태와
  대조합니다. 재전송 전에 target revision의 적용 여부를 먼저 확인합니다.
- 로그에는 파일 전체 content를 남기지 않고 파일 수, 경로 수, revision,
  request ID, snapshot ID와 upstream status만 남깁니다.

## P1 — 로컬 Git commit 지원

- GitHub에 push되지 않은 commit도 받습니다.
- `source_type=client_local_git`로 기록할 수 있습니다.
- GitHub API 조회 실패를 payload 실패로 취급하지 않습니다.
- 변경 파일 전체 문자열을 Model 증분 입력으로 사용합니다.
- 기준 Snapshot 또는 Model의 현재 revision이 없으면 안전하게 `409`를 반환합니다.

## P1 — 시작 및 재시작 복구

- 시작 시 DB migration 적용 여부를 확인하고 실패하면 애플리케이션 readiness를
  실패시킵니다.
- `forwarding` 상태가 timeout 기준을 넘으면 Model `/index/status`와 exact target을
  조회해 `accepted`, `completed`, `failed` 중 하나로 복구합니다.
- `accepted` 상태는 Frontend 상태 조회 시 동기화합니다. Background polling은
  최초 MVP의 필수 조건이 아니며 stale 탐지 worker는 P2에서 추가합니다.
- Model 상태가 `none`이거나 현재 revision을 확인할 수 없으면 자동 재전송하지 않고
  구조화된 recovery 오류로 남깁니다.

## P2 — 운영 기능

- Snapshot 수신, 전달, 응답, 완료 이벤트 로그
- request ID와 snapshot ID 상관관계
- Model latency와 timeout 기록
- 실패 요청 수동 재시도
- stale `accepted` 상태 탐지
- 관리자 project mapping CRUD
- Snapshot 목록과 상태 조회
- 보존 기간 및 대용량 본문 정리 정책

## 비기능 요구사항

- 설정은 환경변수 기반이어야 합니다.
- Windows 경로를 코드에 하드코딩하지 않습니다.
- Model base URL과 token을 소스에 넣지 않습니다.
- 외부 HTTP client는 connection pooling과 명시적인 timeout을 사용합니다.
- DB 기록 실패와 Model 전달 실패의 순서를 명확히 하고 부분 성공을 숨기지 않습니다.
- 로그에 파일 전체 content와 비밀정보를 출력하지 않습니다.
- transport payload 크기, 파일 수, 단일 파일 크기와 보존 기간은
  `06_READINESS_AND_VERIFICATION.md`의 실환경 필수 결정값입니다. 합의 없이
  Frontend나 Model보다 더 작은 고정 제한을 코드에 넣지 않습니다.
