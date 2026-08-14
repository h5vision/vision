---
문서: STATE
상태: 현행정본
버전: v1.2
최종확인: 2026-08-14
대체한_문서: HANDOFF v1.1 · SESSION_HANDOFF_20260813 · PROJECT_STATE(2026-08-03) · PROJECT_FACTS_20260811
판단근거로_쓸_범위: 지금 상태 · 다음 할 일 · 미해결 · 리스크
쓰면_안_되는_범위: 측정 수치 (→ MEASUREMENTS) · 결정과 이유 (→ DECISIONS) · 불변 조건 (→ AGENTS) · 명령어 (→ MANUAL) · 백엔드 계약 (→ API)
---

# STATE — 지금 어디까지 왔고, 다음에 무엇을 하는가

> **이 문서가 사람이 정기적으로 고치는 유일한 문서입니다.**
> 나머지는 거의 안 변하거나(AGENTS), 덧붙이기만 하거나(DECISIONS), 기계가 만듭니다(MEASUREMENTS).

---

## 0. 문서 체계 — 왜 줄였는가

2026-08-13 기준 문서가 17개였고, **낡는 속도가 갱신 속도를 넘었습니다.**
HANDOFF v1.1은 작성 반나절 만에 낡았고, PROJECT_STATE는 열흘째 멈춰 있었습니다.
노력으로 뒤집을 수 있는 문제가 아니라 구조 문제였습니다.

### 🔑 도구가 실시간으로 낼 수 있는 것은 문서에 적지 않습니다

이 원칙 하나가 문서량의 절반을 없앴습니다.

| 알고 싶은 것 | 예전 | 지금 |
|---|---|---|
| 어떤 인덱스가 있고 무슨 설정인가 | 문서에 표로 박음 → 낡음 | `python cli.py doctor` |
| 지금 CFG가 무엇인가 | 문서에 박음 → 낡음 | `python cli.py health` |
| 검색 정확도가 얼마인가 | 손으로 옮겨적음 → 갈라짐 | `python make_measurements.py` |
| 엔드포인트가 몇 개인가 | 문서에 나열 → 코드와 갈라짐 | 서버 기동 로그 · `openapi.json` |

**문서에 적힌 숫자는 적히는 순간부터 틀리기 시작합니다.** 명령어를 적어두는 편이 낫습니다.

### 문서 4개 + 참조 2개

| 문서 | 성격 | 사람이 고치는 빈도 |
|---|---|---|
| `AGENTS.md` | 불변 조건 · 절대 바꾸지 말 것 | 코드 구조가 바뀔 때만 |
| `DECISIONS.md` | 결정과 이유 | **append-only** — 고치는 게 아니라 붙임 |
| `MEASUREMENTS` | 수치 | **0** — `make_measurements.py`가 생성 |
| **`STATE.md`** | 현황 · 다음 · 미해결 | **여기만** |
| `MANUAL.md` | 명령어 · 트러블슈팅 | 참조용. 명령이 바뀔 때만 |
| `API.md` | 백엔드 계약 | 참조용. 계약이 바뀔 때만 |

---

## 1. 30초 요약

**온보딩 AI 코드 어시스턴트**의 검색 계층입니다. 신입 개발자가 낯선 코드베이스에
질문하면 **출처와 함께** 답하게 하는 것이 목표입니다.

> ⚠ **"오프라인"이 아니라 "코드 비유출"입니다.**
> 네트워크 차단(air-gap)이 아니라 **데이터 경계**가 원칙입니다 — 사내 코드·문서가
> 외부 상용 API로 나가지 않으면 됩니다. EC2는 "사내 GPU 서버" 역할입니다.
> (2026-08-10 정정. 완전 폐쇄망 전제는 폐기됐습니다 — DECISIONS §1)

```text
[VSCode Extension]  질문
        ↓
[게이트웨이 · P]     인증 · 세션 · 공개 API · 스트리밍
        ├─→ [rag_lab · md]  검색 + canonical prompt + 출처 후처리
        │         └─→ [Ollama] bge-m3 임베딩
        └─→ [Ollama/Model Router] 답변 생성
```

**rag_lab 직접 검색은 동작하고 8000 emergency chat bridge의 전체 RAG 왕복도 검증했습니다.**
다만 `back/api_test` 정식 FastAPI는 로컬 실행 의존성이 없어 전체 왕복 검증이 아직 남았습니다 — §2.

