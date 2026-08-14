# rag_lab API 계약 — 백엔드 연동용

- 2026-08-03 | md → P
- 최종확인: **2026-08-14**
- 상태: **질의 경로 현행 계약 + 파일 payload 증분 1차 계약.** FastAPI 증분 프록시는 아직 미구현입니다.

---

## 구조

```
[Extension]
     ↓
[P 백엔드]  인증·세션·공개 API·LLM 호출·스트리밍
     ↓ HTTP
[rag_lab]   인덱싱·검색·프롬프트 조립        ← md 소유
     ↓
[Ollama]    임베딩 + LLM (EC2)
```

**P가 하는 일**: Extension 요청 받기 → rag_lab에 검색 요청 → 받은 messages로 생성 모델 호출 →
rag_lab에서 출처 후처리 → 답변 + sources를 Extension에 반환

**rag_lab이 하는 일**: 인덱싱, 검색, 근거 없음 판정, 프롬프트 조립

⚠ **LLM 호출은 P가 합니다.** rag_lab은 messages만 만들어 줍니다.
스트리밍을 붙이려면 P 쪽에서 하는 게 자연스럽기 때문입니다.

⚠ P 백엔드의 PostgreSQL/Qdrant snapshot·generation 코드는 별도 서브시스템으로 유지합니다.
현재 `/v1/chat`과 `/v1/search`의 검색 정본은 rag_lab/Chroma입니다. Qdrant 결과로
rag_lab prompt를 대체하지 마세요.

---

## 접속 정보

| 항목 | 값 |
|---|---|
| 기본 주소 | `http://127.0.0.1:8200` |
| md 노트북에서 실행 | `python server.py --host 0.0.0.0` |
| LAN 접근 시 | `http://<md_IP>:8200` |
| 인증 | 기본 없음. 필요 시 `--token` → `X-VSS-Token` 헤더 |

⚠ 포트는 조정 가능합니다. `--port 8300` 등.

---

## 엔드포인트

### `GET /health`

연결 확인 + 현재 설정 조회.

```json
{
  "ok": true,
  "ollama": "http://127.0.0.1:11500",
  "embed_model": "bge-m3:latest",
  "projects": ["fest-api"],
  "config": {"chunk_size": 1200, "chunk_overlap": 150,
             "top_k": 4, "score_threshold": 0.54},
  "indexes": [{
    "project_id": "fest-api",
    "serving_profile": {"embed_model": "bge-m3:latest", "embed_dim": 1024,
                         "context_header": true, "use_bm25": true},
    "profile_source": "collection",
    "default_config_drift": {
      "context_header": {"index": true, "config": false},
      "use_bm25": {"index": true, "config": false}
    }
  }],
  "mismatch": []
}
```

`config`는 **다음 전체 인덱싱의 기본값**이고, `indexes[].serving_profile`은 기존
프로젝트의 **실제 질의·증분 설정**입니다. 두 값의 차이는
`default_config_drift`에 정보로 표시되며 장애가 아닙니다. `mismatch`는 저장 프로필을
결정할 수 없어 질의·증분이 실제로 차단되는 프로젝트만 담습니다.

---

### `POST /index` — 인덱싱 시작 (FN-A01)

```json
요청  {"project_root": "C:\\Pj\\fest-api", "project_id": "fest-api--rag-v2",
       "profile": "rag-v2"}
응답  202  {"accepted": true, "project_id": "fest-api--rag-v2", "state": "running",
            "profile_id": "rag-v2", "profile_hash": "..."}
      409  {"accepted": false, "reason": "already_running"}
```

⚠ **즉시 반환합니다.** 인덱싱은 백그라운드에서 돕니다.
진행률은 `/index/status`로 폴링하세요.

⚠ `project_root`는 **rag_lab이 도는 머신의 경로**입니다. 지금은 md 노트북.

제품용 전체 인덱싱은 인덱스가 `done`이 된 뒤 브리핑을 후속 생성합니다.
폴링 중 `briefing=generating|ready|failed`를 함께 확인하세요. 과거 `no_briefing` 필드는
호환상 받을 수 있지만 무시되며, 더는 브리핑 생성을 건너뛰지 않습니다.

