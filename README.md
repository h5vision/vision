# Vision Backend P

`backend_P` 브랜치는 VS Code 확장 프로그램 연동을 확인하기 위한 FastAPI 기반 RAG mock 서버입니다.

현재 구현은 다음 구성으로 동작합니다.

- `ingest.py`: 소스 파일을 줄 단위로 청킹하고 Ollama 임베딩을 사용해 ChromaDB에 저장합니다.
- `main.py`: `POST /generate` 요청을 받고 선택 코드와 ChromaDB 검색 결과를 조합합니다.
- 응답 생성: 현재 실제 LLM 호출 대신 고정된 mock 답변을 반환합니다.

## 요구 사항

- Python 3.11 이상 권장
- Ollama
- Ollama 모델 `nomic-embed-text:latest`

```powershell
ollama pull nomic-embed-text:latest
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 설정 확인

현재 `main.py`와 `ingest.py`의 `TARGET_DIR`은 Windows 로컬 경로로 지정되어 있습니다. 다른 PC에서 실행할 때는 두 파일의 `TARGET_DIR`과 필요하면 `OLLAMA_BASE_URL` 또는 `OLLAMA_URL`을 실행 환경에 맞게 변경해야 합니다.

기본값:

```text
TARGET_DIR=C:\Users\PC2412\Documents\HancomAI5
ChromaDB=<TARGET_DIR>\chroma_db
Ollama=http://localhost:11434
Embedding model=nomic-embed-text:latest
```

## 실행

먼저 인덱스를 생성합니다.

```powershell
python ingest.py
```

그다음 API 서버를 실행합니다.

```powershell
python main.py
```

기본 접속 주소:

- API: `http://localhost:8000`
- OpenAPI 문서: `http://localhost:8000/docs`
- 생성 API: `POST http://localhost:8000/generate`

## 요청 예시

```powershell
$body = @{
  version = "1"
  question = "이 프로젝트의 구조를 설명해줘"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/generate" `
  -ContentType "application/json" `
  -Body $body
```

선택한 코드도 함께 보낼 수 있습니다.

```json
{
  "version": "1",
  "question": "이 코드를 설명해줘",
  "code_context": {
    "text": "def hello():\n    return 'hello'",
    "file_path": "example.py",
    "start_line": 1,
    "end_line": 2
  }
}
```

## 현재 제한 사항

- 경로와 Ollama 주소가 환경변수가 아닌 코드 상수로 지정되어 있습니다.
- `/generate`의 답변은 현재 mock 응답이며 실제 LLM 추론 결과가 아닙니다.
- ChromaDB 컬렉션이 없으면 RAG 검색 없이 응답합니다. `ingest.py`를 먼저 실행해야 합니다.
- CORS는 개발 편의를 위해 모든 origin을 허용합니다. 운영 환경에서는 허용 대상을 제한해야 합니다.
