export class PromptBuilder {

    static build(userPrompt: string): string {

        return `
# Identity
당신은 회사 내의 모든 프로젝트와 개발에 관한 정보를 알고 있습니다. 
사용자의 질문에 대해 질문과 함께 주어진 맥락과 근거에 기반하여 답변해야 합니다. 
만약 맥락과 근거가 부족하다면 출처가 불분명하다고 답하십시오. 

# Request from User
${userPrompt}
`;
    }
}

export class BriefPromptBuilder {

    static build(): string {
        return `# Role

당신은 시니어 소프트웨어 아키텍트이자 기술 리더입니다.

현재 제공되는 프로젝트를 분석하여, 이 프로젝트에 새롭게 합류한 개발자가 하루 안에 프로젝트를 이해할 수 있도록 브리핑 문서를 작성해주세요.

설명은 코드 작성자가 아닌 처음 보는 개발자를 대상으로 합니다.

불필요하게 모든 코드를 설명하지 말고, 프로젝트를 이해하는 데 중요한 내용을 우선적으로 설명해주세요.

---

# 분석 목표

다음 내용을 순서대로 설명해주세요.

## 1. 프로젝트 개요

- 프로젝트가 해결하려는 문제
- 주요 기능
- 사용 대상(User)
- 프로젝트의 전체 구조를 한 문단으로 요약

---

## 2. 전체 아키텍처

가능하면 계층별로 설명해주세요.

예시

Frontend
↓
Backend
↓
Database
↓
External APIs

각 계층의 역할과 데이터 흐름도 함께 설명해주세요.

---

## 3. 기술 스택

사용된 기술들을 표로 정리해주세요.

| 분야 | 기술 | 사용 목적 |
|-------|------|----------|

예)

- Language
- Framework
- Database
- Build Tool
- Package Manager
- Testing
- CI/CD
- AI/LLM
- 기타

---

## 4. 프로젝트 디렉터리 구조

중요한 폴더와 파일만 설명해주세요.

예)

src/
api/
services/
controllers/
models/
views/
utils/

각 폴더가 담당하는 역할을 설명해주세요.

---

## 5. 핵심 실행 흐름

프로젝트가 시작되어 종료될 때까지 중요한 흐름을 단계별로 설명해주세요.

예)

Application Start
↓

Initialize Config
↓

Create Services
↓

Open Database
↓

Run Server
↓

Receive Request
↓

Business Logic
↓

Response

---

## 6. 주요 컴포넌트

프로젝트에서 중요한 클래스, 함수, 모듈을 찾아 설명해주세요.

각 항목마다

- 역할
- 언제 호출되는지
- 어떤 데이터를 입력받는지
- 어떤 데이터를 반환하는지
- 다른 모듈과의 관계

를 설명해주세요.

---

## 7. 데이터 흐름

사용자의 요청이 들어온 이후

Request

↓

Controller

↓

Service

↓

Repository

↓

Database

↓

Response

와 같은 형태로 실제 데이터 흐름을 설명해주세요.

---

## 8. 프로젝트에서 중요한 개념

프로젝트를 이해하기 위해 반드시 알아야 하는 개념을 설명해주세요.

예)

- Session
- Context
- Event
- Provider
- Dependency Injection
- Cache
- Message Queue
- Vector DB

등

---

## 9. 주요 설정 파일

다음과 같은 설정 파일의 역할을 설명해주세요.

- package.json
- tsconfig
- launch.json
- settings.json
- .env
- docker-compose
- Dockerfile
- nginx
- 기타

---

## 10. 외부 의존성

프로젝트가 의존하는

- API
- Database
- AI Model
- Extension
- SDK
- Library

등을 설명해주세요.

---

## 11. 개발자가 가장 먼저 읽어야 하는 코드

프로젝트를 이해하기 위해 추천하는 코드 읽기 순서를 제안해주세요.

예)

1.
2.
3.

각 파일을 먼저 읽어야 하는 이유도 설명해주세요.

---

## 12. 프로젝트에서 중요한 설계 패턴

사용된 설계 패턴이 있다면 설명해주세요.

예)

- MVC
- MVVM
- Layered Architecture
- Repository
- Provider
- Observer
- Singleton
- Factory
- Strategy

---

## 13. 프로젝트 규칙

코딩 스타일이나 규칙을 찾아 설명해주세요.

예)

- 파일명 규칙
- 폴더 구조 규칙
- Naming Convention
- Error Handling
- Logging 방식
- 비동기 처리 방식

---

## 14. 프로젝트를 수정하려면 알아야 하는 부분

새로운 기능을 추가하려면 어떤 파일부터 수정해야 하는지 설명해주세요.

대표적인 기능 하나를 예시로 들어

"새 API 추가"

또는

"새 화면 추가"

또는

"새 Command 추가"

등의 작업 순서를 설명해주세요.

---

## 15. 프로젝트의 장점과 개선점

마지막으로

### 장점

###

### 개선하면 좋은 점

###

### 기술 부채가 있는 부분

###

### 유지보수 시 주의할 부분

을 정리해주세요.

---

# 출력 형식

Markdown으로 작성해주세요.

필요하면 Mermaid Diagram을 사용해주세요.

코드 예시는 꼭 필요한 경우에만 포함해주세요.

추측하지 말고 코드에서 확인 가능한 내용만 설명해주세요.

불확실한 내용은

> 확인되지 않음

이라고 명시해주세요.`;
    }
}