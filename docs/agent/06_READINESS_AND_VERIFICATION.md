# 구현 준비와 필수 검증

최종 확인일: 2026-08-26 KST

이 문서는 Snapshot Backend를 구현하면서 Agent가 실환경 값이나 미정 정책을 추측하지
않도록 구현 가능 범위, 필수 입력값, 중단 조건과 검증 증거를 고정합니다.

## 현재 기준선

2026-08-26 KST에 `git ls-remote`로 확인한 값입니다.

| 브랜치 | SHA |
|---|---|
| `backend_P` | `ad17f9c06bdf89a84edaefb2c508569d8ba50cd9` |
| `frontend` | `56b71405e568b059158b1a666fa362f465c6c10a` |
| `model` | `423f45689689df9dd12bd50150e7663d386e4858` |

SHA가 달라지면 이 문서보다 상대 브랜치 실제 코드를 먼저 다시 읽습니다.

## 확정된 런타임 경계

| 호출 주체 | 대상 | 용도 | 근거 |
|---|---|---|---|
| Frontend | `http://192.168.0.7/v1` | Snapshot Backend 기본 endpoint | Frontend `package.json` |
| Frontend | `POST /workspace-overlays` | commit 변경 파일 전달 | `CommitDiffService` |
| Backend | `{RAG_LAB_BASE_URL}/index/update/files` | Model 증분 인덱싱 접수 | Model `API.md`, `server.py` |
| Backend | `{RAG_LAB_BASE_URL}/index/status` | Model 진행 상태 조회 | Model `API.md`, `server.py` |
| Admin Web | `{SNAPSHOT_BACKEND_BASE_URL}/v1/admin/*` | Repository/Branch 설정, Snapshot 이력·재시도 | 독립 Admin Web 요구사항 |
| Frontend | `http://127.0.0.1:11500/api/chat` | 기존 AI/Ollama 생성 호출 | 활성 `chatHandler_RAG_server.ts` |
| Windows portproxy | `192.168.0.12:11500` | Frontend 로컬 `11500`의 실제 연결 대상 | 사용자 실환경 검증 |

RAG Lab의 코드상 기본 예시는 `127.0.0.1:8200`입니다. 이 값은 Backend와 RAG Lab이
같은 호스트일 때만 유효합니다. `11500`은 AI/Ollama 경로이며 Snapshot Model API
주소가 아닙니다.

Admin Web은 VS Code Webview가 아니라 독립 서버에서 제공됩니다. 운영 URL과 origin은
아직 확정되지 않았으며 RAG Lab이나 PostgreSQL에 직접 연결하지 않습니다.

## 구현에 충분히 확정된 항목

- Frontend request 필드와 optional/required 여부
- 실제 40자리 Git SHA 검증
- 변경 후 파일 전체 문자열과 POSIX 상대경로
- Model `/index/update/files` request와 `200`, `202`, `400`, `409` 의미
- Model `/projects` exact ID만 사용하는 project 매핑 원칙
- 내부 Snapshot ID와 외부 Git revision의 분리
- Model `202`와 완료 상태의 분리
- Model 성공·실패 body의 원문 필드 보존
- Frontend POST 기본 timeout 10초와 Backend 접수 경로 8초 기본 budget
- 세 변경 배열이 모두 빈 실제 Git empty commit의 revision-only 전달
- 최초 MVP 상태 동기화는 Frontend의 상태 조회 시 수행하고 background stale worker는 P2
- Snapshot 관리 UI는 독립 Admin Web 서버이며 VS Code Extension에 포함하지 않음
- Admin Web은 Backend `/v1/admin/*`를 통해서만 Repository/Branch와 Snapshot을 관리

위 항목은 추가 질문 없이 contract test와 mock integration 구현을 시작할 수 있습니다.

## 현재 Frontend 사용자 표시 한계

Frontend `APIService.post()`는 응답 JSON을 반환하지만 `CommitDiffService`는 반환값을
사용하지 않습니다. 따라서 Backend가 성공·실패 원인을 완전하게 반환해도 현재 VS Code
UI에는 그 이유가 표시되지 않습니다.

