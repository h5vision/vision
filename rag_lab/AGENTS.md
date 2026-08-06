# AGENTS.md — 이 레포에서 작업하기 전에 반드시 읽을 것

> **VSsVscodeEX / rag_lab** — 오프라인 온보딩 AI 코드 어시스턴트의 검색 계층
>
> 이 파일은 코딩 에이전트를 위한 것입니다. 자세한 맥락은 `HANDOFF.md` 참조.

---

## 이 코드가 하는 일

```
레포 파일 → 청킹 → 임베딩 → Chroma 저장        (인덱싱)
질문 → 임베딩 → 검색 → 임계값 판정 → 프롬프트 조립  (질의)
```

⚠ **LLM 을 호출하지 않습니다.** 프롬프트(messages)만 만들어 돌려주고,
실제 생성은 백엔드(별도 담당자)가 Ollama 로 직접 합니다.

---

## 🔴 절대 바꾸지 말 것

아래를 바꾸면 **이미 확보한 실측 데이터가 전부 무효**가 됩니다.
재측정에는 사람의 판단과 수 시간이 필요합니다.

### 1. 임베딩 모델 — `BAAI/bge-m3` (1024차원)

```python
# vss_rag/config.py
embed_model = "bge-m3:latest"
embed_dim = 1024
```

**근거**: 2026-07-27 실측으로 검색 정확도 Hit@3 90%, MRR 0.900 확인.
2026-07-31 에 Ollama 경로와 sentence-transformers 경로가 **동일한 벡터**를
낸다는 것도 확인(cosine 유사도 1.0000, 6개 문장).

⚠ 모델을 바꾸면 아래가 전부 무효입니다.
- Hit@3 90% 수치
- 유사도 임계값 0.54
- 저장된 인덱스 (차원이 달라 재인덱싱 필요)

### 2. 거리 함수 — cosine

```python
# vss_rag/store.py
metadata={"hnsw:space": "cosine"}
```

임계값 0.54 는 cosine similarity 기준입니다. L2·dot product 로 바꾸면
점수 체계가 통째로 달라집니다.

⚠ Chroma 는 **거리**를 돌려주므로 `1.0 - distance` 변환이 필요합니다.
이 줄을 지우면 임계값 판정이 반대로 동작합니다.

### 3. 임베딩 실패 시 fallback 을 만들지 말 것

```python
# vss_rag/embedder.py — 실패는 예외로 드러나야 합니다
raise EmbeddingError(...)
```

**근거**: 참조 백엔드에 sha256 해시 기반 가짜 임베딩 fallback 이 있었고,
Ollama 실패 시 조용히 전환되어 **의미 없는 벡터가 인덱스에 저장**됐습니다.
에러도 안 나고 검색도 "동작"하지만 품질만 무너집니다.

**"안정성 개선"을 이유로 fallback 을 추가하지 마세요.** 의도된 설계입니다.

### 4. 프롬프트 형식 — `searcher.render_prompt()`

```
프로젝트 검색 결과:
[1] {path} lines {start}-{end}
{text}

질문:
{question}
```

**근거**: 이 형식은 **fine-tuning 학습 데이터와 공유**됩니다.
추론 형식과 학습 형식이 어긋나면 학습 효과가 사라집니다.

형식을 바꾸려면 학습 데이터를 다시 만들어야 합니다.
개선안이 있으면 **코드를 고치지 말고 사람에게 제안**하세요.

### 5. `[N]` ↔ 배열 인덱스 대응

```
프롬프트의 [1]  ↔  contexts[0]  ↔  references 의 n == 1
```

`vss_rag/references.py` 에서 인용된 근거만 추릴 때도 **`n` 은 원래 값을 유지**합니다.

⚠ 1, 2, 3 으로 재번호를 매기지 마세요. 답변 본문의 `[3]` 이 가리킬 대상을 잃습니다.

---

## 🟢 자유롭게 바꿔도 되는 것

