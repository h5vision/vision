import * as vscode from "vscode";
import * as path from "path";
import { APIService } from "../services/APIService";
import * as session from "../utils/session";
import { HistoryService } from "../services/historyService";
import { ChatService } from "../services/chatServices_SSE";

export class ChatHandler {

    constructor (
        private readonly historyServcie: HistoryService
    ) {}

    public handle: vscode.ChatRequestHandler = async (
        request : vscode.ChatRequest,
        context : vscode.ChatContext,
        stream : vscode.ChatResponseStream,
        token : vscode.CancellationToken
    ) => {
        const backendService = new APIService();
        const chatService = new ChatService(backendService);
        const controller = new AbortController();
        const cancellation = token.onCancellationRequested(() => {
            controller.abort();
        });

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

        const project_id = vscode.workspace.getConfiguration("vision").get<string>("projectId") || vscode.workspace.name || 'none';

        // get all the previous participant messages
        const previousMessages = context.history.filter(
            h => h instanceof vscode.ChatResponseTurn
        );
        let session_id = session.getSessionId();
        
        if (!previousMessages) {
            session_id = session.resetSessionId();
        } 
        
        // // 추후 snapshot 기능을 위해 commitId를 가져옵니다. 
        // const commitId = vscode.workspace.getConfiguration("vision").get<string>("commitId");

        let rag = true;
        if (request.command === 'no-rag') {
            rag = false;
        }

        const isStream = vscode.workspace.getConfiguration("vision").get<boolean>("streaming", false);
        const payload = {
            project_id: project_id,
            message: request.prompt,
            rag: rag, 
            stream: true
        };
        this.historyServcie.save(
            project_id,
            session_id,
            'user',
            request.prompt
        );
        let response: any;


        try {
            await chatService.sendMessage(
                payload,
                (event, data) => {

                    if (event !== lastEvent) {
                        stream.progress(dummyLabels[event]);
                        lastEvent = event;
                    }

                    if (event === "delta") {
                        collectedDelta += data.text ?? '';
                        if (isStream) {stream.markdown(data.text ?? '');}
                        return;
                    }

                    if (event === "done") {
                        finalAnswer = data.answer ?? collectedDelta;
                        if (!isStream) {stream.markdown(finalAnswer);}
                        response = data;
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
        
            console.log(response);
            for (const source of response.reference_files) {
                const sourceUri = this.getWorkspaceFileUri(source.path);

                if (!sourceUri) {
                    stream.markdown(`\n- \`${source.path}\``);
                    continue;
                }

                const lineStart = Number(source.line);
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
            this.historyServcie.save(project_id, session_id, 'assistant', response.answer);
        }
        catch (err) {
            if (token.isCancellationRequested) {
                stream.progress("요청 취소됨");
                return;
            }
            stream.markdown("❌ " + err?.toString());
        } finally {
            cancellation.dispose();
        }
    };

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

}
