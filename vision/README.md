# Vision

Vision은 Visual Studio Code 안에서 프로젝트 맥락을 이해하도록 돕는 온프레미스 지향 AI 코딩 어시스턴트 확장입니다. VS Code Chat의 `@vision` 참가자, 프로젝트 인덱싱/RAG, Git-aware 의존성 그래프, 파일 단위 질문을 하나의 개발 환경에 연결합니다.

## 제공 기능

- **`@vision` Chat Participant**: 현재 프로젝트를 대상으로 질문하고 백엔드의 SSE 응답을 VS Code Chat에 표시합니다.
  - 기본 요청은 RAG를 사용합니다.
  - `/no-rag`는 RAG 없이 질문합니다.
  - `/ragonly`는 답변 대신 검색된 참조 파일을 보여 주고 그래프 노드를 강조합니다.
- **코드 설명**: 에디터의 파일 또는 선택 영역에서 `vision: 이 코드 설명해줘`를 실행해 Chat 입력을 채웁니다.
- **Vision Assistant Sidebar**: 백엔드 상태/latency, endpoint, 모델, 스트리밍 표시 여부, 프로젝트와 Git 정보, 인덱싱 상태를 보여 줍니다.
- **프로젝트 인덱싱과 브리핑**: Sidebar에서 프로젝트를 백엔드에 인덱싱하고, 생성된 Markdown 브리핑을 워크스페이스에 저장합니다.
- **파일 의존성 탐색**: Explorer의 `< V > File Dependency` 뷰에서 현재 파일의 import/referenced 파일을 확인합니다.
- **의존성 그래프**: React Flow 기반 그래프에서 파일과 import 관계를 탐색합니다. 노드를 클릭하면 해당 파일이 열리고, Chat의 참조 파일은 강조됩니다.
- **로컬 이력**: 채팅 이력을 VS Code 전역 저장소의 SQLite `history.db`에 저장합니다.
- **Guide Book**: 선택적으로 확장 활성화 시 표시되는 사용 안내 웹뷰를 제공합니다.


## 동작 구조

```text
Developer
  └─ VS Code
      └─ Vision Extension Host (TypeScript)
          ├─ Sidebar Webview (HTML/CSS/JavaScript)
          ├─ @vision Chat Participant
          ├─ File Dependency Tree View
          ├─ Dependency Graph Webview (React + Vite + React Flow)
          └─ Services: API/SSE, Git, history, workspace, dependency analysis
                 ├─ Workspace source files and Git repository
                 ├─ .vscode/dependency-graph.json
                 └─ Configured Vision backend (REST + SSE, project index/RAG/LLM)
```

주요 구현 위치는 [src/extension.ts](src/extension.ts), [src/controller](src/controller), [src/providers](src/providers), [src/services](src/services), [webview](webview), [webview_graph/src](webview_graph/src)입니다. 확장은 필요한 명령이나 뷰가 호출될 때 활성화되며, 활성화 과정에서 Sidebar, Chat, Explorer 트리, 그래프 관리자를 등록합니다.

## 요구 사항

- Node.js와 npm
- Visual Studio Code `^1.125.0`
- `/health`, `/v1/chat`, 인덱싱 API를 제공하는 Vision 백엔드
- 의존성 그래프를 사용할 때 열려 있는 VS Code 워크스페이스
- Git 기반 증분 그래프 갱신과 프로젝트 인덱싱에는 Git 저장소 및 remote 정보

## 설치 및 실행

```bash
git clone https://github.com/h5vision/vision.git
cd vision
npm install
cd webview_graph
npm install
npm run build
cd ..
npm run compile
```

그래프 Webview는 확장 코드가 `webview_graph/dist/assets`의 빌드 결과를 로드하므로, 확장을 실행하기 전에 그래프 프로젝트를 먼저 빌드해야 합니다. 개발 중에는 저장소를 VS Code로 열고 `F5`로 Extension Development Host를 시작합니다.

```bash
# 확장 호스트 TypeScript 자동 컴파일
npm run watch

# 그래프 Webview 개발 서버
cd webview_graph
npm run dev
```

## 설정

VS Code `settings.json`에서 설정할 수 있습니다.

```json
{
  "vision.endpoint": "http://127.0.0.1:5000",
  "vision.modelId": "gpt-oss:20b",
  "vision.projectId": "None",
  "vision.commitId": "None",
  "vision.branch": "None",
  "vision.showGuideBook": false,
  "vision.streaming": true
}
```