---

## 2. 진단 결과 — 검색은 동작하고, 게이트웨이 질의 경로를 복구했습니다

### 🔴 2026-08-14 최신 상태

- SQLAlchemy `_InspectableTypeProtocol` 질문은 현재 `sqlalchemy` 직접 검색에서
  `lib/sqlalchemy/inspection.py`를 근거로 찾습니다. MIT 라이선스는 RAG 동작과 무관합니다.
- 2026-08-14 프론트 호환을 위해 기존 vector-only `sqlalchemy`를 제거하고
  `sqlalchemy--rag-v2`를 `sqlalchemy`로 이관했습니다. 현재 `sqlalchemy`는
  19,510청크, `profile_id=rag-v2`, `use_bm25=true`이며 BM25도 19,510건입니다.
  컬렉션 이름뿐 아니라 내부 청크 ID와 BM25 ID도 `sqlalchemy:` 접두어로 재작성했습니다.
- 출처 없는 일반론 답변의 원인은 FastAPI `/v1/chat`이 rag_lab이 아니라 자체
  Embedding/Qdrant 검색 경로를 사용한 것이었습니다.
- FastAPI 코드는 현재 rag_lab `/prompt` → 생성 모델 → `/finalize` 흐름으로 변경됐습니다.
  `/v1/search`도 rag_lab `/search`를 사용합니다.
- 실제 8000번에서 실행되던 것은 `back/api_test`가 아니라 `C:\Pj\chat_bridge.py`의
  emergency bridge였습니다. 현재 프로세스는 수정본으로 재기동되어 `/v1/chat` 요청이
  8200 `/prompt → Ollama → /finalize`를 거치는 전체 RAG 왕복까지 확인됐습니다.
  단, 8000은 `/prompt`를 직접 공개하지 않으며 외부 진입점은 `/v1/chat`입니다.
- project_id 이관 시점에는 8000/8200 리스너가 없었습니다. 임시 8299 서버의
  `GET /projects`에서 `sqlalchemy`가 `done`, 19,510청크, `rag-v2`, BM25 활성 상태로
  반환되는 것까지 확인한 뒤 임시 서버를 종료했습니다. 이후 실제 8000/8200/Ollama가 기동됐고,
  `POST :8000/v1/chat`에 `project_id=sqlalchemy`를 보내 `status=completed`,
  `rag_provider=rag_lab`, `has_evidence=true`, 답변 `[1]`, 출처
  `lib/sqlalchemy/inspection.py`까지 확인했습니다.
- `has_evidence=false`이면 LLM을 호출하지 않고 `NO_EVIDENCE`, 빈 출처를 반환합니다.
- 변경 파일 전체 문자열 기반 `POST /index/update/files`는 rag_lab에 구현됐습니다.
  `content_sha256`은 선택값이고, 실패 시 Chroma/BM25 rollback을 시도합니다.
- 대형 컬렉션의 BM25 재구축은 검증된 페이지 순회로 변경됐습니다. 조회 실패·중복·누락·
  건수 변경은 빈 역색인으로 바뀌지 않고 실패로 드러나며, 전체·두 증분·재개 경로 모두
  staging 검증 후 교체합니다. 로컬 Git 증분도 실패 시 Chroma/BM25/fingerprint를 함께 복원합니다.
- Frontend → FastAPI → rag_lab 증분 프록시는 아직 없습니다. 현재 FastAPI 변경은
  문법 검사를 통과했지만 로컬 Python에 `psycopg`가 없어 전체 서버를 기동하지 못했습니다.
- FastAPI 공유 설정의 기본 생성 모델은 `gemma3:4b`, rag_lab 측 Ollama에서 관측한 모델은
  `qwen2.5-coder:7b`입니다. 서로 다른 모델 서버일 수 있으므로 배포 환경의 `/v1/models`와
  Ollama tags를 확인해 서빙 설정을 명시적으로 고정해야 합니다.
- 상태 재확인 결과 `sqlalchemy--rag-v3`는 `IncompleteRead(0 bytes read)`로 실패했고
  `building-*` 미완성 컬렉션만 남았습니다. 원자 교체 덕분에 `sqlalchemy--rag-v1`과
  rag-v2 내용을 이관한 `sqlalchemy` 완성본은 영향 없이 사용 가능합니다.
  v3는 재인덱싱 성공 전까지 질의하지 않습니다.

