# Vision - VSCode AI Coding Assistant

> On-premise LLM 기반의 VSCode AI 코딩 어시스턴트

## 📖 Overview

Vision은 VSCode에서 동작하는 AI Coding Assistant Extension입니다.

기업의 폐쇄망 환경(On-premise)에서도 사용할 수 있도록 설계되었으며, 프로젝트 컨텍스트를 이해하고 개발자의 코딩 작업을 지원하는 것을 목표로 합니다.

현재는 다음과 같은 기능을 중심으로 개발 중입니다.

* Backend AI 서버 연결
* 프로젝트 인덱싱
* 프로젝트 의존성 분석
* AI Chat
* 문서 번역 및 코드 설명

---

## ✨ Features

### 🤖 AI Chat

* Backend LLM과 연동
* Streaming 응답 지원
* 프로젝트 컨텍스트 기반 질의응답

### 📂 Project Indexing

* 현재 Workspace 분석
* 프로젝트 구조 인덱싱
* AI가 프로젝트 전체를 이해할 수 있도록 데이터 생성

### 🔍 Dependency Viewer

* 현재 파일이 참조하는 파일
* 현재 파일을 참조하는 파일
* Tree View 제공

### 🌐 Document Translation

선택한 문서를 원하는 언어로 번역합니다.

예시

* Korean → English
* English → Korean
* Japanese → Korean

### ⚙ Backend Connection

Sidebar에서 Backend 서버 상태를 확인할 수 있습니다.

표시 정보

* Connection Status
* Endpoint
* Model Name
* Latency

---

## 🖥 Architecture

```
VSCode Extension
│
├── Sidebar(Webview)
│
├── Commands
│
├── TreeView
│
├── Backend Service
│
└── AI Backend
        │
        └── LLM
```

---

## 📁 Project Structure

```
vision/
│
├── src/
│   ├── commands/
│   ├── providers/
│   ├── services/
│   ├── webview/
│   ├── utils/
│   └── extension.ts
│
├── media/
│
├── package.json
│
└── README.md
```

---

## 🚀 Getting Started

### Install

```bash
git clone <repository>
cd vision
npm install
```

### Compile

```bash
npm run compile
```

### Run Extension

VSCode에서

```
F5
```

를 눌러 Extension Development Host를 실행합니다.

---

## ⚙ Configuration

Vision은 VSCode Settings를 통해 설정할 수 있습니다.

예시

```json
{
    "vision.endpoint": "http://localhost:8000",
    "vision.showGuideBook": true
}
```

---

## 📌 Planned Features

* [ ] RAG 기반 프로젝트 검색
* [ ] Git 변경사항 분석
* [ ] 코드 리뷰
* [ ] Commit Message 생성
* [ ] 프로젝트 요약
* [ ] 코드 생성
* [ ] 테스트 코드 생성
* [ ] 파일 Dependency 시각화 개선
* [ ] Chat History 저장
* [ ] Multi Model 지원

---

## 🛠 Tech Stack

### Extension

* TypeScript
* VSCode Extension API
* Webview API

### Backend

* REST API
* Local LLM (On-premise)

---

## 📷 Screenshots

> 추후 추가 예정

---

## 🤝 Contributing

Issue 및 Pull Request는 언제든 환영합니다.

---

## 📄 License

개발 중
