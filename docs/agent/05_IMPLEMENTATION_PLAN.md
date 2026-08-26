# Snapshot 기능 구현 계획

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

완료 조건:

```text
현재 Frontend payload → 2xx schema validation
임의 SHA/잘못된 경로 → 422 또는 구조화된 400
Frontend에 snapshot_id/content_sha256 요구하지 않음
empty commit → revision-only request로 유효
모든 오류 → JSON body에 reason/detail 존재
```

## Phase 3 — Project 매핑

1. Model `GET /projects` client 구현
2. external project catalog 저장
3. Frontend ID ↔ Model exact ID mapping 구현
4. exact match 외 자동 확정 금지
5. 매핑 없음/모호함 오류 구현

완료 조건:

```text
명시적 매핑 → exact Model project_id 전달
매핑 없음 → Model 호출 없이 구조화된 409
유사 이름만 존재 → 후보는 제공하지만 자동 선택하지 않음
```

## Phase 4 — Snapshot 수신과 전달

1. Snapshot 수신 레코드 생성
2. 파일/삭제/rename 저장
3. Frontend → Model mapper 구현
4. RAG Lab `/index/update/files` 호출
5. upstream 상태/오류 보존
6. 멱등성 구현
7. DB transaction과 `forwarding` crash recovery 구현

완료 조건:

```text
Model 202 → Frontend 202
Model 200 already_applied → Frontend 200
Model 400 reason 유지
Model 409 conflict 유지
동일 target 재전송 → 중복 작업 없음
Model 응답 뒤 DB 기록 실패 → 성공으로 가장하지 않음
```

## Phase 5 — 상태 동기화

1. `/v1/index/status` proxy 구현
2. accepted Snapshot의 상태 polling 또는 조회 시 동기화
3. Model 완료 revision과 target revision 비교
4. `completed`, `failed`, `rejected` 상태 전이
5. stale `forwarding`과 재시작 복구

완료 조건:

```text
202 직후 completed로 오판하지 않음
Model done + commit=target → completed
Model failed → failure reason 저장/반환
Model done + commit=base + update_error → failed
Model done + commit=target + update_error 없음 → completed
```

## Phase 6 — 로컬 commit과 장애 시나리오

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

## 테스트 구조

```text
tests/contract/
  Frontend와 Model JSON 계약

tests/unit/
  validation, mapping, state, idempotency

tests/integration/
  FastAPI → mock RAG Lab 전체 흐름
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
```

현재 Frontend는 Workspace Overlay 응답 JSON을 UI에 표시하지 않습니다. Backend
완료 조건은 구조화된 응답 반환까지이며, 사용자 표시가 제품 GO 조건이면 Frontend
소유자에게 status/body 처리 변경을 별도 인계합니다.

## 구현하지 않을 범위

초기 Snapshot MVP에서는 다음을 구현하지 않습니다.

- Frontend 또는 Model 규약 변경
- FastAPI 자체 청킹/임베딩
- FastAPI 자체 Chroma/BM25 rollback
- 임의 SHA 생성
- 유사 project ID 자동 선택
- GitHub에 없는 로컬 commit 거부
- 증분 실패 시 자동 전체 인덱싱