다음 세션은 먼저 `python cli.py doctor`와 `python cli.py projects`로 변동 상태를 다시 확인합니다.

### 기존에 확인된 fest-api 코퍼스 문제

> **2026-08-13 계층 격리 완료.** 이전에 "오케스트레이션 미기동"으로 보이던 것의 정체입니다.

### 확인된 것

| 계층 | 상태 |
|---|---|
| 터널 · Ollama | ✅ 정상 (임베딩 1초 내외, `bge-m3` · `qwen2.5-coder:7b` 확인) |
| 맥락 헤더 | ✅ 작동 — 청크 앞에 `# 경로 > 섹션` 주입됨 |
| BM25 융합 | ✅ 작동 — 벡터 상위에 없는 청크가 RRF로 올라옴 |
| 임계값 | ✅ 의미 없는 질의를 정확히 거절 |
| **검색 자체** | ✅ **개념 질문("의존성 주입")은 잘 찾습니다** |

**시스템은 설계대로 동작합니다.**

### 🔴 그런데 코드 위치 질문에 실패합니다

"라우터를 등록하는 코드는 어디에 있나요?" → 정답(`fastapi/routing.py`의 `include_router`)이
상위 10위 안에 **없습니다.** 소스코드 청크가 하나도 안 나옵니다.

원인은 코퍼스 구성입니다 (수치 → MEASUREMENTS §4-3):

```
C:\Pj\fest-api 는 FastAPI 레포 자체입니다
docs 79.3%  (그중 12개 언어 번역본이 전체의 74%)
소스코드 5.6%
```

**BGE-M3는 다국어 모델이라 한국어 질문이 프랑스어 번역본과 매칭됩니다.**
같은 내용이 12벌 있으면 점수가 나뉘고 `top_k`를 번역본이 채웁니다.
개념 질문에서 상위 4개 중 2개가 같은 `features.md`의 다른 언어판이었습니다.

→ **검색 알고리즘을 튜닝해도 안 고쳐집니다.** 코퍼스를 고쳐야 합니다 (§3).

### ✅ 프로젝트별 서빙 프로필 적용 *(2026-08-13)*

기존에는 질의와 증분 갱신이 전역 CFG를 읽어서, 설정이 다른 `fest-api`와
`fastapi-cli` 중 하나는 반드시 잘못 동작했습니다. 현재는 다음처럼 분리됐습니다.

```text
새 전체 인덱싱      현재 프로세스 CFG 사용
기존 프로젝트 질의  컬렉션 fingerprint 사용
기존 프로젝트 증분  컬렉션 fingerprint 사용
구 컬렉션           state.json fingerprint를 보조로 사용
```

실측 확인:

- `fest-api`는 서버 CFG와 무관하게 `context_header=true · use_bm25=true`로 검색
- `fastapi-cli`는 `false · false`를 유지
- 세 프로젝트 모두 `/index/update` dry-run이 `params_changed` 없이 정상 계획 생성
- `/projects`의 `outdated`는 source commit 기준으로 판정하며 CFG 차이를 stale로 오인하지 않음

`doctor`와 `/health`가 보여주는 `default_config_drift`는 장애가 아니라
**다음 전체 인덱싱 기본값과 저장 프로필의 차이**입니다.

### ✅ 명시적 rag-v1/v2/v3와 평가 matrix 기반 구현 *(2026-08-13)*

- `rag-v1`: 벡터 기준선
- `rag-v2`: v1 + BM25
- `rag-v3`: v2 + context header
- 비교 셀: `v1/vector`, `v2/vector·hybrid`, `v3/vector·hybrid`
- 질문은 JSONL+Schema로 검증하며 사람·LLM이 같은 계약을 사용
- `experiment.py validate/plan/run/report`로 검증·계획·실행·보고서 생성
- `--allow-index` 없이는 matrix가 대형 전체 인덱싱을 시작하지 않음
- 하이브리드 전체 인덱싱은 BM25 문서 수와 Chroma 청크 수가 같아야 완료

구조·예제·작성 계약은 `EVALUATION_GUIDE.md`가 정본입니다. 현재는 코드·schema·예제 matrix와
`validate/plan`까지만 검증했고, `fest-api--rag-v1/v2/v3` 실제 전체 인덱싱은 아직 실행하지 않았습니다.

### 🔑 계층 격리 절차 — 증상이 다시 나오면

**어느 계층이 고장인지 모르는 채로 시간 쓰는 것이 가장 큰 낭비입니다.**

