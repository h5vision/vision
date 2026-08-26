# 외부 통신 계약

## 기본 원칙

Backend는 자체 외부 규약을 새로 정의하지 않습니다.

- Frontend가 이미 보내는 요청을 그대로 받습니다.
- Model/RAG Lab이 이미 받는 요청으로 전달합니다.
- 추가 데이터는 Backend 내부 기록으로만 관리합니다.
- 상대 규약에 없는 값을 Frontend 필수 입력으로 만들지 않습니다.

## Frontend → Backend

### Endpoint

```http
POST /v1/workspace-overlays
Content-Type: application/json
```

Frontend 설정값 `vision.endpoint`가 `http://192.168.0.7/v1`이면 실제 호출 주소는 다음과 같습니다.

```text
http://192.168.0.7/v1/workspace-overlays
```

### 런타임 주소 구분

```text
http://192.168.0.7/v1         Frontend가 호출하는 Snapshot Backend 기본값
http://127.0.0.1:8200         RAG Lab API 기본 예시
http://127.0.0.1:11500        Frontend 호스트의 AI/Ollama 로컬 진입점
http://192.168.0.12:11500     현재 Windows portproxy가 연결하는 AI/Ollama 대상
```

`11500`의 `/api/chat`과 `8200`의 `/index/update/files`는 서로 다른 계약입니다.
Frontend의 기존 AI 호출 경로를 Snapshot 전달 경로에 합치거나
`RAG_LAB_BASE_URL`을 `11500`으로 설정하지 않습니다.

### Request

```json
{
  "project_id": "h5vision/vision",
  "base_revision": "1111111111111111111111111111111111111111",
  "target_revision": "2222222222222222222222222222222222222222",
  "files": [
    {
      "status": "modified",
      "path": "vision/src/services/gitService.ts",
      "content": "변경 후 파일 전체 문자열",
      "encoding": "utf-8"
    }
  ],
  "deleted_paths": [
    "vision/src/obsolete.ts"
  ],
  "renames": [
    {
      "old_path": "vision/src/old.ts",
      "new_path": "vision/src/new.ts"
    }
  ]
}
```

### Frontend 기준 필드

| 필드 | 필수 | 의미 |
|---|---:|---|
| `project_id` | O | Git remote 경로 또는 workspace 기반 프로젝트 힌트 |
| `base_revision` | O | 이전 실제 Git commit SHA |
| `target_revision` | O | 새 실제 Git commit SHA |
| `files` | O | 추가/수정된 파일의 최종 전체 문자열 |
| `deleted_paths` | O | 삭제된 프로젝트 상대경로 |
| `renames` | O | 이전 경로와 새 경로 |
| `snapshot_id` | X | Frontend에 요구하지 않음 |
| `content_sha256` | X | Frontend에 요구하지 않음 |
| `branch` | X | 현재 payload에는 없음 |

`base_revision`과 `target_revision`은 실제 40자리 Git SHA여야 합니다. GitHub remote에 아직 push되지 않은 로컬 commit도 허용합니다.

## Backend 내부 처리

Backend는 다음 순서로 처리합니다.

```text
JSON/Pydantic 검증
→ Git SHA와 경로 검증
→ Frontend project_id를 Model exact project_id로 매핑
→ 내부 Snapshot 수신 기록
→ Model 요청으로 변환
→ Model 상태 코드와 body 보존
→ 내부 전송 결과 기록
→ Frontend에 구조화된 JSON 반환
```

Backend 내부 `snapshot_id`를 생성할 수 있지만 Git revision과 분리하며 Frontend 요청의 필수 필드로 만들지 않습니다.

## Backend → Model/RAG Lab

### Endpoint

```http
POST {RAG_LAB_BASE_URL}/index/update/files
Content-Type: application/json
X-VSS-Token: <optional>
```

