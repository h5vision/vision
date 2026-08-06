# rag_lab 운용 매뉴얼

- 최종 갱신: 2026-08-05
- 함께 볼 것: `README.md`(설치) · `API.md`(백엔드 연동) · `AGENTS.md`(변경 규칙)

---

# 1. 자주 쓰는 명령

## 매일 시작할 때

```powershell
# ① 터널 확인 (PuTTY 세션이 살아있어야 함)
netstat -ano | findstr 11500

# ② 연결·설정 확인
python cli.py health
```

`health` 출력에서 볼 것:

```
Ollama : http://127.0.0.1:11500
모델   : ['bge-m3:latest', 'qwen2.5-coder:7b']   ← 둘 다 있어야 함
임베딩 : dim=1024  (0.83s)  OK                    ← 1024 확인
인덱스 : ./data/index  projects=['fest-api']      ← 인덱스 목록
config : chunk_size=1200, top_k=4, ...            ← 현재 설정
```

## 인덱싱

```powershell
# 기본 설정으로
python cli.py index C:\Pj\fest-api --project fest-api

# 이미 있어도 강제로 다시
python cli.py index C:\Pj\fest-api --project fest-api --force

# 개선 기능을 켜고 (별도 project_id 로 만들어 비교)
$env:VSS_CONTEXT_HEADER=1
$env:VSS_USE_BM25=1
python cli.py index C:\Pj\fest-api --project fest-api-v2 --force
```

⚠ **환경변수는 명령 실행 전에 설정해야 합니다.** 설정 후 `health` 로 반영을 확인하세요.

⚠ 같은 PowerShell 창에서만 유지됩니다. 창을 새로 열면 다시 설정해야 합니다.

```powershell
# 환경변수 끄기
Remove-Item Env:VSS_CONTEXT_HEADER
Remove-Item Env:VSS_USE_BM25
```

## 상태 확인

```powershell
python cli.py status --project fest-api
```

| `state` | 뜻 |
|---|---|
| `none` | 인덱싱한 적 없음 |
| `running` | 진행 중 |
| `indexing_lexical` | BM25 색인 만드는 중 (거의 끝) |
| `done` | 완료 |
| `failed` | 실패 — `error` 확인 |
| `aborted` | 중단됨 (heartbeat 끊김) |

## 검색

```powershell
python cli.py search "이 프로젝트의 진입점은?" --project fest-api

# 파라미터를 바꿔서 (재인덱싱 불필요)
python cli.py search "질문" --project fest-api --top-k 8 --threshold 0.45
```

출력의 `✓` 는 임계값 통과, `✗` 는 탈락입니다. **탈락한 것도 보여주므로 임계값 조정 근거**가 됩니다.

## LLM 답변까지

```powershell
python cli.py ask "이 프로젝트 구조를 설명해줘" --project fest-api

# 프롬프트 원문도 보기
python cli.py ask "질문" --project fest-api --show-prompt

# 프론트에 갈 JSON 전체
python cli.py ask "질문" --project fest-api --json
```

## 서버 (백엔드 연동용)

```powershell
# 나만 접근
python server.py

# 팀도 접근 (LAN)
python server.py --host 0.0.0.0 --port 8200
```

⚠ **기동 시 워밍업 로그**가 나와야 정상입니다.

```
워밍업 중...
  인덱스 로드      412 ms  ['fest-api']
  임베딩 워밍업    287 ms
```

이게 없으면 첫 요청이 수 초 걸립니다.

## 브리핑

```powershell
# 서버를 띄운 뒤, 다른 창에서
curl.exe -X POST http://127.0.0.1:8200/briefing -H "Content-Type: application/json" -d "{\"project_id\":\"fest-api\"}"

# 캐시 조회
curl.exe "http://127.0.0.1:8200/briefing?project_id=fest-api"
```

⏱ 최초 생성 약 23초. 이후는 캐시라 즉시.

## 측정

```powershell
python bench_ttft.py --project fest-api --repeat 5
python bench_ttft.py --project fest-api --no-stream    # 비교용
```