`profile`은 선택값이지만 정식 비교 실험에서는 필수로 취급합니다. 등록된 프로필은
`GET /profiles`로 확인합니다. 생략하면 호환을 위해 서버의 현재 CFG로 전체 인덱싱합니다.

새 작업에 파일 단위 중단 재개 체크포인트를 남기려면 `"resumable": true`를 추가합니다.
기본값은 false이며 기존 방식으로 이미 진행 중인 작업에는 소급 적용되지 않습니다.

### `GET /profiles` — 인덱싱 프로필 목록

```json
{
  "profiles": [
    {"profile_id": "rag-v1", "profile_hash": "...", "fingerprint": {"use_bm25": false, "context_header": false}},
    {"profile_id": "rag-v2", "profile_hash": "...", "fingerprint": {"use_bm25": true,  "context_header": false}},
    {"profile_id": "rag-v3", "profile_hash": "...", "fingerprint": {"use_bm25": true,  "context_header": true}}
  ]
}
```

하이브리드 프로필은 BM25 문서 수와 Chroma 청크 수가 일치해야 인덱싱 완료가 됩니다.

### `GET /projects` — 인덱싱된 프로젝트와 실제 프로필

```json
{
  "projects": [{
    "project_id": "fest-api--rag-v2",
    "project_root": "C:\\Pj\\fest-api",
    "state": "done",
    "profile_id": "rag-v2",
    "profile_hash": "7df8947ad47d",
    "serving_profile": {"use_bm25": true, "context_header": false},
    "actual_chunks": 21104,
    "outdated": false
  }]
}
```

`profile_id/profile_hash`는 명시적 프로필로 새로 만든 프로젝트에 기록됩니다. 기존 프로젝트는
둘이 `null`일 수 있으므로 실제 질의 설정은 항상 `serving_profile`을 기준으로 봅니다.

질의와 증분 요청은 이 목록에 있는 **완성된 정확한 `project_id`**를 사용합니다.
`auto`, 폴더명 추정, 유사 이름 fallback은 지원하지 않습니다.

📌 공개 상태 조회 키는 계속 `project_id`입니다. 선택적 재개 엔진만 남은 `building-*`의
소유권을 검증하기 위한 내부 `run_id`를 발급하며, 대화·프로젝트 식별자로 사용하지 않습니다.

---

### `GET /index/status?project_id=...` — 진행률 (FN-A02)

```json
{
  "project_id": "fest-api",
  "state": "running",          // none | running | indexing_lexical | promoting | done | failed | aborted
  "processed": 120,
  "total": 300,
  "chunk_count": 1842,
  "commit": "a3f9c21e...",     // done 일 때
  "indexed_at": "2026-08-03T14:22:00+00:00",
  "elapsed_s": 412.3,
  "error": null
}
```

**폴링 주기는 2~3초를 권합니다.**

---

### 중단 재개형 전체 인덱싱 — 선택 기능

```http
GET  /index/resume/status?project_id=fest-api
POST /index/resume
POST /index/restart
```

```json
POST /index/resume
{"project_id":"fest-api", "run_id":"idx_...", "profile":"rag-v2"}

POST /index/restart
{"project_root":"C:\\Pj\\fest-api", "project_id":"fest-api", "profile":"rag-v2"}
```

`POST /index/resume`은 저장된 manifest와 현재 파일 SHA-256, profile fingerprint,
building 컬렉션의 run_id가 모두 일치할 때만 `202`를 반환합니다. 불일치하면 `409`이며
남은 위치를 추측하지 않습니다. `restart`도 체크포인트가 소유한 building만 폐기하고,
체크포인트 없는 과거 building은 자동 삭제하지 않습니다.

구체적인 단계·CLI·오류·제거 절차는 `RESUMABLE_INDEXING_GUIDE.md`가 정본입니다.

---

### `POST /index/update` — rag_lab 머신의 로컬 Git 기반 증분

