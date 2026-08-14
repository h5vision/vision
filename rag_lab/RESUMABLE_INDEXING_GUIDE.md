# 중단 재개형 전체 인덱싱 가이드

상태: 선택 기능 · 기본 비활성화  
적용 범위: 새로 시작하는 **전체 인덱싱**  
적용 제외: 기존 엔진으로 이미 진행 중인 작업, 로컬 Git 증분, 프론트 파일 payload 증분

## 1. 목적과 안전 경계

이 기능은 전체 인덱싱이 중단됐을 때 이미 Chroma에 확정 저장한 파일을 다시 임베딩하지 않고
남은 파일부터 이어서 처리합니다. 완성 인덱스의 이름과 검색 구조는 기존 규약을 바꾸지 않습니다.

```text
<project_id>            완성 인덱스
building-<project_id>   작업 중 인덱스
<project_id>-prev       승격 중 직전 완성본
```

체크포인트를 켜도 현재 완성 인덱스, BM25, 브리핑 형식은 동일합니다. 추가되는 데이터는 다음
SQLite 파일뿐입니다.

```text
data/checkpoints/resume.sqlite3
```

이 DB는 검색·서빙에 쓰이지 않습니다. 삭제하면 재개 이력만 없어지고 완성 인덱스는 유지됩니다.

> 기능 추가 전에 이미 기존 `indexer.py`로 시작한 작업에는 체크포인트가 없습니다.
> 그 작업의 `building-*`은 소급해서 재개하지 않으며 `legacy_incomplete`로 판정합니다.

## 2. 구현 파일

```text
vss_rag/resume/__init__.py
vss_rag/resume/errors.py       오류 코드와 응답
vss_rag/resume/manifest.py     대상 파일 SHA-256과 전체 manifest
vss_rag/resume/checkpoint.py   SQLite run/file 완료 ledger
vss_rag/resume/engine.py       신규 실행·재개·restart·승격 복구
tests/test_resume_index.py     실제 Chroma를 열지 않는 강제 중단 테스트
```

기존 파일의 변경은 연결부에 한정됩니다.

- `config.py`: 기본 OFF 기능 플래그와 DB 경로
- `store.py`: run 소유권 확인, 기존 building 열기, 파일 청크 수 검증, 재개 가능 promote
- `indexer.py`: state와 완료 훅의 public adapter
- `cli.py`: `--resumable`, `--resume`, `--restart`, `resume-status`
- `server.py`: 재개 상태·재개·restart HTTP 라우트

청킹, 임베딩, BM25, 브리핑 코드는 복제하지 않고 기존 모듈을 그대로 호출합니다.

## 3. 저장 순서

파일 묶음마다 반드시 다음 순서를 지킵니다.

```text
파일 읽기·청킹
  → 임베딩
  → building 컬렉션 upsert
  → 경로별 실제 청크 수 확인
  → SQLite에서 파일 completed 기록
```

Chroma 저장 후 체크포인트를 기록하므로 ledger가 실제 데이터보다 앞서지 않습니다. 프로세스가
upsert 직후 죽어 마지막 파일이 Chroma에만 남은 경우, 그 파일은 ledger에서 `pending`입니다.
재개 시 해당 경로만 building 컬렉션에서 지우고 다시 처리합니다.

완료 파일도 재개 시 SQLite `chunk_count`와 Chroma 경로 청크 수를 대조합니다. 다르면 추측해서
진행하지 않고 `completed_file_mismatch`로 중단합니다.

## 4. 신규 실행

기존 경로에 영향을 주지 않고 한 작업만 체크포인트 방식으로 시작하려면 `--resumable`을 씁니다.

```powershell
Set-Location C:\Pj\rag_lab

python cli.py index C:\Pj\mockserver-monorepo `
  --project mockserver-monorepo `
  --profile rag-v2 `
  --resumable
```

모든 제품용 전체 인덱싱을 새 엔진으로 시작하려면 서버 또는 CLI 실행 전에 설정합니다.

```powershell
$env:VSS_RESUME_INDEX_ENABLED = "true"
```

기본값은 `false`입니다. 현재 실행 중인 프로세스에는 소스나 환경변수 변경이 소급 적용되지 않습니다.

## 5. 상태 확인과 재개

```powershell
python cli.py resume-status --project mockserver-monorepo
```

예시:

```json
{
  "project_id": "mockserver-monorepo",
  "run_id": "idx_...",
  "status": "interrupted",
  "phase": "embedding",
  "resumable": true,
  "completed_files": 382,
  "total_files": 917,
  "completed_chunks": 12450
}
```

중단한 프로세스가 종료된 것을 확인한 뒤 다음처럼 재개합니다. 체크포인트에 저장된 레포 경로와
fingerprint를 사용하므로 root는 생략할 수 있습니다.

```powershell
python cli.py index `
  --project mockserver-monorepo `
  --profile rag-v2 `
  --resume
```

같은 머신의 기존 owner PID가 살아 있고 heartbeat도 최근이면 `run_still_active`로 거부합니다.
프로세스가 확실히 종료됐지만 OS 상태 확인이 잘못된 경우에만 `--force`를 사용합니다.

```powershell
python cli.py index --project mockserver-monorepo --resume --force
```

## 6. 폐기하고 처음부터 시작

체크포인트 소유권과 building 컬렉션의 `run_id`가 일치할 때만 자동 폐기합니다.

```powershell
python cli.py index C:\Pj\mockserver-monorepo `
  --project mockserver-monorepo `
  --profile rag-v2 `
  --restart