Model의 `API.md`는 `/index/update/files`가 접수만 즉시 반환하며 10초 timeout을
권장합니다. 현재 Frontend `APIService.post()`도 전체 요청을 10초 뒤 중단하므로,
Backend의 이 엔드포인트는 검증, DB 수신 기록, Model 접수와 응답 기록까지 포함해
Frontend 제한보다 짧은 시간 안에 반환해야 합니다. 구현에서는 Model 호출을 포함한
전체 접수 경로에 8초의 총 timeout budget을 기본값으로 두고 환경변수로 조정합니다.
이 timeout을 넘는 실제 인덱싱 작업은 Model 내부 background 작업이며 `202` 이후
`/index/status`로 확인합니다.

### Request

```json
{
  "project_id": "vision--rag-v2",
  "base_revision": "1111111111111111111111111111111111111111",
  "target_revision": "2222222222222222222222222222222222222222",
  "snapshot_id": "optional-internal-snapshot-id",
  "files": [
    {
      "status": "modified",
      "path": "vision/src/services/gitService.ts",
      "content": "변경 후 파일 전체 문자열",
      "encoding": "utf-8"
    }
  ],
  "deleted_paths": [],
  "renames": []
}
```

`snapshot_id`는 Model의 선택 필드입니다. Backend가 내부 추적을 위해 생성했을 때만 전달합니다. `content_sha256`은 Model이 생략을 허용하고 직접 계산하므로 Backend도 반드시 생성할 필요가 없습니다.

### Model 검증 규칙

- `project_id`: Model `GET /projects`에 존재하는 완성 인덱스의 exact ID
- revision: 40자리 Git SHA
- `files[].status`: `added | modified | renamed`
- `files[].path`: 프로젝트 상대 POSIX 경로
- `files[].content`: 변경 후 전체 문자열
- rename의 `new_path`: `files[]`에도 최종 content가 있어야 함
- 현재 인덱스 revision과 `base_revision`이 다르면 충돌

### 상태 코드 보존

HTTP 상태 코드만 반환해서는 안 됩니다. 성공, 접수, 거부, 충돌, 연결 실패를
Frontend가 구분할 수 있도록 모든 응답은 처리 결과와 이유를 담은 JSON body를
함께 반환합니다.

현재 Frontend `APIService.post()`는 JSON을 반환하지만 `CommitDiffService`가 그 값을
사용하지 않습니다. 아래 계약은 상대 프로그램이 원인을 판별할 수 있는 Backend
응답을 보장하며, VS Code UI 표시까지 보장하지는 않습니다. UI 표시가 필요하면
Frontend 브랜치의 별도 변경으로 응답 body를 소비해야 합니다.

| Frontend 응답 | 의미 | JSON body의 판단 근거 |
|---:|---|---|
| `200` | 같은 target이 이미 적용됨 | `ok: true`, `already_applied: true`, `state: "done"`, 적용된 `commit` |
| `202` | 증분 인덱싱 접수 | `ok: true`, `state: "updating"`, `base_revision`, `target_revision`, 접수 파일 수 |
| `400` | Model 요청 계약 오류 | Model의 `ok`, `reason`, `detail`, `conflict`를 원문 의미와 대소문자 그대로 보존 |
| `409` | revision 충돌, 진행 중, 전체 인덱싱 필요 또는 project 매핑 필요 | `reason`, `detail`, `conflict`와 가능한 경우 충돌·매핑 정보 보존 |
| `422` | Backend request schema 검증 실패 | `ok: false`, `reason: "REQUEST_VALIDATION_FAILED"`, 필드별 `detail` 또는 `errors` |
| `500` | Backend Snapshot 저장 또는 결과 기록 실패 | `ok: false`, Backend `reason`, `detail`, `retryable`, `request_id` |
| `502` | Model 연결 실패 또는 유효하지 않은 upstream 응답 | `ok: false`, `reason`, `detail`, `retryable`을 포함한 구조화된 upstream 오류 |
| `504` | Model timeout | `ok: false`, `reason: "RAG_LAB_TIMEOUT"`, `detail`, `retryable: true` |