---

# 2. 문제가 생겼을 때

## 🔴 `already_running` 에 갇힘

**가장 자주 겪는 문제입니다.** 인덱싱을 `Ctrl+C` 로 끊으면 상태가 `running` 인 채로 남습니다.

```powershell
python cli.py reset --project fest-api
```

안 되면:

```powershell
Remove-Item .\data\state.json
```

⚠ **인덱스 데이터는 안전합니다.** 재인덱싱 시 어차피 지우고 다시 넣습니다.

📌 2분 이상 멈춰 있으면 자동으로 `aborted` 판정되어 재실행이 허용됩니다(`STALE_AFTER=120`).
바로 다시 돌리고 싶으면 `--force` 를 붙이세요.

## 인덱스가 여러 개로 보임

```powershell
python cli.py health          # projects 목록 확인
type .\data\state.json        # 각각의 상태
```

`sweep` 명령을 돌렸거나 다른 이름으로 만들었을 때 생깁니다.

```powershell
# 필요 없는 것 삭제
python -c "import sys; sys.path.insert(0,'.'); from vss_rag.store import Store; from vss_rag.indexer import clear_state; s=Store(); s.reset('지울이름'); clear_state('지울이름'); print(s.projects())"
```

## 파라미터를 바꿨는데 결과가 그대로

**재인덱싱을 안 한 것입니다.**

```powershell
python cli.py index <경로> --project <이름> --force
```

⚠ `--force` 없이 돌리면 "이미 최신"으로 판단해 넘어갑니다.

📌 단 `top_k`, `threshold`, `use_mmr`, `reorder` 는 **재인덱싱 없이 즉시 반영**됩니다.

## 503 / 임베딩 실패

```powershell
# 터널이 살아있나
netstat -ano | findstr 11500

# Ollama 가 응답하나
curl.exe http://127.0.0.1:11500/api/tags
```

| 결과 | 원인 |
|---|---|
| `netstat` 에 아무것도 없음 | **터널 죽음** → PuTTY 재접속 |
| 터널은 있는데 `curl` 실패 | **EC2 쪽 문제** |

## 팀만 접속이 안 됨

```powershell
netstat -ano | findstr 8200
```

| 결과 | 원인 |
|---|---|
| `127.0.0.1:8200` | `--host 0.0.0.0` 없이 실행 |
| `0.0.0.0:8200` 인데도 안 됨 | Windows 방화벽 |

## 첫 요청만 유독 느림

Ollama 에서 모델이 내려간 상태입니다. EC2 에서:

```bash
ollama ps                    # 비어 있으면 언로드됨
```

```powershell
# 워밍업
curl.exe -X POST http://127.0.0.1:11500/api/generate -H "Content-Type: application/json" -d "{\"model\":\"qwen2.5-coder:7b\",\"prompt\":\"hi\",\"stream\":false,\"options\":{\"num_predict\":1}}"
```

---

# 3. 설정 토글

전부 **기본 꺼짐**입니다. 평가셋으로 검증한 뒤 켜세요.

| 환경변수 | 기본 | 효과 | 재인덱싱 |
|---|---|---|---|
| `VSS_CONTEXT_HEADER` | 0 | 청크에 구조 정보 주입 | 🔴 **필요** |
| `VSS_USE_BM25` | 0 | 어휘 검색 융합 | 🔴 **필요** |
| `VSS_USE_MMR` | 0 | 같은 파일 편중 완화 | ❌ 즉시 |
| `VSS_REORDER` | 0 | 근거 배치 조정 | ❌ 즉시 |
| `VSS_CHUNK_SIZE` | 1200 | 청크 크기 | 🔴 필요 |
| `VSS_CHUNK_OVERLAP` | 150 | 겹침 | 🔴 필요 |
| `VSS_TOP_K` | 4 | 근거 개수 | ❌ 즉시 |
| `VSS_THRESHOLD` | 0.54 | 근거 없음 판정선 | ❌ 즉시 |
| `VSS_MMR_LAMBDA` | 0.7 | 낮을수록 다양성 | ❌ |
| `VSS_FUSION_POOL` | 20 | 융합 전 후보 수 | ❌ |
| `VSS_EMBED_BATCH` | 16 | 임베딩 배치 | ❌ |