```json
{"project_id": "fest-api", "dry_run": true}
```

이 경로는 `state.json`에 저장된 `project_root`와 rag_lab 머신의 Git 작업 트리를 읽습니다.
프론트가 파일 내용을 보내는 새 시나리오에는 사용하지 않습니다.

---

### `POST /index/update/files` — 변경 파일 전체 문자열 기반 증분

프론트가 준비한 변경 파일의 **최종 전체 문자열**을 받습니다. diff hunk는 인덱싱 입력이 아닙니다.

```json
{
  "project_id": "sqlalchemy--rag-v2",
  "base_revision": "1111111111111111111111111111111111111111",
  "target_revision": "2222222222222222222222222222222222222222",
  "snapshot_id": "optional-snapshot-id",
  "branch": "main",
  "files": [
    {
      "status": "modified",
      "path": "lib/sqlalchemy/inspection.py",
      "content": "변경 후 파일 전체 문자열",
      "encoding": "utf-8"
    }
  ],
  "deleted_paths": ["lib/sqlalchemy/old_module.py"],
  "renames": [
    {"old_path": "lib/sqlalchemy/old.py", "new_path": "lib/sqlalchemy/new.py"}
  ]
}
```

필수 계약:

- `project_id`: `/projects`에 있는 완성 인덱스의 exact ID.
- `base_revision`·`target_revision`: 각각 40자리 Git SHA.
- `files[].status`: `added | modified | renamed`.
- `files[].path`: `/`, 드라이브 문자, `..`, 역슬래시가 없는 프로젝트 상대 POSIX 경로.
- `files[].content`: 변경 후 파일 전체 문자열.
- `files[].encoding`: 선택. 기본 `utf-8`; `utf-8-sig`, `cp949`, `latin-1`도 지원.
- `files[].content_sha256`: **선택**. 있으면 64자리 SHA-256을 검증하고, 없으면 받은 문자열로 계산.
- rename의 `new_path`는 최종 content를 가진 `files[]` 항목에도 포함.

접수 응답:

```json
{
  "ok": true,
  "project_id": "sqlalchemy--rag-v2",
  "state": "updating",
  "base_revision": "1111111111111111111111111111111111111111",
  "target_revision": "2222222222222222222222222222222222222222",
  "files_received": 1,
  "files_indexed": 1,
  "files_deleted": 1,
  "files_renamed": 1,
  "ignored_paths": []
}
```

- 새 작업 접수: `202 Accepted`.
- 같은 `target_revision`이 이미 적용됨: `200 OK`, `already_applied: true`.
- 계약 오류: `400`과 `reason`.
- revision 충돌·진행 중·전체 인덱싱 필요: `409`와 `reason`.
- 접수 뒤 `GET /index/status?project_id=...`를 폴링합니다.
- 완료 전에는 `target_revision`을 현재 revision으로 표시하지 않습니다.

안전 순서는 다음과 같습니다.

```text
payload 검증 → 공통 청킹 → 새 임베딩 전부 성공 → 기존 경로 snapshot
→ Chroma 경로 교체 → BM25 전체 재구축 → revision 승격
```

Chroma/BM25 교체가 실패하면 직전 데이터를 rollback합니다. 증분이 거부되거나 실패해도
전체 인덱싱으로 자동 전환하지 않습니다. 변경 영향이 기존 인덱스 파일의 50%를 넘으면
`too_many_changes`로 거부합니다.

---

### `GET /index/exists?project_id=...` — 미인덱싱 감지 (FN-A03)

```json
{"exists": true, "project_id": "fest-api",
 "chunk_count": 1842, "indexed_at": "...", "commit": "a3f9c21e..."}
```

`exists: false`면 Extension에서 "인덱싱이 필요합니다" 안내 (SC-01a).

---

### `POST /search` — 검색 (FN-B02)

