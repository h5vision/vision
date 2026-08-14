# rag_lab 인덱싱 프로필·정확도 평가 가이드

이 문서는 사람과 LLM이 같은 규칙으로 인덱싱 버전, 질문 suite, 실험 matrix를 만들고
결과를 해석하기 위한 정본입니다. 측정값은 이 문서에 손으로 복사하지 않습니다.
실행 결과 JSON과 생성 보고서가 측정값의 정본입니다.

## 1. 세 축을 섞지 않습니다

```text
코퍼스 조건      어떤 파일을 포함·제외했는가
인덱싱 프로필    어떻게 청킹·임베딩·BM25 생성했는가
검색 프로필      vector/hybrid, pool, top_k, threshold, MMR 등을 어떻게 적용했는가
```

검색 프로필만 바뀌면 기존 인덱스를 재사용합니다. 청킹·맥락 헤더·임베딩 모델·제외 규칙이
바뀌면 별도 인덱스가 필요합니다.

## 2. 초기 인덱싱 버전

정의 파일은 `profiles/index_profiles.json`입니다.

| 버전 | 벡터 | BM25 생성 | 맥락 헤더 | 앞 버전에서 바뀐 조건 |
|---|---|---|---|---|
| `rag-v1` | O | X | X | 기준선 |
| `rag-v2` | O | O | X | BM25 하나 |
| `rag-v3` | O | O | O | context header 하나 |

동일 레포의 project_id는 `<repo>--<profile>`입니다.

```text
fest-api--rag-v1
fest-api--rag-v2
fest-api--rag-v3
```

버전 정의로 결과가 한 번 생성되면 기존 버전을 수정하지 않습니다. 변경이 필요하면
`rag-v4` 또는 교정 버전처럼 새 ID를 추가합니다. 각 실행에는 이름뿐 아니라 완전히 해석된
fingerprint와 `profile_hash`도 기록되므로 이름만 같은 다른 설정을 감지할 수 있습니다.

현재 `rag-v1~v3`에는 번역 문서나 tests 제외가 들어 있지 않습니다. 코퍼스 변경은 검색
결과에 큰 영향을 주므로, 적용하려면 다음 독립 버전에서 `exclude_globs` 하나만 바꿉니다.

## 3. 프로필 확인과 명시적 인덱싱

```powershell
python cli.py profiles

python cli.py index C:\Pj\fest-api `
  --project fest-api--rag-v2 `
  --profile rag-v2
```

`--profile`을 쓰면 환경변수 CFG가 그 프로필을 덮어쓰지 않습니다. 해석된 설정이 청킹,
임베딩, BM25 생성, 컬렉션 fingerprint까지 명시적으로 전달됩니다.

하이브리드 프로필은 BM25 역색인 문서 수가 Chroma 청크 수와 같아야 완료됩니다. BM25 생성에
실패하거나 수가 다르면 벡터 전용으로 조용히 성공 처리하지 않으며, 새 컬렉션도 승격하지
않습니다.

기존 `cli.py index`에서 `--profile`을 생략하는 방식은 호환용이며 현재 CFG를 사용합니다.
정식 비교 실험에서는 항상 프로필을 명시합니다.

## 4. 질문 suite 형식

질문은 UTF-8 JSONL로 한 줄에 하나씩 작성합니다. JSON Schema는
`evaluation/schemas/question.schema.json`, 태그 목록은 `evaluation/tags.json`입니다.

```json
{"id":"routing-001","question":"라우터를 등록하는 코드는 어디에 있나요?","answerable":true,"type":2,"gold":[{"path":"fastapi/routing.py","line_start":3084,"line_end":3220,"symbol":"include_router"}],"tags":["exact_symbol","architecture","code_vs_docs","korean"],"note":"문서보다 구현 코드가 올라와야 함"}
```

답이 없는 질문은 다음처럼 씁니다.

```json
{"id":"none-001","question":"존재하지 않는 기능은 어디에 있나요?","answerable":false,"type":5,"gold":[],"tags":["no_evidence","hard_negative","korean"]}
```

### 사람·LLM 공통 작성 규칙

