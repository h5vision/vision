---
문서: SECOND_NODE_SETUP
상태: 초안 — md 검토 대기
버전: v0.2
작성: 2026-08-14
목표: **md 노드와 동일한 환경을 다른 컴퓨터에 그대로 구현** (drop-in replacement)
정본_대조: AWS_MODEL_NODE_STATE v1.0 · MANUAL v1.3 · AGENTS v1.4 · STATE v1.1 · config.py · state.json (2026-08-14 실물)
---

# md 노드 복제 설명서 — 첫 세팅 전 과정

> **v0.1 정정**: v0.1은 터널 포트를 `11501`로 분리하라고 권했습니다. **철회합니다.**
> 목표가 "동일 환경 구현"이라면 **`11500` 그대로가 맞습니다.** 근거는 §4-3.

---

# 0. 목표와 완료 조건

## 0-1. 만들려는 것

```
[K·Y Extension] · [P 백엔드]
        │
        ▼  http://<이_컴퓨터_IP>:11500   (Ollama 중계)
        ▼  http://<이_컴퓨터_IP>:8200    (rag_lab 검색)
┌───────────────────────────────────────────┐
│  이 컴퓨터 — md 노트북과 동일 구성          │
│                                           │
│  :11500  PuTTY 터널 입구 (0.0.0.0 bind)   │
│  :8200   rag_lab HTTP 서버 (--host 0.0.0.0)│
│  data\   Chroma 인덱스 2.0 GB + BM25       │
│  C:\Pj\  대상 레포들 (경로가 중요 — §8)    │
└───────────────────────────────────────────┘
        │ SSH 22번 채널
        ▼
[EC2 sshd] ─▶ 127.0.0.1:11434 ─▶ [Ollama / L4]
                                  ├─ bge-m3:latest
                                  └─ qwen2.5-coder:7b
```

## 0-2. 완료 조건 — 이 4개가 다 되면 끝입니다

```
[ ] ① curl.exe http://127.0.0.1:11500/api/tags   → 모델 2개 + digest 일치
[ ] ② python cli.py health                        → 임베딩 dim=1024 OK
[ ] ③ python cli.py doctor                        → 인덱스 3개 이상 done
[ ] ④ python cli.py search "<진짜 질문>" --project sqlalchemy  → 근거가 나옴
```

**④까지 가야 복제입니다.** ①만 되면 "Ollama에 닿는 컴퓨터"일 뿐입니다.

## 0-3. ⚠ 두 노드가 동시에 살아 있어도 되는가

**됩니다. 다만 이득은 가용성뿐입니다.**

```
EC2 Ollama 는 하나이고 OLLAMA_NUM_PARALLEL=1 → 요청은 순차 처리
```

터널이 둘이어도 **질문은 한 번에 하나**입니다. 두 노드에서 동시에 질문하면 두 번째가 대기합니다.
→ **처리량 확보 목적이면 이 작업은 답이 아닙니다.** md 노트북 단일 실패점을 없애는 것이 목적입니다.

**운용 규칙 권장**: 평소엔 한쪽만 켜고, 전환이 필요할 때 P의 설정 IP만 바꿉니다 (§10).

---

# 1. md 노드는 무엇으로 이루어져 있는가 — 6층

**이 표가 이 문서의 목차입니다.** 하나라도 빠지면 §0-2의 어딘가에서 막힙니다.