```json
요청
{"query": "결제 처리는 어디서 시작되나요?",
 "project_id": "fest-api",
 "top_k": 4,           // 생략 시 서버 기본값
 "threshold": 0.54}    // 생략 시 서버 기본값

응답
{
  "has_evidence": true,
  "contexts": [
    {"path": "src/payment/router.py",
     "type": "code",
     "line_start": 20, "line_end": 42,
     "section": null,
     "text": "@router.post('/pay')\ndef pay(req): ...",
     "score": 0.7231}
  ],
  "top_score": 0.7231,
  "threshold": 0.54,
  "reason": "ok",       // ok | below_threshold | empty_index
  "bm25_active": true,
  "serving_profile": {"embed_model": "bge-m3:latest", "embed_dim": 1024,
                       "context_header": true, "use_bm25": true}
}
```

### 🔴 `has_evidence: false` 처리 — FN-B06

근거 점수가 임계값 미만이면 `contexts`가 빈 배열입니다.

**이때 LLM을 호출하지 말고 바로 "근거 없음"을 표시**하는 게 맞습니다.
호출해봐야 답할 재료가 없습니다.

FastAPI 현행 응답은 `answer: "NO_EVIDENCE"`, `source: []`입니다. 검색된 경로를
출처처럼 남기지 마세요.

```
reason = "below_threshold"   검색은 됐으나 점수가 낮음
reason = "empty_index"       인덱스가 비어있음 → 인덱싱 필요
```

---

### `POST /prompt` — 검색 + 프롬프트 조립

`/search`에 프롬프트 조립까지 더한 것입니다. **이쪽을 쓰시는 걸 권합니다.**

⚠ 이 라우트는 rag_lab의 `8200` 엔드포인트입니다. 현재 `8000` emergency bridge가 외부에
공개하는 질의 라우트는 `/v1/chat`이며, 그 내부에서 `8200/prompt`를 호출합니다.
따라서 `POST :8000/prompt`는 `404`이고, Frontend는 `POST :8000/v1/chat`을 사용합니다.
향후 8000에 `/prompt` 프록시를 추가하려면 별도의 공개 계약으로 합의해야 합니다.

```json
요청  {"query": "...", "project_id": "fest-api"}

응답
{
  "has_evidence": true,
  "messages": [
    {"role": "system", "content": "제공된 근거만 사용해 한국어로 답한다. ..."},
    {"role": "user",   "content": "프로젝트 검색 결과:\n[1] src/... lines 20-42\n...\n\n질문:\n..."}
  ],
  "sources": [ ... /search 의 contexts 와 동일 ... ],
  "top_score": 0.7231,
  "threshold": 0.54,
  "bm25_active": true,
  "serving_profile": {"embed_model": "bge-m3:latest", "embed_dim": 1024,
                       "context_header": true, "use_bm25": true}
}
```

**P는 `messages`를 그대로 Ollama `/api/chat`에 넘기면 됩니다.**

```python
r = requests.post(f"{RAG_LAB}/prompt",
                  json={"query": q, "project_id": pid}, timeout=60)
d = r.json()

if not d["has_evidence"]:
    return {"answer": "NO_EVIDENCE", "sources": []}

resp = requests.post(f"{OLLAMA}/api/chat", json={
    "model": "qwen2.5-coder:7b",
    "messages": d["messages"],
    "stream": True,                  # 스트리밍 권장
    "options": {"num_ctx": 8192},
}, timeout=120, stream=True)

# answer 와 함께 d["sources"] 를 그대로 Extension 에 반환
```

### 🔑 `[N]` ↔ `sources` 대응

프롬프트의 `[1]`은 `sources[0]`, `[2]`는 `sources[1]`입니다.
**모델이 답변에 `[2]`라고 쓰면 프론트가 `sources[1]`을 강조**하면 됩니다.

⚠ 이 대응이 깨지면 출처 표시가 틀어집니다. `sources` 배열 순서를 바꾸지 마세요.

### ⚠ 왜 프롬프트 조립을 rag_lab이 하는가

학습 데이터 생성기와 **같은 코드**를 써야 하기 때문입니다.
형식이 어긋나면 fine-tuning 효과가 샙니다
(`PROMPT_DATA_FORMAT_SPEC` §0 "렌더러 하나" 원칙).