```powershell
python cli.py doctor                              # 상태 먼저
python cli.py search "<실제 질문>" --project <pid>  # 게이트웨이·익스텐션을 뺀 상태
```

| 결과 | 진단 | 담당 |
|---|---|---|
| `EmbeddingError` | 터널 / Ollama | md (인프라) |
| 점수는 나오는데 임계값 미만 | 검색 품질 또는 임계값 | md |
| `has_evidence: true`인데 익스텐션에선 답이 없음 | **게이트웨이** | **P** |

⚠ 세 번째 분기가 중요합니다. rag_lab이 근거를 넘겼는데도 답이 안 나오면 md가 볼 일이 아닙니다.

⚠ **`<질문>`을 그대로 넣지 마세요.** 자리표시자로 재면 어떤 코퍼스에서도 낮은 점수가
나와 오진합니다 (2026-08-13에 실제로 발생).

### ⚠ 미검증 가설

임계값은 **맥락 헤더가 없는 코퍼스에서 관찰된 값**인데, 지금은 맥락 헤더가 있는
인덱스에 적용되고 있습니다. **헤더가 있는 쪽 분포를 측정한 적이 없습니다** —
방향도 크기도 모릅니다. 그럴듯한 가설이지 확인된 원인이 아닙니다.

---

## 3. 다음 할 일 — 2026-08-21 중간 발표 역산

> ⚠ **발표에서 요구되는 것은 "정확도 몇 %"가 아니라 "돌아간다"입니다.**
> 라이브 데모가 멈추면 정확도 수치는 의미가 없습니다.
> (⚠ 라이브 데모가 실제로 필수인지는 미확인 — 확인 필요)

| 순서 | 할 일 | 완료 조건 |
|---|---|---|
| **1** | 실패·중단 `building-*` 상태 확인 | v3 `IncompleteRead` 원인 확인, 완성 인덱스와 미완성 흔적 구분 |
| **2** | FastAPI 실행 환경 복구 | `psycopg` 포함 의존성으로 `/v1/health` 응답 |
| **3** | 정식 FastAPI SQLAlchemy 질문 end-to-end 검증 | `back/api_test /v1/chat` 응답에 `[N]`, `source[]`, `rag_provider=rag_lab` 확인 |
| **4** | 파일 payload 증분 FastAPI 얇은 프록시 | upstream 202/400/409와 `reason`, status polling 보존 |
| **5** | 수정·삭제·rename·충돌·rollback 테스트 | 실패해도 직전 revision 검색 가능 |
| **6** | rag-v1/v2/v3 matrix 평가 | 같은 질문 suite와 재현 가능한 profile hash 사용 |
| **7** | 발표 자료·리허설 | 8/21 전 라이브 실패 경로 확인 |

### 🔴 다음 세션 시작 지점

```text
1. doctor/projects/status로 현재 building 상태 재확인
2. FastAPI 의존성 환경 준비 후 /v1/chat 기동
3. back/api_test를 기동해 project_id=sqlalchemy로 정식 FastAPI end-to-end 확인
4. FastAPI 파일 payload 증분·status 얇은 프록시 구현
5. REQUEST_사내문서 K·Y 발송
6. 동일 질문 suite로 rag-v1/v2/v3 matrix 실행
```

⚠ **4번이 가장 급합니다.** 사내 문서 없이는 레포를 무엇으로 바꿔도
"오픈소스에 RAG 붙인 것"이 되고, S3(발표 핵심 장면)가 성립하지 않습니다.

### 🔴 코퍼스 정리

**`C:\Pj\fest-api` 는 FastAPI 레포 자체입니다.** 코퍼스의 74%가 12개 언어 번역본이고
실제 소스코드는 5.6%입니다 (수치 → MEASUREMENTS §4-3).

BGE-M3가 다국어라 한국어 질문이 프랑스어 번역본과 매칭됩니다. 같은 내용이 12벌이면
점수가 나뉘고 `top_k`를 번역본이 채웁니다. **검색 알고리즘을 튜닝해도 안 고쳐집니다.**

```powershell
$env:VSS_EXCLUDE_GLOBS="tests,docs/de/**,docs/fr/**,docs/es/**,docs/hi/**,docs/pt/**,docs/ru/**,docs/tr/**,docs/uk/**,docs/ko/**,docs/ja/**,docs/zh/**,docs/zh-hant/**"
python cli.py journal "번역·tests 제외 재인덱싱 시작"
python cli.py index C:\Pj\fest-api --project fest-api --force
python cli.py journal "재인덱싱 완료" --cmd "index --force (exclude_globs 적용)"
```