- Backend 작업에서는 response status/body 계약과 실제 HTTP 반환까지 검증합니다.
- Frontend 브랜치는 참조 전용이므로 이 저장소에서 수정하지 않습니다.
- 사용자 표시가 필요하면 endpoint, status별 fixture와 실제 JSON 예시를 Frontend
  소유자에게 인계합니다.
- 이 한계는 Backend contract 구현을 막지는 않지만 사용자 가시성을 Production GO에
  포함한다면 Frontend 후속 변경이 필요합니다.

## 실환경 전 필수 입력값

다음 값은 현재 문서나 상대 코드만으로 확정할 수 없습니다. 구현 코드는 환경변수와
명시적 DB 데이터로 받을 수 있게 만들되, 실제 End-to-End 실행 전에는 운영자 또는
사용자가 값을 확인해야 합니다.

| ID | 필요한 값 | 확인 방법 | 미확정 시 안전한 동작 |
|---|---|---|---|
| `LIVE-01` | Backend 호스트에서 접근 가능한 `RAG_LAB_BASE_URL` | `/health`, `/projects`, `/index/status` 실제 HTTP | readiness 실패, Snapshot 전달 금지 |
| `LIVE-02` | RAG Lab token 사용 여부와 `RAG_LAB_TOKEN` | Model 실행 옵션과 `X-VSS-Token` 요청 확인 | token을 추측하지 않음 |
| `LIVE-03` | PostgreSQL `DATABASE_URL`과 migration 권한 | 연결 및 migration dry run | readiness 실패, Model 호출 금지 |
| `LIVE-04` | Frontend ID별 exact Model project ID | Frontend payload와 Model `/projects` 비교 후 관리자 확정 | `409 PROJECT_MAPPING_REQUIRED` |
| `LIVE-05` | Model 현재 완료 revision | `/index/status?project_id=<exact-id>` | revision 전송 금지, 구조화된 `409` |
| `LIVE-06` | request body·파일 수·단일 파일 크기 제한 | 실제 저장소 크기와 Model fingerprint 기준 합의 | 임의의 작은 제한을 하드코딩하지 않음 |
| `LIVE-07` | Snapshot 파일 본문 보존 기간과 삭제 정책 | 보안·운영 담당자 승인 | 자동 삭제하지 않고 운영 준비 미완료 표시 |
| `LIVE-08` | Backend 공개 구간의 TLS·방화벽·인증 정책 | 배포 토폴로지 검토 | Frontend에 새 필수 header를 추가하지 않음 |
| `LIVE-09` | 독립 Admin Web 저장소, 배포 URL과 Backend 허용 origin | 배포 담당자와 DNS/CORS 확인 | Admin Web production GO 금지 |
| `LIVE-10` | Admin 로그인 방식, 관리자 역할과 세션 정책 | IdP/운영 정책 및 `401/403` 실제 검증 | 관리 mutation 비활성화 |
| `LIVE-11` | Repository provider 접근 방식과 credential 소유 주체 | Git/인프라 담당자 권한 검증 | 원격 Repository 쓰기·동기화 금지 |
| `LIVE-12` | `frontend_project_id`별 Repository/Branch/Model binding과 동시 Branch 정책 | Admin 확정 데이터와 실제 사용자 흐름 비교 | binding 없음·중복 시 구조화된 `409` |
| `LIVE-13` | Snapshot 저장 방식: 내부 DB/Object Storage 이력 또는 실제 Git commit/ref push | 제품 소유자와 Git/인프라 담당자 합의 | Git remote 쓰기를 수행하지 않음 |

`LIVE-01`부터 `LIVE-05`까지는 최초 실환경 E2E의 차단 조건입니다. `LIVE-06`부터
`LIVE-13`까지는 로컬 contract 구현을 막지는 않지만 production GO 전에 반드시
확정합니다. Admin Web을 production에 노출하려면 특히 `LIVE-09`부터 `LIVE-13`까지가
차단 조건입니다.

## Project 매핑 레코드 최소 계약

명시적 매핑은 최소한 다음 정보를 저장합니다.