| 설정 | 설명 | package.json 기본값 |
| --- | --- | --- |
| `vision.endpoint` | Vision 백엔드 URL | `http://44.208.79.122:8200` |
| `vision.modelId` | 사용할 모델 ID | `gpt-oss:20b` |
| `vision.projectId` | 선택된 RAG 프로젝트 ID | `None` |
| `vision.commitId` | 선택된 커밋 ID | `None` |
| `vision.branch` | 선택된 Git branch | `None` |
| `vision.questionProject` | 질문에 사용할 별도 프로젝트 컨텍스트 | `{ isExist: false, pid: "None", commit: "None" }` |
| `vision.showGuideBook` | 활성화 때 Guide Book을 열지 여부 | `false` |
| `vision.streaming` | SSE delta를 실시간으로 표시할지 여부 | `true` |

`vision.streaming`은 백엔드 요청 자체를 끄는 설정이 아닙니다. 백엔드는 계속 SSE로 응답하고, 이 값이 `false`이면 확장이 `done` 이벤트까지 답변을 모아 한 번에 표시합니다. 코드의 설정 fallback은 `http://127.0.0.1:5000`이므로 endpoint 설정을 명시하는 것을 권장합니다.

## 프로젝트 인덱싱

1. Git 저장소가 있는 워크스페이스를 엽니다.
2. Activity Bar에서 **Vision Assistant**를 열고 프로젝트 및 Git 정보를 확인합니다.
3. 프로젝트가 없거나 커밋이 최신이 아니면 Sidebar의 인덱싱 동작을 실행합니다.
4. 확장은 Git remote, 프로젝트 ID, branch, 선택 모델을 사용해 `POST /index`를 호출하고 상태를 조회합니다.

인덱싱 프로필은 현재 다음 값으로 전송됩니다.

```json
{
  "chunker": "ast-v3",
  "context_header": true,
  "use_bm25": true,
  "briefing": true
}
```

인덱싱 결과가 `running`이면 Sidebar가 `GET /index/status?project_id=...`를 조회해 진행 상태를 표시합니다. 완료 후 브리핑은 `GET /briefing?project_id=...`로 확인하며, 워크스페이스 루트에 `Vision_brief-{commit의 앞 7자리}.md` 형식으로 저장됩니다.

## 백엔드 API 계약

모든 요청은 `vision.endpoint`를 기준으로 합니다.

| Method | 경로 | 용도 |
| --- | --- | --- |
| `GET` | `/health` | 연결 상태와 latency 확인 |
| `GET` | `/v1/models` | 모델 목록 조회 |
| `POST` | `/v1/chat` | 프로젝트 질문, `text/event-stream` 응답 |
| `GET` | `/projects?view=repos` | 인덱싱된 프로젝트 조회 |
| `POST` | `/index` | 인덱싱 및 브리핑 생성 시작 |
| `GET` | `/index/status?project_id=...` | 인덱싱/브리핑 진행 상태 조회 |
| `GET` | `/briefing?project_id=...` | 프로젝트 브리핑 조회 |
| `POST` | `/workspace-overlays` | 워크스페이스 변경 정보 전송 |

Chat 요청은 대략 다음 정보를 포함합니다.

```json
{
  "project_id": "project-id@branch",
  "message": "user prompt",
  "rag": true,
  "stream": true,
  "model_id": "gpt-oss:20b"
}
```

`/v1/chat`은 `meta`, `stage`, `delta`, `done`, `error` SSE 이벤트를 사용합니다. `meta`와 `done`의 reference 문서는 Chat에 링크로 표시되고 그래프에서 강조됩니다.

## 명령 및 데이터 위치

| 명령 | 설명 |
| --- | --- |
| `vision.explainFile` | 현재 파일 또는 선택 코드를 `@vision` 질문으로 전송 |
| `vision.showDependencyGraph` | Dependency Graph Webview 열기 |
| `vision.initializeDependencyGraph` | 그래프 생성 또는 갱신 |
| `vision.showGuide` / `vision.toggleGuide` | Guide Book 열기 또는 전환 |
| `vision.openDBExternal` | 채팅 이력 DB 위치 열기 |

- 그래프 캐시: 워크스페이스의 `.vscode/dependency-graph.json`
- 채팅 이력: 확장 `globalStorageUri` 아래의 `history.db`
- 프로젝트 브리핑: 워크스페이스 루트의 `Vision_brief-{commit7chars}.md`

Git HEAD가 저장된 그래프의 커밋과 같으면 캐시를 재사용하고, 다르면 변경 파일을 기준으로 그래프를 갱신합니다. Git 저장소가 없으면 커밋은 `None`으로 기록됩니다.

## 개발 명령

루트에서 실행합니다.

```bash
npm run compile
npm run watch
npm run lint
npm test
npm run pretest
```

그래프 Webview에서는 다음을 실행합니다.

```bash
cd webview_graph
npm run build
npm run lint
npm run preview
```

## 라이선스

MIT