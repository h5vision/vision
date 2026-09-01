import * as vscode from "vscode";
import * as path from "path";
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

    private getWorkspaceFileUri(sourcePath: string): vscode.Uri | undefined {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders?.length) {
            return undefined;
        }

        const filePath = path.isAbsolute(sourcePath)
            ? path.normalize(sourcePath)
            : path.resolve(workspaceFolders[0].uri.fsPath, sourcePath);
        const isInWorkspace = workspaceFolders.some(folder => {
            const relativePath = path.relative(folder.uri.fsPath, filePath);
            return relativePath === "" ||
                (!relativePath.startsWith(`..${path.sep}`) &&
                    relativePath !== ".." &&
                    !path.isAbsolute(relativePath));
        });

        return isInWorkspace ? vscode.Uri.file(filePath) : undefined;
    }

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

        const projectId =
            vscode.workspace.getConfiguration("vision").get<string>("projectId") ??
            vscode.workspace.workspaceFolders?.[0]?.name ??
            "__auto__";

        let finalAnswer = "";
        let collectedDelta = "";
        let lastEvent = "";

        const dummyLabels: Record<string, string> = {
            meta: "sLLM 서버로 질문 전송 중",
            stage: "RAG 기반으로 답변 생성 중",
            delta: "답변 전송 중",
            done: "sLLM 답변 완료",
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

        // // add the previous messages to the messages 
        // let responseHistory = [''];
        // previousMessages.forEach(m => {
        //     let fullMessage = '';
        //     m.response.forEach(r => {
        //         const mdPart = r as vscode.ChatResponseMarkdownPart;
        //         if (mdPart.value.value !== 'NO_EVIDENCE') {fullMessage += mdPart.value.value;}
        //     });
        //     responseHistory.push(fullMessage);
        // });
        // messages += responseHistory.join('\n');

        // // 에디터 화면에 열려 있는 파일의 텍스트 전체를 가져옵니다. 
        // const editor = vscode.window.activeTextEditor;
        // let file = '';
        // if (editor) {
        //     file = fs.readFileSync(editor.document.uri.fsPath).toString();
        //     messages += file;
        // }


        const commit_id = vscode.workspace.getConfiguration('vision').get('commitId', 'None');

        let rag = true;
        if (request.command === 'no-rag') {
            rag = false;
        }

        const payload: ChatRequest_SSE = {
            project_id: projectId,
            message: request.prompt,
            stream: true,
            rag: rag
        };
        console.log('payload', payload);
        this.historyService.save(
            projectId,
            session_id,
            "user",
            request.prompt
        );

        try {
            await chatService.sendMessage(
                payload,
                (event, data) => {
                    // delta가 여러 번 와도 "생각중"은 한 번만 표시
                    if (event !== lastEvent) {
                        stream.progress(dummyLabels[event]);
                        lastEvent = event;
                    }

                    if (event === "delta") {
                        collectedDelta += data.text ?? '';
                        stream.markdown(data.text ?? '');
                        return;
                    }

                    if (event === "done") {
                        finalAnswer = data.answer ?? collectedDelta;
                        console.log("finalAnswer: ", finalAnswer);
                        console.log(data);
                        if (data.reference_files && data.reference_files.length > 0) {
                            for (let n = 1; n < data.reference_files.length+1; n++) {
                                const source = data.reference_files[n-1];
                                const sourceUri = this.getWorkspaceFileUri(source.path);
                
                                if (!sourceUri) {
                                    stream.markdown(`\n- \`${source.path}\``);
                                    continue;
                                }
                
                                const lineStart = Number(source.line_start);
                                const openArguments =
                                    Number.isInteger(lineStart) && lineStart > 0
                                        ? [
                                            sourceUri,
                                            {
                                                selection: new vscode.Range(
                                                    lineStart - 1,
                                                    0,
                                                    lineStart - 1,
                                                    0
                                                )
                                            }
                                        ]
                                        : [sourceUri];
                                stream.button({
                                    command: "vscode.open",
                                    title: `${path.basename(source.path)} ${source.line_start ? `:${source.line_start}-${source.lines[1]}` : ''}`,
                                    arguments: openArguments
                                });
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
                    projectId,
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