## 🔑 재인덱싱이 필요한 것을 구분하는 법

**`fingerprint()` 에 포함된 값**이면 재인덱싱이 필요합니다.

```python
# config.py
def fingerprint(self):
    return {
        "embed_model": ...,
        "chunk_size": ...,
        "chunk_overlap": ...,
        "context_header": ...,
        "use_bm25": ...,
    }
```

**저장된 데이터의 내용이 달라지는가**가 기준입니다.

- `chunk_size` → 청크 경계가 달라짐 → **저장 내용 변경**
- `top_k` → 몇 개를 꺼낼지만 다름 → **저장 내용 동일**

## A/B 비교 절차

```
1. 평가셋 확보 (질문 + 정답 위치)
2. 현재 설정으로 채점        → 기준선
3. 토글 하나만 켜고 재측정    → 그 항목의 효과
4. 반복
```

⚠ **한 번에 여러 개를 켜면 무엇이 효과였는지 알 수 없습니다.**

---

# 4. 왜 BM25 와 MMR 을 골랐나

검색 개선 기법은 여러 가지가 있습니다. 그중 이 둘을 먼저 넣은 이유입니다.

## 검토한 선택지

| 기법 | 효과 | 비용 | 채택 |
|---|---|---|---|
| **BM25 하이브리드** | 🟢 큼 | 🟢 낮음 | ✅ |
| **MMR 다양성** | 🟡 중간 | 🟢 **30분** | ✅ |
| 맥락 헤더 | 🟢 큼 | 🟢 낮음 | ✅ |
| 배치 조정 | 🔺 작음 | 🟢 낮음 | ✅ (덤) |
| 재순위화(reranker) | 🟢 **가장 큼** | 🔴 지연 +200~500ms | ⏸ 보류 |
| 쿼리 확장(LLM) | 🟡 | 🔴 지연 +1초 | ❌ |

### 보류·기각 이유

**재순위화** — 효과는 가장 크지만 별도 모델(`bge-reranker-v2-m3`)이 필요하고
**TTFT 예산을 200~500ms 잡아먹습니다.** 최종 형태 TTFT 가 약 850ms 로 계산되는데
여기에 더하면 1.1~1.3초가 됩니다. 아직 여유는 있지만, **먼저 싼 것부터** 하는 게 순서입니다.

**쿼리 확장** — LLM 으로 질문을 재작성하면 **지연이 1초 늘어납니다.**
TTFT 3초 목표에서 3분의 1을 쓰는 셈이라 기각했습니다.

---

## ① BM25 — 벡터가 못 하는 일을 합니다

### 벡터 검색의 약점

벡터 검색은 **의미가 비슷한 것**을 찾습니다. 그래서 **정확한 이름**에 약합니다.

```
질문: "validate_token 함수는 뭘 하나요?"

벡터:  "토큰 검증" 개념이 비슷한 것을 다 가져옴
       → verify_signature, check_auth, is_valid ... 가 섞임
       → 정작 validate_token 이 3위로 밀릴 수 있음

BM25: "validate_token" 이라는 문자열을 정확히 찾음
       → 1위로 집어냄
```

**코드에는 고유명사(함수명·클래스명·변수명)가 많습니다.** 신입이 던지는 질문의 상당수가
"이 이름의 것이 어디 있나"이므로, 정확 매칭이 필요합니다.

### 🔑 반대로 BM25 의 약점

실제 테스트에서 이렇게 나왔습니다.

```
Q: "결제 처리는 어디서 시작되나요?"
   BM25 결과: 없음
   ↑ 코드가 영어("process payment")인데 질문이 한국어
```

**BM25 는 문자열이 일치해야 찾습니다. 언어를 넘나들지 못합니다.**