⚠ **재인덱싱 전에 진짜 질문으로 한 번 재두세요.** before/after 비교가 안 되면
개선인지 알 수 없습니다. 되돌리려면 `VSS_EXCLUDE_GLOBS=""` 로 다시 인덱싱하면 됩니다.

### 8/14 데모 안정화 — 체크리스트

```
[ ] 데모 레포 확정 (D11) — 🔴 로컬 3개 전부 실제 소스코드가 소수입니다 (MEASUREMENTS §4-4)
     FastAPI는 공개 문서가 12개 언어로 완비돼 있어 S3(사내 문서만이 답할 수 있음)를 못 보여줌
[ ] 질문 5개 고정 · 반복 실행해서 매번 도는지
[ ] has_evidence=false 일 때 화면에 무엇이 뜨는지  ← 정의 안 돼 있으면 최대 리스크
[ ] 터널 끊김 대비 — 현재 단일 실패점
[ ] 콜드스타트 회피: OLLAMA_KEEP_ALIVE=-1 확인
```

### 8/15 측정 — 순서와 이유

```
1. eval.py --bm25 off  →  baseline 재측정
2. eval.py --bm25 on   →  같은 인덱스, 융합만 켬      ← 여기까지 재인덱싱 0회
3. fastapi-cli 재인덱싱 (맥락 헤더 + BM25)
4. off / on 두 번 더  →  2×2 완성
5. make_measurements.py --out
```

**왜 재인덱싱 없이 2셀을 먼저 얻나.** 두 토글은 성격이 다릅니다.

```
context_header   청크 텍스트를 바꿈   →  벡터가 달라짐   →  재인덱싱 필수
BM25 융합        역색인을 추가 조회   →  벡터는 그대로   →  검색 시점 스위치
```

`fastapi-cli`는 역색인이 이미 컬렉션과 정합하므로, 헤더 없는 행 2셀을 재인덱싱 없이 얻습니다.
이 순서면 3번이 실패해도 2셀은 남습니다.

**왜 baseline을 다시 재나.** 기존 baseline은 두 가지가 동시에 무효입니다 —
조건 기록이 실제 인덱스와 다르고(§4-1), 평가 하네스도 바뀌었습니다(BM25 융합 추가).
도구와 대조군이 둘 다 흔들린 상태라 옛 값과 직접 비교가 안 됩니다.

⚠ 노이즈 판정선은 `make_measurements.py`가 run마다 계산해 줍니다. 그보다 작은 차이는 읽지 마세요.

---

## 4. 미해결 — 우선순위 순

### 🔴 0. FastAPI 연동은 코드 반영됐지만 전체 왕복 미검증

rag_lab 직접 `/prompt`는 근거를 반환하고 FastAPI 변경 파일은 문법 검사를 통과했습니다.
그러나 로컬 FastAPI는 `psycopg` 의존성이 없어 기동하지 못했습니다. Docker도 확인 당시
사용할 수 없었습니다. 프론트에서 다시 질문하기 전에 실제 배포 환경 재시작과 end-to-end 검증이 필요합니다.

### 🔴 0-1. 파일 payload 증분의 FastAPI 프록시 미구현

rag_lab `POST /index/update/files`는 구현됐지만 프론트가 직접 rag_lab을 호출하는 구조는 목표가 아닙니다.
FastAPI는 인증·요청 제한·상태 코드 보존·status polling만 담당하는 얇은 프록시를 제공해야 합니다.
청킹·임베딩·Chroma/BM25 코드를 FastAPI에 복제하지 않습니다.

### 🔴 1. 측정 기록의 조건이 실제와 달랐습니다 (2026-08-13 관측)

`save_run()`이 인덱스 지문이 아니라 **측정 프로세스의 환경변수**를 조건으로 적었습니다.
그 둘은 얼마든지 어긋납니다.

```
환경변수를 켜고 eval을 돌림  →  기록에는 "켜고 쟀다"
그런데 조회한 인덱스는 꺼진 채로 만들어진 것
→ "맥락 헤더 켜고 쟀더니 이 값" 이라는 잘못된 문장이 성립
```

