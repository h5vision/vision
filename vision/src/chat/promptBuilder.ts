export class PromptBuilder {

    static build(userPrompt: string): string {

        return `
당신은 Vision입니다. 

사용자 질문

${userPrompt}
`;

    }

}