| 층 | 무엇 | 크기 | 절 |
|---|---|---|---|
| 1 | **SSH 터널** — PuTTY, `.ppk`, 0.0.0.0:11500 | — | §4 |
| 2 | **방화벽** — inbound 11500 · 8200 | — | §5 |
| 3 | **Python 런타임** — `chromadb>=1.0` 만 | 수백 MB | §6 |
| 4 | **rag_lab 코드** — 레포 (`data\`·`.venv\` 제외) | 수 MB | §6 |
| 5 | **인덱스** — `data\` (Chroma + BM25 + state.json) | **2.0 GB** | §7 |
| 6 | **대상 레포** — `C:\Pj\` 아래. **경로가 고정입니다** | 수십~수백 MB | §8 |

> 🔴 **5와 6을 빠뜨리는 것이 가장 흔한 실패입니다.** 터널(1)만 만들면 §0-2 ①은 통과하지만
> ③④에서 빈 결과가 나옵니다. **검색 인덱스는 터널로 오지 않습니다.**

---

# 2. 준비물

| | 항목 | 확보 방법 | 비고 |
|---|---|---|---|
| 1 | `.pem` 키 | md 에게 받음 | ✅ 완료됨 |
| 2 | **EC2 현재 퍼블릭 IP** | 🔴 md 에게 **당일 확인** | EIP 미할당. `44.208.79.122`는 7/28 기록 |
| 3 | SSH 사용자명 | md 확인 | `ubuntu` 로 추정 (Ubuntu AMI) — 미확인 |
| 4 | PuTTY + PuTTYgen | https://www.putty.org | 같이 설치됨 |
| 5 | Python 3.10 이상 | python.org | EC2가 3.10.12. 맞추면 안전 |
| 6 | **`data\` 폴더 2.0 GB** | USB / 외장하드 | §7. 네트워크 복사는 느립니다 |
| 7 | **대상 레포들** | git clone 또는 복사 | §8. **commit 을 맞춰야 합니다** |
| 8 | 디스크 여유 | — | 최소 5 GB 권장 |

⚠ **`.pem` 파일을 저장소·채팅·공유폴더에 두지 마세요.** 이 키 하나로 EC2 전체에 들어옵니다.

---

# 3. 순서 — 이 순서를 지키세요

```
① PuTTY 터널          →  검증 ①    ← 여기서 막히면 아래는 의미 없음
② Python + rag_lab 코드
③ data\ 복사          →  검증 ②③
④ 대상 레포 배치       →  검증 ④
⑤ 방화벽 (팀 접속용)   →  다른 노트북에서 검증
⑥ rag_lab 서버 기동
```

> 🔑 **한 단계씩 통과시키세요.** 한꺼번에 하고 안 되면
> 터널 문제인지 방화벽인지 인덱스인지 구분이 안 됩니다.
> 이 프로젝트에서 "어느 계층이 고장인지 모르는 채로 시간 쓰는 것"이 이미 가장 큰 낭비였습니다.

---

# 4. ① SSH 터널

## 4-1. `.pem` → `.ppk` 변환 (⚠ 건너뛰면 인증에서 막힙니다)

**PuTTY 는 `.pem` 을 직접 읽지 못합니다.** `ssh.exe` 는 `.pem` 을 그대로 쓰는데
PuTTY 계열은 `.ppk` 만 씁니다.

```
1. PuTTYgen 실행
2. [Load]  →  파일 형식 필터를 "All Files (*.*)" 로 변경   ← 안 바꾸면 .pem 이 안 보임
3. 받은 .pem 선택
4. "Successfully imported foreign key" 안내가 뜨면 정상
5. [Save private key]  →  암호 없이 저장할지 물으면 Yes  →  <이름>.ppk
```

## 4-2. 세션 설정

| 순서 | 위치 | 설정 |
|---|---|---|
| 1 | `Session` | Host Name = `ubuntu@<EC2_IP>` · Port `22` · **SSH** |
| 2 | `Connection` | `Seconds between keepalives` = **`30`** |
| 3 | `Connection`→`SSH`→`Auth`→`Credentials` | Private key file = **4-1의 `.ppk`** |
| 4 | `Connection`→`SSH`→`Tunnels` | ↓ 4-3 |
| 5 | **`Session` 으로 돌아가서** | 세션 이름 입력 → **`Save`** 🔴 |
| 6 | | `Open` |

> 🔴 **5번을 빠뜨리는 사고가 이미 있었습니다.**
> `Tunnels` 의 `Add` 는 **현재 창의 임시 목록에만** 들어갑니다.
> **첫 접속은 성공하고, PuTTY 를 껐다 켜면 사라집니다** — 그래서 다음날 아침에 발견합니다.

## 4-3. Tunnels — 🔴 `11500` 을 그대로 씁니다

```
Source port  : 11500
Destination  : 127.0.0.1:11434
             : ● Local   ● Auto
             : ☑ Local ports accept connections from other hosts   ← 반드시 체크
[Add]  →  목록에 L11500  127.0.0.1:11434 가 생기는지 확인
```

### 왜 `11500` 동일이 맞는가 — v0.1 권고를 뒤집는 근거

`vss_rag/config.py` 실물 확인 결과:

```python
ollama_url: str = _env("VSS_OLLAMA_URL", "http://127.0.0.1:11500")
```

**`11500` 이 코드의 기본값입니다.** 그대로 쓰면 **환경변수를 하나도 설정하지 않아도**
md 노트북과 동일하게 동작합니다.

포트를 바꾸면 `VSS_OLLAMA_URL` 을 매번 설정해야 하고, **그것을 잊는 것 자체가 새로운 실패 지점**이
됩니다 — 게다가 실패했을 때 증상이 "503 임베딩 실패"라 원인이 포트라는 걸 알아채기 어렵습니다.

**동일 환경 구현이 목적이라면 코드 기본값과 일치시키는 쪽이 맞습니다.**

> ⚠ 대신 v0.1이 걱정했던 **"어느 노드가 응답했는지 구분 불가"** 문제는 남습니다.
> 다만 P 백엔드의 `OLLAMA_BASE_URL` 은 **한 번에 하나의 IP만** 가리키므로,
> "지금 활성 노드가 어디인가"는 **P 설정 한 곳만 보면 됩니다.** 포트로 나눌 이유가 못 됩니다.

⚠ **Destination 에 `http://` 를 붙이지 마세요.** `호스트:포트` 만 씁니다.
붙이면 sshd 가 `http://127.0.0.1` 을 DNS 이름으로 해석하려다 실패합니다.

| 위치 | 형식 |
|---|---|
| PuTTY Destination | `127.0.0.1:11434` ← 스킴 **없음** |
| curl URL | `http://127.0.0.1:11500/api/tags` ← 스킴 **필요** |

## 4-4. 검증 ①

```powershell
netstat -ano | findstr 11500
```

| 출력 | 판정 |
|---|---|
| `TCP  0.0.0.0:11500  ... LISTENING` | ✅ 정상 |
| `TCP  127.0.0.1:11500 ... LISTENING` | 🔴 체크박스 미적용 → 4-3 다시. **Save 후 재접속** 필요 |
| 아무것도 없음 | 🔴 터널 안 뜸 |

```powershell
curl.exe http://127.0.0.1:11500/api/tags
```

⚠ **반드시 `curl.exe`** 입니다. PowerShell 5.x 에서 `curl` 은 `Invoke-WebRequest` 별칭이라
동작·옵션이 다르고 시스템 프록시를 탑니다.

**통과 기준** — 둘 다 보여야 합니다:

```
bge-m3:latest
qwen2.5-coder:7b     digest  dae161e27b0e...
```

> 🔴 응답은 오는데 모델이 `gemma3:4b` 라면 **EC2 가 아니라 로컬 Ollama 에 물어본 것**입니다.
> 이 컴퓨터에 Ollama 가 설치돼 있으면 `11434` 에서 응답합니다 — 터널과 헷갈리지 마세요.

---

# 5. ⑤ 방화벽 — 포트 2개

**팀이 이 컴퓨터에 붙으려면 두 개가 열려야 합니다.**

| 포트 | 무엇 | 누가 붙나 |
|---|---|---|
| `11500` | Ollama 터널 입구 | P 백엔드 (`OLLAMA_BASE_URL`) |
| `8200` | rag_lab HTTP 서버 | P 백엔드 (`/prompt` · `/search` · `/finalize`) |

⚠ **팀이 작업 중이 아닐 때 하세요.** 잘못 건드리면 접속이 끊깁니다.

```powershell
# [조회] 먼저 현재 규칙 파악
Get-NetFirewallRule -Direction Inbound -Enabled True |
  Where-Object { $_.DisplayName -like "*putty*" -or $_.DisplayName -like "*plink*" -or $_.DisplayName -like "*python*" } |
  Format-List DisplayName,Profile,Action

# ⚠[변경] 관리자 권한 PowerShell
New-NetFirewallRule -DisplayName "VSS Ollama Tunnel" `
  -Direction Inbound -Protocol TCP -LocalPort 11500 `
  -RemoteAddress <P노트북_IP> -Profile Any -Action Allow

New-NetFirewallRule -DisplayName "VSS rag_lab Server" `
  -Direction Inbound -Protocol TCP -LocalPort 8200 `
  -RemoteAddress <P노트북_IP> -Profile Any -Action Allow
```

> **중요**: Windows 방화벽은 허용 규칙이 **하나라도** 매칭되면 통과시킵니다.
> 좁은 규칙을 추가하는 것만으로는 보안이 나아지지 않고, **넓은 규칙(프로그램 단위 전면 허용)을
> 비활성화해야** 효과가 있습니다. 그리고 그게 팀을 끊을 수 있는 작업이므로 **작업 중에는 하지 마세요.**
>
> `-Profile Any` 가 중요합니다 — 강습실 wifi 가 Public 으로 분류되면 Private 규칙은 무효입니다.

⚠ **왜 신경 쓰는가**: Ollama 에는 **인증이 없고** `POST /api/delete`(모델 삭제) ·
`POST /api/pull`(임의 다운로드) 이 열려 있습니다. 터널 입구가 LAN 전체에 노출되면 그대로 노출됩니다.

---

# 6. ②③ Python + rag_lab 코드

## 6-1. 설치

```powershell
# 레포 배치 — md 노트북과 같은 경로를 권장
#   C:\Pj\rag_lab\
#   ⚠ data\ 와 .venv\ 는 제외하고 가져옵니다

cd C:\Pj\rag_lab
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install chromadb          # requirements.txt = chromadb>=1.0  — 유일한 필수 의존성
```

⚠ **`.venv\` 를 복사하지 마세요.** 절대경로가 박혀 있어 다른 컴퓨터에서 깨집니다.

## 6-2. 환경변수 — 🟢 아무것도 설정하지 않는 것이 정답입니다

`config.py` 의 기본값이 곧 md 노트북의 현재 설정입니다.

| 변수 | 기본값 | 설정 필요? |
|---|---|---|
| `VSS_OLLAMA_URL` | `http://127.0.0.1:11500` | ❌ (§4-3에서 11500을 썼다면) |
| `VSS_EMBED_MODEL` | `bge-m3:latest` | ❌ |
| `VSS_CHUNK_SIZE` | `1200` | ❌ |
| `VSS_CHUNK_OVERLAP` | `150` | ❌ |
| `VSS_MIN_CHUNK` | `80` | ❌ |
| `VSS_TOP_K` | `4` | ❌ |
| `VSS_THRESHOLD` | `0.5400` | ❌ |
| `VSS_CONTEXT_HEADER` | `False` | ❌ |
| `VSS_USE_BM25` | `False` | ❌ |
| `VSS_INDEX_DIR` | `./data/index` | ❌ |
| `VSS_STATE_PATH` | `./data/state.json` | ❌ |

> 🔑 **기존 프로젝트의 질의·증분은 전역 CFG 가 아니라 컬렉션에 저장된 지문(fingerprint)을 씁니다**
> (2026-08-13 구현). 그래서 `use_bm25=False` 기본값이어도 `fest-api`·`sqlalchemy` 는
> 저장된 대로 BM25 를 켜고 검색합니다. **환경변수를 md 와 맞추려 애쓰지 마세요 — 이미 인덱스 안에 있습니다.**

⚠ `doctor`·`health` 가 보여주는 `default_config_drift` 는 **장애가 아닙니다.**
"다음 전체 인덱싱 기본값과 저장 프로필의 차이"일 뿐입니다.

---

# 7. ③ 인덱스 이전 — `data\` 2.0 GB

## 7-1. 복사 vs 재인덱싱 — 비용 차이가 큽니다

| | 방법 | 소요 | 판정 |
|---|---|---|---|
| **가** | `data\` 폴더 복사 | 2.0 GB 전송 시간 | 🟢 **권장** |
| **나** | 재인덱싱 | **2시간 이상** | 🔴 레포도 필요하고, 결과가 미묘하게 달라질 수 있음 |

**실측 근거** (2026-08-14 직접 측정):

```
C:\Pj\rag_lab\data\             2.0 GB
  ├─ index\      (Chroma)       2.0 GB
  ├─ bm25\                       37 MB
  │    ├─ sqlalchemy.json       21.8 MB
  │    ├─ fest-api.json         16.3 MB
  │    └─ fastapi-cli.json      228 KB
  ├─ briefings\                  44 KB
  ├─ state.json                 4.9 KB
  └─ journal.jsonl              3.3 KB
```

재인덱싱 처리율은 실측 **약 6청크/초**(터널 경유 임베딩에 지배됨):

```
sqlalchemy  19,510청크  ÷ 6  ≈  54분   (실측 기록 3,133.9초와 일치)
fest-api    21,104청크  ÷ 6  ≈  59분   (실측 기록 3,478.6초와 일치)
fastapi-cli    250청크  ÷ 6  ≈  44초
                              ─────────
                              약 2시간
```

→ **USB 로 2.0 GB 옮기는 게 압도적으로 싼 선택입니다.**

## 7-2. 복사 절차

```
1. 🔴 md 노트북에서 rag_lab 서버 · CLI 를 전부 종료
      ← Chroma 는 SQLite. 쓰기 중 복사하면 손상됩니다
2. C:\Pj\rag_lab\data\  통째로 복사
3. 이 컴퓨터의 C:\Pj\rag_lab\data\ 에 붙여넣기
4. python cli.py doctor
```

## 7-3. ⚠ 복사본에 딸려 오는 것들

`state.json` 실물 확인 결과, **완성 인덱스 외에 잔재가 같이 갑니다.**

| 프로젝트 | 상태 | 비고 |
|---|---|---|
| `sqlalchemy` | ✅ done · 19,510청크 · `rag-v2` · BM25 19,510 | 현행 |
| `fest-api` | ✅ done · 21,104청크 · `context_header=true` · BM25 | 현행 |
| `fastapi-cli` | ✅ done · 250청크 | 현행 |
| `sqlalchemy--rag-v1` | done | 비교 실험용 |
| **`fest-api--bad`** | 🔴 **`running` 인 채 36/2870에서 멈춤** | 중단된 run |
| `building-*` | 🔴 미완성 | `sqlalchemy--rag-v3` `IncompleteRead` 실패 잔재 |

**동작에는 영향 없습니다** — 컬렉션 이름이 곧 상태인 설계라 `building-` 접두어는 질의 대상에서 빠집니다.
다만 `doctor` 가 🟡 로 잡습니다. **🔴 만 보세요.**

---

# 8. ④ 대상 레포 배치 — 🔴 경로가 고정입니다

## 8-1. `state.json` 에 절대경로가 박혀 있습니다

실물 확인:

```json
"sqlalchemy"  : { "project_root": "C:\\Pj\\sqlalchemy"  , "commit": "cbef63a9ee83..." }
"fest-api"    : { "project_root": "C:\\Pj\\fest-api"    , "commit": "afe41126f624..." }
"fastapi-cli" : { "project_root": "C:\\Pj\\fastapi-cli" , "commit": "fb2dd86bf442..." }
```

**→ 이 컴퓨터에도 `C:\Pj\` 아래 같은 이름으로 레포가 있어야 합니다.**
다른 드라이브(`D:\`)나 다른 폴더명이면 증분 갱신·재인덱싱이 실패합니다.

> 이것이 `STATE §4-5` 에 열려 있는 **`project_root` 경로 문제**가 실제로 터지는 지점입니다.
> 아키텍처 결정이 나기 전까지는 **경로를 맞추는 것이 유일한 우회**입니다.

## 8-2. 필요한 레포와 commit

```powershell
# 검색만 할 거면 레포 없이도 됩니다 (인덱스에 텍스트가 들어 있음)
# 하지만 아래가 하나라도 필요하면 레포가 있어야 합니다:
#   - 증분 갱신 (git diff 기반)
#   - 재인덱싱
#   - 출처 클릭 → 파일 열기
```

| 레포 | 경로 | commit (맞춰야 함) |
|---|---|---|
| `sqlalchemy` | `C:\Pj\sqlalchemy` | `cbef63a9ee83678f0a8d4ca639bfa030123b9272` |
| `fest-api` | `C:\Pj\fest-api` | `afe41126f624af30038cc8e17b2aaf60ebd4b838` |
| `fastapi-cli` | `C:\Pj\fastapi-cli` | `fb2dd86bf442489f7a01a5ab0509516691dc2d58` |

```powershell
cd C:\Pj\sqlalchemy
git rev-parse HEAD        # 위 값과 일치해야 함
```

⚠ **`sqlalchemy` · `fastapi-cli` 는 인덱싱 당시 `dirty: true`** 였습니다 —
working tree 에 커밋되지 않은 변경이 있는 상태였습니다.
새로 clone 하면 그 변경이 없어서 **증분 갱신 시 diff 가 예상과 다를 수 있습니다.**
→ 가능하면 **레포 폴더째 복사**가 안전합니다.

⚠ **`C:\Pj\sqlalchemy` 에는 `RAG_TEST.md` · `RAG_TEST.json` 이 잔존합니다.**
재인덱싱하면 질문지가 인덱스에 들어가 **측정이 무의미해집니다.** 복사 전에 확인하세요.

## 8-3. 같이 가져가면 좋은 것 (선택)

| 항목 | 왜 |
|---|---|
| `profiles\` | `rag-v1/v2/v3` 정의. matrix 실험에 필요 |
| `evaluation\` · `RAG_TEST_fastapi_cli.md` | 평가셋 |
| `eval_runs.jsonl` | 측정 이력. 없으면 `make_measurements.py` 가 빈 문서를 냄 |

---

# 9. 검증 — 계층별로 끊어서

**어느 계층이 고장인지 모르는 채로 시간 쓰는 것이 가장 큰 낭비입니다.**

```powershell
# ① 터널
netstat -ano | findstr 11500
curl.exe http://127.0.0.1:11500/api/tags        # 모델 2개 + digest

# ② Ollama 연결 + 설정
python cli.py health
#   Ollama : http://127.0.0.1:11500
#   모델   : ['bge-m3:latest', 'qwen2.5-coder:7b']   ← 둘 다
#   임베딩 : dim=1024  OK                            ← 1024 확인

# ③ 인덱스
python cli.py doctor
python cli.py projects

# ④ 실제 검색 — 🔴 자리표시자 금지
python cli.py search "SQLAlchemy 세션은 어디서 만들어지나요?" --project sqlalchemy
```

| ④ 결과 | 진단 | 담당 |
|---|---|---|
| `EmbeddingError` | 터널 / Ollama | 이 컴퓨터 (①로) |
| 점수는 나오는데 임계값 미만 | 검색 품질 또는 질문 | 정상일 수 있음 |
| `has_evidence: true` + 근거 표시 | ✅ **복제 성공** | — |

> 🔴 **`<질문>` 같은 자리표시자를 그대로 넣지 마세요.**
> 어떤 코퍼스에서도 낮은 점수가 나와 오진합니다 (2026-08-13에 실제로 발생).

## ⑤ GPU 가 실제로 도는지 확신이 필요할 때

**GPU 는 거짓말을 하지 않습니다.** EC2 에 PuTTY 창을 하나 더 열고:

```bash
nvidia-smi dmon -s u
```

이 상태에서 생성 요청을 보냅니다. `sm`·`mem` 이 0에서 튀면 실제 추론 발생.

> PuTTY 창을 두 개 여는 것은 문제없습니다. 터널 항목이 있는 세션을 또 열면
> forwarding 만 실패하고(포트 중복) 셸은 정상적으로 열립니다.
> **터널 전용 / 작업 전용 세션을 따로 저장해두면 편합니다.**

## ⑥ 서버 기동 + 팀 접속

```powershell
python server.py --host 0.0.0.0 --port 8200
```

```powershell
netstat -ano | findstr 8200
```

| 출력 | 원인 |
|---|---|
| `127.0.0.1:8200` | `--host 0.0.0.0` 없이 실행 |
| `0.0.0.0:8200` 인데도 팀이 안 됨 | 방화벽 (§5) |

P 노트북에서:

```powershell
Test-NetConnection -ComputerName <이_컴퓨터_IP> -Port 11500
Test-NetConnection -ComputerName <이_컴퓨터_IP> -Port 8200
curl.exe http://<이_컴퓨터_IP>:11500/api/tags
```

---

# 10. 노드 전환 절차 (md → 이 컴퓨터)

**전환에 필요한 것은 P 백엔드의 설정 2개뿐입니다.**

```
OLLAMA_BASE_URL   http://<md_IP>:11500   →   http://<이_컴퓨터_IP>:11500
rag_lab URL       http://<md_IP>:8200    →   http://<이_컴퓨터_IP>:8200
```

포트가 같으므로 **IP 만 바뀝니다.** 이것이 §4-3에서 `11500` 을 유지한 실질적 이득입니다.

```
[ ] 이 컴퓨터에서 §0-2 완료 조건 4개 통과
[ ] 서버 기동 (python server.py --host 0.0.0.0 --port 8200)
[ ] P 에게 IP 전달 → 설정 변경 → 재기동
[ ] 프론트에서 질문 1회 → sources[] 에 실제 파일 경로가 나오는지
[ ] md 노트북 터널은 그때 꺼도 됨
```

⚠ **P 백엔드 timeout 을 15초 이상(60 권장)으로 확인하세요.**
Ollama 콜드스타트가 7.3초입니다. 5초로 잡혀 있으면 재시작 직후 첫 요청이 **반드시** 실패합니다.
(현재 값 미확인 — §13)

---

# 11. 트러블슈팅

## ① `Connection closed by <IP> port 22`

TCP · 프로토콜 · host key 까지 성공하고 **인증에서 실패**한 것입니다. **포트 문제가 아닙니다.**
→ `.ppk` 를 `Auth` 에 지정했는지 확인 (§4-1, §4-2 3번)

## ② `Forwarded connection refused ... [Name or service not known]`

Tunnels 의 **Destination 에 `http://` 를 붙인 경우**입니다. 스킴을 빼세요.

## ③ PuTTY 설정이 껐다 켜면 사라짐

`Tunnels` 의 `Add` 는 임시 목록입니다. **`Session` 화면에서 `Save`.**

## ④ 터널이 `127.0.0.1` 에만 bind 됨

`Local ports accept connections from other hosts` 체크 후 **반드시 Save + 재접속**.
접속 중 변경은 현재 세션에 반영되지 않습니다.
체크박스가 불안하면 Source port 에 직접: `192.168.x.x:11500`

## ⑤ `This key is not known by any other names`

SSH host key 첫 접속(TOFU) 안내. **에러가 아닙니다.** 새 컴퓨터에서는 당연히 뜹니다.

⚠ 반면 `REMOTE HOST IDENTIFICATION HAS CHANGED!` 는 **멈춰야 할 신호**입니다.

## ⑥ 503 / 임베딩 실패

```powershell
netstat -ano | findstr 11500      # 터널 살아있나
curl.exe http://127.0.0.1:11500/api/tags
```

| 결과 | 원인 |
|---|---|
| `netstat` 에 아무것도 없음 | 터널 죽음 → PuTTY 재접속 |
| 터널은 있는데 `curl` 실패 | EC2 쪽 문제 |

## ⑦ 첫 요청만 유독 느림

모델이 언로드된 상태. 콜드스타트 약 7.3초. EC2 에서 `ollama ps` 가 비어 있으면 워밍업:

```bash
curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen2.5-coder:7b","prompt":"hi","stream":false,"options":{"num_predict":1}}' \
  > /dev/null
```

## ⑧ 에러 문구로 원인 구분

| 증상 | 의미 | 범인 |
|---|---|---|
| `connection refused` (즉시) | 도달했으나 그 포트에 아무도 없음 | bind 문제 |
| `timeout` (한참 후) | **도달조차 못 함** | 방화벽 / AP isolation |
| `Recv failure: Connection was reset` | 받았다가 끊음 | Destination 오류 / Ollama 다운 |

## ⑨ 어느 기계인지 프롬프트로 구분

**`...$` = EC2(Linux)** / **`PS C:\...>` = 이 컴퓨터(Windows)**

| 목적 | Windows | Linux |
|---|---|---|
| 문자열 필터 | `findstr` | `grep` |
| 포트 확인 | `netstat -ano` | `ss -ltnp` |
| HTTP | `curl.exe` | `curl` |

## ⑩ `state.json` 저장 실패 (`PermissionError [WinError 5]`)

**알려진 결함입니다.** `state.tmp → state.json` 원자적 교체가 Windows 에서 거부되는 사례.
청크는 들어갔는데 상태만 `failed` 로 기록됩니다. 재시도 로직이 없습니다.

원인 후보 — 미확정: 다른 프로세스가 `state.json` 을 열고 있음 (`server.py` + `cli.py` 동시 실행) ·
백신/Windows Search 순간 잠금 · 동기화 폴더

→ **이 컴퓨터에서도 재발할 수 있습니다.** `C:\Pj` 를 백신 예외·동기화 제외로 두는 것을 권장합니다.

---

# 12. 🚫 하지 말 것

| 항목 | 이유 |
|---|---|
| **SG 에 11434 · 8000 개방 요청** | 권한도 없고 터널로 해결됨. **Ollama 는 인증이 없어 개방 자체가 위험** |
| **EC2 `stop` / `start`** | 🔴 **EIP 미할당 → IP 변경 → 두 컴퓨터의 PuTTY 세션 전부 무효.** `reboot` 은 IP 유지 |
| **`OLLAMA_HOST` 를 `0.0.0.0` 으로 변경** | 인증 없는 LLM 을 인터넷에 노출 |
| **불필요한 `systemctl restart ollama`** | 모델 언로드 → 7.3초 콜드스타트 |
| **`.venv\` 복사** | 절대경로가 박혀 깨짐 |
| **`data\` 를 서버 켜둔 채 복사** | Chroma 는 SQLite. 쓰기 중 복사하면 손상 |
| **`server.py` 와 `cli.py` 동시 실행** | §11-⑩ 의 유력 원인 후보 |
| **레포를 `C:\Pj` 밖에 두기** | `project_root` 절대경로 불일치 (§8-1) |
| **터널을 늘려 처리량 확보 시도** | `NUM_PARALLEL=1` — 순차 처리라 이득 없음 |
| **`VSS_*` 환경변수를 md 와 맞추려 애쓰기** | 기존 프로젝트는 저장된 지문을 씁니다 (§6-2) |

---

# 13. ⬜ 이 문서가 확인하지 못한 것

| # | 항목 | 영향 |
|---|---|---|
| 1 | **EC2 현재 퍼블릭 IP** | 🔴 EIP 미할당. `44.208.79.122` 는 7/28 기록. **가장 흔한 실패 원인이 될 것** |
| 2 | **SSH 사용자명** | `ubuntu` 추정(Ubuntu AMI). 틀리면 §11-① 증상 |
| 3 | **md 노트북 방화벽 현재 규칙** | 7/28 이후 미확인. 전면 허용이 남아 있으면 이미 LAN 노출 상태일 수 있음 |
| 4 | **P 백엔드 timeout** | 5초면 콜드스타트 시 첫 요청 필패 (§10) |
| 5 | **P 백엔드의 rag_lab URL 설정 방식** | 환경변수인지 코드 상수인지 미확인. 전환 비용이 달라짐 |
| 6 | **그 컴퓨터의 Windows · PuTTY 버전** | PuTTYgen 메뉴 명칭이 버전마다 조금 다름 |
| 7 | **`C:\Pj\.git` 의 정체** | `C:\Pj` 자체가 git 저장소로 보임. 레포 복사 시 영향 미확인 |
| 8 | **`C:\Pj\vision\rag_lab` 과의 관계** | STATE 리스크에 "production ↔ Git 사본 분기 — `C:\Pj\rag_lab` 이 정본" 으로 기록됨. **`vision` 쪽을 복사하면 안 됩니다** |
| 9 | **동시 SSH 세션 상한** | sshd 기본 `MaxStartups=10` 이면 충분하나 EC2 설정 미확인 |

---

# 14. 한 장 체크리스트

```
준비
[ ]  1. md 에게 EC2 현재 IP 확인            ← EIP 없음. 가장 흔한 실패 원인
[ ]  2. .pem 확보 · PuTTYgen 으로 .ppk 변환

터널
[ ]  3. PuTTY: Host / keepalive 30 / Auth 에 .ppk
[ ]  4. Tunnels: 11500 → 127.0.0.1:11434 · ☑ other hosts · [Add]
[ ]  5. 🔴 Session 으로 돌아가 Save
[ ]  6. netstat → 0.0.0.0:11500 LISTENING
[ ]  7. curl.exe /api/tags → 모델 2개 + digest 일치 (gemma3 면 로컬 Ollama)

런타임
[ ]  8. rag_lab 코드 배치 (data\ · .venv\ 제외) → C:\Pj\rag_lab
[ ]  9. python -m venv .venv → pip install chromadb
[ ] 10. VSS_* 환경변수는 설정하지 않음

데이터
[ ] 11. 🔴 md 쪽 서버·CLI 종료 확인 후 data\ 2.0GB 복사
[ ] 12. 레포를 C:\Pj\<이름> 에 배치 · git rev-parse HEAD 로 commit 대조
[ ] 13. sqlalchemy 의 RAG_TEST.md 잔존 여부 확인

검증
[ ] 14. python cli.py health   → dim=1024 OK
[ ] 15. python cli.py doctor   → 🔴 만 확인 (🟡 는 정상)
[ ] 16. python cli.py search "<진짜 질문>" --project sqlalchemy → 근거 나옴

팀 오픈
[ ] 17. 방화벽 11500 · 8200 (작업 중 아닐 때)
[ ] 18. python server.py --host 0.0.0.0 --port 8200
[ ] 19. P 노트북에서 Test-NetConnection 두 포트
[ ] 20. P 설정의 IP 두 곳 교체 → 프론트에서 질문 1회
```