### 응답 이유 전달 원칙

- Model이 반환한 최상위 필드는 이름, 값, 의미를 바꾸거나 제거하지 않습니다.
- 특히 `reason`, `detail`, `conflict`, `already_applied`는 그대로 보존합니다.
- Model 성공 응답에 `reason` 또는 `detail`이 없으면 Backend가 기존 필드를
  덮어쓰지 않는 범위에서 설명 필드를 보충할 수 있습니다.
- Backend가 직접 생성하는 오류는 최소한 `ok`, `reason`, `detail`, `retryable`을
  포함합니다.
- `reason`은 프로그램이 분기할 수 있는 안정적인 코드이고 `detail`은 사람이
  실패 또는 성공 이유를 이해할 수 있는 설명입니다.
- `202`의 `ok: true`는 작업이 접수됐다는 뜻이며 인덱싱 완료를 뜻하지 않습니다.
- `retryable: true`는 같은 요청을 즉시 반복하라는 뜻이 아닙니다. `detail`과
  Model 상태를 확인한 뒤 재시도해야 합니다.
- Backend가 생성한 각 응답은 `X-Request-ID` 헤더를 포함하고, Snapshot이 생성된
  뒤에는 JSON body에 `snapshot_id`를 보충할 수 있습니다. 이 값들은 추적용이며
  Frontend 요청 필드는 아닙니다.
- 오류 설명에 파일 전체 content, token 또는 비밀정보를 포함하지 않습니다.

Backend가 성공 설명을 보충하는 경우 권장 코드는 다음과 같습니다.

| 상황 | `reason` | `detail` 예시 |
|---|---|---|
| 기존 target 적용 확인 | `TARGET_ALREADY_APPLIED` | `target_revision이 이미 적용되어 추가 작업을 만들지 않았습니다.` |
| 새 증분 작업 접수 | `INDEX_UPDATE_ACCEPTED` | `증분 인덱싱 요청을 접수했으며 상태 조회가 필요합니다.` |

Backend 자체 오류의 권장 코드는 다음과 같습니다. Model이 반환한 소문자
`reason`은 이 코드로 치환하지 않습니다.

| 상황 | `reason` | `retryable` |
|---|---|---:|
| Frontend request schema 오류 | `REQUEST_VALIDATION_FAILED` | `false` |
| project 매핑 필요 | `PROJECT_MAPPING_REQUIRED` | `false` |
| 저장된 project 매핑이 Model에서 사라짐 | `PROJECT_MAPPING_STALE` | `false` |
| Snapshot 최초 저장 실패 | `SNAPSHOT_PERSIST_FAILED` | `true` |
| Model 응답 뒤 결과 저장 실패 | `SNAPSHOT_RESULT_PERSIST_FAILED` | `true` |
| Model 연결 실패 | `RAG_LAB_UNAVAILABLE` | `true` |
| Model token 불일치 | `RAG_LAB_AUTH_FAILED` | `false` |
| Model `5xx` | `RAG_LAB_UPSTREAM_ERROR` | Model 응답 의미에 따라 결정 |
| Model 응답 해석 실패 | `RAG_LAB_INVALID_RESPONSE` | `true` |
| Model timeout | `RAG_LAB_TIMEOUT` | `true` |

Model의 `401`은 Frontend 사용자의 인증 실패가 아니라 Backend와 RAG Lab 사이의
token 설정 오류입니다. Frontend에 `401`로 오인시키지 않고 `502`와
`RAG_LAB_AUTH_FAILED`로 변환하되 upstream status code와 원문 body를 내부
Snapshot attempt에 보존합니다.

Model의 예상하지 못한 `5xx`는 Frontend에 `502 RAG_LAB_UPSTREAM_ERROR`로
반환하고 upstream status와 body를 attempt에 보존합니다. 연결 실패, token 오류,
timeout, 유효하지 않은 JSON과 Model `5xx`를 Model 계약 오류 `400/409`로 위장하지
않습니다.

