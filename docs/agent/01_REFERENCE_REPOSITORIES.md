# 참조 저장소와 기준선

최종 확인일: 2026-08-26 KST

## 구현 대상

| 항목 | 값 |
|---|---|
| 저장소 | `https://github.com/h5vision/vision.git` |
| 브랜치 | `backend_P` |
| 기준 SHA | `ad17f9c06bdf89a84edaefb2c508569d8ba50cd9` |
| 역할 | Frontend와 Model/RAG Lab 사이의 FastAPI Backend 및 Snapshot 처리 |

`backend_P`는 현재 설계 골격 단계입니다. 과거 mock `main.py` 또는 `ingest.py`가 존재했다는 가정으로 구현하지 말고 현재 HEAD의 실제 파일을 기준으로 시작합니다.

## Frontend 참조

| 항목 | 값 |
|---|---|
| 저장소 | `https://github.com/h5vision/vision.git` |
| 브랜치 | `frontend` |
| 기준 SHA | `56b71405e568b059158b1a666fa362f465c6c10a` |
| 기준 날짜 | 2026-08-25 |
| 브랜치 URL | `https://github.com/h5vision/vision/tree/frontend` |

우선 확인할 파일:

```text
vision/src/services/gitService.ts
vision/src/services/commitDiffService.ts
vision/src/services/APIService.ts
vision/src/types/git.ts
vision/src/types/chat.ts
vision/src/extension.ts
vision/src/controller/sidebarController.ts
vision/src/controller/handlers/projectListHandler.ts
vision/src/chat/chatHandler_RAG_server.ts
vision/src/chat/chatHandler_SSE.ts  # 현재 활성 경로가 아닌 비교 참조
vision/package.json
```

확인된 동작:

- VS Code Git API에서 HEAD 변경을 감지합니다.
- 이전 commit과 새 commit 사이의 변경 파일을 구합니다.
- 변경 파일의 diff가 아니라 새 commit 시점의 전체 파일 문자열을 읽습니다.
- 삭제 경로와 rename 정보를 별도 배열로 만듭니다.
- Frontend가 파일 `content_sha256`을 생성하지 않습니다.
- 상대경로는 `/`를 사용하는 POSIX 형태로 변환합니다.
- 기본 Backend 설정은 `http://192.168.0.7/v1`입니다.
- `CommitDiffService`는 상대 경로 `/workspace-overlays`로 POST합니다.
- `APIService.post()`의 기본 timeout은 10초이며 `CommitDiffService`는 별도 값을
  넘기지 않습니다. Backend는 이 시간 안에 구조화된 응답을 반환해야 합니다.
- Sidebar에서 선택한 project/commit은 Workspace 설정의 `vision.projectId`, `vision.commitId`에 저장됩니다.
- 현재 `extension.ts`가 활성화하는 ChatHandler는 `chatHandler_RAG_server.ts`입니다.
- 이 ChatHandler의 AI 생성 호출은 `http://127.0.0.1:11500/api/chat`입니다.
- 2026-08-26 KST 검증 환경에서 Windows `IP Helper(iphlpsvc)`와
  `netsh portproxy`가 `127.0.0.1:11500`을 `192.168.0.12:11500`으로 전달합니다.

주의점:

- commit payload의 `project_id`는 Git remote URL 또는 로컬 폴더명에서 생성됩니다.
- Sidebar에서 선택한 RAG exact project ID와 commit payload의 `project_id`가 항상 같다고 가정하면 안 됩니다.
- APIService는 현재 비정상 HTTP 응답에서도 JSON body를 읽으므로 Backend가 구조화된 오류 JSON을 반환해야 합니다.
- `CommitDiffService`는 현재 `APIService.post()`의 반환 JSON을 사용하지 않습니다.
  Backend가 성공·실패 이유를 반환해도 VS Code UI에는 표시되지 않으므로, 사용자 표시가
  필요하면 Backend 완료 뒤 Frontend 소유자에게 별도 변경을 인계해야 합니다.
- Frontend의 `127.0.0.1:11500`은 AI/Ollama용 로컬 프록시 진입점입니다.
  Snapshot Backend 주소나 RAG Lab `8200` 주소로 해석하지 않습니다.
- `chatHandler_SSE.ts`가 존재하더라도 현재 `extension.ts` import만으로 활성 경로를
  판정합니다. 파일명만 보고 실행 계약으로 간주하지 않습니다.

## Model/RAG Lab 참조

| 항목 | 값 |
|---|---|
| 저장소 | `https://github.com/h5vision/vision.git` |
| 브랜치 | `model` |
| 기준 SHA | `423f45689689df9dd12bd50150e7663d386e4858` |
| 기준 날짜 | 2026-08-14 |
| 브랜치 URL | `https://github.com/h5vision/vision/tree/model` |

우선 확인할 파일:

```text
rag_lab/API.md
rag_lab/DECISIONS.md
rag_lab/AGENTS.md
rag_lab/server.py
rag_lab/vss_rag/payload_incremental.py
rag_lab/vss_rag/indexer.py
rag_lab/vss_rag/store.py
rag_lab/tests/test_bm25_safety.py
```

확인된 동작:

- `GET /projects`가 인덱싱 완료 프로젝트의 exact `project_id`를 반환합니다.
- `POST /index/update/files`가 변경 파일 전체 문자열 기반 증분 인덱싱을 받습니다.
- `GET /index/status?project_id=...`로 비동기 인덱싱 상태를 조회합니다.
- RAG Lab HTTP API의 기본 예시는 `127.0.0.1:8200`이고 Ollama 기본값은
  `127.0.0.1:11500`입니다. 두 포트는 역할이 다릅니다.
- `base_revision`은 현재 완료 인덱스 revision과 정확히 같아야 합니다.
- `target_revision`이 이미 적용됐으면 idempotent 성공을 반환합니다.
- 전체 새 임베딩 성공 뒤 기존 경로를 교체하며 실패하면 Chroma/BM25를 rollback합니다.
- Model 내부 `snapshot_by_paths()`는 rollback을 위한 VectorDB 임시 데이터이며 제품의 Git Snapshot 레코드와 다른 개념입니다.

## 참조 갱신 절차

구현 시작 전에 다음을 다시 확인합니다.

```powershell
git ls-remote https://github.com/h5vision/vision.git `
  refs/heads/frontend `
  refs/heads/model `
  refs/heads/backend_P
```

SHA가 이 문서와 다르면 변경 파일과 통신 계약을 다시 읽은 뒤 문서의 기준 SHA를 갱신합니다.

SHA가 같아도 실환경 연결 전에는 Backend 호스트 관점의 `RAG_LAB_BASE_URL`, token,
`GET /projects` 결과와 현재 index revision을 별도로 확인합니다. Git 브랜치 SHA가
일치한다는 사실은 실행 중인 서비스의 설정과 데이터가 같다는 뜻이 아닙니다.