현재 형식은 **P의 `generation.py` 현행 형식을 그대로 따랐습니다.**

---

## 오류

| 코드 | 의미 | 대응 |
|---|---|---|
| 400 | 필수 파라미터 누락 | 요청 확인 |
| 401 | 토큰 불일치 | `X-VSS-Token` |
| 404 | 존재하지 않는 `project_id` | `GET /projects`로 실제 ID 확인 |
| 409 | 이미 인덱싱 중 · revision 불일치 · 전체 인덱싱 필요 | `reason` 확인 후 상태 재조회 또는 명시적 전체 인덱싱 |
| **503** | **임베딩 서버 접속 불가** | md 노트북의 터널·Ollama 확인 |
| 500 | 기타 | `detail` 참조 |

⚠ **503은 fallback 없이 실패합니다.** 가짜 임베딩으로 조용히 넘어가지 않습니다 (R18 차단).

---

## 타임아웃 권장

| 엔드포인트 | 타임아웃 |
|---|---|
| `/health`, `/index/status`, `/index/exists` | 10초 |
| `/index` | 10초 (즉시 반환) |
| `/index/update`, `/index/update/files` | 10초 (접수만 즉시 반환) |
| `/search`, `/prompt` | **60초** — 질문 임베딩에 시간이 걸릴 수 있음 |

---

## 미결 / 협의 필요

| # | 항목 |
|---|---|
| 1 | **포트** — 8200이 괜찮은지 |
| 2 | **`project_root` 경로 기준** — rag_lab이 도는 머신. 나중에 EC2로 옮기면 바뀜 |
| 3 | **인증** — 토큰을 쓸지 |
| 4 | **스트리밍** — P가 Ollama 호출하므로 P 쪽에서 구현 |
| 5 | **파일 payload 프록시 공개 경로** — FastAPI endpoint 이름과 응답 envelope |
| 6 | **요청 제한** — 최대 파일 수·파일별 byte·전체 byte |
| 7 | **revision 정본** — 프론트가 `base_revision`을 읽을 API |
| 8 | **증분 뒤 브리핑** — 즉시 재생성·지연 재생성·수동 중 선택 |

---

*질의 계약은 FastAPI 코드에 반영됐고, 파일 payload endpoint는 rag_lab에 구현됐습니다.
Frontend → FastAPI → rag_lab 증분 프록시와 end-to-end 검증은 다음 작업입니다.*

---

# 부록 A. 출처 스키마 (2026-08-03 추가)

프론트 요청 반영: **answer 와 references 분리**, 하이퍼링크용 라인 정보.

## 왜 두 층인가

검색 단위는 **파일이 아니라 청크**입니다.
한 파일에서 3개 청크가 걸리면 `[1][2][3]` 이 전부 같은 파일입니다.

```
[1] translate.py L53-98
[2] translate.py L101-150     ← 같은 파일
[3] translate.py L200-240     ← 같은 파일
[4] utils.py     L10-40
```

화면에 3줄로 보이면 혼란스러우므로 **파일 단위로 묶되**,
`[N]` 대응은 **청크 단위로 유지**해야 합니다.

⚠ 파일로 묶은 뒤 번호를 다시 매기면, 답변의 `[3]` 이 가리킬 대상이 사라집니다.

| 배열 | 단위 | 용도 |
|---|---|---|
| `references` | 청크 | 답변 본문의 `[N]` 클릭 → `references` 에서 `n == N` 찾기 |
| `reference_files` | 파일 | 하단 "출처" 목록 (파일당 한 줄) |

## `POST /finalize`

LLM 생성이 끝난 뒤 호출합니다. **`sources` 는 `/prompt` 에서 받은 것을 그대로** 넘기세요.