### 그래서 둘을 합칩니다

| | 강점 | 약점 |
|---|---|---|
| **벡터** | **언어를 넘나듦** (한국어 질문 ↔ 영어 코드) | 정확한 이름 매칭 약함 |
| **BM25** | **고유명사 정확 매칭** | 언어를 못 넘음 |

**서로 정확히 반대입니다.** 우리 제품은 "한국어로 묻고 영어 코드를 찾는" 상황이면서
동시에 "함수 이름으로 찾는" 상황이라, 둘 다 필요합니다.

### 어떻게 합치나 — RRF

점수를 그냥 더하면 안 됩니다.

```
cosine 유사도:  0 ~ 1
BM25 점수:      0 ~ 30+
                 ↑ 척도가 다름. 더하면 BM25 가 압도
```

정규화해서 더하는 방법도 있지만 분포가 왜곡됩니다.
**RRF(Reciprocal Rank Fusion)** 는 **순위만** 씁니다.

```
score = Σ  1 / (60 + 순위)

벡터 1위:  1/61 = 0.0164
BM25 1위:  1/61 = 0.0164
양쪽 1위:  0.0328          ← 둘 다에서 상위면 크게 오름
```

**척도 문제가 사라지고, 양쪽에서 인정받은 것이 올라옵니다.**

### ⚠ 임계값은 벡터 점수로 유지합니다

```python
top = hits[0]["score"]                          # 벡터 점수
passed = [h for h in hits if h["score"] >= th]  # 벡터 점수로 판정
```

**융합 점수로 임계값을 판정하지 않습니다.**

D9 실측(0.5306 ~ 0.5531)은 **벡터 점수 분포**에서 나온 값입니다.
융합 점수(0.03 대)로 바꾸면 그 기준이 통째로 무효가 됩니다.

→ **융합은 순서만 바꾸고, "근거가 있는가"는 벡터 점수로 판단합니다.**

⚠ 부작용: BM25 로만 올라온 청크는 벡터 점수가 0 이라 임계값을 못 넘습니다.
의도된 동작이지만, 평가셋으로 이 방식이 맞는지 확인해야 합니다.

### 구현 메모

- **표준 라이브러리만** 사용. 외부 의존 없음
- 토크나이저가 `snake_case`, `camelCase` 를 조각으로도 나눔
  (`validate_token` → `validate_token`, `validate`, `token`)
  그래야 "token 검증" 같은 질문도 걸림
- 경로도 색인에 포함 — "payment 관련 파일" 같은 질문 대응
- 벡터 인덱싱이 **끝난 뒤** 저장된 청크를 읽어 색인
  (청킹 단계에서 따로 모으면 중간 실패 시 어긋남)

---

## ② MMR — 실제로 겪은 문제의 해결책

### 관측된 문제

```
출처 4개를 받았는데
   [1] translate.py L53-98
   [2] translate.py L101-150     ← 같은 파일
   [3] translate.py L200-240     ← 같은 파일
   [4] utils.py     L10-40
```

**동작 자체는 정상입니다.** 검색 단위가 파일이 아니라 청크이므로,
한 파일에서 관련 청크가 여러 개 걸리면 상위가 그 파일로 채워집니다.

### 그런데 두 가지 손해가 있습니다

**① 화면상 혼란**

사용자에게 "출처 3개"처럼 보이는데 사실 한 파일입니다.
(이건 `reference_files` 로 파일 단위 묶기를 해서 해결했습니다)

**② 🔴 관점의 편중 — 이게 더 큽니다**

```
LLM 이 받는 근거가 한 파일에서만 옴
   ↓
그 파일에 없는 정보는 답에 반영 안 됨
   ↓
"라우터는 봤지만 서비스 계층은 못 본" 답변
```

특히 **"어디서 시작되나요?" 같은 흐름 질문**에서 손해가 큽니다.
라우터 → 서비스 → 모델을 다 봐야 완전한 답이 되는데, 한 층만 보게 됩니다.

### MMR 이 하는 일