1. `id`는 suite 안에서 영구적으로 유일해야 합니다.
2. `answerable=true`면 `gold`가 최소 하나 있어야 합니다.
3. `answerable=false`면 `gold=[]`이고 `no_evidence` 태그를 붙입니다.
4. `gold.path`는 레포 루트 기준 POSIX 상대 경로입니다.
5. 줄 범위를 쓰면 `line_start`와 `line_end`를 함께 씁니다.
6. 정확한 함수·클래스를 묻는 질문은 가능하면 `symbol`도 기록합니다.
7. 질문은 설정별로 바꾸지 않습니다. 같은 suite를 모든 셀에 넣습니다.
8. LLM이 만든 질문도 검증을 통과하기 전에는 평가에 포함하지 않습니다.
9. no-evidence 질문은 이름만 그럴듯한 것이 아니라 실제 레포 전수 검색으로 부재를 확인합니다.
10. 정답 파일이 이동하거나 symbol이 사라지면 검증 실패로 드러나며, 조용히 오답으로 집계하지 않습니다.

검증기는 ID 중복, 필수 필드, 태그, 실제 경로, 줄 범위, symbol 존재, answerable/gold 모순을
검사합니다.

## 5. 실험 matrix

예제 정본은 `evaluation/matrices/fest-api-rag-v1-v3.json`입니다. 현재 셀은 다음 5개입니다.

```text
rag-v1 / vector
rag-v2 / vector
rag-v2 / hybrid
rag-v3 / vector
rag-v3 / hybrid
```

`rag-v2/vector ↔ rag-v2/hybrid`는 같은 청크·임베딩에서 BM25 융합 효과만 비교합니다.
`rag-v1/vector ↔ rag-v2/vector`는 원칙적으로 같은 결과여야 하며, 다르면 다른 조건이
섞였는지 확인해야 합니다. `rag-v2 ↔ rag-v3`는 context header 효과를 봅니다.

BM25를 만들지 않은 `rag-v1`에 hybrid 검색 셀을 붙이면 validate 단계에서 차단합니다.

## 6. 명령과 안전장치

```powershell
# 스키마·gold·프로필·셀 참조 검증. 데이터 변경 없음
python experiment.py validate evaluation\matrices\fest-api-rag-v1-v3.json

# 생성/재사용할 인덱스와 예상 질의 수 표시. 데이터 변경 없음
python experiment.py plan evaluation\matrices\fest-api-rag-v1-v3.json

# 준비된 인덱스만 사용. 필요한 인덱스가 없으면 중단
python experiment.py run evaluation\matrices\fest-api-rag-v1-v3.json

# plan에 나온 전체 인덱싱을 명시적으로 허용
python experiment.py run evaluation\matrices\fest-api-rag-v1-v3.json --allow-index

# 해당 matrix의 최신 결과로 Markdown 보고서 생성
python experiment.py report evaluation\matrices\fest-api-rag-v1-v3.json
```

`--allow-index` 없이는 대형 전체 인덱싱을 시작하지 않습니다. 실험 전체 인덱싱에는 브리핑
콜백을 붙이지 않습니다. `require_clean=true`이면 dirty repository 또는 git 상태 확인 불가를
실행 단계에서 차단합니다. `validate`와 `plan`은 읽기 전용입니다.

## 7. 평가 층

각 셀은 두 평가 모드를 가질 수 있습니다.

### retrieval

- 벡터 후보와 선택적 BM25/RRF 순위
- Hit@1/3/5
- MRR
- 태그별 Hit@k/MRR
- threshold, MMR, reorder는 적용하지 않음

### pipeline

- 실제 `searcher.search()` 경로
- threshold와 `has_evidence`
- 선택적 MMR/reorder
- NO_EVIDENCE recall
- 최종 contexts 기준 Hit@k/MRR
- `bm25_active`와 지연 시간

하이브리드 셀은 BM25 파일 존재와 Chroma 청크 수 일치를 실행 전에 확인합니다. 벡터 결과가
있는데 `bm25_active=false`이면 실패합니다.

## 8. 결과와 비교 규칙

```text
data/evaluation/runs/<run_id>.json       원본 측정 결과
data/evaluation/reports/<run_id>.md      파생 보고서
```

결과에는 다음 조건이 저장됩니다.