```json
요청
{
  "answer": "translate_page 함수는 ... [1]. 결과는 ... [3].",
  "sources": [ ... /prompt 응답의 sources 그대로 ... ],
  "cited_only": true,      // 기본 true. 실제 인용된 것만
  "include_text": false    // 청크 원문 포함 여부
}

응답
{
  "answer": "translate_page 함수는 ... [1]. 결과는 ... [3].",
  "references": [
    {"n": 1, "path": "scripts/translate.py", "type": "code",
     "line": 53, "line_start": 53, "line_end": 98,
     "section": null, "score": 0.7231, "cited": true},
    {"n": 3, "path": "scripts/translate.py", "type": "code",
     "line": 200, "line_start": 200, "line_end": 240,
     "section": null, "score": 0.5901, "cited": true}
  ],
  "reference_files": [
    {"path": "scripts/translate.py", "type": "code",
     "citations": [1, 3],
     "lines": [[53, 98], [200, 240]],
     "line": 53, "chunk_count": 2,
     "best_score": 0.7231, "cited": true}
  ],
  "cited": [1, 3],
  "no_evidence": false
}
```

### 🔴 `n` 번호는 재배열하지 마세요

`cited_only: true` 로 `[2]` `[4]` 가 빠져도 **`n` 은 원래 값(1, 3)을 유지**합니다.
1, 2 로 다시 매기면 답변 본문의 `[3]` 이 깨집니다.

### 필드

| 필드 | 설명 |
|---|---|
| `n` | ★ 답변의 `[N]` 과 1:1. **변경 금지** |
| `path` | 레포 루트 기준 상대경로 |
| `line` | 프론트 요청 형식. `line_start` 와 같은 값 (점프용) |
| `line_start` / `line_end` | 청크 범위 (강조용) |
| `section` | 마크다운 문서일 때 헤딩 |
| `cited` | 답변이 실제 인용했는지 |
| `citations` | (파일) 이 파일이 갖는 `[N]` 목록 |
| `lines` | (파일) `[[시작, 끝], ...]` |
| `chunk_count` | (파일) 이 파일에서 걸린 청크 수 |

## 하이퍼링크

```
vscode://file/<절대경로>:<line>
```

⚠ **절대경로 변환은 Extension 쪽에서** 하세요.
rag_lab 은 인덱싱한 머신의 경로만 알고, Extension 은 다른 머신에서 돌 수 있습니다.

```javascript
const uri = `vscode://file/${workspaceRoot}/${ref.path}:${ref.line}`;
```

📌 범위 강조까지 하려면 `line_start` ~ `line_end` 를 쓰세요.

## `/prompt` 응답에도 추가됐습니다

생성 **전** 미리보기용으로 `references` / `reference_files` 가 포함됩니다.
답변이 아직 없으므로 `cited` 는 전부 `null` 이고, **검색된 전부**가 들어갑니다.

스트리밍을 쓸 때 **출처 영역을 먼저 그리는 용도**로 유용합니다.

## 흐름

```
① POST /prompt    → messages + references(미리보기)
                     └ 프론트에 출처 먼저 전송 가능
② POST /api/chat  → answer (스트리밍)
③ POST /finalize  → answer + references(인용된 것만)
                     └ 최종 출처로 교체
```

⚠ `/finalize` 는 순수 문자열 처리라 **모델을 호출하지 않습니다.** 빠릅니다.

---

# 부록 B. 스트리밍 (2026-08-04 추가)

## 🔑 핵심 — rag_lab 은 스트리밍을 하지 않습니다

LLM 호출은 **P가 Ollama로 직접** 합니다. rag_lab 은 그 전후에 관여합니다.

```
[질문]
   │
   ├─① POST rag_lab/prompt      messages + references(미리보기)
   │       ↓ 프론트에 출처 먼저 전송 가능
   │
   ├─② POST ollama/api/chat     "stream": true
   │       ↓ 조각을 Extension 으로 중계
   │
   └─③ POST rag_lab/finalize    인용된 것만 추린 최종 출처
           ↓ 출처 영역 교체
