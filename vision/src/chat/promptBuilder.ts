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