```text
frontend_project_id
model_project_id
active
verified_at
verified_model_revision
created_at
updated_at
```

- exact 문자열 일치만 자동 매핑할 수 있습니다.
- 유사 이름과 leaf name은 후보 목록에만 포함합니다.
- 후보만 있는 상태에서는 Model을 호출하지 않습니다.
- Model `/projects`에서 사라진 mapping은 자동으로 다른 ID로 바꾸지 않고 stale로
  표시합니다.
- 실제 mapping 값은 fixture나 소스에 하드코딩하지 않습니다.

## Repository/Branch 바인딩 최소 계약

```text
binding_id
frontend_project_id
repository_id
branch_ref
model_project_id
active
verified_at
created_at
updated_at
```

- `branch_ref`는 `refs/heads/...` full ref를 정본으로 사용합니다.
- 현재 VS Code payload에는 Branch가 없으므로 `frontend_project_id`당 활성 binding을
  하나만 허용합니다.
- Snapshot은 수신 시점의 binding 값을 복사하며 binding 변경으로 과거 이력을
  수정하지 않습니다.
- 독립 Branch는 서로 다른 exact Model project mapping을 원칙으로 합니다.
- 동시 다중 Branch 사용이 필요하면 Frontend의 선택적 Branch/binding 식별 계약을
  확정하기 전까지 production 지원으로 표시하지 않습니다.

## 요청 식별과 Snapshot 식별

- `request_id`는 HTTP 요청마다 Backend가 생성하고 `X-Request-ID` 응답 헤더와
  로그에 사용합니다.
- `snapshot_id`는 유효한 요청의 내부 레코드 식별자로 Backend가 UUID 문자열을
  생성합니다.
- 같은 Snapshot의 Model 재시도는 같은 `snapshot_id`를 사용하고 attempt만
  증가시킵니다.
- `request_id`와 `snapshot_id`를 Git revision으로 사용하지 않습니다.
- Frontend가 두 값을 request 필드로 보내도록 요구하지 않습니다.

## 필수 검증 단계

검증은 다음 순서를 건너뛰지 않습니다.

### 1. 정적 기준선

```powershell
git status -sb
git diff --check
git ls-remote https://github.com/h5vision/vision.git `
  refs/heads/frontend `
  refs/heads/model `
  refs/heads/backend_P