**점수와 다양성을 함께 고려**합니다.

```
value = λ × 점수  −  (1−λ) × (이미 고른 것과의 유사도)
```

- `λ = 1.0` → 점수만 봄 (MMR 끔과 동일)
- `λ = 0.7` → 기본. 점수 우선하되 편중 완화
- `λ = 0.5` → 다양성 강조

### 실제 결과

```
원래:  translate.py 3개 + utils.py 1개
MMR:   translate.py 2개 + config.py 1개 + utils.py 1개
```

### ⚠ 구현상의 타협

**정확한 MMR 은 청크 벡터 간 유사도가 필요합니다.**
그런데 저장소에서 벡터를 다시 꺼내면 비용이 이득보다 큽니다.

그래서 **경로 기반 근사**를 씁니다.

```
같은 파일         유사도 1.0
같은 디렉터리     유사도 0.5
상위 경로 공유    유사도 0.15 × 공유 깊이
무관             유사도 0.0
```

⚠ **"같은 파일이 아니면 내용도 다르다"는 가정**입니다.
대체로 맞지만 완벽하지 않습니다. 정확도가 필요하면 벡터 기반으로 바꿔야 합니다.

### 왜 재인덱싱이 필요 없나

**검색 후처리이기 때문입니다.** 저장된 데이터는 그대로이고,
꺼낸 결과를 어떻게 고를지만 달라집니다.

→ **가장 싸게 시험할 수 있는 개선안**입니다.

---

## ③ 왜 이 순서인가

```
1. 맥락 헤더    저장 내용을 개선      (근본)
2. BM25        검색 방식을 보완      (근본)
3. MMR         결과 선택을 개선      (후처리)
4. 배치 조정    전달 방식을 개선      (후처리)
```

**아래로 갈수록 싸고, 위로 갈수록 효과가 큽니다.**

⚠ 다만 **전부 평가셋 없이는 검증이 불가능**합니다.
"일반적으로 개선되는 기법"이라는 것과 "이 레포에서 개선된다"는 다른 문제입니다.

---

# 5. 파일 구조

```
rag_lab/
├── cli.py                  명령줄 진입점
├── server.py               HTTP API (백엔드 연동)
├── bench_ttft.py           지연 측정
│
├── vss_rag/
│   ├── config.py           모든 설정. 환경변수로 덮어쓰기
│   ├── chunker.py          파일 수집 + 청킹
│   ├── context_header.py   맥락 헤더 생성
│   ├── embedder.py         Ollama 임베딩 (fallback 없음)
│   ├── lexical.py          BM25 어휘 검색
│   ├── store.py            Chroma 벡터 저장
│   ├── rerank.py           MMR + 배치 조정
│   ├── searcher.py         검색 + 임계값 + 프롬프트
│   ├── references.py       [N] 파싱 + 출처 구조화
│   ├── indexer.py          인덱싱 오케스트레이션 + git
│   └── briefing.py         프로젝트 브리핑
│
├── data/
│   ├── index/              Chroma
│   ├── bm25/               역색인
│   ├── briefings/          브리핑 캐시
│   └── state.json          인덱싱 상태
│
├── README.md               설치·시작
├── API.md                  백엔드 연동 계약
├── AGENTS.md               ⚠ 변경 전 필독
├── HANDOFF.md              인계 문서
└── MANUAL.md               이 문서
```

---

# 6. 자주 하는 실수

| 실수 | 증상 | 해결 |
|---|---|---|
| 환경변수 설정 후 `health` 확인 안 함 | 개선이 안 켜짐 | `health` 의 `config` 확인 |
| `--force` 없이 재인덱싱 | 변경이 반영 안 됨 | `--force` 추가 |
| `Ctrl+C` 로 인덱싱 중단 | `already_running` | `cli.py reset` |
| 같은 `project_id` 로 덮어씀 | 비교 불가 | 별도 이름으로 |
| PowerShell 창 새로 열고 환경변수 잊음 | 기본값으로 실행 | 다시 설정 |
| 여러 토글을 한 번에 켬 | 효과 판별 불가 | 하나씩 |

