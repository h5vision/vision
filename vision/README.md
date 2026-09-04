# Vision

Visual Studio Code 안에서 동작하는 온프레미스 sLLM 코딩 어시스턴트 확장입니다. 현재 워크스페이스와 Git 상태를 바탕으로 코드 질문, 프로젝트 브리핑, 파일 의존성 탐색을 제공하며, AI 백엔드는 설정한 사내 또는 자체 호스팅 서버를 사용합니다.

## 주요 기능

- **`@vision` Chat Participant**: VS Code Chat에서 프로젝트와 코드에 대해 질문합니다.
  - 기본 모드: RAG를 사용한 질의
  - `/no-rag`: RAG 없이 질의
  - `/ragonly`: 참조 파일만 확인하고 의존성 그래프에서 강조
  - `/indexing`: 인덱싱 관련 질의를 보내기 위한 명령
- **스트리밍 응답**: SSE(Server-Sent Events)로 답변 생성 과정을 받고, 설정에 따라 답변을 실시간 표시합니다.
- **코드 설명**: 에디터에서 파일 또는 코드를 선택한 뒤 우클릭 메뉴로 `vision: 이 코드 설명해줘`를 실행할 수 있습니다.
- **프로젝트 브리핑**: 백엔드가 생성한 Markdown 브리핑을 워크스페이스에 저장하고 미리 봅니다. Copilot 채팅을 통한 브리핑 요청도 지원합니다.
- **파일 의존성 탐색**: Explorer의 `< V > File Dependency` 뷰에서 현재 파일의 의존 파일과 참조 파일을 확인합니다.
- **의존성 그래프**: 프로젝트 소스 파일의 import 관계를 React Flow 기반 그래프로 표시합니다. 노드를 클릭하면 해당 파일을 에디터에서 열고, AI 답변의 참조 파일은 그래프에서 강조됩니다.
- **Git 기반 갱신**: 그래프를 `.vscode/dependency-graph.json`에 저장하고 Git HEAD를 비교해 최초 생성 또는 변경 파일 중심의 갱신을 수행합니다.
- **채팅 이력 저장**: VS Code 전역 저장소의 `history.db`에 프로젝트별 채팅 이력을 저장합니다.
- **백엔드 상태 확인**: Sidebar에서 연결 상태, endpoint, 모델, latency, 프로젝트 및 Git 정보를 확인하고 설정을 변경합니다.

## 구조

```text
vision/
├── src/                         # VS Code Extension Host (TypeScript)
│   ├── controller/              # Sidebar 및 Chat 요청 처리
│   ├── providers/               # Sidebar, Guide, Tree View, Graph Webview
│   ├── services/                # API, SSE, Git, 이력, 의존성 분석
│   ├── types/                   # 도메인 타입
│   └── extension.ts              # 확장 활성화 및 등록
├── webview/                     # Sidebar와 Guide Book의 HTML/CSS/JavaScript
├── webview_graph/               # React + Vite 의존성 그래프 Webview
├── media/                       # Codicon 등 확장 리소스
├── scripts/copy-assets.js       # Codicon 리소스 복사
└── package.json
```

## 요구 사항

- Node.js 및 npm
- Visual Studio Code `^1.125.0`
- 질문, 인덱싱, 브리핑 기능을 제공하는 Vision 백엔드
- 의존성 그래프를 사용하려면 VS Code에서 워크스페이스를 열어야 합니다. Git 저장소가 있으면 커밋 기준의 증분 갱신을 사용할 수 있습니다.

## 시작하기

```bash
git clone https://github.com/h5vision/vision.git
cd vision
npm install
npm run compile
```

개발 중에는 VS Code에서 이 저장소를 연 뒤 `F5`를 눌러 Extension Development Host를 실행합니다. 소스 변경을 자동으로 컴파일하려면 다음 명령을 사용합니다.

```bash
npm run watch
```

### 의존성 그래프 Webview 개발

그래프 UI는 별도 Vite 프로젝트입니다.

```bash
cd webview_graph
npm install
npm run build
```

개발 서버가 필요한 경우 `npm run dev`를 사용할 수 있습니다. 그래프를 확장에 포함하려면 빌드 결과물(`webview_graph/dist`)이 필요합니다.

## 설정

VS Code 설정(`settings.json`) 또는 명령 팔레트의 `Preferences: Open User Settings (JSON)`에서 지정합니다.