**2026-08-13 수정됨** — 이제 `Store.index_fingerprint()`를 쓰고, CFG와 어긋나면 실행 시 경고합니다.
`fp_source` 필드로 출처를 남기고, `make_measurements.py`가 출처 불명 run을 자동 격리합니다.

→ **기존 baseline은 재측정 대상입니다.**

### 🔴 2. 사내 문서 0편

**검색 대상 자체가 부실합니다.** 검색을 아무리 잘해도 답할 근거가 없습니다.
K·Y에게 4편 요청 → `REQUEST_사내문서_20260812.md` (발송 대기)

### 🟠 3. `project_id` 전역 매핑·정규화 규칙 미정

증상의 직접 원인(유사명 컬렉션 오조회)은 2026-08-12 제거됐습니다.
비교 인덱스의 `<repo>--rag-vN` 명명은 확정됐습니다. 다만 프론트 workspace ID와 rag_lab의
exact project ID를 누가 매핑·정규화할지는 **프론트/백 이관 가능성 때문에 보류**입니다
(`PROJECT_ID_OPTIONS_20260812.md`).

⚠ 보류와 무관하게 처리 가능한 건이 하나 있습니다 —
`get_or_create_collection`이 없는 ID로 질의할 때 **빈 컬렉션을 조용히 만듭니다.**
rag_lab 내부 건이라 이관 논의를 기다릴 이유가 없습니다. 진단 도구 쪽은 이미 막았습니다.

### 🟠 4. 핵심 안전 계약 회귀 테스트 일부 부족

BM25 페이지 크기·중간 조회 실패·중복 ID·건수 변경·문서 수 불일치와 로컬 Git 증분의
BM25 커밋 후 rollback은 자동화됐습니다. 남은 범위는 `[N]` 대응·NO_EVIDENCE와
파일 payload 증분의 수정·삭제·rename·revision 충돌 조합입니다.

### 🟠 5. `project_root` 경로 문제

```
Extension:  개발자 PC의 workspace 경로
rag_lab:    다른 머신에서 실행 → 그 경로가 없음
```

**임의 프로젝트 인덱싱이 성립하지 않습니다.** 아키텍처 결정 필요.

### 🟡 6. 컬렉션 metadata 위생

일부 컬렉션의 metadata가 `status: building`인 채 남아 있고, `target`이 옛 이름을 가리킵니다.
**동작에는 영향 없습니다** — `is_internal()`이 이름만 보기 때문입니다.
"이름이 곧 상태" 설계가 여기서 실제로 방어해 준 사례입니다. 기록만 거짓입니다.
`cli.py doctor`가 🟡로 잡아냅니다. 백필할지는 판단 사항.

### 🟡 7. 파이프라인 전체 평가 경로 없음

`eval.py`는 검색 단계(벡터 + BM25 융합)까지만 잽니다.
임계값·MMR·재배치를 포함한 전체를 재려면 `searcher.search()`를 쓰는 별도 경로가 필요합니다. 미구현.

### 🟡 8. QLoRA 툴체인 미검증

`setup_qlora.sh` + `smoke_train.py`를 W4 본학습 전에 반드시 한 번 돌려야 합니다.
확인 항목: CUDA 인식 · 최대 VRAM · 어댑터 저장 성공.
**버전 조합 실패를 늦게 발견하면 비쌉니다.**

---

## 5. 열린 결정 — md 판단 필요

> 상세와 트레이드오프는 `DECISIONS.md` §4. 여기는 목록만.

| | 항목 | 상태 |
|---|---|---|
| **A** | `tests` 디렉터리 제외 여부 | 평가 베이스라인이 바뀝니다 |
| **B** | 신규 결정 번호 부여 | Claude는 번호를 선점하지 않습니다 |
| **C** | 데모 레포 선정 (D11) | 8/14 데모 준비의 전제 |
| **D** | 모델 결정(D2)을 확정으로 올릴지 | 실물은 확인됨. **품질 검증 여부는 미확인** |
| **E** | `--project` 생략 시 폴더명 사용 | 🔴 권고 — 접미어 사고가 두 번 |
| **F** | `use_bm25`를 `fingerprint()`에서 뺄지 | 평가 쪽에서 `eval_bm25`를 분리하면서 성격이 분명해짐 |
| **G** | 질의 시 인덱스 지문을 채택할지 | ✅ **2026-08-13 구현 완료** — 컬렉션 지문 우선, 구 컬렉션은 `state.json` 지문 보조 |
| **H** | 파일 payload 요청 크기 제한 | 최대 파일 수·파일별 byte·전체 byte 미정 |
| **I** | `base_revision`을 프론트가 읽는 정본 API | `GET /projects` 확장 또는 별도 status proxy 중 미정 |
| **J** | 증분 성공 후 브리핑 재생성 | 즉시·지연·수동 중 미정 |
| **K** | history/context의 canonical prompt 반영 | 학습 형식과 함께 결정 필요. 현재 미적용 |