---

*이 문서에 없는 문제는 `HANDOFF.md` §5(알려진 미해결)를 확인하세요.*

---

# 7. 증분 인덱싱

**바뀐 파일만 다시 처리합니다.** 전체 55분 → 보통 몇 초.

## 명령

```powershell
# 무엇이 바뀌었는지만 확인 (실행 안 함)
python cli.py update --project fest-api --dry-run

# 실행
python cli.py update --project fest-api

# 레포 경로는 생략 가능 (이전 인덱싱 경로를 씀)
python cli.py update C:\Pj\fest-api --project fest-api
```

## `--dry-run` 출력 예

```
a3f9c21e → 7b2f01dd
  수정 3 / 추가 1 / 삭제 0 / 이름변경 1
  → 재인덱싱 대상 4개 (전체 2870)
      src/payment/router.py
      src/payment/service.py
      src/utils/http.py
      src/new_module.py
```

## 서버에서

```
POST /index/update  {"project_id": "fest-api"}
POST /index/update  {"project_id": "fest-api", "dry_run": true}
```

## 🔴 증분이 거부되는 경우

실행하지 않고 **이유를 돌려줍니다.**
55분짜리 전체 인덱싱이 예고 없이 시작되면 곤란하기 때문입니다.

| `reason` | 뜻 | 조치 |
|---|---|---|
| `not_indexed` | 완료된 인덱스 없음 | 전체 인덱싱 |
| **`params_changed`** | **청킹·임베딩 설정 변경** | 전체 인덱싱 |
| `no_commit` | 이전 커밋 기록 없음 | 전체 인덱싱 |
| `not_a_git_repo` | git 레포가 아님 | 전체 인덱싱만 가능 |
| `diff_failed` | 커밋을 못 찾음 (히스토리 변경) | 전체 인덱싱 |
| **`too_many_changes`** | 변경이 50% 초과 | 전체가 더 빠름 |
| `already_running` | 진행 중 | 대기 또는 `--force` |

### `params_changed` 가 왜 전체인가

```
chunk_size 를 1200 → 800 으로 바꿈
   ↓
모든 파일의 청크 경계가 달라짐
   ↓
바뀐 파일만 다시 해봐야 나머지는 옛 설정 그대로
   ↓
섞이면 검색 품질이 예측 불가
```

**`fingerprint` 에 포함된 값이 바뀌면 전체 재인덱싱**입니다.

## 무엇이 감지되나

| 유형 | git | 처리 |
|---|---|---|
| 수정 | `M` | 옛 청크 삭제 → 재청킹 |
| 추가 | `A` | 청킹 후 삽입 |
| 삭제 | `D` | 청크 삭제만 |
| 이름 변경 | `R` | 옛 경로 삭제 + 새 경로 삽입 |
| 복사 | `C` | 새 경로 삽입 |
| **미커밋 변경** | working tree | 재처리 |
| **추적 안 되는 새 파일** | untracked | 삽입 |

⚠ **커밋하지 않은 변경도 반영됩니다.** `git diff <커밋>` 이 작업 트리와 비교하기 때문입니다.

## 처리 순서

```
① 옛 청크 삭제   (수정·삭제·이름변경 옛 경로)
② 재청킹 + 임베딩
③ 저장 (upsert)
④ BM25 역색인 재구축   ← 켜져 있을 때만
```

⚠ **①이 ②보다 먼저여야 합니다.**
청크 수가 줄어든 경우, 나중에 지우면 남는 옛 청크가 생깁니다.

📌 ④는 부분 갱신이 까다로워(df 값이 전역) 전체 재구축합니다.
다만 **임베딩 호출이 없어 수 초면 끝납니다.**

## 상태

```powershell
python cli.py status --project fest-api
```

| `state` | 뜻 |
|---|---|
| `updating` | 증분 진행 중 |
| `done` + `last_mode: incremental` | 증분으로 완료됨 |