```

- 사용자 또는 다른 Agent의 미커밋 파일을 기록하고 보존합니다.
- SHA가 문서와 다르면 contract fixture를 만들기 전에 상대 코드를 다시 읽습니다.

### 2. Contract test

반드시 고정할 fixture:

- Frontend 실제 `GitCommitPayload`
- 추가, 수정, 삭제, rename, Unicode 파일
- 세 변경 배열이 모두 빈 Git empty commit
- 40자리이지만 remote에 없는 로컬 commit
- Model `200 already_applied`, `202 updating`, `400`, `409` 실제 body
- Backend `422`, `500`, `502`, `504` 구조화 body
- Model 원문 `reason`, `detail`, `conflict`, `already_applied` 보존
- Admin Repository/Branch binding CRUD와 soft deactivate body
- Admin Snapshot 목록·상세·재시도 body
- Admin `401`, `403`, binding `409` 구조화 body
- Git 저장 사용 시 인증·non-fast-forward·provider 장애와 멱등 응답

### 3. Unit test

- SHA, 경로, encoding, rename content와 중복 경로 검증
- exact project mapping과 mapping stale 처리
- Snapshot 상태 전이와 금지된 역전이
- 매핑 전·후 idempotency unique 기준
- success/error reason 보충 시 upstream 필드 비변경
- 로그 redaction과 request/snapshot 상관관계
- 활성 binding unique와 Snapshot 수신 시점 값 고정
- Repository/Binding 비활성화 뒤 과거 Snapshot 이력 보존
- Admin 역할별 mutation 허용과 거부

### 4. Mock integration test

- FastAPI → mock RAG Lab request body 완전 비교
- Model `200/202/400/409` status와 body 보존
- Model `401` → `502 RAG_LAB_AUTH_FAILED`
- Model `5xx` → `502 RAG_LAB_UPSTREAM_ERROR`와 원문 attempt 보존
- 연결 실패 → `502 RAG_LAB_UNAVAILABLE`
- 유효하지 않은 JSON → `502 RAG_LAB_INVALID_RESPONSE`
- 8초 budget 초과 → `504 RAG_LAB_TIMEOUT`
- Model 성공 뒤 DB 결과 기록 실패 → 구조화된 `500`
- 동시 동일 target 요청 → Model 호출 한 번
- 재시작 뒤 stale `forwarding` 복구와 중복 호출 방지
- Model `done + base_revision + update_error` → Snapshot `failed`
- Model `done + target_revision + no update_error` → Snapshot `completed`
- Admin Repository/Binding CRUD → 인증·권한·감사 로그 검증
- Branch별 Snapshot cursor pagination → 다른 Branch 이력 혼입 없음
- Snapshot 재시도 → 새 Snapshot 없이 attempt만 증가
- 허용되지 않은 Admin origin → CORS 차단
- Git 저장 사용 시 expected-head 검증과 force-push 금지

### 5. 실환경 End-to-End

mock test 전체 통과 뒤 다음 증거를 남깁니다.

```text
Frontend 실제 request에서 content를 제거한 payload shape
Backend HTTP status, JSON body와 X-Request-ID
내부 snapshot_id와 상태 전이
Model이 수신한 project_id/base/target 및 파일 개수
Model 최초 200 또는 202 body
Model 최종 status의 state/commit/update_error
Frontend가 받은 최종 성공 또는 실패 이유
각 단계 latency와 10초 제한 충족 여부
Admin Web Repository/Branch binding 설정 결과
Admin Web Branch별 Snapshot 목록·상세·attempt 표시
Admin Web 재시도 전후 동일 snapshot_id와 증가한 attempt
Admin 인증 주체와 mutation 감사 이벤트
```

증거에는 파일 전체 content, token, DATABASE_URL credential을 포함하지 않습니다.

## 즉시 중단 조건

다음 조건에서는 우회하거나 추측해 진행하지 않습니다.

- Frontend, Model 또는 backend_P 원격 SHA가 기준과 다름
- Frontend payload가 contract fixture와 다름
- exact project mapping이 없음 또는 Model `/projects`에서 mapping이 사라짐
- Model project가 완성 인덱스가 아니거나 현재 40자리 revision을 확인할 수 없음
- request `base_revision`과 Model 현재 revision이 다름
- RAG Lab token 불일치
- DB migration 미적용 또는 Snapshot 최초 저장 실패
- Model 응답 의미가 문서의 `200/202/400/409`와 다름
- Frontend 10초 안에 구조화된 응답을 반환할 수 없음
- 활성 Repository/Branch binding이 없거나 둘 이상임
- 하나의 Model project에 독립 Branch를 확인 없이 연결하려 함
- Admin 인증/RBAC 없이 관리 mutation을 production에 노출하려 함
- 저장 방식이 미확정인데 Git remote에 commit/ref를 생성하거나 push하려 함

중단 시 구조화된 오류와 확인된 사실을 보고하고 Frontend 필드 변경, 유사 project
자동 선택, 임의 revision 생성, 자동 전체 인덱싱으로 우회하지 않습니다.

## Production GO 조건

```text
LIVE-01 ~ LIVE-13 확인 완료
contract/unit/mock integration 전체 통과
실제 Frontend payload 한 건 이상 성공
동일 target 재전송 멱등성 확인
Model target revision 완료 승격 확인
실패 시 reason/detail/retryable 확인
재시작 복구 확인
로그와 DB 샘플에서 비밀정보·파일 본문 노출 없음
요청 수신부터 Frontend 응답까지 10초 미만
VS Code 자체 가시성이 GO 범위이면 Frontend가 status/body를 소비하고 이유를 표시
독립 Admin URL에서 인증·RBAC·CORS·TLS 검증
Repository/Branch binding 설정 뒤 Branch별 Snapshot 이력 조회
Admin 재시도와 감사 로그 확인
브라우저 bundle과 API 응답에 RAG Lab/DB/Git credential 없음
```