### ⏸ 보류 — 성격 변경 없음

- `project_id` 정규화 — 프론트/백 이관 가능성. `HANDOFF_project_id_20260812.md` **발송 금지**
- 사내 문서 4편 · hard negative 문항 — 프론트 대기
- `API_CONTRACT` 발행 — 코드 확정 후
- AST 청킹 이식 — 8/21 이후
- SQLite 이관 — 우선순위 내려감. 형식이 아니라 이중화가 문제였음

---

## 6. 리스크

| | 리스크 | 완화 |
|---|---|---|
| 🔴 | **터널 단일 실패점** — 끊기면 인덱싱·검색이 전부 멈춤(503) | 로컬 임베딩 전환 검토 중. `sentence-transformers`로 같은 모델을 직접 돌리면 벡터가 동일해 인덱스 호환성 문제 없음. `embedder.py`만 교체 |
| 🔴 | **데모 중 `has_evidence: false`** | 화면 동작을 먼저 정의할 것 (§3 체크리스트) |
| 🟠 | **평가셋이 한 레포뿐** | 다른 레포로 일반화되는지 모름 |
| 🟠 | **production ↔ Git 사본 분기** | `C:\Pj\rag_lab`이 정본. `vision/rag_lab` 동기화 필요 |
| 🟡 | **상태가 네 곳에 흩어짐** | `cli.py doctor`로 상시 대조 가능해짐 |

---

## 7. 팀 · 일정

| | 담당 | 범위 |
|---|---|---|
| **md** | AI · 데이터 · 전체 리드 | 임베딩 · 청킹 · 인덱싱 · 저장 · 검색 · 프롬프트 조립 · 브리핑 · 학습 · 평가 · 모델 노드 운용 |
| **P** | 게이트웨이 | 인증 · 세션 · 대화 히스토리 · 스트리밍 · LLM 호출 |
| **K · Y** | 프론트 · Extension | VSCode 익스텐션 · 화면 |

- 기간: 2026-07-13 ~ 2026-09-17 (최종 데모데이)
- 중간 발표: **2026-08-21**
- 소유권 경계는 DECISIONS D13 · D20이 정본입니다.

---

## 8. 세션 인계 — 정본은 이 문서, 외부 LLM 전달은 롤링 파일 하나

정기 인계는 이 문서를 갱신합니다. 사용자가 다른 LLM에 최근 대화 전체를 전달해 달라고 명시한 경우에만
`C:\Pj\RAG_CURRENT_CONTEXT.md` 하나를 사용합니다. 날짜별 파일을 새로 쌓지 말고 그 파일을 갱신합니다.

```powershell
# 작업 중 — 사람은 한 줄만, 상태는 기계가 찍습니다
python cli.py journal "무엇을 했는지" --cmd "실행한 명령"

# 세션 끝 — 달라진 것만 나옵니다
python cli.py journal --render --since 2026-08-13
```

내부 세션을 넘길 때 할 일은 **이 문서의 §2·§3·§4를 고치는 것**뿐입니다.
나머지(무엇을 언제 했는가)는 `journal`이, 수치는 생성기가, 상태는 `doctor`가 냅니다.

---

## 9. 이 문서 갱신 규칙

```
[ ] 수치를 적지 않았는가              → MEASUREMENTS
[ ] 결정과 이유를 적지 않았는가        → DECISIONS
[ ] 불변 조건을 적지 않았는가          → AGENTS
[ ] 명령어 나열을 적지 않았는가        → MANUAL
[ ] 도구가 실시간으로 낼 수 있는가     → 명령어만 적기
```

**컨셉 수준 변경(방향·아키텍처·타깃)은 즉시 갱신.**
파라미터 수준 변경(이름·기한·개별 결정)은 세션 정리 때 몰아서.

⚠ 이 문서가 코드와 다르면 **코드가 맞습니다.** 문서를 고치세요.
