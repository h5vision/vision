---
문서: README
상태: 현행정본
버전: v2.1
최종확인: 2026-08-14
판단근거로_쓸_범위: 없음 — 이 문서는 **길잡이**입니다
쓰면_안_되는_범위: 전부. 내용은 각 문서를 보세요
---

# rag_lab — VSsVscodeEX 검색 계층

신입 개발자가 낯선 코드베이스에 질문하면 **출처와 함께** 답하게 하는 시스템의
검색 부분입니다. 전체·증분 인덱싱, 검색, 프롬프트 조립, 출처 후처리를 담당하고,
질의 답변의 LLM 호출은 게이트웨이가 합니다. 프로젝트 브리핑 생성만 rag_lab이 LLM을 호출합니다.

```
[VSCode Extension] → [게이트웨이·P] → [rag_lab] → [Ollama]
                                       ↑ 이 레포
```

---

## 처음이라면 이 순서로

```bash
python cli.py health     # 연결 · 인덱스 · CFG 확인
python cli.py doctor     # 상태가 어긋난 곳이 있는지
```

두 명령이 **지금 시스템이 어떤 상태인지 전부** 알려줍니다.
문서에서 찾지 마세요 — 문서에 적힌 숫자는 적히는 순간부터 낡습니다.

---

## 문서 — 무엇을 어디서 찾는가

| 알고 싶은 것 | 볼 곳 |
|---|---|
| **코드를 고치기 전에 알아야 할 것** | `AGENTS.md` 🔴 **필독** |
| 지금 상태 · 다음 할 일 · 미해결 | `STATE.md` |
| 왜 이렇게 정했는가 | `DECISIONS.md` |
| 수치 (정확도 · 성능 · 코퍼스) | `MEASUREMENTS.md` · `MEASUREMENTS_generated.md` |
| 명령어 · 트러블슈팅 | `MANUAL.md` |
| 백엔드 연동 계약 | `API.md` |
| 인덱싱 버전 · 질문 suite · 평가 matrix 작성 | `EVALUATION_GUIDE.md` |
| 다른 LLM에 최근 작업 전체 인계 | `C:\Pj\RAG_CURRENT_CONTEXT.md` (롤링 스냅샷, 정본 아님) |

### 🔑 문서에 없는 것은 도구가 냅니다

| | |
|---|---|
| 인덱스 현황 · 설정 불일치 | `python cli.py doctor` |
| 연결 · CFG · 인덱스별 지문 | `python cli.py health` |
| 검색 정확도 | `python make_measurements.py` |
| 작업 이력 | `python cli.py journal --render` |
| 평가 프로필 목록 | `python cli.py profiles` |
| 정확도 실험 검증·계획 | `python experiment.py validate ...` · `python experiment.py plan ...` |

---

## 설치 · 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Ollama 터널 확인 (기본 11500)
netstat -ano | findstr 11500

python cli.py health
```

명령어 전체와 트러블슈팅은 **`MANUAL.md`** 를 보세요.

---

## 현재 연동 경계

```text
질의: Frontend → FastAPI /v1/chat → rag_lab /prompt → 생성 모델 → rag_lab /finalize
증분(로컬 Git): rag_lab /index/update
증분(프론트 파일 전체 문자열): Frontend → FastAPI 프록시(미구현) → rag_lab /index/update/files
```

질의에는 `GET /projects`에서 확인한 완성 인덱스의 exact `project_id`를 사용합니다.
`auto`나 유사 이름 fallback은 없습니다. 파일 payload 증분의 `content_sha256`은 선택값이며,
생략하면 rag_lab이 받은 전체 문자열에서 계산합니다. 자세한 계약은 `API.md`를 보세요.

---

## 🔴 절대 바꾸지 말 것

`AGENTS.md` §2 가 정본입니다. 요약만:

```
BGE-M3 모델 고정 · cosine 거리 · 임베딩 폴백 없음
프롬프트 형식 · [N] ↔ contexts 인덱스 대응
전체 인덱싱은 선삭제 금지 (begin_build → promote)
```

**코드를 고치기 전에 `AGENTS.md` 를 읽으세요.** 근거를 모르고 되돌리면 안 되는 것들입니다.
