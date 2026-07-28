/**
 * history로 저장하는 chat message 타입
 * role: user, assistant, system
 * content: message content
 */

export interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
    endpoint?: string;
}
/**
 * Chat API 요청 타입   
 * project_id: 프로젝트 ID   
 * message: 사용자 메시지   
 * session_id: 세션 ID  
 * top_k: 검색할 문서 수   
 * history: 이전 대화 내용   
 */
export interface ChatRequest {
    project_id: string;
    message: string;
    session_id: string;
    model_id?: string;
    top_k?: number;
    history?: ChatMessage[];
    context?: unknown;
}

export interface SourceDocument {
    file: string;
    chunk: string;
    score?: number;
}

/**
 * Chat API 응답 타입
 */
export interface ChatResponse {
    answer: string;
    source: SourceDocument[];
    metadata: unknown;
}