- repository와 git commit
- matrix hash와 suite hash
- profile ID와 profile hash
- project_id와 search profile 전체
- 셀별·태그별 지표와 질문별 관측

다음 조건이 다르면 직접 우열 비교하지 않습니다.

- repository 또는 commit
- suite hash 또는 질문 수
- 인덱싱 fingerprint
- 비교하려는 효과 외의 search profile 값

보고서 수치는 관찰값입니다. 새 기본 프로필을 자동 승격하거나 threshold를 자동 적용하지
않습니다. 결정은 `DECISIONS.md`, 현재 상태는 `STATE.md`에 기록합니다.

## 9. LLM에 질문 생성을 맡길 때 전달할 최소 계약

```text
반환 형식은 UTF-8 JSONL이며 한 줄에 question.schema.json 객체 하나만 출력한다.
evaluation/tags.json에 없는 태그를 만들지 않는다.
answerable 질문은 실제 레포 파일을 확인한 gold.path와 가능하면 symbol/줄 범위를 넣는다.
answerable=false 질문은 레포 전수 검색으로 부재를 확인하고 gold=[]로 둔다.
설정별 질문을 따로 만들지 말고 동일 suite가 모든 matrix 셀에 사용되게 한다.
생성 후 반드시 experiment.py validate를 통과시킨다.
```

LLM의 역할은 후보 생성과 정리까지입니다. 실제 부재 여부와 gold의 의미적 타당성은 코드
검증만으로 완전히 보장할 수 없으므로 사람이 표본 검토해야 합니다.

---

## 10. 처음부터 끝까지 실행하는 운영 절차

아래 절차는 현재 구현을 처음 전달받은 사람이 그대로 실행할 수 있는 순서입니다.
모든 명령은 `C:\Pj\rag_lab`에서 실행합니다.

### 10-1. 사전 점검

```powershell
Set-Location C:\Pj\rag_lab

python cli.py health
python cli.py doctor --deep
python cli.py profiles
```

확인할 항목:

- Ollama 접속 성공
- `bge-m3:latest` 모델과 1024차원 확인
- `doctor`의 빨간 오류가 0건인지 확인
- `rag-v1`, `rag-v2`, `rag-v3`가 표시되는지 확인
- 인덱싱할 레포가 Git repository이며 커밋되지 않은 변경이 없는지 확인

`doctor`의 노란 항목은 기록·metadata 차이일 수 있습니다. 메시지를 읽지 않고 전부 수정하지
마세요. `default_config_drift`는 기존 인덱스와 다음 전체 인덱싱 기본값의 차이로 정상일 수
있습니다.

### 10-2. 질문과 matrix 검증

```powershell
python experiment.py validate evaluation\matrices\fest-api-rag-v1-v3.json
```

정상 예시:

```text
OK  matrix=fest-api-rag-v1-v3
    repository=C:\Pj\fest-api
    profiles=rag-v1, rag-v2, rag-v3
    cells=5
```

여기서 실패하면 인덱싱하지 말고 먼저 질문 JSONL 또는 matrix를 수정합니다. 주요 오류는 다음과
같습니다.

| 오류 | 의미 | 조치 |
|---|---|---|
| `실제 파일이 없습니다` | `gold.path`가 현재 레포와 다름 | 레포 루트 기준 경로로 수정 |
| `symbol이 파일에 없습니다` | 코드 변경 또는 잘못된 정답 | 실제 코드 확인 후 수정 |
| `answerable=true인데 gold가 없습니다` | 채점할 정답 없음 | gold 추가 또는 no-evidence로 변경 |
| `등록되지 않은 tag` | 태그 계약 위반 | `evaluation/tags.json`에서 선택 |
| `BM25를 만들지 않은 인덱스` | `rag-v1/hybrid` 같은 불가능한 셀 | vector 셀로 바꾸거나 BM25 프로필 사용 |

### 10-3. 실행 계획 확인

```powershell
python experiment.py plan evaluation\matrices\fest-api-rag-v1-v3.json
```

계획에서 반드시 확인할 것:

- `repository`가 의도한 레포인지
- Git `commit`이 평가하려는 버전인지
- `dirty=False`인지
- 각 프로필의 `project_id`가 `<repo>--rag-vN` 형태인지
- 각 인덱스의 동작이 `create`, `rebuild`, `reuse` 중 무엇인지
- 실행 셀이 아래 다섯 개인지