| 항목 | 조건 |
|---|---|
| **저장소** (Chroma → SQLite/Qdrant 등) | cosine 과 1024차원만 유지 |
| **청킹 전략** (`chunker.py`) | 산출 레코드 필드명 유지 |
| `chunk_size` · `chunk_overlap` · `top_k` | ⚠ 바꾸면 재인덱싱 필요 |
| 서버 구조 · 에러 처리 · 로깅 | |
| 테스트 추가 | 환영 |

### ⚠ 파라미터를 바꿀 때

`config.py` 의 `fingerprint()` 에 포함된 값을 바꾸면 **기존 인덱스가 stale**이 됩니다.
`indexer.is_stale()` 이 이를 감지하지만, **실제 재인덱싱은 자동으로 되지 않습니다.**

```bash
python cli.py index <경로> --project <이름> --force
```

---

## 🚫 이미 판단이 끝난 것 — 다시 제안하지 말 것

| 항목 | 결정 | 이유 |
|---|---|---|
| Redis 도입 | ❌ | 필요한 건 비동기 실행 + 진행률 저장 2개뿐. threading 으로 충분 |
| `job_id` 도입 | ❌ | 동시 인덱싱이 없음. `project_id` 가 식별자 |
| PostgreSQL 사용 | ❌ | 백엔드가 DB 를 제거하기로 함 |
| rag_lab 이 LLM 호출 | ❌ | 스트리밍 중계 단계를 줄이기 위해 백엔드가 직접 호출 |
| async/await 전면 전환 | ❌ | `ThreadingHTTPServer` 로 충분. 병목은 Ollama 의 `NUM_PARALLEL=1` |
| FastAPI 도입 | ❌ | 표준 라이브러리로 충분. 의존성 최소화가 목표 |

---

## 실행

```bash
pip install chromadb          # 유일한 필수 의존성

python cli.py health                                    # 연결 확인
python cli.py index <레포경로> --project <이름>          # 인덱싱
python cli.py search "<질문>" --project <이름>           # 검색
python cli.py ask "<질문>" --project <이름> --json       # 검색 + LLM

python server.py --host 0.0.0.0 --port 8200             # HTTP API
python bench_ttft.py --project <이름> --repeat 5         # 지연 측정
```

### 사전 조건

**임베딩은 원격 Ollama 를 호출합니다.** `VSS_OLLAMA_URL`(기본 `http://127.0.0.1:11500`)
이 살아있어야 인덱싱·검색이 동작합니다.

⚠ 이 주소는 SSH 터널 경유입니다. 터널이 끊기면 503 이 납니다.

---

## 코드 구조

| 파일 | 책임 |
|---|---|
| `config.py` | 모든 파라미터. 환경변수로 덮어쓰기 가능 |
| `chunker.py` | 파일 수집 + 청킹 (코드=줄 윈도우 / 문서=`##` 섹션) |
| `embedder.py` | Ollama 임베딩. **fallback 없음** |
| `store.py` | Chroma. ⚠ 거리→유사도 변환 |
| `indexer.py` | 인덱싱 오케스트레이션 + git commit + 상태 |
| `searcher.py` | 검색 + 임계값 + 프롬프트 조립 + 답변 후처리 |
| `references.py` | `[N]` 파싱 + 출처 구조화 |
| `server.py` | HTTP API (표준 라이브러리) |
| `cli.py` | 명령줄 |

---

## 변경 전 체크리스트

```
[ ] 위 "절대 바꾸지 말 것" 5개에 해당하지 않는가
[ ] "이미 판단이 끝난 것"을 되돌리려는 것은 아닌가
[ ] 파라미터를 바꿨다면 재인덱싱이 필요함을 인지했는가
[ ] 산출 레코드 필드명을 유지했는가 (백엔드 계약)
[ ] HANDOFF.md 의 "알려진 미해결"을 확인했는가
```

⚠ **판단이 애매하면 코드를 고치지 말고 사람에게 물어보세요.**
이 프로젝트는 실측 데이터 위에 서 있고, 근거 없는 변경은 그것을 무너뜨립니다.