```

## ⚠ ①이 TTFT 임계 경로에 있습니다

```
TTFT = /prompt 시간 + Ollama prefill 시간
```

`/prompt` 가 2초 걸리면 스트리밍을 써도 **첫 글자까지 3초**입니다.
그래서 응답에 `timing` 을 항상 포함합니다.

```json
"timing": {"embed_ms": 320.5, "search_ms": 18.2, "total_ms": 345.1}
```

| 필드 | 의미 |
|---|---|
| `embed_ms` | 질문을 벡터로 바꾸는 시간 (Ollama 왕복) |
| `search_ms` | 벡터 검색 |
| `total_ms` | `/prompt` 전체 |

**P 쪽 로그에 `total_ms` 를 남겨두시면** TTFT 예산 초과 시 원인 규명이 빨라집니다.

## `light` 옵션 (기본 true)

```json
{"query": "...", "project_id": "fest-api", "light": true}
```

`sources` 에서 청크 원문을 뺍니다. 원문은 이미 `messages` 안에 있어 **중복**이고,
`/finalize` 는 `path` · `line` 만 있으면 동작합니다.

⚠ 청크 4개면 약 5KB 절감. 네트워크가 느릴 때 유효합니다.
원문이 필요하면 `light: false`.

## 참고 구현

```python
import json, requests

def stream_answer(query, project_id):
    # ① 검색 + 프롬프트 조립
    d = requests.post(f"{RAG_LAB}/prompt",
                      json={"query": query, "project_id": project_id, "light": True},
                      timeout=60).json()

    # 근거 없으면 LLM 호출하지 않음 (FN-B06)
    if not d["has_evidence"]:
        yield {"type": "no_evidence"}
        return

    # 출처를 먼저 보냅니다 — 생성 전에 이미 확정돼 있습니다
    yield {"type": "sources_preview", "reference_files": d["reference_files"]}
    yield {"type": "stage", "text": f"근거 {len(d['sources'])}건 확인"}

    # ② LLM 스트리밍
    yield {"type": "stage", "text": "답변 생성 중..."}
    resp = requests.post(f"{OLLAMA}/api/chat", json={
        "model": "qwen2.5-coder:7b",
        "messages": d["messages"],
        "stream": True,
        "options": {"num_ctx": 8192},
    }, stream=True, timeout=180)

    answer = ""
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            answer += piece
            yield {"type": "delta", "text": piece}     # 조각 중계
        if chunk.get("done"):
            break

    # ③ 인용된 근거만 추려 최종 출처로 교체
    final = requests.post(f"{RAG_LAB}/finalize",
                          json={"answer": answer, "sources": d["sources"]},
                          timeout=30).json()
    yield {"type": "done",
           "answer": final["answer"],
           "references": final["references"],
           "reference_files": final["reference_files"],
           "no_evidence": final["no_evidence"]}
```

## 📌 출처를 두 번 보내는 이유

| 시점 | 내용 | 근거 |
|---|---|---|
| 생성 **전** (`/prompt`) | 검색된 **전부** | 스트리밍 중 화면이 비지 않게 |
| 생성 **후** (`/finalize`) | 모델이 **인용한 것만** | 안 쓴 근거를 출처로 표시하면 오해 |

프론트는 미리보기를 회색으로 표시했다가, `done` 에서 교체하면 자연스럽습니다.

## ⚠ NO_EVIDENCE 후처리

모델이 스트리밍 중 `NO_EVIDENCE` 만 출력할 수 있습니다.
`/finalize` 가 이를 감지해 `no_evidence: true` 로 돌려주므로,
프론트는 그때 SC-10b 전용 화면으로 전환하면 됩니다.

## 서버 기동 시 워밍업

`server.py` 는 시작할 때 인덱스 로드와 임베딩 워밍업을 미리 합니다.

```
  워밍업 중...
    인덱스 로드      412 ms  ['fest-api']
    임베딩 워밍업    287 ms
```

⚠ 이걸 안 하면 **첫 `/prompt` 요청이 수 초** 걸립니다.
서버를 재시작한 직후 바로 데모하지 마시고, 위 줄이 출력된 것을 확인하세요.

## 측정

```powershell
python bench_ttft.py --project fest-api --repeat 5
python bench_ttft.py --project fest-api --no-stream     # 비교용
```

구간별 p50/p95 와 3초 목표 통과 여부를 출력합니다.
