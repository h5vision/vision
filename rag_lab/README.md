# rag_lab — VSsVscodeEX 검색 실험대

md 노트북에서 도는 독립 실험 환경입니다. **P의 백엔드를 전혀 건드리지 않습니다.**

```
[fest-api 레포]  →  청킹  →  임베딩(EC2 Ollama, 터널)  →  Chroma  →  검색
   C:\Pj\fest-api                                          ./data/index
```

---

## 설치

```powershell
cd C:\Pj\rag_lab
python -m venv .venv
.\.venv\Scripts\activate
pip install chromadb
```

⚠ `chromadb`만 필요합니다. torch·transformers 불필요 — **임베딩은 EC2 Ollama를 씁니다.**

## 사전 조건

**EC2 터널이 살아있어야 합니다.**

```powershell
netstat -ano | findstr 11500
# → 0.0.0.0:11500  LISTENING  이면 정상
```

없으면 PuTTY 세션 `vss-tunnel`을 열어주세요.

---

## 사용

```powershell
# 0) 연결 확인 — 먼저 이것부터
python cli.py health

# 1) 인덱싱
python cli.py index C:\Pj\fest-api --project fest-api

# 2) 상태
python cli.py status --project fest-api

# 3) 검색 (임계값 통과/탈락 전부 표시)
python cli.py search "결제 처리는 어디서 시작되나요?" --project fest-api

# 4) 검색 + LLM 답변 (프롬프트 조립까지)
python cli.py ask "이 프로젝트 구조를 설명해줘" --project fest-api --show-prompt

# 5) 청킹 파라미터 비교
python cli.py sweep C:\Pj\fest-api --project fest-api
```

---

## 실험 대상 — md가 조절하는 값

`vss_rag/config.py` 또는 환경변수로 바꿉니다.

| 값 | 기본 | 비고 |
|---|---|---|
| `chunk_size` | 1200 | P는 1600. 검색 품질의 최대 변수 |
| `chunk_overlap` | 150 | P는 200 |
| `top_k` | 4 | |
| `score_threshold` | 0.5400 | **D9 실측 0.53~0.55** |

```powershell
$env:VSS_CHUNK_SIZE=800
$env:VSS_TOP_K=6
python cli.py index C:\Pj\fest-api --project fest-api-c800 --force
```

### 🔴 바꾸면 안 되는 것

```
embed_model = bge-m3      D9 실측(Hit@3 90%, MRR 0.900, 임계값 0.53~0.55)의 전제
거리 함수    = cosine       바꾸면 임계값 전부 무효 → 재측정
```

📌 **저장소(Chroma/SQLite/Qdrant)는 바꿔도 임계값이 유효합니다.** 점수 분포를 결정하는 건 임베딩과 거리 함수이지 저장 위치가 아닙니다.

---

## 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 모든 파라미터 |
| `chunker.py` | 코드는 줄 윈도우, 문서는 `##` 섹션 |
| `embedder.py` | Ollama bge-m3. **fallback 없음** (R18 차단) |
| `store.py` | Chroma. ⚠ 거리→유사도 변환 |
| `indexer.py` | git commit 버전 + 상태 + threading |
| `searcher.py` | 검색 + 임계값 + 프롬프트 조립 |

### 8/3 설계 결정 반영

| 결정 | 구현 |
|---|---|
| git commit 기반 버전 | `indexer.is_stale()` — commit + **파라미터 지문** 비교 |
| `job_id` 미사용 (C안) | `project_id`로 상태 조회 |
| 비동기 = threading | Redis 불필요 |
| 상태 = 1단계 JSON | `./data/state.json` → 2단계 SQLite |

### ⚠ 파라미터 지문이 왜 필요한가

`chunk_size`를 바꿨는데 commit이 같으면 "최신"으로 오판합니다. md가 튜닝하는 상황에서 실제로 발생하므로, `fingerprint`를 함께 저장해 비교합니다.

---

## 산출 형식

`searcher.search()`의 `contexts`는 **백엔드 `Source` 스키마와 호환**됩니다.

```python
{"path": "src/payment/router.py", "type": "code",
 "line_start": 20, "line_end": 42, "section": None,
 "text": "...", "score": 0.7231}
```

`render_prompt()`는 **백엔드 `generation.py`의 현행 형식**을 그대로 씁니다.

```
프로젝트 검색 결과:
[1] src/payment/router.py lines 20-42
...

질문:
...
```

> ⚠ 학습 데이터도 같은 형식이어야 fine-tuning 효과가 샙니다.
> (`PROMPT_DATA_FORMAT_SPEC` §0 "렌더러 하나" 원칙)

---

## 알려진 한계

| 항목 | 내용 |
|---|---|
| 상태 소실 | 1단계 JSON — 프로세스 중단 시 진행 중 상태가 남음. 재인덱싱하면 복구 |
| 동시성 | 파일 락 없음. md 단독 사용 전제 |
| 증분 인덱싱 | 미구현. commit을 저장하므로 `git diff --name-only`로 확장 가능 |
| 평가 | Hit@k 측정 미포함 — 평가셋이 나오면 `eval.py` 추가 |

---

## 다음

1. `health` → 연결 확인
2. `index` → 첫 인덱싱, 청크 수·소요 시간 기록
3. `search` → 임계값 0.54가 이 레포에서도 유효한지 확인
4. **평가셋 작성** — S1~S5 + no-answer + 정답 근거
5. `sweep` → 청킹 파라미터 결정

⚠ **4번이 없으면 3·5번의 결과를 판정할 수 없습니다.** 사내 문서 4편이 나오면 문서 검색 미검증(R9)도 여기서 풀립니다.
