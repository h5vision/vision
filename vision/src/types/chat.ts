export interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
}

export interface ChatRequest {
    project_id: string;
    message: string;
    session_id: string;
    top_k: number;
    history: ChatMessage[];
}

export interface SourceDocument {
    file: string;
    chunk: string;
    score?: number;
}

export interface ChatResponse {
    answer: string;
    source: SourceDocument[];
    metadata: unknown;
}