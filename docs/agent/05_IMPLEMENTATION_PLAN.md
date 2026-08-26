# Snapshot 기능 구현 계획

## 구현 트랙

Phase 2부터 다음 두 트랙을 병렬로 관리합니다.

```text
Backend 트랙   VS Code 수신, Repository/Branch 바인딩, Snapshot, RAG Lab 연동
Admin Web 트랙 독립 브라우저 서버, Repository/Branch 관리, 이력·상태·재시도 UI
```

Admin Web은 VS Code Extension Webview가 아니며 Backend와 독립적으로 빌드·배포합니다.
Admin 구현 저장소가 확정되기 전에는 이 저장소에서 UI 코드를 임의로 만들지 않고 API
계약과 fixture를 먼저 고정합니다.

## Phase 0 — 기준선 고정

1. `backend_P`, `frontend`, `model` 원격 SHA 확인
2. Frontend request fixture 고정
3. Model request/response fixture 고정
4. 상대 규약과 문서가 불일치하면 코드 기준으로 문서 갱신
5. `06_READINESS_AND_VERIFICATION.md`의 실환경 필수 입력값 확인
6. Frontend 10초 timeout과 Backend 접수 경로의 총 budget 고정

완료 조건:

```text
Frontend fixture가 실제 TypeScript payload와 일치
Model fixture가 payload_incremental.py 검증과 일치
새 필수 필드 없음
Frontend, Model, backend_P 원격 SHA가 문서 기준과 일치
실환경 값은 확인된 값과 미확정 값을 구분해 기록
```

## Phase 1 — 프로젝트 골격

1. `backend/` package 생성
2. `core`, `features`, `integrations`, `infrastructure` 생성
3. `main.py`는 `backend.app:app` compatibility entrypoint로 유지
4. 환경변수 설정 추가

최소 환경변수:

```text
RAG_LAB_BASE_URL=http://127.0.0.1:8200
RAG_LAB_TOKEN=
DATABASE_URL=postgresql://...
RAG_LAB_CONNECT_TIMEOUT_SECONDS=2
RAG_LAB_INDEX_ACCEPT_TIMEOUT_SECONDS=8
RAG_LAB_STATUS_TIMEOUT_SECONDS=8
SNAPSHOT_FORWARDING_STALE_SECONDS=30
```

`RAG_LAB_INDEX_ACCEPT_TIMEOUT_SECONDS`는 Frontend의 10초 POST timeout보다 짧아야
합니다. `127.0.0.1:8200`은 Backend와 RAG Lab이 같은 호스트일 때의 예시일 뿐이며,
실환경 주소를 추측하지 않습니다. AI/Ollama의 `127.0.0.1:11500` 또는
`192.168.0.12:11500`을 `RAG_LAB_BASE_URL`로 사용하지 않습니다.

## Phase 2 — Contract 우선 구현

1. Frontend `WorkspaceOverlayRequest` 구현
2. Model `RagLabIndexUpdateRequest/Response` 구현
3. 40자리 Git SHA 검증
4. POSIX 상대경로 및 rename 검증
5. contract test 작성
6. 공통 성공·오류 JSON body와 `X-Request-ID` 계약 작성
7. 변경 배열이 모두 빈 Git empty commit fixture 작성
8. Repository, Branch binding, Snapshot 목록·상세·재시도 관리 API 계약 작성
9. 수신 시점의 활성 binding을 Snapshot에 고정하는 규칙 작성
10. Admin 인증 `401`, 권한 `403`, binding 충돌 `409` 오류 계약 작성
11. Admin Web API fixture와 화면 상태 모델 작성
12. Admin Web 배포 origin, 인증/RBAC와 동시 Branch 사용 여부를 미확정 값으로 등록
13. Snapshot 저장이 내부 DB/Object Storage 이력인지 실제 Git commit/ref push인지 확정

완료 조건:

```text
현재 Frontend payload → 2xx schema validation
임의 SHA/잘못된 경로 → 422 또는 구조화된 400
Frontend에 snapshot_id/content_sha256 요구하지 않음
empty commit → revision-only request로 유효
모든 오류 → JSON body에 reason/detail 존재
기존 VS Code payload에 branch 또는 관리 필드를 새 필수값으로 추가하지 않음
활성 binding 없음·중복 → Model 호출 없이 구조화된 409
Snapshot update/delete와 Repository 물리 삭제는 계약에서 제외
Admin Web은 Backend 관리 API만 호출하고 서비스 credential을 받지 않음
실제 Git 저장 여부와 credential·충돌 계약이 추측 없이 결정됨
```

