export interface SourceDocument {
    path: string;
    type: string;
    chunk_count: string;
    best_score: number;
    citations: number[];
    line_start: number;
    lines: number[];
}

/**
 * Chat API 응답 타입
 */

export interface ChatRequest_SSE {
    project_id: string;
    model_id?: string;
    commit_id?: string;
    message: string;
    stream: boolean;
    rag: boolean;
}

export type ChatStreamEventName =
    | "meta"
    | "stage"
    | "delta"
    | "done"
    | "error";

export interface ChatStreamData {
    request_id: string;

    stage?:
        | "sending"
        | "reasoning"
        | "thinking"
        | "answering"
        | "failed";

    label?: string;
    sequence?: number;
    text?: string;

    answer?: string;
    source?: SourceDocument[];
    reference_files?: SourceDocument[];
    metadata?: Record<string, unknown>;

    status_code?: number;
    error?: string;
    partial?: string;
}