```text
rag-v1/vector
rag-v2/vector
rag-v2/hybrid
rag-v3/vector
rag-v3/hybrid
```

`create`와 `rebuild`는 전체 임베딩을 수행합니다. 계획을 확인하기 전에는
`--allow-index`를 붙이지 마세요.

### 10-4. 개별 프로필만 먼저 인덱싱하는 방법

전체 matrix 실행 전에 한 버전씩 만들고 상태를 확인하려면 다음처럼 실행합니다.

#### 레포 이름만 바꿔서 v1~v3 순차 인덱싱

인덱싱할 레포가 `C:\Pj` 바로 아래에 있다면 아래 블록을 그대로 복사한 뒤
`$RepoName = "fest-api"`의 값만 바꿉니다. 예를 들어 `C:\Pj\sqlalchemy`를 인덱싱하려면
`$RepoName = "sqlalchemy"`로 바꿉니다.

```powershell
Set-Location C:\Pj\rag_lab

# 이 값만 대상 레포의 폴더 이름으로 바꿉니다.
$RepoName = "fest-api"

$RepoRoot = Join-Path "C:\Pj" $RepoName
$Profiles = @("rag-v1", "rag-v2", "rag-v3")

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
  throw "레포 폴더가 없습니다: $RepoRoot"
}

foreach ($Profile in $Profiles) {
  $ProjectId = "${RepoName}--${Profile}"
  Write-Host "`n=== $ProjectId 인덱싱 시작 ===" -ForegroundColor Cyan

  python cli.py index "$RepoRoot" `
    --project "$ProjectId" `
    --profile "$Profile"

  if ($LASTEXITCODE -ne 0) {
    throw "$ProjectId 인덱싱 명령이 실패했습니다. 이후 프로필은 실행하지 않습니다."
  }

  # 출력 메시지만 믿지 않고 저장된 최종 상태도 확인합니다.
  python -c "import sys; from vss_rag import indexer; s=indexer.get_state(sys.argv[1]); print('확인:', sys.argv[1], 'state=' + str(s.get('state')), 'chunks=' + str(s.get('chunk_count'))); raise SystemExit(0 if s.get('state') == 'done' else 1)" "$ProjectId"
  if ($LASTEXITCODE -ne 0) {
    throw "$ProjectId 최종 상태가 done이 아닙니다. 이후 프로필은 실행하지 않습니다."
  }
}

Write-Host "`nrag-v1~v3 순차 인덱싱 완료" -ForegroundColor Green
python cli.py projects
python cli.py doctor --deep
```

위 명령은 다음 세 컬렉션을 순서대로 만들거나, 이미 최신인 컬렉션은 재사용합니다.

```text
<레포명>--rag-v1
<레포명>--rag-v2
<레포명>--rag-v3
```

제품용 `cli.py index`는 각 인덱스 완료 후 브리핑도 생성합니다. 브리핑 생성을 제외한 순수 반복
평가는 `experiment.py run <matrix> --allow-index`를 사용합니다. 이 내부 평가 경로만 브리핑 훅을
주입하지 않습니다. 기존 인덱스가 최신이면 `--force`가 없으므로 불필요한 재구축을 하지 않습니다. 같은 commit이라도
프로필 fingerprint가 달라지면 해당 버전은 stale로 판정되어 다시 생성됩니다.

레포가 `C:\Pj` 바로 아래에 없다면 `$RepoName`과 `$RepoRoot`를 각각 지정합니다.

```powershell
$RepoName = "my-repo"
$RepoRoot = "D:\work\my-repo"
```

이 경우 위 전체 블록에서 `Join-Path`로 `$RepoRoot`를 만드는 한 줄을 삭제하고, 위 두 줄을 대신
사용합니다. `RepoName`은 project_id에 쓰이므로 영문 소문자, 숫자, 하이픈 위주의 짧고 고정된
이름을 권장합니다.

#### 한 버전씩 직접 실행

특정 버전만 개별적으로 만들거나 명령을 하나씩 확인하면서 실행하려면 다음 명령을 사용합니다.

```powershell
python cli.py index C:\Pj\fest-api `
  --project fest-api--rag-v1 `
  --profile rag-v1