```

체크포인트가 없는 과거 `building-*`은 `--restart`로도 자동 삭제하지 않습니다. 다른 작업의
데이터일 수 있으므로 기존 진단·수리 절차로 사람이 판정해야 합니다.

## 7. 8200 HTTP API

### 새 체크포인트 실행

```http
POST /index
Content-Type: application/json

{
  "project_root": "C:\\Pj\\mockserver-monorepo",
  "project_id": "mockserver-monorepo",
  "profile": "rag-v2",
  "resumable": true
}
```

### 재개 상태

```http
GET /index/resume/status?project_id=mockserver-monorepo
```

### 재개

```http
POST /index/resume

{
  "project_id": "mockserver-monorepo",
  "run_id": "idx_...",
  "profile": "rag-v2"
}
```

### 폐기 후 새 실행

```http
POST /index/restart

{
  "project_root": "C:\\Pj\\mockserver-monorepo",
  "project_id": "mockserver-monorepo",
  "profile": "rag-v2"
}
```

8200은 `202`로 작업 시작을 반환하고 진행 상황은 기존 `/index/status`와 새
`/index/resume/status`로 폴링합니다. 8000 공개 API 프록시는 아직 추가하지 않았습니다.
추후 다음 매핑만 얇게 추가하면 됩니다.

```text
GET  /v1/index/resume/status → 8200 GET  /index/resume/status
POST /v1/index/resume        → 8200 POST /index/resume
POST /v1/index/restart       → 8200 POST /index/restart
```

## 8. 단계별 복구

| phase | 재개 동작 |
|---|---|
| `embedding` | 완료 파일 검증 후 pending 파일만 처리 |
| `indexing_lexical` | 임베딩을 반복하지 않고 BM25 전체 재생성 |
| `promoting` | target 컬렉션의 run_id를 확인하고 BM25/state 커밋 마무리 |
| `briefing` | 인덱스는 유지하고 브리핑만 다시 실행 |
| `complete` | 재개하지 않고 `already_complete` 반환 |

BM25는 임베딩보다 빠르고 완전한 문서 집합이 필요하므로 파일 단위 체크포인트를 만들지 않습니다.
중단되면 building 또는 이미 승격된 target 전체를 제한된 크기의 Chroma 페이지로 다시 읽습니다.
페이지 조회 실패·중복 ID·건수 변경은 실패로 처리하고, 문서 수 검증을 통과한 staging BM25만
최종 파일로 교체합니다. promote 이후 복구 단계에서 실패하면 Chroma와 직전 BM25를 함께 rollback합니다.

브리핑은 인덱스 승격 후 실행합니다. 브리핑 실패가 완성 인덱스를 무효화하지 않으며 상태는
`done + briefing=failed`로 남습니다.

## 9. 재개를 거부하는 조건

- 파일 목록 또는 파일 SHA-256이 변경됨: `source_changed`
- 요청 profile과 저장 fingerprint가 다름: `profile_changed`
- 체크포인트 없이 building만 존재: `legacy_incomplete`
- building metadata의 run_id 불일치: `run_id_mismatch`
- 기존 owner가 살아 있음: `run_still_active`
- 완료 ledger와 Chroma 경로 청크 수 불일치: `completed_file_mismatch`
- 전체 checkpoint 청크 수와 building count 불일치: `checkpoint_store_mismatch`

이 경우 남은 위치를 추측하지 않습니다. 원인을 확인한 뒤 명시적으로 restart 또는 기존 수리 절차를
사용합니다.

## 10. 현재 제한

1. 기존 엔진으로 시작한 작업은 재개할 수 없습니다.
2. 로컬 Git 증분과 프론트 파일 payload 증분은 요청 단위 rollback이며 중간 batch 재개 대상이 아닙니다.
3. manifest 생성은 시작 요청에서 파일 전체 SHA-256을 읽으므로 큰 레포에서는 수 초 걸릴 수 있습니다.
4. SQLite는 rag_lab 머신의 로컬 디스크를 전제로 합니다. 여러 머신이 같은 project_id를 동시에
   인덱싱하는 분산 scheduler는 아닙니다.
5. 자동 재개는 하지 않습니다. 사용자가 프로세스 종료와 상태를 확인한 뒤 명시적으로 요청합니다.

## 11. 테스트

실제 `data/index`를 열지 않는 가짜 저장소와 임시 SQLite를 사용합니다.

```powershell
python -m unittest tests.test_resume_index -v
```

현재 자동 테스트는 다음을 확인합니다.

- 소스 변경 시 manifest hash 변경
- 첫 파일 저장 후 강제 오류
- 완료 파일 체크포인트 보존
- 재개 시 완료 파일 임베딩 생략
- 남은 파일만 처리
- 완성 이름으로 승격 후 체크포인트 `complete`

실사용 활성화 전에는 별도 테스트 project_id로 프로세스 강제 종료, BM25 단계 중단, promote 직후
중단, 브리핑 중단을 추가 검증해야 합니다.

## 12. 기능 비활성화·제거

즉시 기존 엔진으로 돌아가려면 다음 설정을 제거하거나 false로 둡니다.

```powershell
Remove-Item Env:\VSS_RESUME_INDEX_ENABLED -ErrorAction SilentlyContinue
```

완전히 제거할 때는 다음 순서가 안전합니다.

1. 기능 플래그 OFF
2. 진행 중인 resumable run이 없는지 확인
3. `server.py`, `cli.py`의 얇은 진입점 제거
4. `store.py`, `indexer.py`의 public adapter 제거
5. `vss_rag/resume/` 삭제
6. 필요하면 `data/checkpoints/resume.sqlite3` 삭제

완성 Chroma 컬렉션, BM25, 브리핑은 제거하거나 변환할 필요가 없습니다.
