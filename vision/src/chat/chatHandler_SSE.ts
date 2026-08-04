import * as vscode from "vscode";
import * as fs from "fs";
import { ChatService } from "../services/chatServices_SSE";
import { APIService } from "../services/APIService";
import * as session from "../utils/session";
import { PromptBuilder } from "./promptBuilder";
import { HistoryService } from "../services/historyService";
import { ChatRequest_SSE } from "../types/chat";

export class ChatHandler {
    constructor(
        private readonly historyService: HistoryService
    ) {}

    public handle: vscode.ChatRequestHandler = async (
        request,
        _context,
        stream,
        token
    ) => {
        const apiService = new APIService();
        const chatService = new ChatService(apiService);

        const controller = new AbortController();

        const cancellation = token.onCancellationRequested(() => {
            controller.abort();
        });

        const projectName =
            vscode.workspace.workspaceFolders?.[0]?.name ??
            "__auto__";

        let finalAnswer = "";
        let collectedDelta = "";
        let lastEvent = "";

        const dummyLabels: Record<string, string> = {
            meta: "sLLM 서버로 질문 전송 중",
            status: "RAG 검색 중",
            delta: "RAG 기반으로 답변 생성 중",
            done: "답변 생성 완료",
            error: "답변 실패"
        };

        let messages = PromptBuilder.build(request.prompt);

        // get all the previous participant messages
        const previousMessages = _context.history.filter(
            h => h instanceof vscode.ChatResponseTurn
        );
        let session_id = session.getSessionId();
        if (!previousMessages) {
            session_id = session.resetSessionId();
        } 

        // add the previous messages to the messages 
        let responseHistory = [''];
        previousMessages.forEach(m => {
            let fullMessage = '';
            m.response.forEach(r => {
                const mdPart = r as vscode.ChatResponseMarkdownPart;
                if (mdPart.value.value !== 'NO_EVIDENCE') {fullMessage += mdPart.value.value;}
            });
            responseHistory.push(fullMessage);
        });
        messages += responseHistory.join('\n');

        // 에디터 화면에 열려 있는 파일의 텍스트 전체를 가져옵니다. 
        const editor = vscode.window.activeTextEditor;
        let file = '';
        if (editor) {
            file = fs.readFileSync(editor.document.uri.fsPath).toString();
            messages += file;
        }

        const payload: ChatRequest_SSE = {
            role: "user",
            content: messages,
            stream: true
        };

        try {
            this.historyService.save(
                projectName,
                "frontend-stream",
                "user",
                request.prompt
            );

            await chatService.sendMessage(
                payload,
                (event, data) => {
                    // delta가 여러 번 와도 "생각중"은 한 번만 표시
                    if (event !== lastEvent) {
                        stream.progress(dummyLabels[event]);
                        lastEvent = event;
                    }

                    if (event === "delta") {
                        // 화면에는 출력하지 않고 비상용으로만 합침
                        if (data.text) {
                            collectedDelta += data.text;
                        }

                        return;
                    }

                    if (event === "done") {
                        finalAnswer =
                            data.answer ??
                            collectedDelta;

                        // 완성된 답변을 한 번만 표시
                        // stream.markdown(finalAnswer);
                        for (const fragment of finalAnswer.split("\n")) {
                            stream.markdown(fragment + '\n');
                        }

                        if (data.source?.length) {
                            stream.markdown(
                                "\n\n---\n**근거 문서**\n"
                            );

                            for (const source of data.source) {
                                const score =
                                    typeof source.score === "number"
                                        ? ` · ${source.score.toFixed(3)}`
                                        : "";

                                stream.markdown(
                                    `\n- \`${source.file}\`${score}`
                                );
                            }
                        }

                        return;
                    }

                    if (event === "error") {
                        throw new Error(
                            data.error ??
                            "답변 생성에 실패했습니다."
                        );
                    }
                },
                controller.signal
            );

            if (finalAnswer) {
                this.historyService.save(
                    projectName,
                    "frontend-stream",
                    "assistant",
                    finalAnswer
                );
            }
        } catch (error) {
            if (token.isCancellationRequested) {
                stream.progress("요청 취소됨");
                return;
            }

            stream.progress("답변 실패");

            const message =
                error instanceof Error
                    ? error.message
                    : String(error);

            stream.markdown(`\n\n❌ ${message}`);
            console.error("Vision SSE 오류", error);
        } finally {
            cancellation.dispose();
        }
    };
}