python cli.py index C:\Pj\fest-api `
  --project fest-api--rag-v2 `
  --profile rag-v2

python cli.py index C:\Pj\fest-api `
  --project fest-api--rag-v3 `
  --profile rag-v3
```

각 실행 후 확인:

```powershell
python cli.py status --project fest-api--rag-v1
python cli.py doctor --deep
```

`rag-v2`와 `rag-v3`는 완료 상태에 도달하기 전에 BM25 역색인을 생성합니다. BM25 문서 수와
Chroma 청크 수가 다르면 실패 처리되므로, 단순히 컬렉션이 존재한다는 이유만으로 성공으로
판정하지 마세요.

### 10-5. matrix가 필요한 인덱스까지 만들도록 실행

계획에서 `create/rebuild`를 확인했고 전체 인덱싱을 허용하려면 실행합니다.

```powershell
python experiment.py run `
  evaluation\matrices\fest-api-rag-v1-v3.json `
  --allow-index
```

동작 순서:

```text
필요한 rag-v1/v2/v3 인덱스 순차 생성 또는 재사용
→ 각 셀 retrieval 평가
→ 각 셀 pipeline 평가
→ 질문별 결과와 집계 저장
```

`--allow-index`를 생략하면 필요한 인덱스 목록만 오류 메시지로 보여주고 중단합니다. 이는
의도된 안전장치입니다. 실험 인덱싱에서는 프로젝트 브리핑을 자동 생성하지 않습니다.

이미 세 인덱스를 개별적으로 만들어 두었다면 다음 명령만으로 평가할 수 있습니다.

```powershell
python experiment.py run evaluation\matrices\fest-api-rag-v1-v3.json
```

단, 레포 commit, fingerprint, BM25 정합성이 모두 같을 때만 `reuse`됩니다.

### 10-6. 결과 보고서 생성

```powershell
python experiment.py report evaluation\matrices\fest-api-rag-v1-v3.json
```

저장 위치:

```text
data/evaluation/runs/<run_id>.json
data/evaluation/reports/<run_id>.md
```

JSON 원본에는 질문별 순위·점수·근거 판정·지연과 모든 조건이 저장됩니다. Markdown은 사람이
빠르게 비교하기 위한 파생 보고서입니다. 숫자가 다르면 JSON을 정본으로 봅니다.

### 10-7. 결과를 읽는 순서

1. `matrix_hash`, `suite_hash`, `commit`이 비교 대상끼리 같은지 확인합니다.
2. `rag-v1/vector ↔ rag-v2/vector`가 거의 동일한지 확인합니다.
3. `rag-v2/vector ↔ rag-v2/hybrid`로 BM25 효과를 확인합니다.
4. `rag-v2/hybrid ↔ rag-v3/hybrid`로 context header 효과를 확인합니다.
5. 전체 점수뿐 아니라 `exact_symbol`, `semantic`, `code_vs_docs`, `no_evidence` 태그별 결과를 봅니다.
6. pipeline의 `no_evidence_recall`과 잘못 통과한 근거 목록을 확인합니다.
7. 특정 셀이 좋아져도 다른 유형이 악화됐으면 자동으로 기본 버전으로 승격하지 않습니다.

현재 제공된 `fest-api-routing.jsonl`은 구조 검증을 위한 시작용 문항입니다. 정식 정확도를
판단하려면 질문 유형별 문항을 충분히 추가하고 사람의 gold 검토를 거쳐야 합니다.

## 11. 질문을 추가하는 절차

1. 대상 레포에서 실제 정답 파일과 symbol을 확인합니다.
2. `evaluation/suites/*.jsonl`에 한 줄 JSON으로 추가합니다.
3. 기존 ID를 수정·재사용하지 않고 새 ID를 부여합니다.
4. `experiment.py validate`를 실행합니다.
5. 사람이 질문과 gold를 표본 검토합니다.
6. suite가 바뀌면 `suite_hash`가 달라지므로 과거 결과와 직접 비교하지 않습니다.

질문 유형별 최소 확인 목록:

| 유형 | 확인 포인트 |
|---|---|
| `semantic` | 한국어 질문으로 영어 구현을 찾는가 |
| `exact_symbol` | 함수·클래스 이름이 정확히 올라오는가 |
| `architecture` | 진입점·등록·호출 관계를 찾는가 |
| `code_vs_docs` | 문서가 아닌 실제 코드가 상위에 오는가 |
| `duplicate` | 번역·중복 문서가 결과를 채우지 않는가 |
| `no_evidence` | 존재하지 않는 기능을 근거 있음으로 처리하지 않는가 |
| `hard_negative` | 이름이 비슷한 오답 파일을 고르지 않는가 |

## 12. 새 인덱싱 버전을 추가하는 절차

새 버전은 `profiles/index_profiles.json`에 추가합니다. 이미 결과가 있는 `rag-v1/v2/v3`를
수정하지 않습니다.

예를 들어 번역 문서 제외를 시험하려면 `rag-v4`를 `rag-v3` 기반으로 추가합니다.

```json
"rag-v4": {
  "label": "Hybrid context with corpus filtering",
  "description": "rag-v3에서 번역·중복 문서 제외만 변경",
  "based_on": "rag-v3",
  "settings": {
    "exclude_globs": "docs/ja/**,docs/fr/**,docs/tr/**"
  }
}
```

추가 후 절차:

```powershell
python cli.py profiles
python experiment.py validate <새-matrix.json>
python experiment.py plan <새-matrix.json>
```

한 버전에 BM25, 청킹 크기, 코퍼스 제외를 동시에 바꾸지 마세요. 결과가 좋아져도 무엇이 원인인지
판별할 수 없습니다.

## 13. 장애 대응

### `dirty repository` 또는 Git 상태 확인 불가

평가 대상 레포의 변경을 커밋하거나 되돌린 뒤 다시 실행합니다. `require_clean=false`로 우회할
수 있지만 정식 비교 결과에는 사용하지 않는 것을 권장합니다.

### `invalid_profile`

```powershell
python cli.py profiles
```

표시되는 정확한 profile ID를 사용합니다. 서버 API에서도 `GET /profiles`로 확인할 수 있습니다.

### BM25 문서 수 불일치

해당 하이브리드 인덱싱은 실패입니다. `doctor --deep`로 상태를 확인하고 자동으로 vector-only로
내려 사용하지 마세요. 직전 인덱스는 복원되고 실패한 새 컬렉션은 `building-*`로 남습니다.
원인을 확인한 후 명시적으로 정리하고 재시도합니다.

### `building-*` 또는 `*-prev` 컬렉션 발견

자동 삭제하지 않습니다. 다른 프로세스가 인덱싱 중인지 먼저 확인하고
`repair_collections.py`의 진단 결과를 기준으로 정리합니다.

### Ollama 또는 임베딩 모델 오류

```powershell
python cli.py health
```

터널, Ollama 서비스, `bge-m3:latest` 모델을 복구한 뒤 다시 실행합니다. 가짜 임베딩 fallback은
사용하지 않습니다.

### hybrid 셀인데 `bm25_active=false`

정상 평가로 기록하지 않습니다. BM25 파일 존재, 문서 수, project profile을 확인하고 해당 셀을
재실행합니다.

## 14. 실행 전·후 체크리스트

### 실행 전

```text
[ ] health 성공
[ ] doctor 빨간 오류 0건
[ ] 대상 repository 경로 확인
[ ] commit 확인 및 dirty=False
[ ] 질문 suite validate 통과
[ ] gold 경로·symbol 사람 검토
[ ] matrix 5개 셀 확인
[ ] plan의 create/rebuild/reuse 확인
[ ] 전체 인덱싱 시간과 Ollama 상태 확인
```

### 실행 후

```text
[ ] rag-v1/v2/v3 상태 done
[ ] 하이브리드 BM25 문서 수 = Chroma 청크 수
[ ] 결과 JSON 생성
[ ] 보고서 Markdown 생성
[ ] commit·matrix_hash·suite_hash 확인
[ ] 태그별 성능과 NO_EVIDENCE 확인
[ ] 결정이 필요하면 DECISIONS.md에 기록
[ ] 현재 상태만 STATE.md에 반영
```
