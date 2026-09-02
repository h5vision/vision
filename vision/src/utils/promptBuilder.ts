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

export class RAGTESTPromptBuilder {
    static build (N:number):string {
        let type = '';
        switch (N) {
            case 1:
                type = `유형 1 — 이 코드가 뭘 하는지 (15개)

함수나 클래스 하나를 지목하고 무슨 일을 하는지 묻습니다.
"process_payment 함수는 무엇을 하나요?"
"UserRepository 클래스의 역할은 뭔가요?"
"validate_token 은 어떤 검증을 하나요?"
"이 함수는 뭘 하나요?" 형태로 질문을 만듭니다

질문의 대상이 될 함수를 선정할 때 정답 위치도 함께 저장해 놓습니다. 

정답 위치: 그 함수가 정의된 파일 (보통 1곳)`;
            break;

            case 2:
                type = `유형 2 — 어디서 시작하는지 (15개)

어떤 기능의 실행이 어디서 시작되는지 묻습니다.

"결제 요청은 어디서 처리되나요?"
"파일 업로드 기능은 어디에 정의돼 있나요?"
"데이터베이스 연결은 어디서 설정하나요?"

정답 위치는 여러 파일일 수 있습니다

- 정답 위치:
  - src/routers/payment.py  20~45줄     ← 요청을 받는 곳
  - src/services/payment.py  12~38줄    ← 실제 처리하는 곳

📌 여러 곳을 적어주시면 더 좋습니다. 실제로 한 곳만 봐서는 이해가 안 되는 경우가 많습니다.
`;
            break;
            case 3:
                type = `유형 3 — 프로젝트 전체 구조 (8개)

프로젝트를 처음 보는 사람이 던질 큰 질문입니다.

"이 프로젝트는 무엇을 하는 서비스인가요?"
"주요 폴더는 어떻게 구성돼 있나요?"
"새 기능을 추가하려면 어느 폴더를 봐야 하나요?"
"이 프로젝트를 실행하려면 뭘 설치해야 하나요?"

정답 위치: README.md, 폴더 구조, package.json / requirements.txt 같은 설정 파일

- 정답 위치:
  - README.md  1~30줄

`;
            break;
            case 4:
                type = `유형 4 — 에러가 났을 때 (8개)

에러가 발생하면 어디를 봐야 하는지 묻습니다.

"결제 처리 중 시간 초과가 나면 원인은 어디에 있나요?"
"'파일을 찾을 수 없음' 에러는 어디서 발생하나요?"

정답 위치: 그 에러를 일으키거나 처리하는 코드
`;
            break;
            case 5:
                type = `유형 5 — 🔴 답이 없는 질문 (15개)

그럴듯하지만 레포에 답이 없는 질문을 일부러 만듭니다.

✅ 좋은 예
   "이 프로젝트의 배포 절차는 어떻게 되나요?"   ← 배포 관련 파일이 없음
   "테스트는 어떻게 실행하나요?"                 ← 테스트 코드가 없음
   "사용자 인증은 어떻게 처리하나요?"            ← 인증 기능 자체가 없음
   "로그는 어디에 저장되나요?"                   ← 로그 설정이 없음

정답은 반드시

"문서에서 확인할 수 없습니다."

또는

"문서에 해당 내용이 없습니다."

처럼 작성하고, 절대 추측하지 않습니다.

비고란에 어떤 단어로 검색했는지 적어주시면 md 가 판단하기 좋습니다.

- 비고: auth, login, token, permission 으로 검색했으나 결과 없음
`;
            break;
        }
        return `당신은 RAG(Retrieval-Augmented Generation) 시스템을 평가하기 위한 QA Benchmark를 제작하는 전문가입니다.

아래에 제공되는 프로젝트 문서를 분석하여,
RAG 시스템의 검색 성능과 답변 생성 성능을 모두 평가할 수 있는 테스트셋을 생성하세요.

=========================
목표
=========================

생성되는 질문들은 단순한 문장 복사가 아니라,
실제 사용자가 프로젝트를 이해하기 위해 질문할 법한 내용이어야 합니다.

질문의 난이도는 다양하게 구성하며,
검색만으로 해결되는 문제와
여러 문서를 종합해야 하는 문제를 적절히 섞어야 합니다.

답변은 반드시 문서에 근거해야 하며,
문서에 존재하지 않는 내용은 절대 추가하지 않습니다.

=========================
생성 규칙
=========================

${type}

=========================
각 문제 출력 형식
=========================

출력물 1. 
각 문제마다 아래 JSON 형식을 따르는 json을 
RAG_TEST.json 파일에 추가한다. 
id는 파일 내용에 이어서 작성하여 붙인다. 

{
  "id": 1,
  "category": "Fact Retrieval",
  "difficulty": "Easy",
  "question": "...",

  "answer": "...",

  "evidence": [
      {
          "document": "README.md",
          "section": "Installation",
          "quote": "..."
      }
  ],

  "keywords": [
      "...",
      "..."
  ],

  "requires_multi_document": false,

  "expected_reasoning": "질문의 답을 찾기 위해 어떤 정보를 종합해야 하는지 설명",

  "evaluation": {
     "requires_retrieval": true,
     "requires_reasoning": false,
     "requires_multi_hop": false,
     "hallucination_risk": "Low"
  }  
}

출력물 2. 
문제마다 아래 markdown 형식에 맞추어 
RAG_TEST.md 파일에 추가한다. 

## Q1
- 유형: 2
- 질문: 결제 요청은 어디서 처리되나요?
- 정답 위치:
  - src/routers/payment.py  20~45줄
  - src/services/payment.py  12~38줄
- 한 줄 요약: POST /pay 라우터가 받아서 PaymentService.process() 로 넘긴다
- 비고: 라우터와 서비스 둘 다 봐야 완전한 답이 됨

=========================
질문 작성 규칙
=========================

좋은 질문의 조건
- 실제 개발자가 할 법한 질문
- 검색이 필요한 질문
- 답이 하나로 명확한 질문
- 문서 근거가 존재하는 질문


=========================
답변 작성 규칙
=========================

- 문서 내용만 사용한다.
- 추론은 가능하지만 문서 밖의 지식은 사용하지 않는다.
- 근거 문장을 반드시 포함한다.
- 답변은 가능한 한 짧고 명확하게 작성한다.


=========================
프로젝트 문서
=========================

현재 vscode에 열려 있는 프로젝트를 대상으로 한다. `;
    }
}