```json
{
  "vision.endpoint": "http://127.0.0.1:5000",
  "vision.modelId": "gpt-oss:20b",
  "vision.projectId": "None",
  "vision.commitId": "None",
  "vision.showGuideBook": false,
  "vision.streaming": true
}
```

| 설정 | 설명 | 기본값 |
| --- | --- | --- |
| `vision.endpoint` | Vision 백엔드 주소 | `http://44.208.79.122:8200` |
| `vision.modelId` | 사용할 모델 ID | `gpt-oss:20b` |
| `vision.projectId` | RAG에 사용할 프로젝트 ID | `None` |
| `vision.commitId` | 선택된 프로젝트의 커밋 ID | `None` |
| `vision.showGuideBook` | 확장 활성화 시 Guide Book을 열지 여부 | `false` |
| `vision.streaming` | Chat 답변을 스트리밍으로 표시할지 여부 | `true` |

`projectId`와 `commitId`는 워크스페이스 및 Git 정보 조회 시 확장이 자동으로 갱신할 수 있습니다.

## 백엔드 API 계약

확장은 `vision.endpoint`를 기준으로 다음 API를 호출합니다.

| 경로 | 용도 |
| --- | --- |
| `GET /health` | 백엔드 상태 및 latency 확인 |
| `GET /v1/models` | 모델 목록 조회 |
| `POST /v1/chat` | Chat 요청 및 SSE 응답 |
| `GET /projects?view=repos` | 인덱싱된 프로젝트 목록 조회 |
| `GET /briefing?project_id=...` | 프로젝트 브리핑 조회 |
| `POST /workspace-overlays` | Git 커밋 diff 전송 |

`POST /v1/chat`의 응답은 `text/event-stream`이어야 하며, 확장은 `meta`, `stage`, `delta`, `done`, `error` 이벤트를 처리합니다. `delta`에는 부분 답변, `done`에는 최종 답변과 참조 문서 정보가 포함됩니다.

## 확장 기능 사용

1. Extension Development Host 또는 설치된 VS Code에서 워크스페이스를 엽니다.
2. Activity Bar의 **Vision Assistant**를 열어 백엔드 연결과 프로젝트 정보를 확인합니다.
3. VS Code Chat에서 `@vision`을 선택해 질문합니다.
4. Explorer의 `< V > File Dependency` 뷰 또는 Sidebar의 그래프 버튼으로 의존성을 확인합니다.
5. 그래프의 파일 노드를 클릭하면 해당 소스 파일이 열립니다.

확장 명령은 다음과 같습니다.

| 명령 | 설명 |
| --- | --- |
| `vision.showDependencyGraph` | 의존성 그래프 열기 |
| `vision.initializeDependencyGraph` | 그래프 생성 또는 갱신 |
| `vision.showGuide` / `vision.toggleGuide` | Guide Book 열기 또는 전환 |
| `vision.openDBExternal` | 채팅 이력 DB 위치 열기 |
| `vision.explainFile` | 현재 파일 또는 선택 코드에 대한 질문을 Chat에 입력 |

## 개발 명령

루트 프로젝트에서 실행합니다.

```bash
npm run compile   # Codicon 복사 후 Extension TypeScript 컴파일
npm run watch     # 변경 감지 컴파일
npm run lint      # src ESLint 검사
npm test          # VS Code 통합 테스트
npm run pretest   # 컴파일 및 lint 후 테스트 준비
```

그래프 프로젝트에서는 다음 명령을 사용합니다.

```bash
npm run build
npm run lint
npm run preview
```

## 데이터 및 주의 사항

- 의존성 그래프는 워크스페이스의 `.vscode/dependency-graph.json`에 저장됩니다. 이 파일을 커밋할지 여부는 팀의 저장소 정책에 맞춰 결정하세요.
- 채팅 이력 DB는 확장의 VS Code 전역 저장소에 생성되며, `vision.openDBExternal` 명령으로 위치를 열 수 있습니다.
- 백엔드 endpoint는 기본값이 포함되어 있지만, 실제 사내 네트워크 정책과 실행 중인 서버에 맞춰 변경해야 합니다.
- 현재 import 분석은 TypeScript/JavaScript, Python, C/C++, Java, Rust, Go 파일을 대상으로 하며, 외부 패키지나 동적 import는 프로젝트 설정에 따라 그래프에 포함되지 않을 수 있습니다.

## 라이선스

MIT