## Phase 3 — Repository/Project 매핑과 Admin Web 골격

1. Model `GET /projects` client 구현
2. external project catalog 저장
3. Frontend ID ↔ Model exact ID mapping 구현
4. exact match 외 자동 확정 금지
5. 매핑 없음/모호함 오류 구현
6. Repository CRUD와 soft deactivate 구현
7. Repository/Branch ↔ exact Model project binding CRUD 구현
8. `frontend_project_id`당 활성 binding 하나를 DB constraint로 보장
9. 독립 Admin Web 프로젝트 골격, API client와 인증 경계 구성
10. Repository 목록·등록·수정·비활성화와 Branch binding 화면 구현

완료 조건:

```text
명시적 매핑 → exact Model project_id 전달
매핑 없음 → Model 호출 없이 구조화된 409
유사 이름만 존재 → 후보는 제공하지만 자동 선택하지 않음
Repository/Branch binding 확정 → 이후 Snapshot에 불변 값으로 복사 가능
binding 변경 → 과거 Snapshot 소속 불변
Admin Web → Browser에서 독립 URL로 실행되고 Backend API만 호출
관리 mutation → 인증·권한 검사와 감사 이벤트 기록
```

## Phase 4 — Snapshot 수신·전달과 Branch별 이력

1. Snapshot 수신 레코드 생성
2. 파일/삭제/rename 저장
3. Frontend → Model mapper 구현
4. RAG Lab `/index/update/files` 호출
5. upstream 상태/오류 보존
6. 멱등성 구현
7. DB transaction과 `forwarding` crash recovery 구현
8. Snapshot 목록·상세·attempt 조회 API 구현
9. Repository/Branch/상태/기간 cursor pagination 필터 구현
10. Admin Web Snapshot 목록·상세·실패 이유 화면 구현
11. 실제 Git 저장이 확정된 경우에만 provider adapter와 expected-head 기반 push 구현

완료 조건:

```text
Model 202 → Frontend 202
Model 200 already_applied → Frontend 200
Model 400 reason 유지
Model 409 conflict 유지
동일 target 재전송 → 중복 작업 없음
Model 응답 뒤 DB 기록 실패 → 성공으로 가장하지 않음
Repository/Branch별 Snapshot 이력 조회 → target과 상태가 정확히 표시됨
Snapshot 상세 → reason/detail/conflict와 attempt를 content/token 없이 표시
Snapshot revision·파일 본문 수정 API 없음
Git 저장 사용 시 non-fast-forward/인증/부분 실패가 구조화되어 DB 성공과 구분됨
```

## Phase 5 — 상태 동기화와 운영 UI

1. `/v1/index/status` proxy 구현
2. accepted Snapshot의 상태 polling 또는 조회 시 동기화
3. Model 완료 revision과 target revision 비교
4. `completed`, `failed`, `rejected` 상태 전이
5. stale `forwarding`과 재시작 복구
6. 기존 `snapshot_id` 기반 수동 재시도 API 구현
7. Admin Web 상태 갱신, 재시도, stale 표시와 결과 알림 구현
8. Repository/Branch 선택부터 Snapshot 완료 확인까지 Admin E2E fixture 작성

완료 조건:

```text
202 직후 completed로 오판하지 않음
Model done + commit=target → completed
Model failed → failure reason 저장/반환
Model done + commit=base + update_error → failed
Model done + commit=target + update_error 없음 → completed
재시도 → Snapshot 중복 없이 attempt만 증가
Admin Web → completed/failed와 성공·실패 이유를 구분해 표시
Repository/Branch 선택 → 해당 Branch의 이력만 조회
```

## Phase 6 — 보안·배포·로컬 commit과 장애 시나리오

Admin Web 운영 항목:

- 독립 Admin Web 서버/container 빌드와 배포
- 운영 Admin URL, TLS, 허용 CORS origin 검증
- 로그인과 RBAC, 세션 만료, `401/403` 처리
- Repository/Binding mutation과 재시도 감사 로그
- Repository/Binding 비활성화와 과거 Snapshot 이력 보존
- `LIVE-07` 확정 뒤에만 Snapshot 보존·삭제 기능 활성화
- 서비스 token과 credential이 브라우저 bundle/network 응답에 없는지 검사
- Git 저장 사용 시 force-push 금지, non-fast-forward, 권한 만료와 provider 장애 검증