예를 들어 새 작업이 접수된 경우 Model body를 보존하면서 다음과 같이 성공
이유를 보충할 수 있습니다.

```json
{
  "ok": true,
  "reason": "INDEX_UPDATE_ACCEPTED",
  "detail": "증분 인덱싱 요청을 접수했으며 상태 조회가 필요합니다.",
  "project_id": "vision--rag-v2",
  "state": "updating",
  "base_revision": "1111111111111111111111111111111111111111",
  "target_revision": "2222222222222222222222222222222222222222",
  "files_received": 1,
  "files_indexed": 1,
  "files_deleted": 0,
  "files_renamed": 0,
  "ignored_paths": []
}
```

Model 연결에 실패한 경우에는 HTTP `502`와 함께 다음처럼 반환합니다.

```json
{
  "ok": false,
  "reason": "RAG_LAB_UNAVAILABLE",
  "detail": "RAG Lab에 연결할 수 없습니다.",
  "retryable": true
}
```

## 상태 조회

Backend는 Frontend가 Model에 직접 접근하지 않도록 상태 조회를 프록시합니다.

```http
GET /v1/index/status?project_id=<frontend-or-mapped-id>
```

내부 호출:

```http
GET {RAG_LAB_BASE_URL}/index/status?project_id=<exact-model-project-id>
```

Model 상태 body의 최상위 필드는 제거하지 않습니다. Snapshot 완료 판정은 다음 세
조건을 모두 만족해야 합니다.

```text
state == "done"
commit == Snapshot target_revision
update_error가 없거나 null
```

Model은 증분 실패 뒤 rollback에 성공하면 기존 인덱스를 계속 제공하기 위해
`state: "done"`과 기존 base revision을 유지하면서 `update_error`를 기록할 수
있습니다. 따라서 `state: "done"` 하나만 보고 Snapshot을 `completed`로 바꾸면
안 됩니다. `state: "updating"`은 계속 polling하고 `state: "failed"` 또는
`update_error`가 존재하면 실패 이유를 Snapshot에 저장합니다.

## Project ID 매핑

다음 두 값은 다를 수 있습니다.

```text
Frontend project_id = h5vision/vision
Model project_id    = vision--rag-v2
```

문자열 유사도나 leaf name으로 자동 확정하지 않습니다. 명시적인 매핑 테이블을 사용합니다. 매핑이 없으면 가능한 후보를 포함한 구조화된 `409 PROJECT_MAPPING_REQUIRED`를 반환하고 관리자가 확정할 수 있게 합니다.

```json
{
  "ok": false,
  "reason": "PROJECT_MAPPING_REQUIRED",
  "detail": "Frontend project_id에 대한 exact Model project 매핑이 필요합니다.",
  "conflict": true,
  "retryable": false,
  "frontend_project_id": "h5vision/vision",
  "candidates": [
    {
      "project_id": "vision--rag-v2",
      "state": "done",
      "commit": "1111111111111111111111111111111111111111"
    }
  ]
}
```

`candidates`는 관리자 판단을 돕는 정보일 뿐 첫 항목을 자동 선택하지 않습니다.
명시적 매핑이 Model `/projects`에서 사라지면 같은 형식의
`409 PROJECT_MAPPING_STALE`을 반환하고 Model을 호출하지 않습니다.

## Admin Web → Backend

Admin Web은 VS Code Extension과 분리된 브라우저용 독립 서비스입니다. Admin
Web은 Backend의 관리 API만 호출하며 RAG Lab, PostgreSQL 또는 Git provider에
직접 접근하지 않습니다.

권장 API 경계:

```http
GET    /v1/admin/repositories
POST   /v1/admin/repositories
GET    /v1/admin/repositories/{repository_id}
PATCH  /v1/admin/repositories/{repository_id}
DELETE /v1/admin/repositories/{repository_id}
GET    /v1/admin/repositories/{repository_id}/branches

GET    /v1/admin/branch-bindings
POST   /v1/admin/branch-bindings
PATCH  /v1/admin/branch-bindings/{binding_id}
DELETE /v1/admin/branch-bindings/{binding_id}

GET    /v1/admin/snapshots?repository_id=...&branch_ref=...
GET    /v1/admin/snapshots/{snapshot_id}
POST   /v1/admin/snapshots/{snapshot_id}/retry
```

Branch에는 `/`가 포함될 수 있으므로 Snapshot 목록 필터는 path segment보다
`branch_ref` query parameter를 사용합니다. `DELETE` Repository/Binding은 최초
MVP에서 물리 삭제가 아니라 `active=false` 비활성화로 처리합니다.

### Repository/Branch 바인딩

현재 VS Code Workspace Overlay payload에는 `branch`가 없습니다. 기존 payload에
새 필수 필드를 추가하지 않으면서 Branch별 이력을 보존하기 위해 Admin이 다음 활성
바인딩을 명시적으로 확정합니다.

```json
{
  "frontend_project_id": "h5vision/vision",
  "repository_id": "github:h5vision/vision",
  "branch_ref": "refs/heads/backend_P",
  "model_project_id": "vision--rag-v2",
  "active": true
}
```

- Backend는 Snapshot 수신 시점의 `binding_id`, `repository_id`, `branch_ref`,
  `model_project_id`를 Snapshot 레코드에 복사합니다.
- 이후 Admin이 활성 바인딩을 변경해도 과거 Snapshot의 Repository/Branch 소속을
  다시 쓰지 않습니다.
- 현재 Frontend 계약에서는 `frontend_project_id`당 활성 바인딩을 하나만 허용합니다.
  없거나 둘 이상이면 Model을 호출하지 않고 구조화된 `409`를 반환합니다.
- 같은 Model project는 단일 완료 revision을 가지므로 서로 독립적인 Branch를 같은
  `model_project_id`에 자동 연결하지 않습니다. Branch별 exact Model project 매핑을
  관리자가 확정합니다.
- 여러 사용자가 같은 `frontend_project_id`에서 서로 다른 Branch를 동시에 전송해야
  하면 Admin의 전역 활성 바인딩만으로 구분할 수 없습니다. 이 경우 Frontend에
  선택적 `repository_id`/`branch_ref` 또는 별도 binding 식별자를 전달하는 계약을
  상대 팀과 합의해야 합니다.

권장 Backend 오류 코드는 다음과 같습니다.

| 상황 | HTTP | `reason` | `retryable` |
|---|---:|---|---:|
| 활성 저장 대상 없음 | `409` | `SNAPSHOT_DESTINATION_REQUIRED` | `false` |
| 활성 바인딩이 둘 이상 | `409` | `SNAPSHOT_DESTINATION_AMBIGUOUS` | `false` |
| Repository/Branch 비활성 | `409` | `SNAPSHOT_DESTINATION_INACTIVE` | `false` |
| 관리자 인증 없음 | `401` | `ADMIN_AUTHENTICATION_REQUIRED` | `false` |
| 관리자 권한 부족 | `403` | `ADMIN_PERMISSION_DENIED` | `false` |

관리 API도 모든 응답에 `X-Request-ID`와 구조화된 `reason`, `detail`을 반환합니다.
Admin Web 브라우저에는 RAG Lab token, DATABASE_URL, Git credential을 반환하지
않습니다.

여기서 `repository_id`와 `branch_ref`는 최소한 Snapshot 이력을 분류하는 불변
namespace입니다. 이 계약만으로 Backend가 Git remote에 commit 또는 ref를 생성하고
push하도록 허가된 것은 아닙니다. 실제 Git 저장이 제품 요구라면 provider API/SSH
방식, credential 소유 주체, expected branch head, force-push 금지, 충돌·부분 실패
응답을 Phase 2에서 별도 확정해야 합니다.