필수 테스트:

- GitHub에 없는 유효한 40자리 로컬 commit
- Model current revision 불일치
- Model offline
- Model timeout
- 동일 target 재전송
- 삭제만 있는 commit
- rename commit
- 변경 비율 초과 `too_many_changes`
- 파일 본문에 Unicode/한글 포함
- 경로 traversal 요청
- 세 배열이 모두 빈 실제 Git empty commit
- Frontend 10초보다 먼저 반환되는 Model timeout
- Model `401` token 오류와 유효하지 않은 JSON 응답
- Model `state=done`, `commit=base_revision`, `update_error` 실패 상태
- Model 응답 직후 DB 결과 기록 실패
- 프로세스 재시작 시 stale `forwarding` 복구
- 활성 Repository/Branch binding 없음·중복·비활성
- binding 변경 전후 과거 Snapshot 소속 불변
- Branch 이름에 `/`와 Unicode 포함
- 관리자 미인증 `401`, 권한 부족 `403`
- 허용하지 않은 Admin origin의 CORS 차단
- 같은 Snapshot 재시도 시 attempt만 증가
- Git 저장 사용 시 동일 target 재시도가 중복 commit/ref를 만들지 않음

## 테스트 구조

```text
tests/contract/
  Frontend, Model과 Admin API JSON 계약

tests/unit/
  validation, mapping, state, idempotency

tests/integration/
  FastAPI → mock RAG Lab과 Admin API 전체 흐름

admin-web tests/
  Repository/Binding CRUD, Snapshot 목록·상세·재시도 UI
```

권장 검증 명령:

```powershell
python -m compileall -q backend
python -m pytest -q tests/contract
python -m pytest -q tests/unit
python -m pytest -q tests/integration
python -m pytest -q
```

실환경 검증은 mock 통합 테스트가 모두 통과한 뒤에만 수행하며, 필요한 주소·token·
project mapping·DATABASE_URL은 `06_READINESS_AND_VERIFICATION.md` 체크리스트로
확인합니다.

## 최초 End-to-End GO 조건

```text
Frontend 실제 payload 수신 성공
Frontend project_id의 명시적 Model 매핑 성공
Snapshot 내부 기록 성공
Model /index/update/files가 정확한 payload 수신
202와 request/snapshot 상관관계 저장
Model /index/status 완료 확인
target revision 승격 확인
Frontend에 구조화된 결과 반환
Backend response fixture와 Frontend 인계 문서 제공
로그에 파일 본문/토큰 노출 없음
Frontend 요청 시작부터 구조화된 응답까지 10초 미만
200/202/400/409/422/502/504 응답 사유를 body로 판별 가능
프로세스 재시작 뒤 중복 Model 작업 없이 Snapshot 상태 복구
독립 Admin URL에서 로그인과 권한 검사 성공
Admin에서 Repository/Branch binding 설정 성공
Admin에서 Branch별 Snapshot 이력·상세·attempt 조회 성공
Admin에서 실패 이유 확인과 동일 Snapshot 재시도 성공
관리 mutation 감사 로그 확인
브라우저에 RAG Lab/DB/Git credential 노출 없음
```

현재 VS Code Frontend는 Workspace Overlay 응답 JSON을 UI에 표시하지 않습니다.
Snapshot 관리와 상세 오류 표시는 독립 Admin Web이 담당합니다. VS Code 자체 알림이
제품 요구에 추가될 때만 Frontend 소유자에게 status/body 처리 변경을 별도 인계합니다.

## 구현하지 않을 범위

초기 Snapshot MVP에서는 다음을 구현하지 않습니다.

- 기존 VS Code 필수 payload 또는 Model 규약 변경
- FastAPI 자체 청킹/임베딩
- FastAPI 자체 Chroma/BM25 rollback
- 임의 SHA 생성
- 유사 project ID 자동 선택
- GitHub에 없는 로컬 commit 거부
- 증분 실패 시 자동 전체 인덱싱
- VS Code Webview 기반 관리자 CRUD
- 보존 정책 확정 전 Snapshot 물리 삭제
